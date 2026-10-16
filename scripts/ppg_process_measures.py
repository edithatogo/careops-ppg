"""Read-only portfolio/process measures from complete native List exports."""
from __future__ import annotations

import argparse
import csv
import html
import io
import json
import re
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

from ppg_assurance import validate as validate_assurance
from ppg_readiness import validate as validate_readiness
from ppg_source_sync import digest

ZONE = ZoneInfo('Australia/Brisbane')
VERSION = ('CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256')


def calendar_date(value):
    if not isinstance(value, str):
        raise ValueError('date missing')
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return date.fromisoformat(value)
    moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if moment.tzinfo is None:
        raise ValueError('timestamp timezone missing')
    return moment.astimezone(ZONE).date()


def blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def measure(bundle):
    if bundle.get('schemaVersion') != 1:
        raise ValueError('unsupported export schema')
    if set(bundle.get('sources', {})) != {'cases', 'readiness', 'assurance'}:
        raise ValueError('source cohort differs from measure contract')
    as_of = datetime.fromisoformat(bundle['asOfUtc'].replace('Z', '+00:00'))
    if as_of.tzinfo is None:
        raise ValueError('asOf timezone required')
    today = as_of.astimezone(ZONE).date()
    kind = bundle.get('datasetKind', 'operational')
    if kind not in ('operational', 'fictional-example'):
        raise ValueError('unsupported dataset kind')
    data, input_counts, excluded = {}, {}, []
    for key in ('cases', 'readiness', 'assurance'):
        source = bundle['sources'][key]
        if (source.get('complete') is not True or source.get('repeatReadVerified') is not True or source.get('nextLink') or
                source.get('itemCount') != len(source['items']) or not source.get('resourceRef')):
            raise ValueError('incomplete native export: ' + key)
        items = source['items']
        input_counts[key] = len(items)
        identity = 'CaseUID' if key == 'cases' else 'EventUID'
        seen, rows = set(), []
        for item in items:
            uid = item.get(identity)
            if not isinstance(uid, str) or not uid.strip() or uid in seen:
                raise ValueError('missing or duplicate identity: ' + key)
            seen.add(uid)
            flag = item.get('FictionalTest', False)
            if flag is not None and type(flag) is not bool:
                raise ValueError('invalid fictional flag')
            if kind == 'operational' and (flag or (key == 'cases' and uid.startswith('fictional-'))):
                excluded.append({'source': key, 'id': uid, 'reason': 'fictional-test'})
            else:
                rows.append(item)
        data[key] = rows
    case_ids = {case['CaseUID'] for case in data['cases']}
    valid = {}
    for key in ('readiness', 'assurance'):
        valid[key] = []
        for event in data[key]:
            reasons = []
            if event.get('CaseUID') not in case_ids:
                reasons.append('case-not-in-export')
            if key == 'readiness':
                reasons.extend(validate_readiness(event))
            else:
                reasons.extend(validate_assurance(event,
                    [e for e in data[key] if e['EventUID'] != event['EventUID']], data['readiness']))
            if reasons:
                excluded.append({'source': key, 'id': event['EventUID'], 'reason': 'invalid-event', 'details': reasons})
            else:
                valid[key].append(event)
    cases = []
    for case in data['cases']:
        target = case.get('targetDate')
        target_state, target_day = 'unconfirmed', None
        if isinstance(target, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', target):
            try:
                target_day = date.fromisoformat(target)
                target_state = 'past-target' if target_day < today else 'today' if target_day == today else 'future'
            except ValueError:
                pass
        try:
            age = (today - calendar_date(case.get('Created'))).days
            if age < 0:
                raise ValueError('future Created')
        except (ValueError, TypeError):
            age = None
            excluded.append({'source': 'cases', 'id': case['CaseUID'], 'reason': 'case-age-unmeasurable'})
        cases.append({'CaseUID': case['CaseUID'], 'title': case.get('Title') or case['CaseUID'],
                      'recordedStatus': case.get('caseStatus') or 'Not recorded',
                      'recordedRoleStatement': case.get('accountableRole') or 'Not recorded',
                      'missingRole': blank(case.get('accountableRole')), 'missingNextAction': blank(case.get('nextAction')),
                      'nextAction': case.get('nextAction'), 'targetText': target, 'targetState': target_state,
                      'ageCalendarDays': age,
                      'readinessEventCount': sum(e['CaseUID'] == case['CaseUID'] for e in valid['readiness']),
                      'assuranceEventCount': sum(e['CaseUID'] == case['CaseUID'] for e in valid['assurance'])})
    ready = {e['EventUID']: e for e in valid['readiness']}
    assurance = {e['EventUID']: e for e in valid['assurance']}
    samples = {key: [] for key in ('readiness-to-decision', 'decision-to-publication', 'implementation-to-verification')}
    timing_exclusions = []
    for event in valid['assurance']:
        key, parent, parent_date = None, None, None
        if event['Stage'] == 'Decision':
            key = 'readiness-to-decision'
            parent = ready.get(event.get('ReadinessEventUID'))
            parent_date = parent.get('AssessedOn') if parent else None
            eligible_parent = bool(parent and parent.get('Finding') == 'Ready for decision')
        elif event['Stage'] in ('Publication', 'Verification'):
            key = 'decision-to-publication' if event['Stage'] == 'Publication' else 'implementation-to-verification'
            parent = assurance.get(event.get('ParentEventUID'))
            parent_date = parent.get('OccurredOn') if parent else None
            expected_stage = 'Decision' if event['Stage'] == 'Publication' else 'Implementation'
            eligible_parent = bool(parent and parent.get('Stage') == expected_stage and parent.get('RecordState') == 'Recorded')
        if not key:
            continue
        reason = None
        if event.get('RecordState') != 'Recorded' or not eligible_parent:
            reason = 'missing-recorded-endpoint-or-explicit-link'
        elif any(parent.get(field) != event.get(field) for field in VERSION):
            reason = 'version-or-identity-mismatch'
        else:
            try:
                start, end = calendar_date(parent_date), calendar_date(event.get('OccurredOn'))
                if end < start or end > today or start > today:
                    raise ValueError('negative or future interval')
                samples[key].append({'fromEventUID': parent['EventUID'], 'toEventUID': event['EventUID'],
                                     'CaseUID': event['CaseUID'], 'versionRef': event['ReviewedVersionRef'],
                                     'DocumentSHA256': event['DocumentSHA256'],
                                     'calendarDays': (end - start).days})
            except (ValueError, TypeError):
                reason = 'unqualified-endpoint-date'
        if reason:
            timing_exclusions.append({'measure': key, 'eventUID': event['EventUID'], 'reason': reason})
    durations = {key: {'sampleCount': len(values), 'caseCount': len({s['CaseUID'] for s in values}),
                        'medianCalendarDays': median([s['calendarDays'] for s in values]) if values else None,
                        'status': 'measured-recorded-pairs' if values else 'not-measurable',
                        'samples': sorted(values, key=lambda s: s['toEventUID'])} for key, values in samples.items()}
    ages = [c['ageCalendarDays'] for c in cases if c['ageCalendarDays'] is not None]
    return {'schemaVersion': 1, 'datasetKind': kind, 'asOfUtc': bundle['asOfUtc'], 'asOfBrisbaneDate': today.isoformat(),
            'mode': 'frozen-local-manual-projection', 'inputSHA256': digest(bundle),
            'sources': {key: {k: v for k, v in bundle['sources'][key].items() if k != 'items'} for key in data},
            'sourceContext': bundle.get('sourceContext', {'status': 'unknown'}),
            'inputCounts': input_counts, 'includedCounts': {key: len(rows) for key, rows in data.items()},
            'summary': {'recordedCases': len(cases), 'missingRole': sum(c['missingRole'] for c in cases),
                        'missingNextAction': sum(c['missingNextAction'] for c in cases),
                        'unconfirmedTarget': sum(c['targetState'] == 'unconfirmed' for c in cases),
                        'pastTarget': sum(c['targetState'] == 'past-target' for c in cases),
                        'qualifiedTargetDenominator': sum(c['targetState'] != 'unconfirmed' for c in cases),
                        'caseAgeSampleCount': len(ages), 'medianCaseAgeCalendarDays': median(ages) if ages else None,
                        'casesWithValidatedHistory': sum(bool(c['readinessEventCount'] or c['assuranceEventCount']) for c in cases),
                        'validatedEventCounts': {key: len(rows) for key, rows in valid.items()},
                        'openConditionEventCount': sum(e.get('ConditionsState') == 'Open' for rows in valid.values() for e in rows)},
            'byRecordedStatus': dict(sorted(Counter(c['recordedStatus'] for c in cases).items())),
            'byRecordedRoleStatement': dict(sorted(Counter(c['recordedRoleStatement'] for c in cases).items())),
            'cases': sorted(cases, key=lambda c: c['CaseUID']), 'durations': durations,
            'exclusions': excluded, 'timingExclusions': timing_exclusions,
            'interpretation': 'All recorded cases, not inferred active assignments. Event rows/pairs are not stage completion or policy approval. No trend, saving or SLA inferred.',
            'itemWrites': 0, 'checkpointAdvanced': False}


def render(report):
    esc = lambda value: html.escape(str(value))
    labels = {'recordedCases': 'Recorded cases (all statuses)', 'missingRole': 'Blank role statements (not role acceptance)',
              'missingNextAction': 'Cases with blank next actions', 'unconfirmedTarget': 'Cases with unconfirmed targets',
              'pastTarget': 'Cases past a qualified recorded target', 'qualifiedTargetDenominator': 'Cases with qualified target dates',
              'caseAgeSampleCount': 'Cases with measurable age', 'medianCaseAgeCalendarDays': 'Median age since creation (calendar days)',
              'casesWithValidatedHistory': 'Cases with validated event rows', 'validatedEventCounts': 'Validated event rows by source',
              'openConditionEventCount': 'Event rows recording open conditions'}
    durations = {'readiness-to-decision': 'Readiness finding → recorded decision',
                 'decision-to-publication': 'Recorded decision → publication event',
                 'implementation-to-verification': 'Recorded implementation → verification event'}
    rows = ''.join('<tr><td>' + esc(labels[key]) + '</td><td>' + esc(value if value is not None else 'Not measurable') + '</td></tr>' for key, value in report['summary'].items())
    timing = ''.join('<tr><td>' + esc(durations[key]) + '</td><td>' + str(value['sampleCount']) + '</td><td>' +
                     esc(value['medianCalendarDays'] if value['sampleCount'] else 'Not measurable') + '</td></tr>'
                     for key, value in report['durations'].items())
    return ('<!doctype html><meta charset="utf-8"><title>PPG process measures</title>'
            '<style>body{font:16px system-ui;margin:2rem;max-width:95rem}table{border-collapse:collapse}'
            'td,th{border:1px solid #bbb;padding:.6rem;text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>'
            '<h1>' + ('[FICTIONAL EXAMPLE] ' if report['datasetKind'] == 'fictional-example' else '') +
            'Portfolio and recorded process measures</h1><p>Frozen manual snapshot as of ' + esc(report['asOfUtc']) +
            ' (Brisbane date ' + esc(report['asOfBrisbaneDate']) + '). Not an automatically refreshed dashboard.</p><p>' +
            esc(report['interpretation']) + '</p><h2>Source context</h2><pre>' + esc(json.dumps(report['sourceContext'], indent=2)) +
            '</pre><h2>Portfolio and evidence coverage</h2><table>' + rows +
            '</table><h2>Recorded stage elapsed time</h2><p>Calendar days; explicit version-matched event pairs only. '
            'Zero samples is not zero days. No working-time or case completion inference.</p><table><tr><th>Measure</th>'
            '<th>Pairs</th><th>Median calendar days</th></tr>' + timing + '</table><h2>Case detail, provenance and exclusions</h2><pre>' +
            esc(json.dumps({key: report[key] for key in ('cases', 'byRecordedStatus', 'byRecordedRoleStatement', 'inputCounts',
                                 'sources', 'exclusions', 'timingExclusions', 'durations', 'inputSHA256')}, ensure_ascii=False, indent=2)) + '</pre>')


def csv_report(report):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(['measure', 'value', 'denominator', 'asOfUtc', 'inputSHA256', 'datasetKind'])
    for key, value in report['summary'].items():
        if not isinstance(value, dict):
            denominator = (report['summary']['qualifiedTargetDenominator'] if key == 'pastTarget' else
                           report['summary']['caseAgeSampleCount'] if key == 'medianCaseAgeCalendarDays' else
                           sum(report['summary']['validatedEventCounts'].values()) if key == 'openConditionEventCount' else
                           report['summary']['recordedCases'])
            writer.writerow([key, value, denominator, report['asOfUtc'], report['inputSHA256'], report['datasetKind']])
    for key, value in report['durations'].items():
        writer.writerow([key, value['medianCalendarDays'], value['sampleCount'], report['asOfUtc'], report['inputSHA256'], report['datasetKind']])
    return stream.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = measure(json.loads(args.input.read_text()))
    args.output.mkdir(parents=True, exist_ok=False)
    for name, value in [('measures.json', json.dumps(report, ensure_ascii=False, indent=2)),
                        ('measures.html', render(report)), ('measures.csv', csv_report(report))]:
        (args.output / name).write_text(value)


if __name__ == '__main__':
    main()

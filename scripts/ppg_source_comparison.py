"""Read-only source comparison and affected-case projection; no native writes."""
from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from uuid import UUID

from ppg_source_sync import digest


def index(plan):
    """Use prepared exact identities and raw values, never fuzzy title matching."""
    if not plan.get('source') or not re.fullmatch('[0-9a-f]{64}', plan.get('sourceSha256', '')):
        raise ValueError('source provenance required')
    raw = {r['sourceRow']: r['fields'] for r in plan['rawRecords']}
    if len(raw) != len(plan['rawRecords']) or len(raw) != plan['inputCount']:
        raise ValueError('raw row accounting mismatch')
    result, used_rows = {}, set()
    for op in plan['operations']:
        uid = str(UUID(op['DocumentUID']))
        if uid in result or op['sourceRow'] not in raw or op['sourceRow'] in used_rows:
            raise ValueError('duplicate identity or missing raw row')
        used_rows.add(op['sourceRow'])
        fields = raw[op['sourceRow']]
        if any(not k.startswith('source') for k in fields):
            raise ValueError('non-source field in raw record')
        result[uid] = fields
    if len(result) + len(plan['exceptions']) != plan['inputCount']:
        raise ValueError('identity accounting mismatch')
    return result


def compare(baseline, candidate, cases):
    if baseline['source'] != candidate['source']:
        raise ValueError('different source namespaces')
    if baseline['exceptions'] or baseline['missingUIDs']:
        raise ValueError('baseline must be a complete reconciled plan')
    before, after = index(baseline), index(candidate)
    changes = []
    for uid in sorted(before.keys() | after.keys()):
        if uid not in after:
            changes.append({'DocumentUID': uid, 'kind': 'missing-source-exception', 'fields': []})
        elif uid not in before:
            changes.append({'DocumentUID': uid, 'kind': 'added-known-identity', 'fields': []})
        else:
            fields = []
            for key in sorted(before[uid].keys() | after[uid].keys()):
                old, new = before[uid], after[uid]
                if (key in old) != (key in new) or digest(old.get(key)) != digest(new.get(key)):
                    fields.append({'field': key, 'beforePresent': key in old,
                                   'afterPresent': key in new, 'before': old.get(key), 'after': new.get(key)})
            if fields:
                changes.append({'DocumentUID': uid, 'kind': 'changed', 'fields': fields})
    affected = {c['DocumentUID'] for c in changes}
    case_rows, unresolved, seen = [], [], set()
    for case in cases:
        key = case['CaseUID']
        if not isinstance(key, str) or not key or key in seen:
            raise ValueError('missing or duplicate CaseUID')
        seen.add(key)
        links = case.get('linkedDocumentUIDs')
        if isinstance(links, str):
            try:
                links = json.loads(links)
            except ValueError:
                links = None
        try:
            if not isinstance(links, list) or not links:
                raise ValueError()
            links = sorted({str(UUID(uid)) for uid in links})
        except (ValueError, TypeError, AttributeError):
            unresolved.append({'CaseUID': key, 'reason': 'document-links-unqualified'})
            continue
        unknown = sorted(set(links) - (before.keys() | after.keys()))
        if unknown:
            unresolved.append({'CaseUID': key, 'reason': 'linked-identity-not-in-comparison', 'DocumentUIDs': unknown})
        hits = sorted(set(links) & affected)
        if hits:
            case_rows.append({'CaseUID': key, 'DocumentUIDs': hits,
                              'action': 'Check changed source evidence; existing case decisions retained'})
    held = bool(candidate['exceptions'] or candidate['missingUIDs'] or before.keys() - after.keys())
    return {'schemaVersion': 1, 'mode': 'local-manual-read-only',
            'status': 'Source change detected—reconciliation held' if held else 'comparison-only',
            'authority': 'Source metadata comparison; document content and current approval not assessed',
            'inputs': {'baselinePlanSHA256': digest(baseline), 'candidatePlanSHA256': digest(candidate),
                       'casesSHA256': digest(cases), 'baselineSourceSHA256': baseline['sourceSha256'],
                       'candidateSourceSHA256': candidate['sourceSha256'], 'source': baseline['source'],
                       'baselineProvenance': baseline.get('provenance', {}),
                       'candidateProvenance': candidate.get('provenance', {})},
            'changes': changes, 'affectedCases': sorted(case_rows, key=lambda c: c['CaseUID']),
            'unresolvedCases': sorted(unresolved, key=lambda c: c['CaseUID']), 'identityExceptions': candidate['exceptions'],
            'missingUIDs': candidate['missingUIDs'], 'coverage': 'partial' if held or unresolved else 'complete',
            'caseWrites': 0, 'catalogueWrites': 0, 'checkpointAdvanced': False}


def render(report):
    rows = ''.join('<tr><td>' + html.escape(c['DocumentUID']) + '</td><td>' +
                   html.escape(c['kind']) + '</td><td><pre>' +
                   html.escape(json.dumps(c['fields'], ensure_ascii=False, indent=2)) +
                   '</pre></td></tr>' for c in report['changes'])
    summary = (f"{len(report['changes'])} document differences; "
               f"{len(report['affectedCases'])} cases linked to known differences; "
               f"{len(report['identityExceptions'])} identity exceptions; "
               f"{len(report['missingUIDs'])} missing identities. Coverage: {report['coverage']}.")
    return ('<!doctype html><meta charset="utf-8"><title>PPG source comparison</title>'
            '<style>body{font:16px system-ui;margin:2rem;max-width:100rem}table{border-collapse:collapse;width:100%}'
            'td,th{border:1px solid #bbb;padding:.6rem;text-align:left;vertical-align:top}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>'
            '<h1>Source comparison and affected cases</h1><p>' + html.escape(report['status']) +
            '</p><p>' + html.escape(summary) + '</p><p>Frozen manual report; not a continuous feed. '
            'Zero linked cases does not rule out effects from unresolved identities. See input versions below.</p><p>' +
            html.escape(report['authority']) + '</p><table><tr><th>DocumentUID</th>'
            '<th>Change</th><th>Before / after</th></tr>' + rows + '</table><h2>Cases and exceptions</h2><pre>' +
            html.escape(json.dumps({k: report[k] for k in ('affectedCases', 'unresolvedCases',
                               'identityExceptions', 'coverage', 'inputs')}, ensure_ascii=False, indent=2)) +
            '</pre><h2>Qualification</h2><pre>' + html.escape(json.dumps(report.get('qualification', {}), indent=2)) + '</pre>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'candidate', 'cases', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    report = compare(*(json.loads(getattr(args, name).read_text()) for name in ('baseline', 'candidate', 'cases')))
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'comparison.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    (args.output / 'comparison.html').write_text(render(report))


if __name__ == '__main__':
    main()

"""Validate a source-bound review without assigning a catalogue identity."""
import copy
import hashlib
import json
import re


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def content_digest(report):
    return digest(json.dumps({k: v for k, v in report.items() if k != 'contentSHA256'},
                             sort_keys=True, ensure_ascii=False).encode())


def assess(screen, index, subject_inventory, subject_bytes, original, text_bytes,
           criteria, findings, source_observations=(), criterion_responses=None):
    if type(index) is not int or not 0 <= index < len(screen['corpus']):
        raise ValueError('Unknown corpus index')
    if any(index in r['sourceIndexes'] for r in screen['records']):
        raise ValueError('Associated sources require the catalogue pair route')
    if not findings and criterion_responses is None:
        raise ValueError('A source review requires passage-backed findings')
    source = screen['corpus'][index]
    if (digest(original) != source['sourceSha256'] or digest(text_bytes) != source['textSha256']
            or digest(subject_bytes) != subject_inventory['sourceSha256']):
        raise ValueError('Source or subject bytes changed')
    elements = {e['sourceLocator']: e for e in subject_inventory['elements']}
    if len(elements) != len(subject_inventory['elements']):
        raise ValueError('Ambiguous subject locator')
    lines = text_bytes.decode('utf-8').split('\n')
    criterion_ids = {c['criterionId'] for c in criteria['criteria']}
    seen = set()
    checked = copy.deepcopy(findings)
    observations = copy.deepcopy(list(source_observations))
    for finding in checked:
        if finding['findingId'] in seen:
            raise ValueError('Duplicate finding')
        seen.add(finding['findingId'])
        if (finding['criterionId'] not in criterion_ids
                or finding['suggestedAction'] not in criteria['decisionOptions']
                or finding['claimType'] not in {'evidence', 'inference', 'unknown'}
                or finding.get('humanDecision') is not None
                or not all(finding.get(k) for k in ['statement', 'benefit', 'effort', 'dependencies', 'uncertainty'])):
            raise ValueError('Invalid finding context or supplied decision')
        if finding['claimType'] == 'unknown' and finding['suggestedAction'] != 'seek_further_evidence':
            raise ValueError('Unknown cannot support disposition')
        if {c['sourceId'] for c in finding['citations']} != {'subject-inspection', 'unassociated-text'}:
            raise ValueError('Both source representations required')
    responses = None
    if criterion_responses is not None:
        responses = copy.deepcopy(list(criterion_responses))
        response_ids = [r['criterionId'] for r in responses]
        if (not criterion_ids or len(criterion_ids) != len(criteria['criteria'])
                or len(response_ids) != len(set(response_ids)) or set(response_ids) != criterion_ids):
            raise ValueError('Complete unique criterion responses required')
        for response in responses:
            related = [f for f in checked if f['criterionId'] == response['criterionId']]
            finding_ids = response.get('findingIds', [])
            option = response.get('response')
            if (option not in {'supported_finding', 'no_issue_in_checked_scope',
                               'not_applicable_with_rationale', 'unknown_missing_evidence'}
                    or option not in criteria['responseOptions']
                    or response.get('scope') != 'historical_retained_text_only'
                    or not response.get('rationale')
                    or set(finding_ids) != {f['findingId'] for f in related}
                    or len(finding_ids) != len(set(finding_ids))
                    or {c['sourceId'] for c in response.get('citations', [])}
                       != {'subject-inspection', 'unassociated-text'}):
                raise ValueError('Invalid criterion response context or finding links')
            if option == 'supported_finding':
                if (not related or any(f['claimType'] == 'unknown' for f in related)
                        or response.get('claimType') not in {'evidence', 'inference'}):
                    raise ValueError('Supported response needs supported findings')
            elif option == 'unknown_missing_evidence':
                if (response.get('claimType') != 'unknown'
                        or any(f['claimType'] != 'unknown' for f in related)):
                    raise ValueError('Unknown response cannot promote supported findings')
            elif related or response.get('claimType') != 'inference':
                raise ValueError('No-issue/not-applicable response cannot conceal findings')
    for entry in [*checked, *observations, *(responses or [])]:
        if not entry.get('citations') or not entry.get('statement') or entry.get('humanDecision') is not None:
            raise ValueError('Evidence and no supplied decision required')
        for citation in entry['citations']:
            if citation['sourceId'] == 'subject-inspection':
                element = elements.get(citation['locator'])
                passage = element['text'] if element else None
                expected = subject_inventory['sourceSha256']
                if element and element.get('containsRevisions') and entry.get('claimType') != 'unknown':
                    raise ValueError('Unresolved revision requires an unknown finding')
            elif citation['sourceId'] == 'unassociated-text':
                match = re.fullmatch(r'lines=(\d+)-(\d+)', citation['locator'])
                if not match or not 1 <= int(match[1]) <= int(match[2]) <= len(lines):
                    raise ValueError('Invalid source passage')
                passage = '\n'.join(lines[int(match[1])-1:int(match[2])])
                expected = source['textSha256']
            else:
                raise ValueError('Unknown citation source')
            if (citation['sourceSha256'] != expected or not citation.get('quote')
                    or not passage or citation['quote'] not in passage):
                raise ValueError('Citation does not match retained bytes')
    report = dict(schemaVersion=1, kind='unassociated_retained_source_review',
                  sourceIndex=index, originalSHA256=source['sourceSha256'],
                  textSHA256=source['textSha256'], subjectInspectionSHA256=digest(subject_bytes),
                  sourceAssertions=copy.deepcopy(source), findings=checked,
                  sourceObservations=observations, criteriaVersion=criteria['criteriaVersion'],
                  criteriaSHA256=digest(json.dumps(criteria, sort_keys=True).encode()),
                  catalogueIdentityAssigned=False, currentAuthorityVerified=False,
                  humanDecision=None, findingsStatus='provisional_manual_review',
                  limitations=['No catalogue identity, current template or source authority established.',
                               'Available extracted text review is distinct from complete visual fidelity.'])
    if responses is not None:
        report['criterionResponses'] = responses
        report['criterionResponseVersion'] = '1.0.0'
        report['responseScope'] = 'historical_retained_text_only'
    report['contentSHA256'] = content_digest(report)
    return report

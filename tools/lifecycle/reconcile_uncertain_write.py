"""Read-only developer reconciliation of a privately bound fictional LC02 write.

Consumes native run/action/state/history evidence. Never calls Microsoft APIs,
resubmits a write, manufactures an after-proof or establishes policy authority.
"""
import argparse
import hashlib
import json
from pathlib import Path


def classify(binding, journal, run, action, inputs, response, observation,
             current, history, source, source_bytes):
    result = {'classification': 'held', 'reasons': [], 'nativeWrites': 0,
              'resubmitAllowed': False, 'automaticRecoveryQualified': False}
    reasons = result['reasons']
    expected = binding.get('expectedRequest', {})
    if binding.get('qualificationOnly') is not True or not expected.get('CaseUID', '').startswith('LC-FICTIONAL-'):
        reasons.append('unbound-fictional-target')
    if journal.get('request') != expected or journal.get('before') != expected.get('before'):
        reasons.append('journal-request-or-preimage-mismatch')
    if journal.get('beforeETag') != expected.get('expectedCaseETag') or expected.get('expectedCaseETag') in (None, '', '*'):
        reasons.append('original-token-mismatch')
    run_id = run.get('name')
    if not run_id or journal.get('preparedByRun') != run_id:
        reasons.append('run-not-attributable-to-journal')
    action_id = action.get('id', '')
    run_resource = run.get('id', '')
    if (not run_id or not run_resource.endswith('/runs/' + run_id)
            or action_id != run_resource + '/actions/Conditional_case_write'
            or action.get('name') != 'Conditional_case_write'
            or action.get('runName') != run_id):
        reasons.append('wrong-native-action')
    if run.get('properties', {}).get('status') not in ('Succeeded', 'Failed', 'Cancelled', 'Canceled', 'TimedOut'):
        reasons.append('run-not-terminal')
    fields = list(expected.get('before', {}))
    protected = list(dict.fromkeys(fields + ['Title', 'evidenceDraftLink']))
    def field(row, key):
        # Native ListItemVersion uses ID; ListItem uses Id. Keep the raw
        # evidence intact and map only this observed built-in identity alias.
        if key == 'Id' and 'VersionId' in row and 'Id' not in row:
            return row.get('ID')
        return row.get(key)
    protected_projection = lambda row: {k: field(row, k) for k in protected}
    projection = lambda row: {k: field(row, k) for k in fields}
    observed_body = observation.get('body', {})
    observed_etag = observation.get('headers', {}).get('ETag')
    # Keep tokens opaque. A fresh REST/history read corroborates the retained
    # native HTTP observation; CLI and connector ETag formats are not interchanged.
    if (not observed_etag or observed_etag == '*' or protected_projection(current) != protected_projection(observed_body)
            or current.get('GUID') != observed_body.get('GUID')
            or current.get('OData__UIVersionString') != observed_body.get('OData__UIVersionString')
            or current.get('Id') != binding.get('caseItemId')):
        reasons.append('current-observation-drift')
    for page in (history, history.get('d', {})):
        if any(page.get(key) for key in ('nextLink', '@nextLink', 'odata.nextLink', '@odata.nextLink', '__next')):
            reasons.append('incomplete-native-history')
    versions = history.get('value', history.get('d', {}).get('results', []))
    if any('ID' in v and (v['ID'] != binding.get('caseItemId')
                         or ('Id' in v and v['Id'] != v['ID'])) for v in versions):
        reasons.append('version-item-identity-mismatch')
    latest = [v for v in versions if v.get('IsCurrentVersion') is True]
    if (len(latest) != 1 or protected_projection(latest[0]) != protected_projection(current)
            or latest[0].get('VersionLabel') != current.get('OData__UIVersionString')):
        reasons.append('current-history-mismatch')
    if (source.get('UniqueId') != binding.get('sourceUniqueId')
            or source.get('ETag') != expected.get('sourceETag')
            or hashlib.sha256(source_bytes).hexdigest() != expected.get('sourceSHA256')):
        reasons.append('source-pin-mismatch')
    if reasons:
        return result
    status = action.get('properties', {}).get('status')
    if status == 'Skipped':
        if projection(current) == expected['before'] and observed_etag == journal['beforeETag']:
            result['classification'] = 'not-applied-no-resubmit'
        else:
            reasons.append('skipped-action-but-preimage-not-retained')
        return result
    desired = dict(expected['before'], nextAction=expected['desiredNextAction'])
    parameters = inputs.get('parameters', {})
    headers = parameters.get('parameters/headers', {})
    body = parameters.get('parameters/body')
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except ValueError:
            body = None
    if (parameters.get('dataset') != binding.get('siteUrl')
            or parameters.get('parameters/uri') != binding.get('caseUri')
            or parameters.get('parameters/method') != 'POST'
            or headers.get('X-HTTP-Method') != 'MERGE'
            or headers.get('IF-MATCH') != journal['beforeETag']
            or body != {'nextAction': expected['desiredNextAction']}):
        reasons.append('write-inputs-not-exactly-attributable')
    if status != 'Succeeded' or response.get('statusCode') != 204:
        reasons.append('write-acknowledgement-not-proven')
    if response.get('headers', {}).get('ETag') != observed_etag:
        reasons.append('write-token-not-current-token')
    if projection(current) != desired:
        reasons.append('expected-after-state-not-retained')
    before_versions = [v for v in versions if projection(v) == expected['before']]
    if (len(before_versions) != 1 or latest[0].get('VersionId', 0) <= before_versions[0].get('VersionId', 0)
            or any(field(current, k) != field(before_versions[0], k)
                   for k in protected if k != 'nextAction')):
        reasons.append('before-after-history-not-attributable')
    if not reasons:
        result['classification'] = 'committed-no-resubmit'
        result['manualContinuation'] = ('Review the original native run/action and exact history; '
                                        'retain the committed classification. Never rerun the mutation. '
                                        'If a receipt is still missing, continue only its separately '
                                        'guarded reconciliation path; do not invent a native after-proof.')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True, help='Private file containing evidence file paths')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    bundle = json.loads(Path(args.bundle).read_text())
    values = {k: json.loads(Path(bundle[k]).read_text()) for k in
              ('binding', 'journal', 'run', 'action', 'inputs', 'response',
               'observation', 'current', 'history', 'source')}
    values['source_bytes'] = Path(bundle['source_bytes']).read_bytes()
    result = classify(**values)
    # Recovery evidence and previous classifications must never be overwritten.
    with Path(args.output).open('x') as output:
        output.write(json.dumps(result, indent=2) + '\n')
    print(result['classification'])


if __name__ == '__main__':
    main()

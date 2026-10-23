"""GET-only selected-case prerequisite check; no prepared revision is bound yet.

This deliberately cannot open consultation. A later qualified revision consumer
must bind the separate output and its exact version, not reuse the source scope.
"""
import argparse
import copy
import hashlib
import json
import uuid
from pathlib import Path


def build(context, target, binding):
    original = context['properties']['definition']
    digest = hashlib.sha256(json.dumps(original, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if digest != binding['approvedContextDefinitionSHA256'] or binding.get('qualificationOnly') is not True:
        raise ValueError('Exact reviewed fictional context required')
    if binding.get('preparedRevision') is not None:
        raise ValueError('This missing-prerequisite profile cannot qualify a prepared revision')
    uuid.UUID(binding['projectionCommitUniqueId'])
    if not binding['projectionCommitETag'] or binding['projectionCommitETag'] == '*':
        raise ValueError('Exact retained projection-commit token required')
    if not binding['expectedCaseUID'].startswith('LC-FICTIONAL-OP-'):
        raise ValueError('Fictional operator case required')
    refs = target['properties']['connectionReferences']
    if refs['shared_sharepointonline']['connectionName'] != context['properties']['connectionReferences']['shared_sharepointonline']['connectionName']:
        raise ValueError('Retain qualified connection')
    out = {'properties': {'displayName': 'PPG Lifecycle | FICTIONAL preparation preflight', 'state': 'Stopped',
        'definition': copy.deepcopy(original), 'connectionReferences': copy.deepcopy(refs)}}
    d = out['properties']['definition']; d['triggers']['manual']['runtimeConfiguration'] = {'concurrency': {'runs': 1}}
    actions = d['actions']; template = copy.deepcopy(actions['Resolve_context']['actions']['Read_selected_case'])
    context_ref = "outputs('Selected_case_context')"; commit = "outputs('Parse_projection_commit')"
    def read(uri, previous=None):
        result = copy.deepcopy(template); result['inputs']['parameters']['parameters/uri'] = uri
        result['runAfter'] = {previous: ['Succeeded']} if previous else {}
        return result
    def comp(value, previous=None):
        return {'type': 'Compose', 'inputs': value, 'runAfter': {previous: ['Succeeded']} if previous else {}}
    def hold(reason):
        return comp({'preparationQualified': False, 'consultationOpenable': False, 'writeCount': 0,
            'reason': reason, 'realPolicyEffects': False, 'preparedRevision': None})
    uri = "_api/web/GetFileById('" + binding['projectionCommitUniqueId'] + "')"
    work = {'Read_projection_commit_before': read(uri + '?$select=UniqueId,ETag')}
    work['Read_projection_commit_content'] = read(uri + '/$value', 'Read_projection_commit_before')
    work['Parse_projection_commit'] = comp("@if(contains(body('Read_projection_commit_content'),'$content'),json(base64ToString(body('Read_projection_commit_content')?['$content'])),json(string(body('Read_projection_commit_content'))))", 'Read_projection_commit_content')
    work['Read_projection_commit_after'] = read(uri + '?$select=UniqueId,ETag', 'Parse_projection_commit')
    checks = ["equals(" + commit + "?['kind'],'fictional-ownership-projection-commit-v1')",
        "equals(" + commit + "?['CaseUID']," + context_ref + "?['CaseUID'])",
        "equals(" + commit + "?['afterCaseETag']," + context_ref + "?['caseETag'])",
        "equals(body('Read_selected_case')?['caseStatus'],'Ownership accepted — FICTIONAL')",
        "equals(body('Read_selected_case')?['accountableRole'],outputs('Parse_baseline')?['request']?['proposedRole'])"]
    for name in ('Read_projection_commit_before', 'Read_projection_commit_after'):
        checks += ["equals(body('" + name + "')?['ETag'],'" + binding['projectionCommitETag'].replace("'", "''") + "')",
            "equals(toLower(body('" + name + "')?['UniqueId']),'" + binding['projectionCommitUniqueId'].lower() + "')"]
    for key in ('baselineReference', 'baselineUniqueId', 'baselineETag'):
        checks += ["equals(" + commit + "?['context']?['" + key + "']," + context_ref + "?['" + key + "'])"]
    for key in ('CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256'):
        checks += ["equals(" + commit + "?['context']?['scope']?['" + key + "']," + context_ref + "?['scope']?['" + key + "'])"]
    missing = hold('No qualified prepared-revision binding exists for this selected case/source. Retain the original source and incomplete other-case drafts; do not open consultation.')
    missing['inputs'].update({'ownershipProjectionVerified': True, 'CaseUID': '@' + context_ref + "?['CaseUID']",
        'originalSourceScope': '@' + context_ref + "?['scope']", 'originalSourceIsPreparedRevision': False,
        'requiredConsultationScope': 'CaseUID plus separate prepared-file identity/version/hash and explicit required-role coverage',
        'nextAction': 'Document owner supplies a qualified case/source-bound prepared revision and receipt; then qualify consultation input/coverage checks'})
    work['Verify_preparation_prerequisites'] = {'type': 'If', 'expression': '@and(' + ','.join(checks) + ')',
        'actions': {'Held_missing_prepared_revision': missing},
        'else': {'actions': {'Held_unverified_ownership': hold('Current case and retained ownership projection do not match; no preparation or consultation progression')}},
        'runAfter': {'Read_projection_commit_after': ['Succeeded']}}
    actions['Check_selected_preparation'] = {'type': 'If',
        'expression': "@and(equals(" + context_ref + "?['contextValid'],true),equals(" + context_ref + "?['CaseUID'],'" + binding['expectedCaseUID'].replace("'", "''") + "'))",
        'actions': work, 'else': {'actions': {'Held_wrong_preparation_context': hold('Select the supported occurrence; no cross-case preparation fallback')}},
        'runAfter': {'Resolve_context': ['Succeeded']}}
    actions['Held_preparation_error'] = hold('Preparation prerequisites could not be verified; no event or case writes')
    actions['Held_preparation_error']['runAfter'] = {'Check_selected_preparation': ['Failed', 'TimedOut', 'Skipped']}
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('context', 'target', 'binding', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(build(json.loads(args.context.read_text()), json.loads(args.target.read_text()), json.loads(args.binding.read_text())), indent=2) + '\n')

"""Compose existing selected-case operations without swapping native definitions.

Initiation retains its separate manual flow. This router shares the reviewed
selected-row context across context inspection, ownership projection and the
current preparation prerequisite. Native identities remain privately bound.
"""
import argparse
import copy
import json
import re
from pathlib import Path
from build_selected_ownership_projection import build as build_projection
from build_preparation_preflight import build as build_preparation
from build_prepared_revision_check import build_actions as build_prepared_reader, CASE_INPUT_FIELDS
from build_prepared_readiness_check import build_actions as build_readiness_reader
from build_prepared_closure_check import build_actions as build_closure_reader

MODES = ('Check context', 'Project ownership', 'Check preparation')


def rename_actions(actions, prefix):
    """Namespace action references while preserving shared outer context reads."""
    names = set()
    def collect(group):
        for name, action in group.items():
            names.add(name)
            collect(action.get('actions', {}))
            collect(action.get('else', {}).get('actions', {}))
    collect(actions)
    mapping = {name: prefix + name for name in names}
    def text(value):
        pattern = r"\b(body|outputs|actions|result)\('([^']+)'\)"
        return re.sub(pattern, lambda m: m.group(1) + "('" + mapping.get(m.group(2), m.group(2)) + "')", value)
    def value(item):
        if isinstance(item, str): return text(item)
        if isinstance(item, list): return [value(v) for v in item]
        if isinstance(item, dict):
            out = {}
            for key, val in item.items():
                if key == 'actions': out[key] = group(val)
                elif key == 'runAfter': out[key] = {mapping.get(k, k): value(v) for k, v in val.items()}
                else: out[key] = value(val)
            return out
        return item
    def group(items): return {mapping[k]: value(v) for k, v in items.items()}
    return group(actions)


def projection_actions(profile):
    actions = copy.deepcopy(profile['properties']['definition']['actions'])
    actions.pop('Resolve_context')
    actions['Read_projection_case']['runAfter'] = {}
    return actions


def allow_selected_evidence_link_replay(actions):
    """Only the later evidence link may advance the committed case snapshot."""
    replay = actions['Verify_projection_evidence']['actions']['Choose_projection_path']['actions']
    verify = replay['Verify_committed_projection']
    commit = "outputs('Parse_committed_projection')"
    token = "equals(" + commit + "?['afterCaseETag'],outputs('Read_projection_case')?['headers']?['ETag'])"
    evidence = "equals(" + commit + "?['afterCase']?['evidenceDraftLink'],body('Read_projection_case')?['evidenceDraftLink'])"
    for clause in (token, evidence):
        if verify['expression'].count(',' + clause) != 1: raise ValueError('Review changed committed replay contract')
        verify['expression'] = verify['expression'].replace(',' + clause, '')
    # The strict projection helper also compares the full retained/current row.
    # Retain that protection here, allowing only the deliberate later evidence
    # selection and its service-managed revision fields. Role, status and every
    # unknown human field remain part of the comparison.
    def row(value, ignored):
        return "union(" + value + ",json('" + json.dumps(
            {key: None for key in ignored}, separators=(',', ':')) + "'))"
    retained = commit + "?['afterCase']"
    current = "body('Read_projection_case')"
    strict = "equals(" + row(retained, ('odata.id',)) + ',' + row(current, ('odata.id',)) + ')'
    ignored = ('odata.id', 'odata.etag', 'Modified', 'EditorId',
               'OData__UIVersionString', 'evidenceDraftLink')
    historical = "equals(" + row(retained, ignored) + ',' + row(current, ignored) + ')'
    if verify['expression'].count(',' + strict) != 1:
        raise ValueError('Review changed full-row committed replay contract')
    verify['expression'] = verify['expression'].replace(',' + strict, ',' + historical)
    exact = '@and(' + token + ',' + evidence + ')'
    receipt = verify['actions']['Native_projection_replay']['inputs']
    receipt.update(caseAtProjectionSnapshot=exact, currentSnapshotMatches=exact,
        historicalReplay='@not(' + exact[1:] + ')', currentProjectionQualified=exact,
        progressionGranted=False, caseOwnershipUpdated=False,
        originalBeforeCaseETag='@' + commit + "?['context']?['caseETag']",
        originalAfterCaseETag='@' + commit + "?['afterCaseETag']",
        currentCaseETag="@outputs('Read_projection_case')?['headers']?['ETag']")
    return actions


def preparation_ownership_actions(profile, context):
    """Verify prior ownership while allowing only an evidence-link advance."""
    actions = copy.deepcopy(profile['properties']['definition']['actions'])
    for key in ('Resolve_context', 'Held_unverified_read'): actions.pop(key, None)
    check = actions['Check_selected_preparation']; check['runAfter'] = {}
    work = check['actions']; verify = work['Verify_preparation_prerequisites']
    current = copy.deepcopy(context['properties']['definition']['actions']['Resolve_context']['actions']['Read_selected_case'])
    current['inputs']['parameters']['parameters/uri'] = current['inputs']['parameters']['parameters/uri'].replace('?$select=Id,CaseUID,linkedDocumentUIDs,sourceBaselineRef,accountableRole,caseStatus','')
    current['runAfter'] = {'Read_projection_commit_after':['Succeeded']}
    work['Read_preparation_ownership_case'] = current
    old = "equals(outputs('Parse_projection_commit')?['afterCaseETag'],outputs('Selected_case_context')?['caseETag'])"
    fresh = "equals(outputs('Read_preparation_ownership_case')?['headers']?['ETag'],outputs('Selected_case_context')?['caseETag'])"
    if verify['expression'].count(old) != 1: raise ValueError('Review changed preparation ownership contract')
    verify['expression'] = verify['expression'].replace(old, fresh)
    preserved = ["equals(outputs('Parse_projection_commit')?['afterCase']?['"+k+"'],body('Read_preparation_ownership_case')?['"+k+"'])" for k in CASE_INPUT_FIELDS]
    verify['expression'] = '@and(' + verify['expression'][1:] + ',' + ','.join(preserved) + ')'
    verify['runAfter'] = {'Read_preparation_ownership_case':['Succeeded']}
    verify['actions'] = {'Verified_preparation_ownership':{'type':'Compose','runAfter':{},'inputs':{
        'ownershipProjectionVerified':True,'CaseUID':"@outputs('Selected_case_context')?['CaseUID']",
        'originalSourceScope':"@outputs('Selected_case_context')?['scope']",
        'originalAfterCaseETag':"@outputs('Parse_projection_commit')?['afterCaseETag']",
        'currentCaseETag':"@outputs('Read_preparation_ownership_case')?['headers']?['ETag']"}}}
    return actions


def runtime_projection(context, target, binding):
    """Bind a fresh fictional occurrence from server-read context, not form pins."""
    selected = copy.deepcopy(binding)
    placeholders = {'expectedCaseUID': 'LC-FICTIONAL-OP-RUNTIME-SELECTED',
        'expectedCaseETag': 'runtime-selected-case-token',
        'expectedResponseUID': 'LC02-OP-RESP-RUNTIME-SELECTED',
        'caseItemUri': binding['caseItemUri'].rsplit('/items(', 1)[0] + '/items(2147483647)',
        'journalName': 'LC02-runtime-projection-before.json',
        'commitName': 'LC02-runtime-projection-commit.json'}
    selected.update(placeholders)
    actions = projection_actions(build_projection(context, target, selected))
    c = "outputs('Selected_case_context')"; request = "outputs('Parse_baseline')?['request']"
    response_uid = "first(body('Read_projection_responses')?['value'])?['EventUID']"
    case_base = binding['caseItemUri'].rsplit('/items(', 1)[0]
    def quote(s): return "'" + s.replace("'", "''") + "'"
    def convert(v):
        if isinstance(v, dict): return {k: convert(w) for k, w in v.items()}
        if isinstance(v, list): return [convert(w) for w in v]
        if not isinstance(v, str): return v
        if v == placeholders['caseItemUri']:
            return "@concat(" + quote(case_base + '/items(') + ",string(int(" + c + "?['nativeItemId'])),')')"
        if v == placeholders['expectedResponseUID']: return '@' + response_uid
        for key, expr in [('expectedCaseUID', c + "?['CaseUID']"), ('expectedCaseETag', c + "?['caseETag']"), ('expectedResponseUID', response_uid)]:
            v = v.replace(quote(placeholders[key]), expr)
        for key, suffix in [('journalName', '-before.json'), ('commitName', '-commit.json')]:
            if placeholders[key] in v:
                before, after = v.split(placeholders[key])
                filename = "concat('LC02-projection-'," + request + "?['requestReference']," + quote(suffix) + ')'
                return '@concat(' + quote(before) + ',' + filename + ',' + quote(after) + ')'
        return v
    actions = convert(actions)
    ref = request + "?['requestReference']"
    valid = "@and(startsWith(string(" + ref + "),'LC02-OP-'),lessOrEquals(length(string(" + ref + ")),64),equals(uriComponent(string(" + ref + ")),string(" + ref + ")),not(contains(string(" + ref + "),decodeUriComponent('%27'))))"
    actions['Validate_runtime_request'] = {'type': 'If', 'expression': valid, 'runAfter': {},
        'actions': {'Runtime_request_valid': {'type': 'Compose', 'inputs': True, 'runAfter': {}}},
        'else': {'actions': {'Refuse_runtime_request': {'type': 'Terminate', 'runAfter': {},
            'inputs': {'runStatus': 'Failed', 'runError': {'code': 'UnsafeRequestReference',
                'message': 'Retain a bounded URI-safe fictional request reference; no projection writes.'}}}}}}
    actions['Read_projection_case']['runAfter'] = {'Validate_runtime_request': ['Succeeded']}
    guard = actions['Verify_projection_evidence']
    guard['expression'] = '@and(' + guard['expression'][1:] + ",startsWith(string(" + response_uid + "),'LC02-OP-RESP-'),lessOrEquals(length(string(" + response_uid + ")),80),not(empty(" + c + "?['caseETag'])),not(equals(" + c + "?['caseETag'],'*')),empty(body('Read_projection_offer')?['odata.nextLink']),empty(body('Read_projection_offer')?['@odata.nextLink']),empty(body('Read_projection_responses')?['odata.nextLink']),empty(body('Read_projection_responses')?['@odata.nextLink']))"
    after = actions['Verify_projection_evidence']['actions']['Choose_projection_path']['else']['actions']['Verify_initial_projection']['actions']['Verify_projection_before']['actions']['Verify_projection_after']
    after['expression'] = '@and(' + after['expression'][1:] + ",empty(body('Projection_response_history_after')?['odata.nextLink']),empty(body('Projection_response_history_after')?['@odata.nextLink']))"
    return actions


def runtime_preparation(context, target, binding, projection_binding):
    """Read this occurrence's native projection commit; hold unbound preparation."""
    fake_uid = '00000000-0000-4000-8000-000000000001'
    fake_token = 'runtime-commit-token'
    selected = {**binding, 'expectedCaseUID': 'LC-FICTIONAL-OP-RUNTIME-SELECTED',
        'projectionCommitUniqueId': fake_uid, 'projectionCommitETag': fake_token}
    profile = build_preparation(context, target, selected)
    group = preparation_ownership_actions(profile, context)
    c = "outputs('Selected_case_context')"; request = "outputs('Parse_baseline')?['request']"
    ref = request + "?['requestReference']"; found = "first(body('Find_selected_projection_commit')?['value'])"
    def quote(value): return "'" + value.replace("'", "''") + "'"
    def convert(value):
        if isinstance(value, dict): return {k:convert(v) for k,v in value.items()}
        if isinstance(value, list): return [convert(v) for v in value]
        if not isinstance(value, str): return value
        if fake_uid in value and value.startswith('_api/web/GetFileById('):
            suffix = value.split("')", 1)[1]
            return "@concat('_api/web/GetFileById(',decodeUriComponent('%27')," + found + "?['UniqueId'],decodeUriComponent('%27'),')'," + quote(suffix) + ')'
        value = value.replace(quote('LC-FICTIONAL-OP-RUNTIME-SELECTED'), c + "?['CaseUID']")
        value = value.replace(quote(fake_uid), "toLower(" + found + "?['UniqueId'])")
        return value.replace(quote(fake_token), found + "?['ETag']")
    group = convert(group)
    check = group['Check_selected_preparation']; check['runAfter'] = {}
    check['expression'] = '@and(' + check['expression'][1:] + ",startsWith(string(" + ref + "),'LC02-OP-'),lessOrEquals(length(string(" + ref + ")),64),equals(uriComponent(string(" + ref + ")),string(" + ref + ")),not(contains(string(" + ref + "),decodeUriComponent('%27'))))"
    work = check['actions']; template = copy.deepcopy(work['Read_projection_commit_before'])
    template['runAfter'] = {}
    template['inputs']['parameters']['parameters/uri'] = '@concat(' + quote(projection_binding['folderUri'] + "/Files?$filter=Name eq '") + ",concat('LC02-projection-'," + ref + ",'-commit.json')," + quote("'&$select=Name,UniqueId,ETag") + ')'
    selection = "@and(equals(length(body('Find_selected_projection_commit')?['value']),1),not(empty(" + found + "?['UniqueId'])),not(empty(" + found + "?['ETag'])),not(equals(" + found + "?['ETag'],'*')),empty(body('Find_selected_projection_commit')?['odata.nextLink']),empty(body('Find_selected_projection_commit')?['@odata.nextLink']))"
    held = {'type':'Compose','runAfter':{},'inputs':{'preparationQualified':False,'consultationOpenable':False,'writeCount':0,'preparedRevision':None,'reason':'A unique current ownership projection commit is required before preparation; no broader or cross-case fallback'}}
    check['actions'] = {'Find_selected_projection_commit':template,'Verify_selected_projection_commit':{'type':'If','runAfter':{'Find_selected_projection_commit':['Succeeded']},'expression':selection,'actions':work,'else':{'actions':{'Held_missing_ownership_commit':held}}}}
    return group


def build(context, target, binding):
    legacy_binding = binding['legacyProjection']
    legacy = build_projection(context, target, legacy_binding)
    prep = build_preparation(context, target, binding['preparation'])
    out = copy.deepcopy(context)
    out['properties'] = {**out['properties'], 'displayName': 'PPG Lifecycle | FICTIONAL case work', 'state': 'Stopped',
        'connectionReferences': copy.deepcopy(target['properties']['connectionReferences'])}
    d = out['properties']['definition']; a = d['actions']
    a.pop('Held_unverified_read', None)
    trigger = d['triggers']['manual']; trigger['runtimeConfiguration'] = {'concurrency': {'runs': 1}}
    old_schema = trigger['inputs']['schema']
    row = old_schema.get('properties', {}).get('rows', old_schema.get('rows'))['items']
    row['properties'] = {'text': {'type': 'string', 'title': 'Operation',
        'description': 'Check context / Project ownership / Check preparation. No real role authority or publication.',
        'x-ms-dynamically-added': True, 'x-ms-content-hint': 'TEXT'}}
    row['required'] = ['text']
    trigger['inputs']['schema'] = {'type': 'object', 'properties': {'rows': {'type': 'array', 'items': row}}}
    a['Validate_case_operation'] = {'type': 'If', 'expression': "@contains(createArray('Check context','Project ownership','Check preparation'),triggerBody()?['text'])", 'runAfter': {},
        'actions': {'Case_operation_valid': {'type': 'Compose', 'inputs': True, 'runAfter': {}}},
        'else': {'actions': {'Refuse_case_operation': {'type': 'Terminate', 'runAfter': {}, 'inputs': {'runStatus': 'Failed', 'runError': {'code': 'UnsupportedCaseOperation', 'message': 'Choose an explicit supported case-work operation; no writes.'}}}}}}
    a['Resolve_context']['runAfter'] = {'Validate_case_operation': ['Succeeded']}
    legacy_actions = rename_actions(allow_selected_evidence_link_replay(projection_actions(legacy)), 'Legacy_')
    selected_actions = rename_actions(allow_selected_evidence_link_replay(runtime_projection(context, target, legacy_binding)), 'Selected_')
    a['Route_ownership_projection'] = {'type': 'If', 'expression': "@and(equals(triggerBody()?['text'],'Project ownership'),equals(outputs('Selected_case_context')?['contextValid'],true))", 'runAfter': {'Resolve_context': ['Succeeded']},
        'actions': {'Choose_projection_contract': {'type': 'If', 'expression': "@equals(outputs('Selected_case_context')?['CaseUID'],'" + legacy_binding['expectedCaseUID'].replace("'", "''") + "')", 'runAfter': {},
            'actions': legacy_actions, 'else': {'actions': selected_actions}}}, 'else': {'actions': {}}}
    prep_actions = preparation_ownership_actions(prep, context)
    a['Route_preparation_check'] = {'type': 'If', 'expression': "@and(equals(triggerBody()?['text'],'Check preparation'),equals(outputs('Selected_case_context')?['contextValid'],true))", 'runAfter': {'Resolve_context': ['Succeeded']},
        'actions': {'Choose_preparation_contract': {'type': 'If', 'expression': "@equals(outputs('Selected_case_context')?['CaseUID'],'" + legacy_binding['expectedCaseUID'].replace("'", "''") + "')", 'runAfter': {}, 'actions': rename_actions(prep_actions, 'Preparation_'), 'else': {'actions': rename_actions(runtime_preparation(context, target, binding['preparation'], legacy_binding), 'SelectedPreparation_')}}}, 'else': {'actions': {}}}
    prepared_mode = a['Route_preparation_check']['actions']
    prepared_mode['Prepared_ownership_context'] = {'type':'Compose','runAfter':{'Choose_preparation_contract':['Succeeded']},'inputs':"@coalesce(outputs('Preparation_Verified_preparation_ownership'),outputs('SelectedPreparation_Verified_preparation_ownership'),json('{}'))"}
    reader = build_prepared_reader(context, binding['preparedSelection'], "outputs('Prepared_ownership_context')")
    reader['Check_prepared_ownership']['runAfter'] = {'Prepared_ownership_context':['Succeeded']}
    reader['Held_prepared_reader_error'] = {'type':'Compose','runAfter':{'Check_prepared_ownership':['Failed','TimedOut','Skipped']},'inputs':{'preparationQualified':False,'consultationOpenable':False,'writeCount':0,'realPolicyEffects':False,'reason':'Selected prepared file or qualification evidence could not be verified; no fallback or progression'}}
    prepared_mode.update(reader)
    if binding.get('preparedReadiness') is not None:
        # Reuse the same execution's ownership and prepared reader, never form pins.
        row['properties']['text']['description'] += ' / Check readiness (read-only evidence observation).'
        a['Validate_case_operation']['expression'] = "@contains(createArray('Check context','Project ownership','Check preparation','Check readiness'),triggerBody()?['text'])"
        a['Route_preparation_check']['expression'] = "@and(contains(createArray('Check preparation','Check readiness'),triggerBody()?['text']),equals(outputs('Selected_case_context')?['contextValid'],true))"
        a['Route_readiness_check'] = {'type': 'If',
            'expression': "@and(equals(triggerBody()?['text'],'Check readiness'),equals(outputs('Selected_case_context')?['contextValid'],true))",
            'runAfter': {'Route_preparation_check': ['Succeeded']},
            'actions': build_readiness_reader(context, binding['preparedReadiness']), 'else': {'actions': {}}}
    if binding.get('preparedClosure') is not None:
        row['properties']['text']['description'] += ' / Check closure (read-only evidence observation).'
        operations = list(MODES) + (['Check readiness'] if binding.get('preparedReadiness') is not None else []) + ['Check closure']
        prep_operations = ['Check preparation'] + (['Check readiness'] if binding.get('preparedReadiness') is not None else []) + ['Check closure']
        def choices(values): return 'createArray(' + ','.join("'" + value + "'" for value in values) + ')'
        a['Validate_case_operation']['expression'] = '@contains(' + choices(operations) + ",triggerBody()?['text'])"
        a['Route_preparation_check']['expression'] = '@and(contains(' + choices(prep_operations) + ",triggerBody()?['text']),equals(outputs('Selected_case_context')?['contextValid'],true))"
        a['Route_closure_check'] = {'type': 'If',
            'expression': "@and(equals(triggerBody()?['text'],'Check closure'),equals(outputs('Selected_case_context')?['contextValid'],true))",
            'runAfter': {'Route_preparation_check': ['Succeeded']},
            'actions': build_closure_reader(context, binding['preparedClosure']), 'else': {'actions': {}}}
    a['Route_context_check'] = {'type': 'If', 'expression': "@equals(triggerBody()?['text'],'Check context')", 'runAfter': {'Resolve_context': ['Succeeded']},
        'actions': {'Native_case_context_result': {'type': 'Compose', 'runAfter': {}, 'inputs': {'context': "@outputs('Selected_case_context')", 'contextValid': "@equals(outputs('Selected_case_context')?['contextValid'],true)", 'writeCount': 0, 'realPolicyEffects': False}}}, 'else': {'actions': {}}}
    a['Hold_unverified_case_context'] = {'type': 'If', 'expression': "@not(equals(outputs('Selected_case_context')?['contextValid'],true))", 'runAfter': {'Resolve_context':['Succeeded']}, 'actions': {'Held_selected_case_context': {'type':'Compose','runAfter':{},'inputs':{'contextValid':False,'writeCount':0,'realPolicyEffects':False,'reason':'Selected context is unsupported or changed; all mode-specific effects skipped'}}}, 'else':{'actions':{}}}
    a['Held_case_context_error'] = {'type': 'Compose', 'runAfter': {'Resolve_context': ['Failed', 'TimedOut']},
        'inputs': {'contextValid': False, 'writeCount': 0, 'realPolicyEffects': False, 'reason': 'Context not verified; all mode-specific effects skipped'}}
    def depth(group, current=0):
        maximum = current
        for action in group.values():
            inner = current + (action.get('type') in ('If', 'Scope', 'Foreach', 'Until', 'Switch'))
            maximum = max(maximum, depth(action.get('actions', {}), inner), depth(action.get('else', {}).get('actions', {}), inner))
        return maximum
    if depth(a) > 8: raise ValueError('Native WDL control nesting exceeds eight')
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('context', 'target', 'binding', 'output'): parser.add_argument('--' + key, required=True, type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(build(json.loads(args.context.read_text()), json.loads(args.target.read_text()), json.loads(args.binding.read_text())), indent=2) + '\n')

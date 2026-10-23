"""Add an explicit next-review entry to the existing fictional initiation form.

Pure local composition: no native I/O or qualification claim. The original
builder/API and successful initiation actions are untouched. With complete reviewed
configuration, the new branch performs runtime selection, historical continuity,
source/prepared/stage revalidation and canonical intent/case/receipt creation.
Absent or partial configuration retains explicit holds. A coherent uploaded JSON
or caller qualification flag cannot substitute for authoritative native reads.
No selected completed case is compiled into the emitted branch.

Namespace utilities operate on WDL call sites, not human/proof data. Components
must identify literal Compose inputs explicitly; runtime-loaded records never
pass through these compile-time utilities.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from uuid import UUID

from build_selected_event_routes import audit_actions

LEGACY_FIELDS = ('text', 'text_1', 'text_2', 'text_3', 'text_4')
LITERAL_INPUTS = frozenset(('Next_expected_case', 'Next_expected_date', 'Next_expected_commit'))
OPTIONAL_FIELDS = {
    'text_5': {'type': 'string', 'title': 'Operation (blank = initiate review)',
               'description': 'Leave blank or enter Initiate review for the existing path. Create next review requires a qualified completed review.',
               'x-ms-dynamically-added': True, 'x-ms-content-hint': 'TEXT'},
    'text_6': {'type': 'string', 'title': 'Completed review reference',
               'description': 'For Create next review only: the retained closure request reference. Unqualified references are refused.',
               'x-ms-dynamically-added': True, 'x-ms-content-hint': 'TEXT'},
}
_CALL = re.compile(r"\b(body|outputs|actions|result)(\(\s*')([^']+)('\s*\))")


def _quoted_end(text, start):
    index = start + 1
    while index < len(text):
        if text[index] == "'":
            if index + 1 < len(text) and text[index + 1] == "'":
                index += 2
                continue
            return index + 1
        index += 1
    raise ValueError('Unterminated WDL string literal')


def _wdl_segment(text, mapping):
    pieces, references, index = [], set(), 0
    while index < len(text):
        call = _CALL.match(text, index)
        if call:
            references.add(call[3])
            pieces.append(call[1] + call[2] + mapping.get(call[3], call[3]) + call[4])
            index = call.end()
        elif text[index] == "'":
            end = _quoted_end(text, index)
            pieces.append(text[index:end])
            index = end
        else:
            pieces.append(text[index])
            index += 1
    return ''.join(pieces), references


def expression_parts(text, mapping=None):
    """Return rewritten WDL and its actual references; literal text is unchanged."""
    mapping = mapping or {}
    if text.startswith('@') and not text.startswith(('@@', '@{')):
        return _wdl_segment(text, mapping)
    pieces, references, index = [], set(), 0
    while index < len(text):
        if text.startswith('@@', index):
            pieces.append('@@')
            index += 2
        elif text.startswith('@{', index):
            end, depth = index + 2, 1
            while end < len(text):
                if text[end] == "'":
                    end = _quoted_end(text, end)
                    continue
                if text[end] == '{':
                    depth += 1
                if text[end] == '}':
                    depth -= 1
                    if depth == 0:
                        break
                end += 1
            if depth:
                raise ValueError('Unterminated WDL interpolation')
            rewritten, found = _wdl_segment(text[index + 2:end], mapping)
            pieces.append('@{' + rewritten + '}')
            references.update(found)
            index = end + 1
        else:
            pieces.append(text[index])
            index += 1
    return ''.join(pieces), references


def _groups(action):
    if isinstance(action.get('actions'), dict):
        yield action['actions']
    if isinstance(action.get('else', {}).get('actions'), dict):
        yield action['else']['actions']
    for branch in action.get('cases', {}).values():
        yield branch.get('actions', {})
    if isinstance(action.get('default', {}).get('actions'), dict):
        yield action['default']['actions']


def _flatten(group):
    result = {}
    def visit(siblings):
        for name, action in siblings.items():
            if name in result:
                raise ValueError('Ambiguous native action name: ' + name)
            result[name] = action
            for children in _groups(action):
                visit(children)
    visit(group)
    return result


def _values(value, mapping, references):
    if isinstance(value, str):
        rewritten, found = expression_parts(value, mapping)
        references.update(found)
        return rewritten
    if isinstance(value, list):
        return [_values(item, mapping, references) for item in value]
    if isinstance(value, dict):
        return {key: _values(item, mapping, references) for key, item in value.items()}
    return copy.deepcopy(value)


def namespace_actions(group, prefix='NextReview_', literal_inputs=LITERAL_INPUTS):
    """Namespace one emitted component; protected data and input objects survive."""
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', prefix):
        raise ValueError('Safe explicit action namespace required')
    mapping = {name: prefix + name for name in _flatten(group)}
    literal_inputs = set(literal_inputs)
    def rename(siblings):
        result = {}
        for name, action in siblings.items():
            out = {}
            for key, value in action.items():
                if key == 'actions':
                    out[key] = rename(value)
                elif key == 'else':
                    out[key] = copy.deepcopy(value)
                    if 'actions' in value:
                        out[key]['actions'] = rename(value['actions'])
                elif key == 'cases':
                    out[key] = {label: {**copy.deepcopy(branch),
                                       'actions': rename(branch.get('actions', {}))}
                                for label, branch in value.items()}
                elif key == 'default':
                    out[key] = {**copy.deepcopy(value), 'actions': rename(value.get('actions', {}))}
                elif key == 'runAfter':
                    out[key] = {mapping.get(parent, parent): copy.deepcopy(statuses)
                                for parent, statuses in value.items()}
                elif key == 'inputs' and name in literal_inputs:
                    # Do not even lex a protected record via its ancestor action.
                    out[key] = copy.deepcopy(value)
                else:
                    out[key] = _values(value, mapping, set())
            result[mapping[name]] = out
        return result
    return rename(group)


def action_references(group, literal_inputs=None):
    if literal_inputs is None:
        literal_inputs = LITERAL_INPUTS | {'NextReview_' + name for name in LITERAL_INPUTS}
    references, literal_inputs = set(), set(literal_inputs)
    for name, action in _flatten(group).items():
        for key, value in action.items():
            if key in ('actions', 'else', 'cases', 'default', 'runAfter'):
                continue
            if key == 'inputs' and name in literal_inputs:
                continue
            _values(value, {}, references)
    return references


def _literal(value):
    return "'" + value.replace("'", "''") + "'"


def _all(*parts):
    return '@and(' + ','.join(part[1:] if part.startswith('@') else part for part in parts) + ')'


def _field(key):
    return "trim(coalesce(triggerBody()?['" + key + "'],''))"


def _ascii_checks(value, dot=False):
    # URI equality excludes non-ASCII, whitespace, slash and percent escapes;
    # these are the remaining URI-safe punctuation outside the producer alphabet.
    excluded = ['!', '~', '*', '(', ')', "'"] + ([] if dot else ['.'])
    return ['equals(encodeUriComponent(' + value + '),' + value + ')'] + [
        'not(contains(' + value + ',' + _literal(char) + '))' for char in excluded]


def next_input_expression():
    """Supported native WDL checks, never a simulator-only regular expression."""
    checks = ["equals(" + _field('text_5') + ",'Create next review')"]
    for key, prefix in [('text', 'LC02-OP-'), ('text_1', 'OCC-')]:
        value = _field(key)
        checks += ['startsWith(' + value + ',' + _literal(prefix) + ')',
                   'greater(length(' + value + '),' + str(len(prefix)) + ')',
                   'lessOrEquals(length(' + value + '),' + str(len(prefix) + 50) + ')']
        checks += _ascii_checks(value)
    for key, maximum in [('text_2', 1000), ('text_3', 1000), ('text_4', 200)]:
        value = _field(key)
        checks += ["startsWith(" + value + ",'FICTIONAL')",
                   'lessOrEquals(length(' + value + '),' + str(maximum) + ')']
    # Match the closing component's request-reference syntax, not a Case9 ID.
    reference = _field('text_6')
    checks += ['greater(length(' + reference + '),0)',
               'lessOrEquals(length(' + reference + '),80)'] + _ascii_checks(reference, dot=True)
    return _all(*checks)


def _failed(code, message):
    return {'type': 'Terminate', 'inputs': {'runStatus': 'Failed',
            'runError': {'code': code, 'message': message}}, 'runAfter': {}}


def case_work_identity_digest(case_work):
    identity = {'flowName': case_work['name'],
                'environmentName': case_work['properties']['environment']['name'],
                'definition': case_work['properties']['definition']}
    return hashlib.sha256(json.dumps(identity, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def rebind_case_work_handoff(candidate, previous, current, approved_definition_sha256):
    """Refresh only a locator fingerprint after an owned consumer deployment.

    Preserve general next-review receipt routing and all creation/recovery guards;
    never rebuild those later adaptations from the initial entry template.
    """
    definition = candidate['properties']['definition']
    actual = hashlib.sha256(json.dumps(definition, sort_keys=True,
                                      separators=(',', ':')).encode()).hexdigest()
    if actual != approved_definition_sha256:
        raise ValueError('Exact reviewed current producer definition required')
    if (previous['name'] != current['name']
            or previous['properties']['environment']['name'] != current['properties']['environment']['name']
            or previous['properties'].get('connectionReferences') != current['properties'].get('connectionReferences')):
        raise ValueError('Retain the same existing consumer identity, environment and connections')
    nodes = _flatten(definition['actions'])
    existing = nodes['Operator_case_work_handoff']['inputs']
    if existing.get('entrypointSHA256') != case_work_identity_digest(previous):
        raise ValueError('Previous native consumer does not match retained locator fingerprint')
    base = copy.deepcopy(candidate)
    actions = base['properties']['definition']['actions']
    if set(actions) != {'Validate_operator_input', 'NextReview_Entry',
                        'Operator_handoff_receipt', 'Operator_handoff_ready'}:
        raise ValueError('Reviewed installed operator-entry and handoff shape required')
    actions.pop('Operator_handoff_receipt')
    actions.pop('Operator_handoff_ready')
    regenerated = with_case_work_handoff(base, current, case_work_identity_digest(current))
    fresh = _flatten(regenerated['properties']['definition']['actions'])['Operator_case_work_handoff']['inputs']
    old_fields, new_fields = copy.deepcopy(existing), copy.deepcopy(fresh)
    old_fields.pop('entrypointSHA256'); new_fields.pop('entrypointSHA256')
    if old_fields != new_fields:
        raise ValueError('Consumer locator contract changed beyond its inspected fingerprint')
    out = copy.deepcopy(candidate)
    out['properties']['state'] = 'Stopped'
    _flatten(out['properties']['definition']['actions'])['Operator_case_work_handoff']['inputs']['entrypointSHA256'] = fresh['entrypointSHA256']
    return out


def with_case_work_handoff(candidate, case_work, entrypoint_sha256):
    """Add a locator-only handoff to an inspected existing manual case-work form.

    Pure composition, never invocation or proof of deployment/access. The target
    identity/definition digest and form/context shape prevent routing to a changed
    or unrelated entrypoint. The consumer must resolve the case and recheck all
    authoritative evidence itself; no receipt token is used as permission.
    """
    target = case_work['properties']['definition']
    digest = case_work_identity_digest(case_work)
    if digest != entrypoint_sha256:
        raise ValueError('Case-work identity or definition changed since inspection')
    flow = str(UUID(case_work['name']))
    environment = case_work['properties']['environment']['name']
    if not re.fullmatch(r'(?:Default-)?[0-9a-fA-F-]{36}', environment):
        raise ValueError('Observed native environment identity required')
    UUID(environment.removeprefix('Default-'))
    trigger = target['triggers']['manual']
    schema = trigger['inputs']['schema']
    if (trigger.get('type') != 'Request' or trigger.get('kind') != 'Button'
            or set(schema['properties']) != {'text', 'text_6'}
            or set(schema['required']) != {'text', 'text_6'}
            or any(schema['properties'][key].get('type') != 'string'
                   for key in ('text', 'text_6'))
            or schema['properties']['text'].get('title') != 'Operation'
            or schema['properties']['text_6'].get('title') != 'Case reference'):
        raise ValueError('Inspected two-field manual case-work entry required')
    nodes = _flatten(target['actions'])
    context = nodes['Selected_case_context']['inputs']
    if (context.get('contextOrigin') != 'manual_case_reference_lookup'
            or context.get('limits', {}).get('selectedRowProvenanceClaimed') is not False
            or "'Check context'" not in nodes['Validate_case_operation']['expression']
            or 'Verify_case_reference_identity' not in nodes):
        raise ValueError('Existing server-resolved Check context route required')
    out = copy.deepcopy(candidate)
    actions = out['properties']['definition']['actions']
    if set(actions) != {'Validate_operator_input', 'NextReview_Entry'}:
        raise ValueError('Unmodified operator-entry composition required')
    producer = _flatten(actions)
    request = producer['Request']['inputs']
    source_scope = context['scope']
    from build_multisource_case_context import _check_context_shape
    try:
        eligible_profiles = _check_context_shape(target)
    except (KeyError, TypeError) as error:
        raise ValueError('Incomplete eligible-source consumer contract') from error
    scope_keys = ('DocumentUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256')
    eligible_scopes = [{key: profile['sha256' if key == 'DocumentSHA256' else key]
                        for key in scope_keys} for profile in eligible_profiles] if eligible_profiles else None
    if ((eligible_scopes is not None and {key:request[key] for key in scope_keys} not in eligible_scopes)
            or (eligible_scopes is None and (context['sourcePins']['DocumentUID'] != request['DocumentUID']
                or any(source_scope[key] != request[key] for key in
                       ('DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256'))))):
        raise ValueError('Case-work source profile does not match initiation')
    create = producer['Create_case']['inputs']['parameters']
    read = nodes['Read_selected_case']['inputs']['parameters']
    lookup = nodes['Find_case_reference']['inputs']['parameters']
    collection = create['parameters/uri'].replace("'", "''")
    if (create['dataset'] != read['dataset'] or read['dataset'] != lookup['dataset']
            or read['parameters/method'] != 'GET' or lookup['parameters/method'] != 'GET'
            or not read['parameters/uri'].startswith("@concat('" + collection + "('")
            or not lookup['parameters/uri'].startswith("@concat('" + collection + '?$filter=CaseUID eq ')):
        raise ValueError('Case-work lookup must target the same case collection')
    next_name = 'NextOccurrence_Native_initiation_receipt'
    next_receipt = "outputs('" + next_name + "')" if next_name in producer else "json('null')"
    initial = "or(equals(" + _field('text_5') + ",''),equals(" + _field('text_5') + ",'Initiate review'))"
    actions['Operator_handoff_receipt'] = {
        'type': 'Compose', 'inputs': "@if(" + initial + ",outputs('Native_initiation_receipt')," + next_receipt + ')',
        'runAfter': {'NextReview_Entry': ['Succeeded']}}
    receipt = "outputs('Operator_handoff_receipt')"
    valid = ["equals(" + receipt + "?['realPolicyEffects'],false)",
             "equals(" + receipt + "?['ownershipAccepted'],false)",
             "equals(" + receipt + "?['CaseUID'],concat('LC-FICTIONAL-OP-'," + _field('text_1') + '))',
             "equals(" + receipt + "?['requestReference']," + _field('text') + ')',
             "equals(" + receipt + "?['occurrenceReference']," + _field('text_1') + ')',
             "greater(int(coalesce(" + receipt + "?['caseItemId'],0)),0)",
             "if(" + initial + ",true,and(equals(" + receipt + "?['qualified'],true),equals(" + receipt + "?['reconcileBeforeRetry'],false)))"]
    source_checks = ["equals(" + receipt + "?['retainedReceipt']?['request']?['" + key + "']," + _literal(request[key]) + ')'
                     for key in ('DocumentUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256')]
    if eligible_scopes is None:
        supported = 'and(' + ','.join(source_checks) + ')'
    else:
        supported = 'or(' + ','.join('and(' + ','.join(
            "equals(" + receipt + "?['retainedReceipt']?['request']?['" + key + "']," + _literal(scope[key]) + ')'
            for key in scope_keys) + ')' for scope in eligible_scopes) + ')'
    valid.append('if(' + initial + ',true,' + supported + ')')
    actions['Operator_handoff_ready'] = {
        'type': 'If', 'expression': '@and(' + ','.join(valid) + ')',
        'runAfter': {'Operator_handoff_receipt': ['Succeeded']},
        'actions': {'Operator_case_work_handoff': {
            'type': 'Compose', 'runAfter': {}, 'inputs': {
                'handoffReady': True, 'locatorOnly': True,
                'entryUrl': 'https://make.powerautomate.com/environments/' + environment + '/flows/' + flow + '/details',
                'entrypointSHA256': digest,
                'formValues': {'text': 'Check context', 'text_6': '@' + receipt + "?['CaseUID']"},
                'requestReference': '@' + receipt + "?['requestReference']",
                'occurrenceReference': '@' + receipt + "?['occurrenceReference']",
                'instruction': 'Open the existing case-work form and enter these two values. Inspect its freshly resolved case and evidence before choosing any later action.',
                'flowInvoked': False, 'writeCount': 0, 'ownershipAccepted': False,
                'readinessGranted': False, 'approvalGranted': False,
                'ordinaryUserAccessQualified': False, 'realPolicyEffects': False}}},
        'else': {'actions': {'Operator_handoff_held': {
            'type': 'Compose', 'runAfter': {}, 'inputs': {
                'handoffReady': False, 'writeCount': 0,
                'reason': 'No matching completed initiation receipt. Retain all outputs and reconcile before continuing; do not resubmit or invent another request.'}}}}}
    if len(actions['Operator_handoff_ready']['expression']) > 8192:
        raise ValueError('Operator handoff exceeds native expression limit')
    audit_actions(out['properties']['definition'])
    unresolved = action_references(actions) - _flatten(actions).keys()
    if unresolved:
        raise ValueError('Unresolved operator handoff references: ' + ','.join(sorted(unresolved)))
    return out


def build(legacy, binding=None):
    """Compose a stopped local operator candidate with the retained legacy path.

    Complete reviewed bindings enable the emitted native validation/writer code;
    actual deployment and runtime qualification remain separate. Arbitrary action
    graphs and caller-supplied qualification flags are rejected.
    """
    resolver = None
    if binding not in (None, {}):
        from build_native_completed_review import build_actions
        try:
            resolver = build_actions(legacy, binding)
        except ValueError as error:
            raise ValueError('General completed-review resolver binding is not qualified or integrated: ' + str(error)) from error
    props = copy.deepcopy(legacy['properties'])
    definition = props['definition']
    if set(definition['actions']) != {'Validate_operator_input'}:
        raise ValueError('Use the retained uncomposed initiation definition')
    if set(definition['triggers']) != {'manual'}:
        raise ValueError('Existing manual initiation trigger required')
    trigger = definition['triggers']['manual']
    schema = trigger['inputs']['schema']
    if set(schema['properties']) != set(LEGACY_FIELDS) or schema['required'] != list(LEGACY_FIELDS):
        raise ValueError('Exact existing five-field entry required')
    if trigger.get('runtimeConfiguration', {}).get('concurrency', {}).get('runs') != 1:
        raise ValueError('Retain existing single-run concurrency')
    original = definition['actions']['Validate_operator_input']
    if original['type'] != 'If' or not isinstance(original.get('expression'), str):
        raise ValueError('Existing validated initiation route required')
    legacy_mode = "@and(or(equals(" + _field('text_5') + ",''),equals(" + _field('text_5') + ",'Initiate review')),empty(" + _field('text_6') + '))'
    original['expression'] = _all(original['expression'], legacy_mode)
    original['else'] = {'actions': {'Route_legacy_input_refusal': {
        'type': 'If', 'expression': legacy_mode,
        'actions': original['else']['actions'],
        'else': {'actions': {'Skip_initial_initiation': {
            'type': 'Compose', 'inputs': {'writeCount': 0, 'reason': 'Original initiation not selected'}, 'runAfter': {}}}},
        'runAfter': {}}}}
    definition['actions']['NextReview_Entry'] = {
        'type': 'If', 'expression': next_input_expression(),
        'actions': {'NextReview_unavailable': _failed('GeneralCompletedReviewUnavailable',
            'An independently qualified general completed-review control source and resolver are required; no case/source/read/write operation was performed.')},
        'else': {'actions': {'NextReview_input_refusal': {
            'type': 'If', 'expression': '@not(' + legacy_mode[1:] + ')',
            'actions': {'NextReview_invalid': _failed('InvalidNextReviewEntry',
                'Use a supported operation, safe request/occurrence references and completed-review reference; no responsibility is accepted.')},
            'else': {'actions': {'NextReview_skip': {'type': 'Compose', 'inputs': {'writeCount': 0}, 'runAfter': {}}}},
            'runAfter': {}}}},
        'runAfter': {'Validate_operator_input': ['Succeeded']}}
    if resolver is not None:
        definition['actions']['NextReview_Entry']['actions'] = resolver
    schema['properties'].update(copy.deepcopy(OPTIONAL_FIELDS))
    audit_actions(definition)
    unresolved = action_references(definition['actions']) - _flatten(definition['actions']).keys()
    if unresolved:
        raise ValueError('Unresolved WDL action references: ' + ','.join(sorted(unresolved)))
    return {'properties': {'displayName': props['displayName'], 'state': 'Stopped',
                           'definition': definition, 'connectionReferences': props['connectionReferences']}}

"""Bind exact fictional test inputs to the existing native serial test harness.

Offline authoring only. Reuses the recovery control-file pattern when UI entry is
unavailable. Original validation/effect actions remain intact; this is not normal
operator-entry, user-access or production qualification.
"""
import copy
import hashlib
import json
import re
from urllib.parse import urlsplit
from build_selected_event_routes import audit_actions


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def build(source, stopped_target, binding):
    props = source['properties']; target = stopped_target['properties']
    definition = props['definition']; expected = binding.get('expectedInput')
    fixture = binding.get('fixtureCaseUID', '')
    pin = binding.get('controlFile', {})
    trigger = definition.get('triggers', {}).get('manual', {})
    target_trigger = target['definition'].get('triggers', {}).get('manual', {})
    if (binding.get('qualificationOnly') is not True
            or binding.get('approvedSourceDefinitionSHA256') != digest(definition)
            or binding.get('approvedStoppedTargetDefinitionSHA256') != digest(target['definition'])
            or target.get('state') != 'Stopped' or target.get('isManaged') is not False
            or props['connectionReferences'] != target['connectionReferences']
            or set(props['connectionReferences']) != {'shared_sharepointonline'}
            or set(definition.get('triggers', {})) != {'manual'}
            or trigger.get('type') != 'Request' or trigger.get('kind') != 'Button'
            or trigger.get('runtimeConfiguration', {}).get('concurrency', {}).get('runs') != 1
            or set(target['definition'].get('triggers', {})) != {'manual'}
            or target_trigger.get('type') != 'Request' or target_trigger.get('kind') != 'Button'
            or target_trigger.get('runtimeConfiguration', {}).get('concurrency', {}).get('runs') != 1
            or not re.fullmatch(r'LC-FICTIONAL-OP-[A-Za-z0-9_-]{1,100}', fixture)
            or not isinstance(expected, dict) or not expected
            or any(not re.fullmatch(r'text(?:_[1-8])?', k) or not isinstance(v, str)
                   for k, v in expected.items())
            or (expected.get('text_6') != fixture
                and not (expected.get('text_5') == 'Initiate review'
                         and 'LC-FICTIONAL-OP-' + expected.get('text_1', '') == fixture))
            or not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', str(pin.get('UniqueId', '')))
            or not isinstance(pin.get('ETag'), str) or not pin['ETag'].strip() or pin['ETag'] == '*'
            or not isinstance(binding.get('siteUrl'), str)
            or not binding['siteUrl'].startswith('https://')
            or '?' in binding['siteUrl'] or '#' in binding['siteUrl']):
        raise ValueError('Exact fictional inputs, control pin and observed stopped SharePoint-only target required')
    site_parts = urlsplit(binding['siteUrl'])
    if not site_parts.netloc or site_parts.username or site_parts.password:
        raise ValueError('Exact qualified site required')
    schema = trigger.get('inputs', {}).get('schema', {})
    if not set(schema.get('required', [])) <= set(expected):
        raise ValueError('Controlled input must satisfy original required fields')
    actions = definition['actions']
    def datasets(value):
        if isinstance(value, dict):
            if value.get('type') == 'OpenApiConnection':
                yield value.get('inputs', {}).get('parameters', {}).get('dataset')
            for child in value.values():yield from datasets(child)
        elif isinstance(value, list):
            for child in value:yield from datasets(child)
    if any(value != binding['siteUrl'] for value in datasets(actions)):
        raise ValueError('Control file must use the original qualified site')
    if any(name.startswith('Qualification_') for name in actions):
        raise ValueError('Do not adapt an already adapted definition')
    serialized = json.dumps(actions)
    if 'triggerBody()' not in serialized or any(v in serialized for v in ('triggerOutputs(', 'trigger()[')):
        raise ValueError('Only the reviewed triggerBody input contract is supported')
    def rewrite(value):
        if isinstance(value, str):return value.replace('triggerBody()', "outputs('Qualification_input')")
        if isinstance(value, list):return [rewrite(x) for x in value]
        if isinstance(value, dict):return {k: rewrite(v) for k, v in value.items()}
        return value
    original = rewrite(copy.deepcopy(actions))
    roots = [name for name, action in original.items() if not action.get('runAfter')]
    if not roots:raise ValueError('Original action roots required')
    for name in roots:original[name]['runAfter'] = {'Qualification_input_guard': ['Succeeded']}
    site = binding['siteUrl']; fileuri = "_api/web/GetFileById('" + pin['UniqueId'] + "')"
    def read(uri, after=None):
        return {'type': 'OpenApiConnection', 'inputs': {'host': {
            'apiId': '/providers/Microsoft.PowerApps/apis/shared_sharepointonline',
            'connectionName': 'shared_sharepointonline', 'operationId': 'HttpRequest'},
            'parameters': {'dataset': site, 'parameters/method': 'GET', 'parameters/uri': uri,
                           'parameters/headers': {'Accept': 'application/json;odata=minimalmetadata'}}},
            'runAfter': {after: ['Succeeded']} if after else {}}
    prefix = {'Qualification_control_before': read(fileuri + '?$select=UniqueId,ETag')}
    prefix['Qualification_control_content'] = read(fileuri + '/$value', 'Qualification_control_before')
    prefix['Qualification_input'] = {'type': 'Compose', 'inputs':
        "@if(contains(body('Qualification_control_content'),'$content'),json(base64ToString(body('Qualification_control_content')?['$content'])),json(string(body('Qualification_control_content'))))",
        'runAfter': {'Qualification_control_content': ['Succeeded']}}
    prefix['Qualification_control_after'] = read(fileuri + '?$select=UniqueId,ETag', 'Qualification_input')
    quote = lambda v: "'" + v.replace("'", "''") + "'"
    checks = ["equals(body('Qualification_control_before')?['" + k + "']," + quote(pin[k]) + ')'
              for k in ('UniqueId', 'ETag')]
    checks += ["equals(body('Qualification_control_before')?['" + k + "'],body('Qualification_control_after')?['" + k + "'])"
               for k in ('UniqueId', 'ETag')]
    checks += ["equals(outputs('Qualification_input'),json(" + quote(json.dumps(expected, separators=(',', ':'))) + '))']
    prefix['Qualification_input_guard'] = {'type': 'If', 'expression': '@and(' + ','.join(checks) + ')',
        'runAfter': {'Qualification_control_after': ['Succeeded']}, 'actions': {},
        'else': {'actions': {'Qualification_refuse_changed_input': {'type': 'Terminate',
            'inputs': {'runStatus': 'Failed', 'runError': {'code': 'QualificationInputChanged',
                'message': 'Reviewed fictional input file identity, token or content changed; no original action permitted.'}},
            'runAfter': {}}}}}
    out = {'properties': {'displayName': 'PPG Lifecycle | FICTIONAL controlled qualification',
        'state': 'Stopped', 'definition': copy.deepcopy(definition),
        'connectionReferences': copy.deepcopy(target['connectionReferences'])}}
    out['properties']['definition']['triggers']['manual']['inputs'] = {
        'schema': {'type': 'object', 'properties': {}, 'required': []}}
    out['properties']['definition']['actions'] = {**prefix, **original}
    geometry = audit_actions(out['properties']['definition'])
    if geometry['actionCount'] > 500 or geometry['maximumActionDepth'] > 8:
        raise ValueError('Controlled fixture exceeds native geometry limits')
    return out

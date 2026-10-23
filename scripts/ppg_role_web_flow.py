"""Build a bounded on-demand role projection; bindings remain private."""
import copy


def build(bindings):
    site = bindings['site']
    refs = copy.deepcopy(bindings['connectionReferences'])
    if set(refs) != {'shared_sharepointonline', 'shared_excelonlinebusiness'}:
        raise ValueError('Only the qualified Standard connector pair is allowed')
    if any(r.get('source') != 'Embedded' for r in refs.values()):
        raise ValueError('Embedded existing connections required')
    roles = bindings['registers']
    if set(roles) != {'roles','assignments','appointments','handovers'}:
        raise ValueError('Complete four-register bindings required')
    roles = {key: roles[key] for key in ('roles', 'assignments', 'appointments', 'handovers')}
    actions = {}
    def http(name, uri, after=None):
        action = dict(type='OpenApiConnection', inputs=dict(host=dict(apiId='/providers/Microsoft.PowerApps/apis/shared_sharepointonline',connectionName='shared_sharepointonline',operationId='HttpRequest'),parameters={'dataset':site,'parameters/method':'GET','parameters/uri':uri,'parameters/headers':{'Accept':'application/json;odata=nometadata'}}),runAfter={after:['Succeeded']} if after else {})
        actions[name] = action
        return name
    previous = None
    for key in roles:
        previous = http('Read_'+key,"_api/web/lists(guid'"+roles[key]+"')/items?$top=5000",previous)
    actions['Projection_request'] = dict(type='Compose',runAfter={previous:['Succeeded']},inputs=dict(kind='ppg-role-projection-v1',asOf="@triggerBody()?['asOf']",native={key:"@body('Read_"+key+"')" for key in roles},scriptSHA256=bindings['scriptSHA256'],roleContractSHA256=bindings['roleContractSHA256']))
    parameters = copy.deepcopy(bindings['scriptParameters'])
    if set(parameters) != {'source','drive','file','scriptSource','scriptDrive','scriptId'}:
        raise ValueError('Exact qualified workbook/script locations required')
    parameters['ScriptParameters/requestJson'] = "@string(outputs('Projection_request'))"
    actions['Run_role_projection'] = dict(type='OpenApiConnection',runAfter={'Projection_request':['Succeeded']},inputs=dict(host=dict(apiId='/providers/Microsoft.PowerApps/apis/shared_excelonlinebusiness',connectionName='shared_excelonlinebusiness',operationId='RunScriptProdV2'),parameters=parameters))
    actions['Parsed_projection'] = dict(type='Compose',runAfter={'Run_role_projection':['Succeeded']},inputs="@json(body('Run_role_projection')?['result'])")
    previous = 'Parsed_projection'
    for key in roles:
        previous = http('Recheck_'+key,"_api/web/lists(guid'"+roles[key]+"')/items?$top=5000",previous)
    condition = "@and("+','.join("equals(body('Read_"+key+"'),body('Recheck_"+key+"'))" for key in roles)+')'
    actions['Source_snapshot_stable'] = dict(type='If',runAfter={previous:['Succeeded']},expression=condition,
        actions={'Report_projection':dict(type='Compose',runAfter={},inputs="@outputs('Parsed_projection')")},
        **{'else':{'actions':{'Hold_changed_source':dict(type='Terminate',runAfter={},inputs={'runStatus':'Failed','runError':{'code':'RoleSourceChanged','message':'Role inputs changed during projection; no source or assignment is modified.'}})}}})
    definition={'$schema':'https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#','contentVersion':'1.0.0.0',
        'parameters':{'$authentication':{'type':'SecureObject','defaultValue':{}},'$connections':{'type':'Object','defaultValue':{}}},
        'triggers':{'manual':{'type':'Request','kind':'Button','inputs':{'schema':{'type':'object','properties':{'asOf':{'type':'string','title':'As-of date (YYYY-MM-DD)','description':'Explicit Gregorian date; historical appointments and decisions are preserved.','x-ms-dynamically-added':True,'x-ms-content-hint':'TEXT'}},'required':['asOf']}}}},
        'actions':actions,'outputs':{}}
    return {'properties':{'displayName':'PPG | On-demand role responsibility projection','state':'Stopped','definition':definition,'connectionReferences':refs}}


def script_package(source):
    """Describe the connector response envelope, not just main's return value."""
    import json
    return {
        'version': '0.3.0',
        'description': 'Read-only dated responsibility projection',
        'noCodeMetadata': '',
        'apiInfo': json.dumps({'variant': 'synchronous', 'variantVersion': 2}),
        'body': source,
        'parameterInfo': json.dumps({
            'version': 1,
            'originalParameterOrder': [{'name': 'requestJson', 'index': 0}],
            'parameterSchema': {'type': 'object', 'properties': {
                'requestJson': {'type': 'string'}}, 'required': ['requestJson']},
            'returnSchema': {'type': 'object', 'properties': {
                'result': {'type': 'string'},
                'logs': {'type': 'array', 'items': {'type': 'string'}}}},
            'signature': {'comment': 'Bounded role responsibility projection',
                          'parameters': [{'name': 'workbook', 'comment': ''},
                                         {'name': 'requestJson', 'comment': ''}]}
        })
    }


SNAPSHOT_FIELDS = ('Title', 'SnapshotKey', 'RunKey', 'AsOfDate', 'SourceSHA256',
                   'DocumentUID', 'AssignmentKey', 'RoleKey', 'ResponsibilityType',
                   'HolderKey', 'ResolutionState', 'Projection', 'SourceManifest')


def with_persistence(candidate, bindings):
    """Append/reuse exact snapshots; never update a pre-existing business row."""
    import re
    result = copy.deepcopy(candidate)
    target = bindings['snapshotList']
    if not re.fullmatch(r'[0-9a-fA-F-]{36}', target):
        raise ValueError('Verified snapshot List GUID required')
    actions = result['properties']['definition']['actions']
    guard = actions['Source_snapshot_stable']['actions']
    root = "_api/web/lists(guid'" + target + "')/items"

    def http(uri, method='GET', body=None, after=None):
        params = {'dataset': bindings['site'], 'parameters/method': method,
                  'parameters/uri': uri,
                  'parameters/headers': {'Accept': 'application/json;odata=nometadata'}}
        if body is not None:
            params['parameters/headers']['Content-Type'] = 'application/json;odata=nometadata'
            params['parameters/body'] = body
        value = {'type': 'OpenApiConnection', 'inputs': {
            'host': {'apiId': '/providers/Microsoft.PowerApps/apis/shared_sharepointonline',
                     'connectionName': 'shared_sharepointonline', 'operationId': 'HttpRequest'},
            'parameters': params}, 'runAfter': {after: ['Succeeded']} if after else {}}
        if method != 'GET':
            value['inputs']['retryPolicy'] = {'type': 'none'}
        return value

    def lookup(loop):
        return "@concat('" + root.replace("'", "''") + "?$top=2&$filter=SnapshotKey eq ''', items('" + loop + "')?['SnapshotKey'], '''')"

    def exact(action, loop):
        return '@and(' + ','.join(
            "equals(first(body('" + action + "')?['value'])?['" + field + "'],items('" + loop + "')?['" + field + "'])"
            for field in SNAPSHOT_FIELDS) + ')'

    def refuse(code):
        # A failed assertion inside a loop prevents completion. Terminate is not
        # supported inside Foreach; the named action records the failure reason.
        return {'type': 'Compose', 'inputs': '@div(1,0)', 'runAfter': {},
                'description': code}

    def validate(action, loop):
        return {'type': 'If', 'runAfter': {action: ['Succeeded']},
                'expression': "@and(equals(length(body('" + action + "')?['value']),1)," + exact(action, loop)[1:] + ')',
                'actions': {'Exact_' + loop: {'type': 'Compose', 'inputs': 'Exact existing snapshot', 'runAfter': {}}},
                'else': {'actions': {'Snapshot_conflict_' + loop: refuse('Snapshot missing, duplicate or edited; preserve existing row')}}}

    preflight = {'Lookup_preflight': http(lookup('Preflight_snapshots'))}
    preflight['Existing_or_absent'] = {'type': 'If', 'runAfter': {'Lookup_preflight': ['Succeeded']},
        'expression': "@equals(length(body('Lookup_preflight')?['value']),0)",
        'actions': {}, 'else': {'actions': {'Validate_existing': validate('Lookup_preflight', 'Preflight_snapshots')}}}
    # Nested actions depend only on siblings, not the parent's external lookup.
    preflight['Existing_or_absent']['else']['actions']['Validate_existing']['runAfter'] = {}
    guard['Preflight_snapshots'] = {'type': 'Foreach', 'foreach': "@outputs('Parsed_projection')?['records']",
                                  'runAfter': {}, 'runtimeConfiguration': {'concurrency': {'repetitions': 1}}, 'actions': preflight}
    save = {'Lookup_snapshot': http(lookup('Persist_snapshots'))}
    save['Create_if_absent'] = {'type': 'If', 'runAfter': {'Lookup_snapshot': ['Succeeded']},
        'expression': "@equals(length(body('Lookup_snapshot')?['value']),0)",
        'actions': {'Create_snapshot': http(root, 'POST', "@string(items('Persist_snapshots'))")},
        'else': {'actions': {}}}
    save['Read_saved_snapshot'] = http(lookup('Persist_snapshots'), after='Create_if_absent')
    save['Verify_saved_snapshot'] = validate('Read_saved_snapshot', 'Persist_snapshots')
    guard['Persist_snapshots'] = {'type': 'Foreach', 'foreach': "@outputs('Parsed_projection')?['records']",
                                'runAfter': {'Preflight_snapshots': ['Succeeded']},
                                'runtimeConfiguration': {'concurrency': {'repetitions': 1}}, 'actions': save}
    previous = 'Persist_snapshots'
    for key, guid in bindings['registers'].items():
        name = 'Final_read_' + key
        guard[name] = http("_api/web/lists(guid'" + guid + "')/items?$top=5000", after=previous)
        previous = name
    guard.pop('Report_projection')
    guard['Confirm_completed_snapshot'] = {'type': 'If', 'runAfter': {previous: ['Succeeded']},
        'expression': '@and(' + ','.join("equals(body('Read_" + key + "'),body('Final_read_" + key + "'))" for key in bindings['registers']) + ')',
        'actions': {'Report_projection': {'type': 'Compose', 'runAfter': {}, 'inputs': {
            'state': 'completed_dated_snapshot', 'snapshotCount': "@length(outputs('Parsed_projection')?['records'])",
            'runKey': "@outputs('Parsed_projection')?['manifest']?['runKey']",
            'projection': "@outputs('Parsed_projection')", 'operatorNote': 'Use this run key and expected count; partial failed runs are not completed snapshots.'}}},
        'else': {'actions': {'Source_changed_after_persistence': refuse('Source changed; any partial rows are retained, not a completed snapshot')}}}
    result['properties']['definition']['triggers']['manual']['runtimeConfiguration'] = {'concurrency': {'runs': 1}}
    return explicit_holds(result)


def explicit_holds(candidate):
    """Use supported flags in serial loops and explicit termination outside them."""
    result = copy.deepcopy(candidate)
    actions = result['properties']['definition']['actions']
    actions['Initialise_snapshot_conflict'] = {
        'type': 'InitializeVariable', 'runAfter': {'Parsed_projection': ['Succeeded']},
        'inputs': {'variables': [{'name': 'SnapshotConflict', 'type': 'boolean', 'value': False}]}}
    actions['Recheck_roles']['runAfter'] = {'Initialise_snapshot_conflict': ['Succeeded']}
    guard = actions['Source_snapshot_stable']['actions']

    def flag():
        return {'type': 'SetVariable', 'runAfter': {},
                'inputs': {'name': 'SnapshotConflict', 'value': True}}

    def stop(code, message):
        return {'type': 'Terminate', 'runAfter': {},
                'inputs': {'runStatus': 'Failed', 'runError': {'code': code, 'message': message}}}

    # Replace deliberate expression failures with monotonic flags. Serial loops
    # never reset the flag, so a later exact row cannot hide an earlier conflict.
    for loop, check in [('Preflight_snapshots', 'Validate_existing'),
                        ('Persist_snapshots', 'Verify_saved_snapshot')]:
        inner = guard[loop]['actions']
        validation = (inner['Existing_or_absent']['else']['actions'][check]
                      if loop == 'Preflight_snapshots' else inner[check])
        old_expression = validation['expression']
        action = 'Lookup_preflight' if loop == 'Preflight_snapshots' else 'Read_saved_snapshot'
        # Cardinality check precedes first() evaluation, including empty results.
        validation['expression'] = "@equals(length(body('" + action + "')?['value']),1)"
        validation['actions'] = {'Compare_' + loop: {
            'type': 'If', 'runAfter': {},
            'expression': old_expression,
            'actions': {'Exact_' + loop: {'type': 'Compose', 'inputs': 'Exact snapshot', 'runAfter': {}}},
            'else': {'actions': {'Flag_edited_' + loop: flag()}}}}
        validation['else'] = {'actions': {'Flag_cardinality_' + loop: flag()}}

    save = guard['Persist_snapshots']
    save['actions'] = {'Continue_if_exact': {
        'type': 'If', 'runAfter': {}, 'expression': "@equals(variables('SnapshotConflict'),false)",
        'actions': save['actions'], 'else': {'actions': {}}}}
    confirm = guard['Confirm_completed_snapshot']
    confirm['else']['actions'] = {'Source_changed_after_persistence': stop(
        'RoleSourceChangedAfterSave', 'Role inputs changed after saving; retain partial rows and reconcile this run. No completed snapshot is declared.')}
    # A saved-row conflict is a separate diagnostic from a changed source.
    previous = confirm['runAfter']
    confirm['runAfter'] = {}
    guard['Saved_snapshots_exact'] = {
        'type': 'If', 'runAfter': previous,
        'expression': "@equals(variables('SnapshotConflict'),false)",
        'actions': {'Confirm_completed_snapshot': confirm},
        'else': {'actions': {'Hold_saved_snapshot_conflict': stop(
            'RoleSnapshotChangedDuringSave', 'A saved snapshot is missing, duplicated or edited; preserve rows and reconcile the exact run before retry.')}}}
    del guard['Confirm_completed_snapshot']
    save['runAfter'] = {}
    downstream = {k: guard.pop(k) for k in list(guard) if k != 'Preflight_snapshots'}
    guard['Preflight_snapshots_exact'] = {
        'type': 'If', 'runAfter': {'Preflight_snapshots': ['Succeeded']},
        'expression': "@equals(variables('SnapshotConflict'),false)",
        'actions': downstream,
        'else': {'actions': {'Hold_existing_snapshot_conflict': stop(
            'RoleSnapshotConflict', 'An existing snapshot differs from the expected record. No snapshots were created. Preserve the existing wording and refer the conflict to the operator.')}}}
    return result

"""Bounded source-only updates for the existing catalogue flow; no native I/O."""
import copy
import re


def build(existing):
    """Batch existing identities; retain the guarded serial path for new identities.

    Every operation uses its captured ETag, no mutation retries, and only the
    existing source-field whitelist. The original whole-catalogue readback and
    commit-last checkpoint remain authoritative after all batches succeed.
    """
    flow = copy.deepcopy(existing)
    definition = flow['properties']['definition']
    reconcile = definition['actions']['Daily_due']['actions']['Reconcile']['actions']
    guard = reconcile['Guard_input']['actions']
    original = guard['Write_changes']
    row = original['actions']['Serial_check']['actions']['Row_work']['actions']
    write = row['Compare_source']['else']['actions']
    patch = write['Write_source']['else']['actions']['Patch_source']
    params = patch['inputs']['parameters']
    match = re.search(r"lists\(guid''([a-fA-F0-9-]{36})''\)", params['parameters/uri'])
    if not match:
        raise ValueError('catalogue_list_binding_missing')
    site, list_id = params['dataset'], match.group(1)
    fields = write['Whitelisted_fields']['inputs']
    if not fields or any(not k.startswith(('source', 'rawSource')) for k in fields):
        raise ValueError('source_fields_only')
    def after(name): return {} if name is None else {name: ['Succeeded']}
    def compose(value, prev=None):
        return {'type': 'Compose', 'runAfter': after(prev), 'inputs': value}
    def select(source, value, prev=None):
        return {'type': 'Select', 'runAfter': after(prev), 'inputs': {'from': source, 'select': value}}
    def increment(name, prev):
        return {'type': 'IncrementVariable', 'runAfter': after(prev),
                'inputs': {'name': name, 'value': "@length(outputs('Batch_rows'))"}}
    # JSON serialisation escapes ETags and IDs before building the lookup object.
    a = {'Native_pairs': select("@body('Read_current')?['d']?['results']",
         "@concat('\"',item()?['DocumentUID'],'\":',string(item()))"),
         'Native_map': compose("@json(concat('{',join(body('Native_pairs'),','),'}'))", 'Native_pairs')}
    batch = {'Batch_rows': compose("@take(skip(outputs('Work_operations'),mul(items('Catalogue_batches'),20)),20)"),
             'Batch_boundary': compose("@concat('batch_',guid())", 'Batch_rows')}
    # Reuse the existing explicit whitelist rather than passing arbitrary fields.
    payload = 'json(\'{}\')'
    for key in fields:
        payload = f"setProperty({payload},'{key}',item()?['fields']?['{key}'])"
    crlf = "decodeUriComponent('%0D%0A')"
    pieces = ["'--'", "outputs('Batch_boundary')", crlf,
              "'Content-Type: multipart/mixed; boundary=changeset_'", "item()?['DocumentUID']", crlf, crlf,
              "'--changeset_'", "item()?['DocumentUID']", crlf,
              "'Content-Type: application/http'", crlf, "'Content-Transfer-Encoding: binary'", crlf, crlf,
              "'MERGE " + site + "/_api/web/lists(guid''" + list_id + "'')/items('",
              "string(outputs('Native_map')?[item()?['DocumentUID']]?['Id'])", "') HTTP/1.1'", crlf,
              "'Content-Type: application/json;odata=nometadata'", crlf,
              "'Accept: application/json;odata=nometadata'", crlf, "'If-Match: '",
              "outputs('Native_map')?[item()?['DocumentUID']]?['__metadata']?['etag']", crlf, crlf,
              'string(' + payload + ')', crlf, "'--changeset_'", "item()?['DocumentUID']", "'--'", crlf]
    batch['Batch_parts'] = select("@outputs('Batch_rows')", '@concat(' + ','.join(pieces) + ')', 'Batch_boundary')
    batch['Count_batch_attempts'] = increment('attemptedWrites', 'Batch_parts')
    batch['Pending_batch_receipt'] = compose({
        'runId': "@workflow()?['run']?['name']", 'status': 'running_batch_attempt',
        'attemptedWrites': "@variables('attemptedWrites')", 'writeCount': "@variables('writeCount')",
        'batch': "@items('Catalogue_batches')", 'operations': "@outputs('Batch_rows')",
        'asOfUtc': '@utcNow()'}, 'Count_batch_attempts')
    persist = copy.deepcopy(write['Persist_pending_write'])
    persist['runAfter'] = after('Pending_batch_receipt')
    persist['inputs']['parameters']['parameters/body'] = "@string(outputs('Pending_batch_receipt'))"
    persist['inputs']['retryPolicy'] = {'type': 'none'}
    batch['Persist_batch_attempt'] = persist
    send = copy.deepcopy(patch)
    send['runAfter'] = after('Persist_batch_attempt')
    send['inputs']['retryPolicy'] = {'type': 'none'}
    send['inputs']['parameters'] = {'dataset': site, 'parameters/method': 'POST',
        'parameters/uri': '_api/$batch', 'parameters/headers': {
            'Content-Type': "@concat('multipart/mixed; boundary=',outputs('Batch_boundary'))",
            'Accept': 'application/json'},
        'parameters/body': "@concat(join(body('Batch_parts'),''),'--',outputs('Batch_boundary'),'--',decodeUriComponent('%0D%0A'))"}
    batch['Send_catalogue_batch'] = send
    batch['Batch_response'] = compose("@if(contains(body('Send_catalogue_batch'),'$content'),base64ToString(body('Send_catalogue_batch')?['$content']),string(body('Send_catalogue_batch')))", 'Send_catalogue_batch')
    batch['Batch_statuses'] = select("@skip(split(outputs('Batch_response'),'HTTP/1.1 '),1)",
        "@first(split(item(),decodeUriComponent('%0D%0A')))", 'Batch_response')
    batch['Batch_errors'] = {'type': 'Query', 'runAfter': after('Batch_statuses'), 'inputs': {
        'from': "@body('Batch_statuses')", 'where': "@not(equals(item(),'204 No Content'))"}}
    batch['Require_batch_success'] = {'type': 'If', 'runAfter': after('Batch_errors'),
        'expression': "@and(equals(length(body('Batch_statuses')),length(outputs('Batch_rows'))),empty(body('Batch_errors')))",
        'actions': {}, 'else': {'actions': {'Batch_operation_failed': compose('@div(1,0)')}}}
    batch['Count_batch_writes'] = increment('writeCount', 'Require_batch_success')
    batch['Count_batch_readbacks'] = increment('readbackCount', 'Count_batch_writes')
    batch['Batch_cooldown'] = {'type': 'Wait', 'runAfter': after('Count_batch_readbacks'),
                             'inputs': {'interval': {'count': 10, 'unit': 'Second'}}}
    a['Catalogue_batches'] = {'type': 'Foreach', 'runAfter': after('Native_map'),
        'foreach': "@range(0,div(add(length(outputs('Work_operations')),19),20))",
        'runtimeConfiguration': {'concurrency': {'repetitions': 1}}, 'actions': {
            'Continue_batches': {'type': 'If', 'runAfter': {},
                'expression': "@equals(variables('abortRun'),false)", 'actions': {
                    'Batch_work': {'type': 'Scope', 'runAfter': {}, 'actions': batch},
                    'Abort_batch': {'type': 'SetVariable', 'runAfter': {'Batch_work': ['Failed', 'TimedOut']},
                                    'inputs': {'name': 'abortRun', 'value': True}}},
                'else': {'actions': {}}}}}
    # New-identity authorisation and create behaviour remain on the existing path.
    original['runAfter'] = {}
    guard['Write_changes'] = {'type': 'If', 'runAfter': after('Work_operations'),
        'expression': "@and(empty(body('Unqualified_new_identities')),equals(length(body('Read_current')?['d']?['results']),add(length(outputs('Parse_candidate')?['operations']),length(coalesce(outputs('Parse_candidate')?['acknowledgedMissingUIDs'],json('[]'))))),equals(outputs('Qualification_settings')?['probeSameValueFirst'],false),equals(outputs('Qualification_settings')?['failAfterReadbacks'],0))",
        'actions': a, 'else': {'actions': {}}}
    fast = guard['Write_changes']['expression'][1:]
    original['runAfter'] = after('Write_changes')
    original['expression'] = "@and(not(" + fast + "),greater(length(outputs('Work_operations')),0))"
    guard['Serial_identity_writes'] = original
    definition['contentVersion'] = '1.1.0.0'
    return flow

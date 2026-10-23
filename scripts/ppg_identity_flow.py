"""Extend an exported QW3 definition; no network or deployment side effects.

The success checkpoint becomes the active identity-contract store. The original
ledger remains the immutable bootstrap. This is one commit-last write, avoiding a
split ledger/checkpoint transaction. The same single-concurrency importer creates
only explicitly authorised new UIDs and stamps their package for safe recovery.
"""
from __future__ import annotations
import copy
import json
import re
from pathlib import Path

MARKER = 'sourceIdentityDecisionRef'


def extend_importer(exported: dict) -> dict:
    result = copy.deepcopy(exported)
    definition = result['properties']['definition']
    actions = definition['actions']
    if 'Read_identity_application' in actions:
        raise ValueError('identity_application_extension_already_present')
    triggers = definition['triggers']
    if len(triggers) != 1 or next(iter(triggers.values())).get('runtimeConfiguration', {}).get('concurrency', {}).get('runs') != 1:
        raise ValueError('sole_serial_importer_required')
    daily = actions['Daily_due']['actions']
    acquisition = daily['Acquire_fresh']['actions']
    reconciliation = daily['Reconcile']['actions']
    guard = reconciliation['Guard_input']
    work = guard['actions']
    row = work['Write_changes']['actions']['Serial_check']['actions']['Row_work']['actions']
    compare = row['Compare_source']
    writer = compare['else']['actions']
    native = writer['Patch_source']['inputs']['parameters']
    if native['parameters/headers'].get('X-HTTP-Method') != 'MERGE' or native['parameters/headers'].get('If-Match') != "@first(body('Find_native'))?['__metadata']?['etag']":
        raise ValueError('qualified_conditional_source_writer_required')
    current_uri = reconciliation['Read_current']['inputs']['parameters']['parameters/uri']
    list_match = re.search(r"_api/web/lists\(guid'([a-f0-9-]+)'\)/items", current_uri)
    if not list_match:
        raise ValueError('bound_catalogue_required')
    catalogue = list_match.group(1)
    ledger_read = acquisition['Read_identity_ledger']
    ledger_uri = ledger_read['inputs']['parameters']['parameters/uri']
    if not ledger_uri.endswith("/identity-ledger.json')/$value"):
        raise ValueError('qualified_bootstrap_ledger_required')
    app_read = copy.deepcopy(actions['Read_success_checkpoint'])
    app_read['runAfter'] = {'Parse_success_checkpoint':['Succeeded']}
    app_read['inputs']['parameters']['parameters/uri'] = ledger_uri.replace('identity-ledger.json','identity-application.json')
    actions['Read_identity_application'] = app_read
    parse = copy.deepcopy(actions['Parse_success_checkpoint'])
    parse['runAfter'] = {'Read_identity_application':['Succeeded']}
    parse['inputs'] = parse['inputs'].replace('Read_success_checkpoint','Read_identity_application')
    actions['Parse_identity_application'] = parse
    actions['Daily_due']['runAfter']['Parse_identity_application'] = ['Succeeded']
    application_pending = "and(not(empty(outputs('Parse_identity_application')?['packageHash'])),not(equals(outputs('Parse_identity_application')?['packageHash'],outputs('Parse_success_checkpoint')?['lastIdentityApplicationHash'])))"
    expression = actions['Daily_due']['expression']
    actions['Daily_due']['expression'] = '@or('+expression[1:]+','+application_pending+')'
    # The checkpoint is the authoritative active contract after the first commit.
    params = acquisition['Extract_copy']['inputs']['parameters']
    params['ScriptParameters/identityLedgerJson'] = "@if(empty(outputs('Parse_success_checkpoint')?['identityLedger']),base64ToString(body('Read_identity_ledger')?['$content']),string(outputs('Parse_success_checkpoint')?['identityLedger']))"
    params['ScriptParameters/identityApplicationJson'] = "@if("+application_pending+",string(outputs('Parse_identity_application')),'')"
    retained = copy.deepcopy(acquisition['Save_extraction'])
    retained['runAfter'] = {'Save_records':['Succeeded']}
    retained['inputs']['parameters']['name'] = "@concat('qw3-identity-application-',workflow()?['run']?['name'],'.json')"
    retained['inputs']['parameters']['body'] = "@string(outputs('Parse_identity_application'))"
    acquisition['Save_identity_application'] = retained
    snapshot = copy.deepcopy(retained)
    snapshot['runAfter'] = {'Save_identity_application':['Succeeded']}
    snapshot['inputs']['parameters']['name'] = "@concat('qw3-identity-snapshot-',workflow()?['run']?['name'],'.json')"
    snapshot['inputs']['parameters']['body'] = "@string(addProperty(addProperty(body('Extract_copy')?['result']?['candidate']?['provenance'],'sourceSha256',body('Extract_copy')?['result']?['candidate']?['sourceSha256']),'records',body('Extract_copy')?['result']?['candidate']?['rawRecords']))"
    acquisition['Save_identity_snapshot'] = snapshot
    same = "and(equals(body('Extract_copy')?['result']?['candidate']?['sourceSha256'],outputs('Parse_success_checkpoint')?['sourceSha256']),equals(body('Extract_copy')?['result']?['candidate']?['contractHash'],outputs('Parse_success_checkpoint')?['identityContractHash']))"
    selected = daily['Selected_candidate']['inputs']
    selected['reusedCandidate'] = '@'+same
    selected['candidateFile'] = "@if("+same+",coalesce(outputs('Parse_success_checkpoint')?['candidateFile'],'native-candidate.json'),concat('qw3-candidate-',workflow()?['run']?['name'],'.json'))"
    # Preserve source/candidate drift checks, replace only the frozen contract and
    # 985-set assumptions with explicit script-validated identity sets.
    old = guard['expression']
    fixed = re.findall(r"equals\(outputs\('Parse_candidate'\)\?\['contractHash'\],'[a-f0-9]{64}'\)",old)
    if len(fixed) != 1:
        raise ValueError('frozen_contract_guard_shape_changed')
    revised = old.replace(fixed[0],"equals(outputs('Parse_candidate')?['contractHash'],body('Extract_copy')?['result']?['candidate']?['contractHash'])")
    count = "length(outputs('Parse_candidate')?['operations'])"
    revised = revised.replace("equals(length(body('Read_current')?['d']?['results']),985)","equals(length(body('Read_current')?['d']?['results']),length(union(body('Current_UIDs'),body('Current_UIDs'))))")
    revised = revised.replace("equals(length(union(body('Current_UIDs'),body('Current_UIDs'))),985)","equals(length(union(body('Current_UIDs'),body('Current_UIDs'))),length(body('Current_UIDs')))")
    revised = revised.replace(",985)",","+count+")")
    revised = revised.replace("equals("+count+","+count+")", "equals("+count+",outputs('Parse_candidate')?['inputCount'])")
    reconciliation['Current_identity_values'] = {
        'type':'Select','runAfter':{'Current_UIDs':['Succeeded']},
        'inputs':{'from':"@body('Read_current')?['d']?['results']",
                  'select':"@item()?['DocumentUID']"}}
    reconciliation['Missing_base_identities'] = {
        'type':'Query','runAfter':{'Current_identity_values':['Succeeded']},
        'inputs':{'from':"@body('Extract_copy')?['result']?['identityContract']?['baseUIDs']",
                  'where':"@not(contains(body('Current_identity_values'),item()))"}}
    reconciliation['Unqualified_new_identities'] = {
        'type':'Query','runAfter':{'Missing_base_identities':['Succeeded']},
        'inputs':{'from':"@body('Read_current')?['d']?['results']",
                  'where':"@and(not(contains(body('Extract_copy')?['result']?['identityContract']?['baseUIDs'],item()?['DocumentUID'])),not(and(contains(coalesce(body('Extract_copy')?['result']?['identityApplication']?['newUIDs'],json('[]')),item()?['DocumentUID']),equals(item()?['"+MARKER+"'],body('Extract_copy')?['result']?['identityApplication']?['packageHash']))))"}}
    guard['runAfter'] = {'Unqualified_new_identities':['Succeeded']}
    guard['expression'] = "@and("+revised[1:]+",equals(body('Extract_copy')?['result']?['identityContract']?['baseContractHash'],outputs('Parse_success_checkpoint')?['identityContractHash']),empty(body('Missing_base_identities')),empty(body('Unqualified_new_identities')))"
    for name in ('Read_current','Read_current_after'):
        p = reconciliation[name]['inputs']['parameters']
        p['parameters/uri'] += ','+MARKER
    # Empty Find_native must take the create branch without evaluating first([]).
    compare['expression'] = "@if(empty(body('Find_native')),false,"+compare['expression'][1:]+")"
    patch = writer.pop('Patch_source')
    patch['runAfter'] = {}
    create = copy.deepcopy(patch)
    create['inputs']['parameters'].update({
        'parameters/uri':"_api/web/lists(guid'"+catalogue+"')/items",
        'parameters/headers':{'Accept':'application/json;odata=verbose','Content-Type':'application/json;odata=nometadata'},
        'parameters/body':"@string(addProperty(addProperty(outputs('Whitelisted_fields'),'DocumentUID',outputs('Current_operation')?['DocumentUID']),'"+MARKER+"',body('Extract_copy')?['result']?['identityApplication']?['packageHash']))"})
    # Each missing target must be among the package's explicitly approved new IDs.
    # Input validation rejects missing baseline identities. A creation additionally
    # fails expression evaluation before any HTTP call unless its UID is explicitly
    # authorised. Keep this in the input: another If exceeds PA's nesting limit.
    create['inputs']['parameters']['parameters/body'] = create['inputs']['parameters']['parameters/body'].replace(
        "'DocumentUID',outputs('Current_operation')?['DocumentUID']",
        "'DocumentUID',if(contains(coalesce(body('Extract_copy')?['result']?['identityApplication']?['newUIDs'],json('[]')),outputs('Current_operation')?['DocumentUID']),outputs('Current_operation')?['DocumentUID'],div(1,0))")
    writer['Write_source'] = {'type':'If','runAfter':{'Whitelisted_fields':['Succeeded']},
        'expression':"@empty(body('Find_native'))",'actions':{'Create_identity':create},
        'else':{'actions':{'Patch_source':patch}}}
    writer['Count_write']['runAfter'] = {'Write_source':['Succeeded']}
    read = writer['Read_written']['inputs']['parameters']
    select = read['parameters/uri'].split("'?$select=")[1].split("')")[0]
    read['parameters/uri'] = "@concat('_api/web/lists(guid''"+catalogue+"'')/items?$filter=DocumentUID eq ''',outputs('Current_operation')?['DocumentUID'],'''&$select="+select+','+MARKER+"')"
    verify = writer['Verify_written']
    verify['expression'] = "@and(equals(length(body('Read_written')?['d']?['results']),1),"+verify['expression'][1:].replace("body('Read_written')?['d']","first(body('Read_written')?['d']?['results'])")+")"
    verify['expression'] = "@and("+verify['expression'][1:]+",if(empty(body('Find_native')),equals(first(body('Read_written')?['d']?['results'])?['"+MARKER+"'],body('Extract_copy')?['result']?['identityApplication']?['packageHash']),true))"
    # Initial read is an inventory snapshot. UIDs are unique and one serial worker
    # is enforced. New identities keep a creation-package marker on retries.
    final = reconciliation['Guard_readback']
    final['expression'] = final['expression'].replace(',985)',','+count+')')
    final['actions']['Set_full_readback_count']['inputs']['value'] = '@'+count
    summary = final['actions']['Completed_summary']['inputs']
    summary.update({
        'identityLedger':"@body('Extract_copy')?['result']?['identityContract']?['ledger']",
        'lastIdentityApplicationHash':"@coalesce(body('Extract_copy')?['result']?['identityApplication']?['packageHash'],outputs('Parse_success_checkpoint')?['lastIdentityApplicationHash'],'')",
        'identityApplicationFile':"@concat('qw3-identity-application-',workflow()?['run']?['name'],'.json')",
        'identityApplicationStatus':"@if(empty(body('Extract_copy')?['result']?['identityApplication']),'unchanged','verified')"})
    def check_depth(group, depth=0):
        for action in group.values():
            if depth > 8:
                raise ValueError('native_action_nesting_limit_exceeded')
            if 'actions' in action: check_depth(action['actions'], depth+1)
            if 'else' in action: check_depth(action['else'].get('actions',{}), depth+1)
    check_depth(definition['actions'])
    result['properties']['definition'] = definition
    return result


def extend_absence_retention(exported: dict) -> dict:
    """Retain explicitly acknowledged missing rows; never issue writes for them."""
    result = copy.deepcopy(exported)
    definition = result['properties']['definition']
    triggers = definition['triggers']
    if len(triggers) != 1 or next(iter(triggers.values())).get('runtimeConfiguration', {}).get('concurrency', {}).get('runs') != 1:
        raise ValueError('sole_serial_importer_required')
    reconciliation = definition['actions']['Daily_due']['actions']['Reconcile']['actions']
    if 'Retained_absent_before' in reconciliation:
        raise ValueError('absence_retention_extension_already_present')
    guard = reconciliation['Guard_input']
    missing = "outputs('Parse_candidate')?['missingUIDs']"
    acknowledged = "coalesce(outputs('Parse_candidate')?['acknowledgedMissingUIDs'],json('[]'))"
    clause = 'empty(' + missing + ')'
    if guard['runAfter'] != {'Unqualified_new_identities': ['Succeeded']} or clause not in guard['expression']:
        raise ValueError('qualified_identity_guard_required')
    reconciliation['Retained_absent_before'] = {
        'type': 'Query', 'runAfter': copy.deepcopy(guard['runAfter']),
        'inputs': {'from': "@body('Read_current')?['d']?['results']",
                   'where': '@contains(' + acknowledged + ",item()?['DocumentUID'])"}}
    selected = re.search(r'\$select=([^&]+)', reconciliation['Read_current']['inputs']['parameters']['parameters/uri'])
    if not selected:
        raise ValueError('qualified_retained_field_projection_required')
    fields = selected.group(1).split(',')
    if not {'Id', 'DocumentUID', MARKER} <= set(fields):
        raise ValueError('qualified_retained_identity_projection_required')
    retained_projection = {field: "@item()?['" + field + "']" for field in fields}
    # SharePoint's __metadata.id is generated afresh for each request. ETag is
    # the item-version proof; include every selected value but exclude that ID.
    retained_projection['retainedETag'] = "@if(empty(item()?['__metadata']?['etag']),div(1,0),item()?['__metadata']?['etag'])"
    reconciliation['Canonical_retained_before'] = {
        'type': 'Select', 'runAfter': {'Retained_absent_before': ['Succeeded']},
        'inputs': {'from': "@body('Retained_absent_before')", 'select': retained_projection}}
    guard['runAfter'] = {'Canonical_retained_before': ['Succeeded']}
    guard['expression'] = guard['expression'].replace(clause,
        'and(equals(length(' + missing + '),length(' + acknowledged + ')),'
        'equals(length(union(' + missing + ',' + acknowledged + ')),length(' + acknowledged + ')),'
        "equals(length(body('Retained_absent_before')),length(" + acknowledged + ')))')
    union_count = "equals(length(union(body('Candidate_UIDs'),body('Current_UIDs'))),length(outputs('Parse_candidate')?['operations']))"
    if union_count not in guard['expression']:
        raise ValueError('qualified_identity_set_guard_required')
    guard['expression'] = guard['expression'].replace(union_count,
        "equals(length(union(body('Candidate_UIDs'),body('Current_UIDs'))),add(length(outputs('Parse_candidate')?['operations']),length(" + acknowledged + ')))')
    # Only active source operations are compared/written. Absent catalogue rows
    # remain in the inventory and must read back byte-equivalent selected values.
    canonical = reconciliation['Canonical_after']
    if canonical['inputs']['from'] != "@body('Read_current_after')?['d']?['results']":
        raise ValueError('qualified_final_readback_required')
    reconciliation['Active_current_after'] = {
        'type': 'Query', 'runAfter': copy.deepcopy(canonical['runAfter']),
        'inputs': {'from': canonical['inputs']['from'],
                   'where': '@not(contains(' + acknowledged + ",item()?['DocumentUID']))"}}
    reconciliation['Retained_absent_after'] = {
        'type': 'Query', 'runAfter': {'Active_current_after': ['Succeeded']},
        'inputs': {'from': canonical['inputs']['from'],
                   'where': '@contains(' + acknowledged + ",item()?['DocumentUID'])"}}
    reconciliation['Canonical_retained_after'] = {
        'type': 'Select', 'runAfter': {'Retained_absent_after': ['Succeeded']},
        'inputs': {'from': "@body('Retained_absent_after')", 'select': copy.deepcopy(retained_projection)}}
    canonical['runAfter'] = {'Canonical_retained_after': ['Succeeded']}
    canonical['inputs']['from'] = "@body('Active_current_after')"
    final = reconciliation['Guard_readback']
    count = "length(outputs('Parse_candidate')?['operations'])"
    old = "equals(length(body('Read_current_after')?['d']?['results'])," + count + ')'
    if old not in final['expression']:
        raise ValueError('qualified_catalogue_count_guard_required')
    final['expression'] = final['expression'].replace(old,
        "equals(length(body('Read_current_after')?['d']?['results']),add(" + count + ',length(' + acknowledged + ')))')
    before = "body('Canonical_retained_before')"
    after = "body('Canonical_retained_after')"
    # Inventory order is not an identity. Require equal, duplicate-free sets of
    # complete projections (including item identity and mandatory ETag).
    unchanged = (
        'and(equals(length(union(' + before + ',' + before + ')),length(' + before + ')),'
        'equals(length(union(' + after + ',' + after + ')),length(' + after + ')),'
        'equals(length(' + before + '),length(' + after + ')),'
        'equals(length(union(' + before + ',' + after + ')),length(' + before + ')))')
    final['expression'] = '@and(' + final['expression'][1:] + ',' + unchanged + ')'
    final['actions']['Completed_summary']['inputs'].update({
        'retainedAbsentUIDs': '@' + acknowledged,
        'retainedAbsentReadbackCount': "@length(body('Retained_absent_after'))",
        'retainedAbsentUnchanged': '@' + unchanged,
        'catalogueReadbackCount': "@length(body('Read_current_after')?['d']?['results'])"})
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--retain-absence', action='store_true')
    args=parser.parse_args()
    extend = extend_absence_retention if args.retain_absence else extend_importer
    result=extend(json.loads(args.export.read_text()))
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2)
        stream.write('\n')


if __name__ == '__main__':main()

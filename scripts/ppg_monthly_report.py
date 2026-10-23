#!/usr/bin/env python3
"""Build a native, read-only monthly catalogue report flow. Bindings stay private.

The flow writes only its report files in the existing evidence library.
It neither distributes reports nor changes catalogue/case/source records.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

SOURCE_FIELDS = ('rawSourceRecordRef', 'sourceAsOfUtc', 'sourceCustodian',
                 'sourceDocumentId', 'sourceNextReviewDateRaw', 'sourceNextReviewMonth',
                 'sourceRisk', 'sourceRowNumber', 'sourceSnapshotRef', 'sourceStatus', 'sourceTitle')


def build(binding, source_binding, *, manual=False, qualification_suffix=""):
    if qualification_suffix and (not qualification_suffix.replace("-", "").isalnum() or len(qualification_suffix) > 64):
        raise ValueError("invalid qualification suffix")
    site = binding['destination']['siteUrl']
    library = urlparse(site).path + '/PPG Review Evidence'
    catalogue = binding['destination']['catalogueListId']
    refs = {'shared_sharepointonline': source_binding['refs']['shared_sharepointonline']}
    actions = {}

    def http(uri, after=None, method='GET', body=None):
        params = {'dataset': site, 'parameters/method': method,
                  'parameters/uri': uri,
                  'parameters/headers': {'Accept': 'application/json;odata=nometadata'}}
        if body is not None:
            params['parameters/body'] = body
            params['parameters/headers']['Content-Type'] = 'application/octet-stream'
        return {'type': 'OpenApiConnection', 'inputs': {
            'host': {'apiId': '/providers/Microsoft.PowerApps/apis/shared_sharepointonline',
                     'connectionName': 'shared_sharepointonline', 'operationId': 'HttpRequest'},
            'parameters': params}, 'runAfter': after or {}}

    def add(name, value, kind='Compose', after=None):
        # Top-level actions deliberately form one serial, inspectable acquisition.
        previous = list(actions)[-1:]
        actions[name] = {'type': kind, 'inputs': value,
                         'runAfter': after if after is not None else
                         ({previous[0]: ['Succeeded']} if previous else {})}

    def read(name, filename):
        previous = list(actions)[-1:]
        uri = (f"_api/web/GetFileByServerRelativePath(decodedurl='{library}/{filename}')/$value")
        actions['Read_' + name] = http(uri, {previous[0]: ['Succeeded']} if previous else {})
        add(name, parse('Read_' + name))

    def parse(name):
        return (f"@if(contains(body('{name}'),'$content'),"
                f"json(base64ToString(body('{name}')?['$content'])),json(string(body('{name}'))))")

    add('Report_time', '@utcNow()')
    add('Month', "@formatDateTime(convertTimeZone(outputs('Report_time'),'UTC','E. Australia Standard Time'),'yyyy-MM')")
    add('Window_end', "@formatDateTime(addToTime(concat(outputs('Month'),'-01T00:00:00Z'),3,'Month'),'yyyy-MM')")
    read('Checkpoint', 'qw3-last-successful.json')
    # Read the candidate named by the successful checkpoint, never latest failed acquisition.
    actions['Read_Candidate'] = http(
        f"@concat('_api/web/GetFileByServerRelativePath(decodedurl=''{library}/',outputs('Checkpoint')?['candidateFile'],''')/$value')",
        {'Checkpoint': ['Succeeded']})
    add('Candidate', parse('Read_Candidate'))
    read('Source', 'qw3-source-state.json')
    actions['Read_Catalogue'] = http(
        f"_api/web/lists(guid'{catalogue}')/items?$select=DocumentUID,{','.join(SOURCE_FIELDS)}&$top=5000",
        {'Source': ['Succeeded']})
    add('Catalogue', parse('Read_Catalogue'))
    projection = {'DocumentUID': "@item()?['DocumentUID']"}
    projection.update({k: f"@item()?['fields']?['{k}']" for k in SOURCE_FIELDS})
    projection['sourceRowNumber'] = "@int(item()?['fields']?['sourceRowNumber'])"
    add('Candidate_fields', {'from': "@outputs('Candidate')?['operations']", 'select': projection}, 'Select')
    native = {'DocumentUID': "@item()?['DocumentUID']"}
    native.update({k: f"@item()?['{k}']" for k in SOURCE_FIELDS})
    native['sourceRowNumber'] = "@int(item()?['sourceRowNumber'])"
    add('Retained_UIDs', "@coalesce(outputs('Checkpoint')?['retainedAbsentUIDs'],json('[]'))")
    add('Retained_catalogue', {'from': "@outputs('Catalogue')?['value']", 'where': "@contains(outputs('Retained_UIDs'),item()?['DocumentUID'])"}, 'Query')
    add('Active_catalogue', {'from': "@outputs('Catalogue')?['value']", 'where': "@not(contains(outputs('Retained_UIDs'),item()?['DocumentUID']))"}, 'Query')
    add('Catalogue_fields', {'from': "@body('Active_catalogue')", 'select': native}, 'Select')
    add('All_UIDs', {'from': "@outputs('Catalogue')?['value']", 'select': "@item()?['DocumentUID']"}, 'Select')
    add('Ledger_UIDs', {'from': "@outputs('Checkpoint')?['identityLedger']?['aliases']", 'select': "@coalesce(item()?['documentUID'],item()?['DocumentUID'])"}, 'Select')
    add('Ledger_aliases', {'from': "@outputs('Checkpoint')?['identityLedger']?['aliases']", 'select': "@coalesce(item()?['sourceDocumentId'],item()?['alias'])"}, 'Select')
    add('Ledger_pairs', {'from': "@outputs('Checkpoint')?['identityLedger']?['aliases']", 'select': {'DocumentUID': "@coalesce(item()?['documentUID'],item()?['DocumentUID'])", 'sourceDocumentId': "@coalesce(item()?['sourceDocumentId'],item()?['alias'])"}}, 'Select')
    add('Candidate_pairs', {'from': "@outputs('Candidate')?['operations']", 'select': {'DocumentUID': "@item()?['DocumentUID']", 'sourceDocumentId': "@item()?['fields']?['sourceDocumentId']"}}, 'Select')
    add('All_acknowledgement_UIDs', {'from': "@coalesce(outputs('Checkpoint')?['identityLedger']?['sourceAbsenceAcknowledgements'],json('[]'))", 'select': "@item()?['DocumentUID']"}, 'Select')
    add('Current_acknowledgements', {'from': "@coalesce(outputs('Checkpoint')?['identityLedger']?['sourceAbsenceAcknowledgements'],json('[]'))", 'where': "@contains(outputs('Retained_UIDs'),item()?['DocumentUID'])"}, 'Query')
    add('Acknowledged_UIDs', {'from': "@body('Current_acknowledgements')", 'select': "@item()?['DocumentUID']"}, 'Select')
    add('Invalid_acknowledgements', {'from': "@body('Current_acknowledgements')", 'where': "@not(and(equals(item()?['sourceSha256'],outputs('Checkpoint')?['sourceSha256']),equals(item()?['effect'],'retain_unchanged'),not(empty(trim(string(item()?['actor'])))),not(empty(trim(string(item()?['evidenceReference'])))),not(empty(trim(string(item()?['decisionEvidence'])))),not(empty(trim(string(item()?['baseContractHash']))))))"}, 'Query')
    add('Identities', {'from': "@body('Catalogue_fields')", 'select': {'id': "@item()?['DocumentUID']"}}, 'Select')
    op = "outputs('Candidate')?['operations'][item()]"
    raw = "outputs('Candidate')?['rawRecords'][item()]"
    add('Mismatched_routes', {'from': "@range(0,length(outputs('Candidate')?['operations']))",
        'where': f"@not(and(equals({op}?['sourceRow'],{raw}?['sourceRow']),equals({op}?['fields'],{raw}?['projectedFields']),equals({op}?['fields']?['sourceDocumentId'],{raw}?['fields']?['sourceDocumentId'])))"}, 'Query')
    checks = [
        "equals(outputs('Checkpoint')?['status'],'completed')",
        f"equals(outputs('Candidate')?['allowed'],json('{json.dumps(list(SOURCE_FIELDS), separators=(chr(44), chr(58)))}'))",
        "equals(length(outputs('Candidate')?['exceptions']),0)",
        "equals(length(outputs('Candidate')?['missingUIDs']),length(outputs('Retained_UIDs')))",
        "equals(length(union(outputs('Retained_UIDs'),outputs('Retained_UIDs'))),length(outputs('Retained_UIDs')))",
        "equals(length(intersection(outputs('Candidate')?['missingUIDs'],outputs('Retained_UIDs'))),length(outputs('Retained_UIDs')))",
        "equals(length(coalesce(outputs('Candidate')?['acknowledgedMissingUIDs'],json('[]'))),length(outputs('Retained_UIDs')))",
        "equals(length(intersection(coalesce(outputs('Candidate')?['acknowledgedMissingUIDs'],json('[]')),outputs('Retained_UIDs'))),length(outputs('Retained_UIDs')))",
        "equals(length(body('Retained_catalogue')),length(outputs('Retained_UIDs')))",
        "equals(length(body('All_UIDs')),coalesce(outputs('Checkpoint')?['catalogueReadbackCount'],outputs('Checkpoint')?['readbackCount']))",
        "equals(length(union(body('All_UIDs'),body('All_UIDs'))),length(body('All_UIDs')))",
        "equals(length(union(body('Ledger_UIDs'),body('Ledger_UIDs'))),length(body('All_UIDs')))",
        "equals(length(intersection(body('All_UIDs'),body('Ledger_UIDs'))),length(body('All_UIDs')))",
        "equals(length(union(body('Ledger_aliases'),body('Ledger_aliases'))),length(body('Ledger_aliases')))",
        "equals(outputs('Checkpoint')?['identityLedger']?['sourceSystemId'],outputs('Candidate')?['source'])",
        "equals(length(body('Acknowledged_UIDs')),length(outputs('Retained_UIDs')))",
        "equals(length(intersection(body('Acknowledged_UIDs'),outputs('Retained_UIDs'))),length(outputs('Retained_UIDs')))",
        "equals(length(body('Invalid_acknowledgements')),0)",
        "equals(length(union(body('All_acknowledgement_UIDs'),body('All_acknowledgement_UIDs'))),length(body('All_acknowledgement_UIDs')))",
        "equals(length(intersection(body('All_acknowledgement_UIDs'),body('All_UIDs'))),length(body('All_acknowledgement_UIDs')))",
        "equals(length(intersection(body('Candidate_pairs'),body('Ledger_pairs'))),length(body('Candidate_pairs')))",
        "or(empty(outputs('Retained_UIDs')),and(equals(outputs('Checkpoint')?['retainedAbsentUnchanged'],true),equals(outputs('Checkpoint')?['retainedAbsentReadbackCount'],length(outputs('Retained_UIDs'))),not(empty(outputs('Checkpoint')?['lastIdentityApplicationHash'])),not(empty(outputs('Checkpoint')?['runId']))))",
        "equals(outputs('Candidate')?['sourceSha256'],outputs('Checkpoint')?['sourceSha256'])",
        "equals(outputs('Candidate')?['contractHash'],outputs('Checkpoint')?['identityContractHash'])",
        "greater(length(body('Catalogue_fields')),0)",
        "equals(length(body('Catalogue_fields')),outputs('Checkpoint')?['readbackCount'])",
        "equals(length(body('Catalogue_fields')),outputs('Candidate')?['inputCount'])",
        "equals(length(body('Candidate_fields')),length(body('Catalogue_fields')))",
        "equals(length(intersection(body('Catalogue_fields'),body('Candidate_fields'))),length(body('Catalogue_fields')))",
        "equals(length(union(body('Identities'),body('Identities'))),length(body('Identities')))",
        "not(contains(body('Identities'),json('{\"id\":null}')))",
        "not(contains(body('Identities'),json('{\"id\":\"\"}')))",
        "not(contains(outputs('Catalogue'),'odata.nextLink'))",
        "not(contains(outputs('Catalogue'),'@odata.nextLink'))",
        "equals(length(body('Mismatched_routes')),0)",
        "equals(length(outputs('Candidate')?['rawRecords']),length(body('Candidate_fields')))"
    ]
    add('Guard_checks', {f"check_{i+1}": "@" + check for i, check in enumerate(checks)})
    add('Guard', "@and(" + ",".join(checks) + ")")

    report = {}
    def radd(name, kind, inputs, after=None):
        previous = list(report)[-1:]
        report[name] = {'type': kind, 'inputs': inputs, 'runAfter': after if after is not None else
                        ({previous[0]: ['Succeeded']} if previous else {})}

    month = f"coalesce({op}?['fields']?['sourceNextReviewMonth'],'')"
    year = f"first(split({month},'-'))"
    digits = year
    for digit in '0123456789':
        digits = f"replace({digits},'{digit}','')"
    valid = (f"and(equals(length({month}),7),equals(length(split({month},'-')),2),"
             f"equals(length({year}),4),equals({digits},''),not(equals({year},'0000')),"
             f"contains(createArray('01','02','03','04','05','06','07','08','09','10','11','12'),last(split({month},'-'))))")
    bucket = (f"if(not({valid}),'Date exception',if(less({month},outputs('Month')),'Overdue',"
              f"if(equals({month},outputs('Month')),'Due this month',"
              f"if(lessOrEquals({month},outputs('Window_end')),'Due next three months','Later'))))")
    fields = {
        'Bucket': '@' + bucket, 'Review month': '@' + month,
        'Custodian': f"@coalesce({raw}?['fields']?['sourceCustodian'],'')",
        'Authorising officer': f"@coalesce({raw}?['fields']?['sourceAuthorisingOfficer'],'')",
        'Operational hierarchy': f"@coalesce({raw}?['fields']?['sourceExecutiveHierarchy'],'')",
        'Service director': f"@coalesce({raw}?['fields']?['sourceServiceDirector'],'')",
        'Service': f"@coalesce({raw}?['fields']?['sourceServiceIndex'],'')",
        'DocumentUID': '@' + op + "?['DocumentUID']",
        'Document ID': '@' + op + "?['fields']?['sourceDocumentId']",
        'Title': '@' + op + "?['fields']?['sourceTitle']",
        'Source status': '@' + op + "?['fields']?['sourceStatus']",
        'Risk': '@' + op + "?['fields']?['sourceRisk']",
        'Source comments': f"@coalesce({raw}?['fields']?['sourceComments'],'')",
        'Review date raw': '@' + op + "?['fields']?['sourceNextReviewDateRaw']",
        'Evidence': '@' + op + "?['fields']?['rawSourceRecordRef']",
    }
    radd('Rows', 'Select', {'from': "@range(0,length(outputs('Candidate')?['operations']))", 'select': fields})
    # Sorting groups the CSV by recorded roles; no assignments or recipient lookup.
    radd('Sorted_rows', 'Compose', "@sort(sort(sort(body('Rows'),'Custodian'),'Operational hierarchy'),'Authorising officer')")
    for name, value in [('Overdue','Overdue'), ('Due_now','Due this month'),
                        ('Due_soon','Due next three months'), ('Exceptions','Date exception'), ('Later','Later')]:
        radd(name, 'Query', {'from': "@outputs('Sorted_rows')", 'where': f"@equals(item()?['Bucket'],'{value}')"})
    radd('Freshness', 'Compose', "@if(not(equals(outputs('Source')?['sourceETag'],outputs('Checkpoint')?['centralSourceETag'])),'SOURCE CHANGED / RECONCILIATION PENDING - last verified catalogue only',if(or(empty(outputs('Source')?['checkedUtc']),greater(ticks(outputs('Report_time')),ticks(addMinutes(coalesce(outputs('Source')?['checkedUtc'],'1900-01-01T00:00:00Z'),90)))),'SOURCE CHECK STALE OR UNKNOWN - last verified catalogue only','Latest observed source matches verified catalogue; policy currency not assessed'))")
    radd('Reportable_rows', 'Query', {'from': "@outputs('Sorted_rows')", 'where': "@not(equals(item()?['Bucket'],'Later'))"})
    # CSV formula injection protection. Prefix only potentially executable source text.
    safe = {}
    for key in fields:
        value = f"string(coalesce(item()?['{key}'],''))"
        safe[key] = (f"@if(or(startsWith(trim({value}),'='),startsWith(trim({value}),'+'),"
                     f"startsWith(trim({value}),'-'),startsWith(trim({value}),'@'),"
                     f"startsWith({value},decodeUriComponent('%09')),startsWith({value},decodeUriComponent('%0D'))),concat('''',{value}),{value})")
    safe.update({'Report month': "@outputs('Month')", 'Freshness': "@outputs('Freshness')",
                 'Last successful UTC': "@outputs('Checkpoint')?['asOfUtc']",
                 'Source SHA256': "@outputs('Checkpoint')?['sourceSha256']",
                 'Generated UTC': "@outputs('Report_time')"})
    radd('CSV_safe_rows', 'Select', {'from': "@body('Reportable_rows')", 'select': safe})
    radd('CSV', 'Table', {'from': "@body('CSV_safe_rows')", 'format': 'CSV'})
    retained_fields = {'DocumentUID': "@item()?['DocumentUID']"}
    retained_fields.update({key: f"@item()?['{key}']" for key in SOURCE_FIELDS})
    retained_fields['Accounting'] = 'Retained source absence; current clinical status unresolved; original recorded fields preserved'
    radd('Retained_rows', 'Select', {'from': "@body('Retained_catalogue')", 'select': retained_fields})
    retained_safe = {}
    for key in retained_fields:
        value = f"string(coalesce(item()?['{key}'],''))"
        retained_safe[key] = (f"@if(or(startsWith(trim({value}),'='),startsWith(trim({value}),'+'),"
                             f"startsWith(trim({value}),'-'),startsWith(trim({value}),'@'),"
                             f"startsWith({value},decodeUriComponent('%09')),startsWith({value},decodeUriComponent('%0D'))),concat('''',{value}),{value})")
    radd('Retained_safe_rows', 'Select', {'from': "@body('Retained_rows')", 'select': retained_safe})
    radd('Retained_CSV', 'Table', {'from': "@body('Retained_safe_rows')", 'format': 'CSV'})
    # Ensure the successful checkpoint did not advance during acquisition.
    report['Recheck_checkpoint'] = http(
        f"_api/web/GetFileByServerRelativePath(decodedurl='{library}/qw3-last-successful.json')/$value",
        {'Retained_CSV': ['Succeeded']})
    radd('Checkpoint_after', 'Compose', parse('Recheck_checkpoint'))
    filebase = "concat('PPG-monthly-review-',outputs('Month'),'" + ("-" + qualification_suffix if qualification_suffix else "") + "')"
    csv_uri = f"@concat('_api/web/GetFolderByServerRelativePath(decodedurl=''{library}'')/Files/add(url=''',{filebase},'.csv'',overwrite=true)')"
    write = http(csv_uri, body="@body('CSV')", method='POST')
    write['runAfter'] = {}
    readback = http(f"@concat('_api/web/GetFileByServerRelativePath(decodedurl=''{library}/',{filebase},'.csv'')/$value')", {'Write_CSV': ['Succeeded']})
    csv_text = "@if(contains(body('Readback_CSV'),'$content'),base64ToString(body('Readback_CSV')?['$content']),string(body('Readback_CSV')))"
    summary = ("@concat('# Monthly review report — ',outputs('Month'),decodeUriComponent('%0A%0A'),"
        "'**',outputs('Freshness'),'**',decodeUriComponent('%0A%0A'),"
        "'Active source rows: ',string(length(body('Rows'))),'; retained absent rows: ',string(length(body('Retained_rows'))),'; total catalogue identities: ',string(length(body('All_UIDs'))),'; overdue: ',string(length(body('Overdue'))),"
        "'; due this month: ',string(length(body('Due_now'))),'; following three months through ',outputs('Window_end'),': ',string(length(body('Due_soon'))),"
        "'; date exceptions: ',string(length(body('Exceptions'))),'; later: ',string(length(body('Later'))),decodeUriComponent('%0A%0A'),"
        f"'[Download the full grouped CSV]({site}/PPG%20Review%20Evidence/',{filebase},'.csv)',decodeUriComponent('%0A%0A'),"
        f"'[Retained source absences CSV]({site}/PPG%20Review%20Evidence/',{filebase},'-retained.csv)',decodeUriComponent('%0A%0A'),"
        "'Retained absences are excluded from active-source date buckets and shown separately with original recorded fields. Absence does not establish clinical retirement or current approval. ',"
        "'Source-bound absence acknowledgements: ',string(body('Current_acknowledgements')),decodeUriComponent('%0A%0A'),"
        "'Open in Excel; overdue, current-month, next-three-month and date-exception rows are already selected. Filter recorded roles as needed. Later rows are accounted for in the total above; no status-based exclusions. ',"
        "'Month precision: earlier months are overdue; the current month is due this month; the following three calendar months are due soon. No day is invented and no review interval is recalculated. ',"
        "'Recorded roles and source status/comments are source assertions. Status may disagree with date classification. Roles are not recipient selections or assignments. ',"
        "'Report preparation only; no distribution, approval, publication, source edits or case edits.',decodeUriComponent('%0A%0A'),"
        "'Last successful reconciliation UTC: ',outputs('Checkpoint')?['asOfUtc'],decodeUriComponent('%0A'),"
        "'Source metadata checked UTC: ',coalesce(outputs('Source')?['checkedUtc'],'unknown'),decodeUriComponent('%0A'),"
        "'Source snapshot SHA256: ',outputs('Checkpoint')?['sourceSha256'],decodeUriComponent('%0A'),"
        "'Generated UTC: ',outputs('Report_time'),decodeUriComponent('%0A'))")
    retained_write = http(f"@concat('_api/web/GetFolderByServerRelativePath(decodedurl=''{library}'')/Files/add(url=''',{filebase},'-retained.csv'',overwrite=true)')", method='POST', body="@body('Retained_CSV')")
    retained_write['runAfter'] = {'CSV_readback': ['Succeeded']}
    retained_readback = http(f"@concat('_api/web/GetFileByServerRelativePath(decodedurl=''{library}/',{filebase},'-retained.csv'')/$value')", {'Write_retained_CSV': ['Succeeded']})
    retained_text = "@if(contains(body('Readback_retained_CSV'),'$content'),base64ToString(body('Readback_retained_CSV')?['$content']),string(body('Readback_retained_CSV')))"
    after_read = {'type': 'If', 'expression': "@and(equals(outputs('CSV_readback'),body('CSV')),equals(outputs('Retained_CSV_readback'),body('Retained_CSV')))",
        'actions': {'Write_summary': http(
            f"@concat('_api/web/GetFolderByServerRelativePath(decodedurl=''{library}'')/Files/add(url=''',{filebase},'.md'',overwrite=true)')",
            method='POST', body=summary)},
        'else': {'actions': {'Readback_failure': {'type': 'Terminate', 'inputs': {'runStatus': 'Failed', 'runError': {'code': 'ReportReadbackMismatch', 'message': 'CSV readback differs; summary not committed.'}}}}},
        'runAfter': {'Retained_CSV_readback': ['Succeeded']}}
    radd('Write_if_stable', 'Compose', True)  # replaced below with guarded publication
    report['Write_if_stable'] = {'type': 'If', 'expression': "@equals(outputs('Checkpoint'),outputs('Checkpoint_after'))",
        'actions': {'Write_CSV': write, 'Readback_CSV': readback,
                    'CSV_readback': {'type': 'Compose', 'inputs': csv_text, 'runAfter': {'Readback_CSV': ['Succeeded']}},
                    'Write_retained_CSV': retained_write, 'Readback_retained_CSV': retained_readback,
                    'Retained_CSV_readback': {'type': 'Compose', 'inputs': retained_text, 'runAfter': {'Readback_retained_CSV': ['Succeeded']}},
                    'Commit_summary': after_read},
        'else': {'actions': {'Moving_checkpoint': {'type': 'Terminate', 'inputs': {'runStatus': 'Failed', 'runError': {'code': 'MovingCheckpoint', 'message': 'Checkpoint changed; rerun report from the new baseline.'}}}}},
        'runAfter': {'Checkpoint_after': ['Succeeded']}}
    previous = list(actions)[-1]
    actions['Generate_if_verified'] = {'type': 'If', 'expression': "@outputs('Guard')", 'actions': report,
        'else': {'actions': {'Unverified_catalogue': {'type': 'Terminate', 'inputs': {'runStatus': 'Failed', 'runError': {'code': 'UnverifiedCatalogue', 'message': 'Catalogue/candidate/checkpoint mismatch or incomplete source roles; no report written.'}}}}},
        'runAfter': {previous: ['Succeeded']}}
    trigger = ({'manual': {'type': 'Request', 'kind': 'Button', 'inputs': {'schema': {'type': 'object', 'properties': {}}},
                           'runtimeConfiguration': {'concurrency': {'runs': 1}}}} if manual else
               {'Monthly': {'type': 'Recurrence', 'recurrence': {'frequency': 'Month', 'interval': 1,
                    'timeZone': 'E. Australia Standard Time', 'startTime': '2026-11-01T08:00:00'},
                    'runtimeConfiguration': {'concurrency': {'runs': 1}}}})
    definition = {'$schema': 'https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#',
        'contentVersion': '1.0.0.0', 'parameters': {'$authentication': {'type': 'SecureObject', 'defaultValue': {}},
        '$connections': {'type': 'Object', 'defaultValue': {}}}, 'triggers': trigger, 'actions': actions, 'outputs': {}}
    return {'env': source_binding['env'], 'name': 'PPG — Monthly due and overdue report',
            'state': 'Stopped', 'connectionRefs': refs, 'definition': definition}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binding', type=Path, default=Path('.local/deployment.json'))
    parser.add_argument('--source-binding', type=Path, default=Path('.local/source-sync/native-scheduled-qualified-definition.json'))
    parser.add_argument('--output', type=Path, default=Path('.local/monthly-report/create.json'))
    parser.add_argument('--manual', action='store_true', help='Qualification trigger; production uses monthly recurrence')
    args = parser.parse_args()
    if '.local' not in args.output.parts:
        parser.error('Tenant-bound definitions must remain under .local')
    request = build(json.loads(args.binding.read_text()), json.loads(args.source_binding.read_text()), manual=args.manual)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(request, indent=2) + '\n')
    print('Prepared monthly report flow; no native writes performed')

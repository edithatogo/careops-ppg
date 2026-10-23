"""Build read-only selected-case context for qualified fictional operator cases.

Consumes observed native selected-item trigger and explicit private source binding.
No deployment, case/source/request/event writes, free target URI or approval logic.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from uuid import UUID


def build(probe, binding):
    if binding.get('qualificationOnly') is not True:
        raise ValueError('Explicit qualification binding required')
    source = binding['source']
    if not isinstance(source.get('ETag'), str) or not source['ETag'].strip() or source['ETag'] == '*':
        raise ValueError('An exact nonempty source ETag is required')
    UUID(source['UniqueId'])
    if hashlib.sha256(source['content'].encode()).hexdigest() != source['sha256']:
        raise ValueError('Qualified source content/hash mismatch')
    out = copy.deepcopy(probe)
    props = out['properties']
    props['state'] = 'Stopped'
    props['displayName'] = 'PPG Lifecycle | selected case context — read only'
    definition = props['definition']
    trigger = definition['triggers']['manual']
    if trigger['kind'] != 'ApiConnection' or trigger['inputs']['operationId'] != 'GetItemHybridTriggerSchema':
        raise ValueError('Observed SharePoint selected-item trigger required')
    site, case_uri = binding['siteUrl'], binding['caseListUri']
    if trigger['inputs']['parameters']['dataset'] != site:
        raise ValueError('Selected trigger site mismatch')
    expected_list = "_api/web/lists(guid'" + trigger['inputs']['parameters']['table'] + "')/items"
    if case_uri != expected_list:
        raise ValueError('Selected trigger list mismatch')
    refs = props['connectionReferences']
    if set(refs) != {'shared_sharepointonline'}:
        raise ValueError('Existing qualified SharePoint connection only')
    def q(value):
        return str(value).replace("'", "''")
    def literal(value):
        return "'" + q(value) + "'"
    def read(uri, previous=None):
        return {'type': 'OpenApiConnection', 'inputs': {
            'host': {'apiId': '/providers/Microsoft.PowerApps/apis/shared_sharepointonline',
                     'connectionName': 'shared_sharepointonline', 'operationId': 'HttpRequest'},
            'parameters': {'dataset': site, 'parameters/method': 'GET', 'parameters/uri': uri,
                           'parameters/headers': {'Accept': 'application/json;odata=nometadata'}}},
            'runAfter': {previous: ['Succeeded']} if previous else {}}
    def compose(value, previous=None):
        return {'type': 'Compose', 'inputs': value, 'runAfter': {previous: ['Succeeded']} if previous else {}}
    def held(reason):
        return compose({'contextValid': False, 'reason': reason, 'writeCount': 0,
                        'realPolicyEffects': False, 'asOfUtc': '@utcNow()'})
    def condition(expression, previous, yes, reason):
        return {'type': 'If', 'expression': '@and(' + ','.join(expression) + ')',
                'runAfter': {previous: ['Succeeded']}, 'actions': yes,
                'else': {'actions': {'Held_' + previous: held(reason)}}}
    selected_uri = "@concat(" + literal(case_uri + '(') + ",string(int(triggerBody()?['entity']?['ID'])),')?$select=Id,CaseUID,linkedDocumentUIDs,sourceBaselineRef,accountableRole,caseStatus')"
    actions = {'Read_selected_case': read(selected_uri)}
    prefix = site.split('/teams/')[0] + binding['evidenceFolder'] + '/LC02-operator-request-'
    suffix = "substring(string(body('Read_selected_case')?['sourceBaselineRef']),min(length(string(body('Read_selected_case')?['sourceBaselineRef']))," + str(len(prefix)) + '))'
    checks = ["greater(int(triggerBody()?['entity']?['ID']),0)",
              "equals(body('Read_selected_case')?['Id'],int(triggerBody()?['entity']?['ID']))",
              "startsWith(string(body('Read_selected_case')?['CaseUID']),'LC-FICTIONAL-OP-')",
              "startsWith(string(body('Read_selected_case')?['sourceBaselineRef'])," + literal(prefix) + ')',
              "endsWith(string(body('Read_selected_case')?['sourceBaselineRef']),'.json')"]
    for invalid in ['/', '\\', '%', '..', '?', '#', "'"]:
        checks.append('not(contains(' + suffix + ',' + literal(invalid) + '))')
    host = site.split('/teams/')[0]
    # Source-baseline URL is allowlisted before it becomes a same-site file path.
    # WDL uses single quoted literals; encode the enclosing OData quote explicitly.
    baseline_uri = "@concat('_api/web/GetFileByServerRelativePath(decodedurl=',decodeUriComponent('%27'),substring(body('Read_selected_case')?['sourceBaselineRef']," + str(len(host)) + "),decodeUriComponent('%27'),')')"
    def file_read_uri(extra):
        return baseline_uri[:-1] + ',' + literal(extra) + ')'
    baseline = {
        'Read_baseline_before': read(file_read_uri('?$select=UniqueId,ETag')),
        'Read_baseline_content': read(file_read_uri('/$value'), 'Read_baseline_before'),
        'Parse_baseline': compose("@json(if(contains(body('Read_baseline_content'),'$content'),base64ToString(body('Read_baseline_content')?['$content']),string(body('Read_baseline_content'))))", 'Read_baseline_content'),
        'Read_baseline_after': read(file_read_uri('?$select=UniqueId,ETag'), 'Parse_baseline'),
    }
    def baseline_metadata_checks(names):
        result = []
        for name in names:
            result += ["not(empty(body('" + name + "')?['ETag']))",
                       "not(equals(body('" + name + "')?['ETag'],'*'))",
                       "not(empty(body('" + name + "')?['UniqueId']))"]
        for left, right in zip(names, names[1:]):
            result += ["equals(body('" + left + "')?['ETag'],body('" + right + "')?['ETag'])",
                       "equals(body('" + left + "')?['UniqueId'],body('" + right + "')?['UniqueId'])"]
        return result
    request = "outputs('Parse_baseline')?['request']"
    verified_request = [
        "equals(outputs('Parse_baseline')?['kind'],'fictional-operator-initiation-request')",
        "equals(" + request + "?['schemaVersion'],1)",
        "equals(" + request + "?['qualificationOnly'],true)",
        "equals(" + request + "?['realPolicyEffects'],false)",
        "equals(" + request + "?['CaseUID'],body('Read_selected_case')?['CaseUID'])",
        "equals(" + request + "?['CaseUID'],concat('LC-FICTIONAL-OP-'," + request + "?['occurrenceReference']))",
        "equals(body('Read_selected_case')?['sourceBaselineRef'],concat(" + literal(prefix) + ',' + request + "?['requestReference'],'.json'))",
        "equals(json(body('Read_selected_case')?['linkedDocumentUIDs']),createArray(" + literal(source['DocumentUID']) + '))',
        "equals(body('Read_baseline_before')?['ETag'],body('Read_baseline_after')?['ETag'])",
    ]
    verified_request += baseline_metadata_checks(['Read_baseline_before', 'Read_baseline_after'])
    for key, expected in {'DocumentUID': source['DocumentUID'], 'DocumentReference': source['DocumentReference'],
                          'ReviewedVersionRef': source['ReviewedVersionRef'], 'DocumentSHA256': source['sha256']}.items():
        verified_request.append('equals(' + request + "?['" + key + "']," + literal(expected) + ')')
    source_uri = "_api/web/GetFileById('" + source['UniqueId'] + "')"
    source_actions = {
        'Read_source_before': read(source_uri + '?$select=UniqueId,ETag,Length'),
        'Read_source_content': read(source_uri + '/$value', 'Read_source_before'),
        'Read_source_after': read(source_uri + '?$select=UniqueId,ETag,Length', 'Read_source_content'),
        'Recheck_case': read(selected_uri, 'Read_source_after'),
        'Recheck_baseline': read(file_read_uri('?$select=UniqueId,ETag'), 'Recheck_case'),
    }
    final_checks = [
        "equals(outputs('Read_selected_case')?['headers']?['ETag'],outputs('Recheck_case')?['headers']?['ETag'])",
        "not(empty(outputs('Read_selected_case')?['headers']?['ETag']))",
        "not(equals(outputs('Read_selected_case')?['headers']?['ETag'],'*'))",
        "equals(body('Read_baseline_after')?['ETag'],body('Recheck_baseline')?['ETag'])",
    ]
    final_checks += baseline_metadata_checks(['Read_baseline_before', 'Read_baseline_after', 'Recheck_baseline'])
    for name in ['Read_source_before', 'Read_source_after']:
        final_checks.append("equals(body('" + name + "')?['ETag']," + literal(source['ETag']) + ')')
        final_checks.append("equals(body('" + name + "')?['UniqueId']," + literal(source['UniqueId']) + ')')
    decoded = "if(contains(body('Read_source_content'),'$content'),base64ToString(body('Read_source_content')?['$content']),string(body('Read_source_content')))"
    final_checks.append('equals(' + decoded + ',' + literal(source['content']) + ')')
    context = {'contextValid': True, 'CaseUID': "@body('Read_selected_case')?['CaseUID']",
               'occurrence': '@' + request + "?['occurrenceReference']",
               'nativeItemId': "@body('Read_selected_case')?['Id']",
               'caseETag': "@outputs('Read_selected_case')?['headers']?['ETag']",
               'baselineReference': "@body('Read_selected_case')?['sourceBaselineRef']",
               'baselineETag': "@body('Read_baseline_after')?['ETag']",
               'baselineUniqueId': "@body('Read_baseline_after')?['UniqueId']",
               'selectedTriggerItemId': "@int(triggerBody()?['entity']?['ID'])",
               'scope': {'CaseUID': "@body('Read_selected_case')?['CaseUID']", 'DocumentReference': source['DocumentReference'],
                         'ReviewedVersionRef': source['ReviewedVersionRef'], 'DocumentSHA256': source['sha256']},
               'sourcePins': {'UniqueId': source['UniqueId'], 'ETag': source['ETag'], 'DocumentUID': source['DocumentUID']},
               'limits': {'fictionalOnly': True, 'fixedQualifiedSourceProfile': True, 'genericExtractionQualified': False,
                          'ordinaryUserAccessQualified': False, 'ownershipEvidenceChecked': False, 'grantsAuthority': False},
               'businessPrerequisites': 'Not evaluated; a proposed role is not ownership acceptance or readiness',
               'writeCount': 0, 'realPolicyEffects': False, 'asOfUtc': '@utcNow()', 'runId': "@workflow()?['run']?['name']"}
    source_actions['Verify_source_and_case'] = condition(final_checks, 'Recheck_baseline', {'Selected_case_context': compose(context)}, 'Source version/content or case/baseline changed')
    baseline['Verify_request'] = condition(verified_request, 'Read_baseline_after', source_actions, 'Saved request, case, occurrence or source identity mismatch')
    actions['Verify_baseline_boundary'] = condition(checks, 'Read_selected_case', baseline, "@if(or(lessOrEquals(int(triggerBody()?['entity']?['ID']),0),not(equals(body('Read_selected_case')?['Id'],int(triggerBody()?['entity']?['ID'])))),'Selected native item identity mismatch','Unsupported case baseline; select a qualified operator-created fictional occurrence')")
    definition['actions'] = {
        'Resolve_context': {'type': 'Scope', 'actions': actions, 'runAfter': {}},
        'Held_unverified_read': {'type': 'Compose', 'runAfter': {'Resolve_context': ['Failed', 'TimedOut']},
                                 'inputs': {'contextValid': False, 'reason': 'Selected native case/request could not be verified; no fallback or broader search',
                                            'writeCount': 0, 'realPolicyEffects': False, 'asOfUtc': '@utcNow()'}},
    }
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('observed_trigger_definition', 'binding', 'output'):
        parser.add_argument(key, type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(build(json.loads(args.observed_trigger_definition.read_text()), json.loads(args.binding.read_text())), indent=2) + '\n')

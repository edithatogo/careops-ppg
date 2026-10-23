"""Connect reviewed native selected context to a fictional ownership offer.

No native I/O. Reuses a privately approved context definition and the target
flow's existing connection. Never consumes operator-pasted context or accepts a role.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path


def build(context, target, binding):
    definition = context['properties']['definition']
    digest = hashlib.sha256(json.dumps(definition, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if binding.get('qualificationOnly') is not True or digest != binding.get('approvedContextDefinitionSHA256'):
        raise ValueError('Use the exact privately reviewed selected-context definition')
    source_ref = context['properties']['connectionReferences']['shared_sharepointonline']
    target_ref = target['properties']['connectionReferences']['shared_sharepointonline']
    if source_ref['connectionName'] != target_ref['connectionName']:
        raise ValueError('Target must retain the already qualified same connection')
    out = {'properties': {'displayName': 'PPG Lifecycle | FICTIONAL selected ownership offer', 'state': 'Stopped',
                          'definition': copy.deepcopy(definition),
                          'connectionReferences': {'shared_sharepointonline': copy.deepcopy(target_ref)}}}
    out['properties']['definition']['triggers']['manual']['runtimeConfiguration'] = {'concurrency': {'runs': 1}}
    actions = out['properties']['definition']['actions']['Resolve_context']['actions']
    request_actions = actions['Verify_baseline_boundary']['actions']
    source_actions = request_actions['Verify_request']['actions']
    success = source_actions['Verify_source_and_case']['actions']
    eventbase = binding['eventListUri']
    def existing_event_creates(node):
        if isinstance(node, dict):
            params = node.get('inputs', {}).get('parameters', {}) if isinstance(node.get('inputs'), dict) else {}
            if params.get('parameters/method') == 'POST':
                yield params.get('parameters/uri')
            for value in node.values():
                yield from existing_event_creates(value)
        elif isinstance(node, list):
            for value in node:
                yield from existing_event_creates(value)
    if (not eventbase.endswith('/items')
            or eventbase not in list(existing_event_creates(target['properties']['definition']))):
        raise ValueError('Use the existing privately qualified event list')
    reference_read = actions['Read_selected_case']
    def http(uri, previous=None, method='GET', body=None):
        a = copy.deepcopy(reference_read)
        a['runAfter'] = {previous: ['Succeeded']} if previous else {}
        p = a['inputs']['parameters']; p['parameters/uri'] = uri; p['parameters/method'] = method
        p['parameters/headers'] = {'Accept': 'application/json;odata=nometadata', 'Content-Type': 'application/json;odata=nometadata'}
        if body is not None: p['parameters/body'] = body
        return a
    def compose(v, previous=None):
        return {'type': 'Compose', 'inputs': v, 'runAfter': {previous: ['Succeeded']} if previous else {}}
    def held(reason):
        return compose({'offerRecorded': False, 'qualified': False, 'eventWriteCount': 0, 'effectState': 'not-attempted', 'reason': reason, 'caseWrites': 0, 'sourceWrites': 0,
                        'ownershipAccepted': False, 'realPolicyEffects': False, 'asOfUtc': '@utcNow()'})
    def condition(clauses, previous, yes, reason):
        return {'type': 'If', 'expression': '@and(' + ','.join(clauses) + ')',
                'runAfter': {previous: ['Succeeded']}, 'actions': yes,
                'else': {'actions': {'Offer_held_' + previous: held(reason)}}}
    request = "outputs('Parse_baseline')?['request']"
    context_ref = "outputs('Selected_case_context')"
    payload = {'Title': "@concat('FICTIONAL ownership offer — '," + context_ref + "?['CaseUID'])",
               'EventUID': "@concat('LC02-OP-OFFER-'," + request + "?['requestReference'])",
               'CaseUID': '@' + context_ref + "?['scope']?['CaseUID']",
               'DocumentReference': '@' + context_ref + "?['scope']?['DocumentReference']",
               'ReviewedVersionRef': '@' + context_ref + "?['scope']?['ReviewedVersionRef']",
               'DocumentSHA256': '@' + context_ref + "?['scope']?['DocumentSHA256']",
               'SubjectRole': '@' + request + "?['proposedRole']", 'FromRole': 'FICTIONAL initiating role',
               'EventKind': 'Ownership handoff', 'RecordState': 'Proposed', 'ConditionsState': 'None recorded',
               'ActorName': 'FICTIONAL technical operator; no real role transfer',
               'EvidenceReference': '@' + context_ref + "?['baselineReference']", 'OccurredOn': '@utcNow()',
               'Summary': "@concat('FICTIONAL offer from selected native case ',string(" + context_ref + "?['nativeItemId']),'; request '," + request + "?['requestReference'],'; no assignment')",
               'NextAction': 'Record explicit acceptance or decline against this offer; no assignment is implied',
               'FictionalTest': True}
    query = "@concat('" + eventbase.replace("'", "''") + "?$filter=EventUID eq ',decodeUriComponent('%27'),outputs('Offer_payload')?['EventUID'],decodeUriComponent('%27'))"
    work = {'Offer_payload': compose(payload), 'Find_offer': http(query, 'Offer_payload')}
    def refresh(name, source_name, previous):
        work[name] = copy.deepcopy(source_actions[source_name]); work[name]['runAfter'] = {previous: ['Succeeded']}
    refresh('Offer_case_before', 'Recheck_case', 'Find_offer')
    refresh('Offer_source_before', 'Read_source_after', 'Offer_case_before')
    refresh('Offer_baseline_before', 'Recheck_baseline', 'Offer_source_before')
    def stable(case, source, baseline):
        return ["equals(outputs('" + case + "')?['headers']?['ETag']," + context_ref + "?['caseETag'])",
                "equals(body('" + source + "')?['ETag']," + context_ref + "?['sourcePins']?['ETag'])",
                "equals(body('" + source + "')?['UniqueId']," + context_ref + "?['sourcePins']?['UniqueId'])",
                "equals(body('" + baseline + "')?['ETag']," + context_ref + "?['baselineETag'])",
                "equals(body('" + baseline + "')?['UniqueId']," + context_ref + "?['baselineUniqueId'])"]
    apply = {'Ensure_offer': {'type': 'If', 'expression': "@equals(length(body('Find_offer')?['value']),0)",
                             'runAfter': {}, 'actions': {'Create_offer': http(eventbase, method='POST', body="@string(outputs('Offer_payload'))")}, 'else': {'actions': {}}},
             'Read_offer': http(query, 'Ensure_offer')}
    clauses = ["equals(length(body('Read_offer')?['value']),1)"]
    clauses += ["equals(first(body('Read_offer')?['value'])?['" + k + "'],outputs('Offer_payload')?['" + k + "'])" for k in payload if k != 'OccurredOn']
    after = {}
    for name, source_name, previous in [('Offer_case_after', 'Recheck_case', None),
                                        ('Offer_source_after', 'Read_source_after', 'Offer_case_after'),
                                        ('Offer_baseline_after', 'Recheck_baseline', 'Offer_source_after')]:
        after[name] = copy.deepcopy(source_actions[source_name]); after[name]['runAfter'] = {previous: ['Succeeded']} if previous else {}
    receipt = {'offerRecorded': True, 'qualified': True, 'EventUID': "@outputs('Offer_payload')?['EventUID']",
               'nativeEventId': "@first(body('Read_offer')?['value'])?['Id']", 'scope': '@' + context_ref + "?['scope']",
               'createdCount': "@if(equals(length(body('Find_offer')?['value']),0),1,0)",
               'ownershipAccepted': False, 'caseWrites': 0, 'sourceWrites': 0, 'requestWrites': 0, 'notifications': 0,
               'actorAuthorityQualified': False, 'realPolicyEffects': False,
               'runId': "@workflow()?['run']?['name']", 'asOfUtc': '@utcNow()'}
    after['Verify_offer_after'] = condition(stable('Offer_case_after', 'Offer_source_after', 'Offer_baseline_after'),
        'Offer_baseline_after', {'Native_offer_receipt': compose(receipt)}, 'Offer exists but case/source/baseline changed; retain event and reconcile')
    after['Verify_offer_after']['else']['actions'] = {'Offer_after_drift': compose({'offerRecorded': True, 'qualified': False, 'eventReference': "@outputs('Offer_payload')?['EventUID']", 'eventWriteCount': "@if(equals(length(body('Find_offer')?['value']),0),1,0)", 'effectState': 'retained-event-context-changed', 'reason': 'Retain the verified event and reconcile changed case/source/baseline; no role acceptance', 'caseWrites': 0, 'sourceWrites': 0, 'requestWrites': 0, 'ownershipAccepted': False, 'realPolicyEffects': False})}
    apply['Verify_offer'] = condition(clauses, 'Read_offer', after, 'Retained offer conflicts with the verified selected request; no overwrite')
    apply['Verify_offer']['else']['actions'] = {'Offer_readback_unverified': compose({'offerRecorded': None, 'qualified': False, 'eventReference': "@outputs('Offer_payload')?['EventUID']", 'eventWriteCount': None, 'effectState': 'unverified-reconcile-before-retry', 'reason': 'Inspect existing event and actual create action; do not overwrite or blindly resubmit', 'caseWrites': 0, 'sourceWrites': 0, 'requestWrites': 0, 'ownershipAccepted': False, 'realPolicyEffects': False})}
    work['Verify_offer_before'] = condition(stable('Offer_case_before', 'Offer_source_before', 'Offer_baseline_before'),
        'Offer_baseline_before', apply, 'Selected context changed before event execution; no offer write')
    stage = ["equals(" + context_ref + "?['contextValid'],true)",
             "equals(body('Read_selected_case')?['caseStatus'],'Initiated — FICTIONAL')",
             "equals(body('Read_selected_case')?['accountableRole'],concat('UNACCEPTED — proposed fictional role: '," + request + "?['proposedRole']))",
             "startsWith(string(" + request + "?['proposedRole']),'FICTIONAL')",
             "lessOrEquals(length(string(" + request + "?['proposedRole'])),200)",
             "startsWith(string(" + request + "?['requestReference']),'LC02-OP-')",
             "lessOrEquals(length(string(" + request + "?['requestReference'])),64)"]
    # Keep the reviewed context graph intact and avoid a ninth nesting level.
    # Stage and fresh-token checks gate the only event-create branch together.
    work['Offer_payload']['runAfter'] = {'Selected_case_context': ['Succeeded']}
    work['Verify_offer_before']['expression'] = '@and(' + ','.join(stage + stable('Offer_case_before', 'Offer_source_before', 'Offer_baseline_before')) + ')'
    success.update(work)
    catch = out['properties']['definition']['actions']['Held_unverified_read']['inputs']
    catch.pop('writeCount', None)
    catch.update(offerRecorded=None, qualified=False, eventWriteCount=None, effectState='unverified-reconcile-before-retry',
                 reason='Context or offer execution could not be verified; preserve any retained event and inspect the native run before retry',
                 caseWrites=0, sourceWrites=0, requestWrites=0, ownershipAccepted=False)
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--context', required=True); p.add_argument('--target', required=True); p.add_argument('--binding', required=True); p.add_argument('--output', required=True); a = p.parse_args()
    Path(a.output).write_text(json.dumps(build(json.loads(Path(a.context).read_text()), json.loads(Path(a.target).read_text()), json.loads(Path(a.binding).read_text())), indent=2) + '\n')

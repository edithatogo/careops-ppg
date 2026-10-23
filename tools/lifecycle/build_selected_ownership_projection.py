"""Build a bounded fictional ownership projection; native bindings stay private.

Retains a create-only before journal and commit. An uncommitted journal holds
for reconciliation, never automatic resubmission of an uncertain case mutation.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path


def build(context, target, binding):
    definition = context['properties']['definition']
    digest = hashlib.sha256(json.dumps(definition, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if binding.get('qualificationOnly') is not True or digest != binding['approvedContextDefinitionSHA256']:
        raise ValueError('Exact approved context required')
    refs = target['properties']['connectionReferences']
    if refs['shared_sharepointonline']['connectionName'] != context['properties']['connectionReferences']['shared_sharepointonline']['connectionName']:
        raise ValueError('Retain qualified connection')
    for key in ('expectedCaseUID', 'expectedCaseETag', 'expectedResponseUID', 'eventListUri', 'caseItemUri', 'folderUri', 'journalName', 'commitName'):
        if not binding.get(key) or binding[key] == '*':
            raise ValueError('Explicit nonwildcard private binding required: ' + key)
    if not binding['expectedCaseUID'].startswith('LC-FICTIONAL-OP-') or not binding['expectedResponseUID'].startswith('LC02-OP-RESP-'):
        raise ValueError('Fictional operator profile only')
    if any('/' in binding[k] or "'" in binding[k] for k in ('journalName', 'commitName')):
        raise ValueError('Single safe receipt filenames required')
    out = {'properties': {'displayName': 'PPG Lifecycle | FICTIONAL selected ownership projection', 'state': 'Stopped',
        'definition': copy.deepcopy(definition), 'connectionReferences': copy.deepcopy(refs)}}
    d = out['properties']['definition']; d['triggers']['manual']['runtimeConfiguration'] = {'concurrency': {'runs': 1}}
    a = d['actions']; a.pop('Held_unverified_read')
    template = copy.deepcopy(a['Resolve_context']['actions']['Read_selected_case'])
    def action(uri, previous, method='GET', body=None, headers=None):
        r = copy.deepcopy(template); q = r['inputs']['parameters']; q['parameters/uri'] = uri; q['parameters/method'] = method
        q['parameters/headers'] = {'Accept': 'application/json;odata=nometadata', **(headers or {})}
        if body is not None: q['parameters/body'] = body
        r['runAfter'] = {previous: ['Succeeded']} if previous else {}
        if method != 'GET': r['inputs']['retryPolicy'] = {'type': 'none'}
        return r
    def compose(body, previous=None):
        return {'type': 'Compose', 'inputs': body, 'runAfter': {previous: ['Succeeded']} if previous else {}}
    def guard(expr, yes, no, previous=None):
        return {'type': 'If', 'expression': expr, 'actions': yes, 'else': {'actions': no},
            'runAfter': {previous: ['Succeeded']} if previous else {}}
    def held(reason, count=0):
        return compose({'qualified': False, 'caseWriteCount': count, 'realResponsibilityTransferred': False, 'reason': reason})
    def allof(checks): return '@and(' + ','.join(checks) + ')'
    def eq(left, right): return 'equals(' + left + ',' + right + ')'
    def literal(value): return "'" + value.replace("'", "''") + "'"
    c = "outputs('Selected_case_context')"; req = "outputs('Parse_baseline')?['request']"
    role = req + "?['proposedRole']"; scope = c + "?['scope']"
    caseuri = binding['caseItemUri']; eventbase = binding['eventListUri']; folder = binding['folderUri']
    def query(field, expression):
        return "@concat(" + literal(eventbase + '?$filter=' + field + ' eq ') + ",decodeUriComponent('%27')," + expression + ",decodeUriComponent('%27'))"
    offeruid = "concat('LC02-OP-OFFER-'," + req + "?['requestReference'])"
    a['Read_projection_case'] = action(caseuri, 'Resolve_context')
    a['Read_projection_offer'] = action(query('EventUID', offeruid), 'Read_projection_case')
    a['Read_projection_responses'] = action(query('ParentEventUID', offeruid), 'Read_projection_offer')
    for name, filename, prev in [('Read_projection_journal', binding['journalName'], 'Read_projection_responses'), ('Read_projection_commit', binding['commitName'], 'Read_projection_journal')]:
        a[name] = action(folder + "/Files?$filter=Name eq '" + filename + "'&$select=Name,UniqueId,ETag", prev)
    def complete_collection(name):
        return ["empty(body('" + name + "')?['" + key + "'])"
                for key in ('odata.nextLink', '@odata.nextLink', 'nextLink', '__next')]
    complete = []
    for name in ('Read_projection_offer', 'Read_projection_responses', 'Read_projection_journal', 'Read_projection_commit'):
        complete += complete_collection(name)
        complete.append("lessOrEquals(length(body('" + name + "')?['value']),1)")
    a['Projection_queries_complete'] = compose(allof(complete), 'Read_projection_commit')
    parent = "first(body('Read_projection_offer')?['value'])"; response = "first(body('Read_projection_responses')?['value'])"
    basechecks = [eq("outputs('Projection_queries_complete')", 'true'), eq(c + "?['contextValid']", 'true'), eq(c + "?['CaseUID']", literal(binding['expectedCaseUID'])),
        eq(c + "?['nativeItemId']", "body('Read_projection_case')?['Id']"),
        eq(c + "?['CaseUID']", "body('Read_projection_case')?['CaseUID']"),
        eq(c + "?['caseETag']", "outputs('Read_projection_case')?['headers']?['ETag']"),
        eq("length(body('Read_projection_offer')?['value'])", '1'), eq("length(body('Read_projection_responses')?['value'])", '1'),
        eq(parent + "?['EventUID']", offeruid), eq(parent + "?['RecordState']", "'Proposed'"),
        eq(response + "?['ParentEventUID']", offeruid), eq(response + "?['EventUID']", literal(binding['expectedResponseUID'])),
        eq(response + "?['RecordState']", "'Accepted'"), eq(response + "?['ConditionsState']", "'None recorded'"),
        "startsWith(string(" + role + "),'FICTIONAL')",
        "empty(" + response + "?['SupersedesEventUID'])",
        "empty(" + parent + "?['SupersedesEventUID'])"]
    basechecks += ["not(empty(trim(string(" + response + "?['" + k + "']))))" for k in ('Summary', 'EvidenceReference', 'NextAction')]
    for item in (parent, response):
        basechecks += [eq(item + "?['FictionalTest']", 'true'), eq(item + "?['EventKind']", "'Ownership handoff'"),
            eq(item + "?['SubjectRole']", role), eq(item + "?['FromRole']", "'FICTIONAL initiating role'")]
        basechecks += [eq(item + "?['" + k + "']", scope + "?['" + k + "']") for k in ('CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256')]
    # Fresh full-item reads bracket the event evidence with opaque connector ETags.
    def itemuri(item): return "@concat(" + literal(eventbase + '(') + ",string(" + item + "?['Id']),')')"
    casekeys = ['Id', 'CaseUID', 'Title', 'linkedDocumentUIDs', 'sourceBaselineRef', 'proposedOutcome', 'nextAction', 'targetDate', 'evidenceDraftLink', 'Created', 'GUID', 'AuthorId']
    def protected_case(value):
        return "union(" + value + ",json('{\"odata.id\":null,\"odata.etag\":null,\"Modified\":null,\"EditorId\":null,\"OData__UIVersionString\":null,\"accountableRole\":null,\"caseStatus\":null}'))"
    def exact_case(value):
        return "union(" + value + ",json('{\"odata.id\":null}'))"
    mutation = {'accountableRole': '@' + role, 'caseStatus': 'Ownership accepted — FICTIONAL'}
    new = {}
    new['Projection_journal'] = compose({'kind': 'fictional-ownership-projection-before-v1', 'runId': "@workflow()?['run']?['name']",
        'beforeCase': "@body('Read_projection_case')", 'beforeCaseETag': "@outputs('Read_projection_case')?['headers']?['ETag']",
        'context': '@' + c, 'offer': '@' + parent, 'response': '@' + response, 'proposedPatch': mutation})
    new['Create_projection_journal'] = action(folder + "/Files/add(url='" + binding['journalName'] + "',overwrite=false)", 'Projection_journal', 'POST', "@string(outputs('Projection_journal'))", {'Content-Type': 'application/json'})
    new['Projection_case_before'] = action(caseuri, 'Create_projection_journal')
    new['Projection_offer_before'] = action(itemuri(parent), 'Projection_case_before')
    new['Projection_response_before'] = action(itemuri(response), 'Projection_offer_before')
    # Same source/baseline URIs as the reviewed context, with fresh metadata reads.
    contextactions = a['Resolve_context']['actions']['Verify_baseline_boundary']['actions']['Verify_request']['actions']
    sourceuri = contextactions['Read_source_before']['inputs']['parameters']['parameters/uri']
    baselineuri = a['Resolve_context']['actions']['Verify_baseline_boundary']['actions']['Read_baseline_before']['inputs']['parameters']['parameters/uri']
    def fresh_reads(actions, prefix, previous):
        actions[prefix + '_source'] = action(sourceuri, previous)
        actions[prefix + '_baseline'] = action(baselineuri, prefix + '_source')
    fresh_reads(new, 'Projection_before', 'Projection_response_before')
    def pins(prefix):
        return [eq("body('" + prefix + "_source')?['ETag']", c + "?['sourcePins']?['ETag']"),
            eq("toLower(body('" + prefix + "_source')?['UniqueId'])", "toLower(" + c + "?['sourcePins']?['UniqueId'])"),
            eq("body('" + prefix + "_baseline')?['ETag']", c + "?['baselineETag']"),
            eq("body('" + prefix + "_baseline')?['UniqueId']", c + "?['baselineUniqueId']")]
    eventkeys = ['Id', 'EventUID', 'ParentEventUID', 'CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256', 'RecordState', 'EventKind', 'FictionalTest', 'SubjectRole', 'FromRole', 'ConditionsState', 'Summary', 'EvidenceReference', 'NextAction', 'OccurredOn', 'SupersedesEventUID']
    beforechecks = pins('Projection_before') + [eq("outputs('Projection_case_before')?['headers']?['ETag']", literal(binding['expectedCaseETag']))]
    for name, item in [('Projection_offer_before', parent), ('Projection_response_before', response)]:
        beforechecks += [eq("body('" + name + "')?['" + k + "']", item + "?['" + k + "']") for k in eventkeys]
        beforechecks += ["not(empty(outputs('" + name + "')?['headers']?['ETag']))", "not(equals(outputs('" + name + "')?['headers']?['ETag'],'*'))"]
    write = {'Apply_projection': action(caseuri, None, 'POST', "@string(outputs('Projection_journal')?['proposedPatch'])", {'Content-Type': 'application/json;odata=nometadata', 'X-HTTP-Method': 'MERGE', 'IF-MATCH': "@outputs('Projection_case_before')?['headers']?['ETag']"})}
    write['Projection_case_after'] = action(caseuri, 'Apply_projection')
    write['Projection_offer_after'] = action(itemuri(parent), 'Projection_case_after')
    write['Projection_response_after'] = action(itemuri(response), 'Projection_offer_after')
    write['Projection_response_history_after'] = action(query('ParentEventUID', offeruid), 'Projection_response_after')
    fresh_reads(write, 'Projection_after', 'Projection_response_history_after')
    postchecks = pins('Projection_after') + [eq("body('Projection_case_after')?['accountableRole']", role),eq("body('Projection_case_after')?['caseStatus']", "'Ownership accepted — FICTIONAL'"),eq("length(body('Projection_response_history_after')?['value'])", '1'),eq("first(body('Projection_response_history_after')?['value'])?['EventUID']", literal(binding['expectedResponseUID']))]
    postchecks += complete_collection('Projection_response_history_after')
    postchecks += [eq(protected_case("body('Projection_case_after')"), protected_case("body('Read_projection_case')")),
                   "not(equals(outputs('Projection_case_after')?['headers']?['ETag'],'*'))"]
    postchecks += [eq("body('Projection_case_after')?['" + k + "']", "body('Read_projection_case')?['" + k + "']") for k in casekeys]
    postchecks += [eq("outputs('Projection_" + k + "_before')?['headers']?['ETag']", "outputs('Projection_" + k + "_after')?['headers']?['ETag']") for k in ('offer','response')]
    postchecks += ["not(empty(outputs('Projection_case_after')?['headers']?['ETag']))", "not(equals(outputs('Projection_case_after')?['headers']?['ETag'],outputs('Projection_case_before')?['headers']?['ETag']))"]
    committed = {'Projection_commit': compose({'kind': 'fictional-ownership-projection-commit-v1', 'runId': "@workflow()?['run']?['name']", 'CaseUID': '@'+c+"?['CaseUID']", 'responseUID': literal(binding['expectedResponseUID']).strip("'"), 'afterCase': "@body('Projection_case_after')", 'afterCaseETag': "@outputs('Projection_case_after')?['headers']?['ETag']", 'context': '@'+c, 'offerETag': "@outputs('Projection_offer_after')?['headers']?['ETag']", 'responseETag': "@outputs('Projection_response_after')?['headers']?['ETag']", 'caseWriteCount': 1, 'realResponsibilityTransferred': False})}
    committed['Create_projection_commit'] = action(folder + "/Files/add(url='" + binding['commitName'] + "',overwrite=false)", 'Projection_commit','POST',"@string(outputs('Projection_commit'))",{'Content-Type':'application/json'})
    committed['Read_saved_projection_commit'] = action(folder + "/Files('" + binding['commitName'] + "')/$value", 'Create_projection_commit')
    committed['Parse_saved_projection_commit'] = compose("@if(contains(body('Read_saved_projection_commit'),'$content'),json(base64ToString(body('Read_saved_projection_commit')?['$content'])),json(string(body('Read_saved_projection_commit'))))", 'Read_saved_projection_commit')
    saved_matches = eq("outputs('Parse_saved_projection_commit')", "outputs('Projection_commit')")
    committed['Native_projection_receipt'] = compose({'qualified': '@' + saved_matches,
        'caseWriteCount': '@if(' + saved_matches + ',1,null)', 'caseOwnershipProjected': '@' + saved_matches,
        'reconcileBeforeRetry': '@not(' + saved_matches + ')',
        'realResponsibilityTransferred': False, 'runId': "@workflow()?['run']?['name']"}, 'Parse_saved_projection_commit')
    write['Verify_projection_after'] = guard(allof(postchecks), committed, {'Hold_uncertain_projection': held('Case mutation may exist; retain journal and reconcile; no automatic resubmit', None)}, 'Projection_after_baseline')
    new['Verify_projection_before'] = guard(allof(beforechecks),write, {'Hold_stale_projection': held('Evidence changed after journal; preserve it for reconciliation')},'Projection_before_baseline')
    initialchecks = [eq("length(body('Read_projection_journal')?['value'])", '0'),eq("outputs('Read_projection_case')?['headers']?['ETag']",literal(binding['expectedCaseETag'])),eq("body('Read_projection_case')?['caseStatus']", "'Initiated — FICTIONAL'"),eq("body('Read_projection_case')?['accountableRole']","concat('UNACCEPTED — proposed fictional role: ',"+role+')')]
    initial = {'Verify_initial_projection':guard(allof(initialchecks),new,{'Hold_existing_journal_or_stage':held('Uncommitted journal or case-stage/version mismatch; reconcile before retry',None)})}
    replay = {'Read_committed_projection':action(folder+"/Files('"+binding['commitName']+"')/$value",None)}
    replay['Parse_committed_projection'] = compose("@if(contains(body('Read_committed_projection'),'$content'),json(base64ToString(body('Read_committed_projection')?['$content'])),json(string(body('Read_committed_projection'))))",'Read_committed_projection')
    commit = "outputs('Parse_committed_projection')"
    replaychecks = [eq("length(body('Read_projection_journal')?['value'])",'1'),eq(commit+"?['kind']","'fictional-ownership-projection-commit-v1'"),eq(commit+"?['CaseUID']",c+"?['CaseUID']"),eq(commit+"?['responseUID']",literal(binding['expectedResponseUID'])),eq(commit+"?['afterCaseETag']","outputs('Read_projection_case')?['headers']?['ETag']"),eq("body('Read_projection_case')?['accountableRole']",role),eq("body('Read_projection_case')?['caseStatus']","'Ownership accepted — FICTIONAL'")]
    replaychecks += [eq(commit+"?['afterCase']?['"+k+"']","body('Read_projection_case')?['"+k+"']") for k in casekeys]
    replaychecks += [eq(exact_case(commit + "?['afterCase']"), exact_case("body('Read_projection_case')"))]
    replay['Projection_replay_offer'] = action(itemuri(parent), 'Parse_committed_projection')
    replay['Projection_replay_response'] = action(itemuri(response), 'Projection_replay_offer')
    replaychecks += [eq(commit+"?['offerETag']","outputs('Projection_replay_offer')?['headers']?['ETag']"),eq(commit+"?['responseETag']","outputs('Projection_replay_response')?['headers']?['ETag']")]
    replaychecks += [eq(commit+"?['context']?['"+k+"']",c+"?['"+k+"']") for k in ('baselineReference','baselineUniqueId','baselineETag')]
    replay['Verify_committed_projection'] = guard(allof(replaychecks),{'Native_projection_replay':compose({'qualified':True,'caseWriteCount':0,'caseOwnershipProjected':True,'realResponsibilityTransferred':False,'originalRunId':'@'+commit+"?['runId']"})},{'Hold_changed_commit':held('Retained projection does not match current evidence; no writes')},'Projection_replay_response')
    branch = {'Choose_projection_path':guard('@' + eq("length(body('Read_projection_commit')?['value'])",'1'),replay,initial)}
    a['Verify_projection_evidence'] = guard(allof(basechecks),branch,{'Hold_invalid_projection':held('Unique matching fictional acceptance and context required')},'Projection_queries_complete')
    a['Projection_error'] = compose({'qualified':False,'caseWriteCount':None,'effectState':'unverified-reconcile-before-retry','realResponsibilityTransferred':False,'reason':'Inspect journal/native run; do not repeat an uncertain case write'})
    a['Projection_error']['runAfter'] = {'Verify_projection_evidence':['Failed','TimedOut','Skipped']}
    return out


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('context','target','binding','output'):p.add_argument('--'+k,required=True,type=Path)
    args=p.parse_args();args.output.write_text(json.dumps(build(json.loads(args.context.read_text()),json.loads(args.target.read_text()),json.loads(args.binding.read_text())),indent=2)+'\n')

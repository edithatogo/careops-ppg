"""Extend the existing fictional initiation profile with retained review lineage.

Local builder only. Original source baseline fields retain their existing
meaning; completed prepared/issued revisions are separate provenance. Native
storage, authentication, actual closure and operator acceptance are not supplied.
"""
import base64
import copy
import datetime
import hashlib
import json
import re
from uuid import UUID
from build_operator_initiation import build as initiation_build


def build(reference, binding):
    if binding.get('qualificationOnly') is not True:
        raise ValueError('Explicit fictional next-occurrence binding required')
    inputs = binding.get('canonicalInputs', {})
    if set(inputs) != {'text', 'text_1', 'text_2', 'text_3', 'text_4'}:
        raise ValueError('Existing five initiation inputs required')
    for key, prefix in [('text', 'LC02-OP-'), ('text_1', 'OCC-')]:
        if not re.fullmatch(re.escape(prefix) + r'[A-Za-z0-9_-]{1,50}', inputs[key]):
            raise ValueError('Distinct bounded request and occurrence keys required')
    for key in ['text_2', 'text_3', 'text_4']:
        if not isinstance(inputs[key], str) or not inputs[key].startswith('FICTIONAL'):
            raise ValueError('Explicit fictional outcome, action and proposed role required')
    if inputs['text_4'] != 'FICTIONAL Case9 next-occurrence test role':
        raise ValueError('Explicitly commissioned proposed test role required')
    if binding.get('targetDateFieldType') != 'Text':
        raise ValueError('Existing targetDate Text field required; no timestamp or timezone coercion')
    origin = binding.get('completedReview', {})
    parent = origin.get('case', {})
    if not str(parent.get('CaseUID', '')).startswith('LC-FICTIONAL-OP-') or parent.get('caseStatus') != 'Review closed — FICTIONAL':
        raise ValueError('Retained closed fictional occurrence required')
    if parent['CaseUID'] == 'LC-FICTIONAL-OP-' + inputs['text_1']:
        raise ValueError('Next occurrence cannot reuse completed CaseUID')
    if binding.get('completedCaseETag') in (None, '', '*'):
        raise ValueError('Exact completed case token required')
    uri = binding.get('completedCaseUri', '')
    if not re.fullmatch(r"_api/web/lists\(guid'[0-9a-fA-F-]{36}'\)/items\([1-9][0-9]*\)", uri):
        raise ValueError('Literal completed native item required')
    date = binding.get('date', {})
    commit = binding.get('closureCommit', {})
    for label, file in [('date', date), ('closure', commit)]:
        meta = file.get('metadata', {})
        if not re.fullmatch(r'[0-9a-fA-F-]{36}', meta.get('UniqueId', '')) or meta.get('ETag') in (None, '', '*'):
            raise ValueError('Actual retained ' + label + ' file identity/token required')
        UUID(meta['UniqueId'])
        if not isinstance(meta.get('Length'), int) or not meta.get('UIVersionLabel'):
            raise ValueError('Retained file version/length required')
        try:
            raw = base64.b64decode(file['contentBase64'], validate=True)
            parsed = json.loads(raw)
        except (KeyError, ValueError, TypeError) as error:
            raise ValueError('Exact retained JSON bytes required') from error
        if len(raw) != meta['Length'] or hashlib.sha256(raw).hexdigest() != file.get('SHA256') or parsed != file.get('record'):
            raise ValueError('Retained JSON bytes/hash/record mismatch')
    record = date['record']; closed = commit['record']; contract = closed.get('contract', {})
    observation = contract.get('observation', {})
    if (closed.get('kind') != 'fictional-prepared-closure-commit-v1'
            or contract.get('CaseUID') != parent['CaseUID'] or closed.get('realPolicyEffects') is not False
            or closed.get('afterProof', {}).get('afterCase') != {**parent, 'odata.id': None}
            or closed['afterProof'].get('afterCaseETag') != binding['completedCaseETag']):
        raise ValueError('Actual closure commit must retain this closed case and token')
    if (record.get('FictionalTest') is not True or record.get('notOperational') is not True or record.get('policyAuthorityGranted') is not False or record.get('scope') != observation.get('preparedScope')
            or record.get('reviewDate') != observation.get('nextReviewDate')
            or record.get('ruleReference') != observation.get('nextReviewRuleReference')
            or date['metadata']['UniqueId'] != observation.get('nextReviewEvidenceFileUID')):
        raise ValueError('Explicit fictional date/rule provenance must match closure')
    review_date = record['reviewDate']
    if not isinstance(review_date, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', review_date):
        raise ValueError('Explicit calendar review date in YYYY-MM-DD form required; no coercion')
    datetime.date.fromisoformat(review_date)
    if not isinstance(record.get('ruleReference'), str) or not record['ruleReference'].startswith('fictional://'):
        raise ValueError('Explicit fictional review rule required')
    scope = observation.get('preparedScope', {})
    if (set(scope) != {'CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256'}
            or scope.get('CaseUID') != parent['CaseUID']
            or not all(isinstance(v, str) and v.strip() for v in scope.values())
            or not re.fullmatch(r'[0-9a-f]{64}', scope['DocumentSHA256'])):
        raise ValueError('Complete exact reviewed prepared scope required')
    issued = observation.get('issuedFile', {})
    if set(issued) != {'UniqueId', 'ETag'} or issued.get('ETag') in (None, '', '*'):
        raise ValueError('Exact retained issued identity/token required')
    UUID(issued['UniqueId'])
    if contract.get('kind') != 'fictional-prepared-closure-contract-v1' or contract.get('patch') != {'caseStatus': 'Review closed — FICTIONAL'}:
        raise ValueError('Existing guarded closure contract required')
    before, after = closed.get('beforeProof', {}), closed.get('afterProof', {})
    if (before.get('kind') != 'fictional-prepared-closure-before-v1'
            or after.get('kind') != 'fictional-prepared-closure-after-v1'
            or before.get('contract') != contract or after.get('contract') != contract
            or before.get('beforeCaseETag') != contract.get('initialCaseETag')
            or before.get('beforeCase', {}).get('caseStatus') != contract.get('initialCaseStatus')):
        raise ValueError('Complete durable closure before/after provenance required')
    for key in ['closureEvidenceConsistent', 'nextReviewDateProvenanceConsistent', 'nextOccurrencePrerequisitesConsistent']:
        if observation.get(key) is not True:
            raise ValueError('Qualified retained closure/date observation required')
    if origin.get('preparedScope') != observation.get('preparedScope') or origin.get('issuedFile') != observation.get('issuedFile'):
        raise ValueError('Completed prepared and issued provenance must match closure')
    init = copy.deepcopy(binding['initiation'])
    if not uri.startswith(init['caseListUri'] + '('):
        raise ValueError('Reuse existing authoritative case list')
    source = init['source']
    if any(origin.get('originalSource', {}).get(k) != source.get(k) for k in
           ['DocumentUID', 'DocumentReference', 'ReviewedVersionRef', 'sha256']):
        raise ValueError('Original source baseline cannot be replaced by reviewed/issued pins')
    out = initiation_build(reference, init)
    out['properties']['displayName'] = 'PPG Lifecycle | FICTIONAL next review occurrence'
    definition = out['properties']['definition']
    outer = definition['actions']['Validate_operator_input']
    def literal(value): return "'" + value.replace("'", "''") + "'"
    def eq(a, b): return 'equals(' + a + ',' + b + ')'
    def allof(parts): return '@and(' + ','.join(parts) + ')'
    outer['expression'] = '@and(' + outer['expression'][1:] + ',' + ','.join(
        eq("triggerBody()?['" + k + "']", literal(v)) for k, v in inputs.items()) + ')'
    original = outer['actions']
    template = original['Read_source_before']
    def http(path, previous=None, method='GET', body=None):
        action = copy.deepcopy(template)
        params = action['inputs']['parameters']
        params.update({'parameters/method': method, 'parameters/uri': path})
        params.pop('parameters/body', None)
        if body is not None: params['parameters/body'] = body
        action['inputs']['retryPolicy'] = {'type': 'none'}
        action['runAfter'] = {previous: ['Succeeded']} if previous else {}
        return action
    def comp(value, previous=None):
        return {'type': 'Compose', 'inputs': value, 'runAfter': {previous: ['Succeeded']} if previous else {}}
    def hold(reason):
        return comp({'qualified': False, 'caseCreatedCount': None, 'requestCreatedCount': None,
            'reconcileBeforeRetry': True, 'ownershipAccepted': False, 'realPolicyEffects': False, 'reason': reason})
    def gate(checks, yes, name, previous=None):
        return {'type': 'If', 'expression': allof(checks), 'actions': yes,
            'else': {'actions': {name: hold(name)}}, 'runAfter': {previous: ['Succeeded']} if previous else {}}
    def parse(action):
        return "@if(contains(body('" + action + "'),'$content'),json(base64ToString(body('" + action + "')?['$content'])),json(string(body('" + action + "'))))"
    def file_uri(file): return "_api/web/GetFileById('" + file['metadata']['UniqueId'] + "')"
    def clean(expression): return "union(" + expression + ",json('{\"odata.id\":null}'))"
    metadata_fields = ['UniqueId', 'ETag', 'UIVersionLabel', 'Length']
    origin_reads = {'Next_expected_case': comp({**parent, 'odata.id': None}),
        'Next_expected_date': comp(record, 'Next_expected_case'),
        'Next_expected_commit': comp(closed, 'Next_expected_date')}
    previous = 'Next_expected_commit'
    checks = []
    for name, file in [('date', date), ('commit', commit)]:
        before, content, after, parsed = ['Next_' + name + suffix for suffix in ['_before', '_content', '_after', '_record']]
        route = file_uri(file)
        origin_reads[before] = http(route + '?$select=' + ','.join(metadata_fields), previous)
        origin_reads[content] = http(route + '/$value', before)
        origin_reads[after] = http(route + '?$select=' + ','.join(metadata_fields), content)
        origin_reads[parsed] = comp(parse(content), after); previous = parsed
        checks += [eq("body('" + action + "')?['" + k + "']" if k != 'Length' else "int(body('" + action + "')?['Length'])", literal(str(file['metadata'][k])) if k != 'Length' else str(file['metadata'][k]))
            for action in [before, after] for k in metadata_fields]
        checks += [eq("outputs('" + parsed + "')", "outputs('Next_expected_" + name + "')")]
    origin_reads['Next_completed_case'] = http(uri, previous)
    # Match the retained closure case GET contract; its complete raw parent
    # includes minimalmetadata annotations. New-case/source reads stay unchanged.
    origin_reads['Next_completed_case']['inputs']['parameters']['parameters/headers'] = {
        'Accept': 'application/json;odata=minimalmetadata'}
    origin_reads['Next_case_identity_field'] = http(init['caseListUri'].rsplit('/items', 1)[0] + "/fields/getbyinternalnameortitle('CaseUID')?$select=InternalName,EnforceUniqueValues", 'Next_completed_case')
    origin_reads['Next_target_date_field'] = http(init['caseListUri'].rsplit('/items', 1)[0] + "/fields/getbyinternalnameortitle('targetDate')?$select=InternalName,TypeAsString,MaxLength", 'Next_case_identity_field')
    checks += [eq("body('Next_target_date_field')?['InternalName']", "'targetDate'"),
        eq("body('Next_target_date_field')?['TypeAsString']", "'Text'"),
        "greaterOrEquals(int(body('Next_target_date_field')?['MaxLength']),10)"]
    checks += [eq(clean("body('Next_completed_case')"), "outputs('Next_expected_case')"),
        eq("outputs('Next_completed_case')?['headers']?['ETag']", literal(binding['completedCaseETag'])),
        eq("body('Next_case_identity_field')?['InternalName']", "'CaseUID'"),
        eq("body('Next_case_identity_field')?['EnforceUniqueValues']", 'true')]
    # Existing source guard, request readback and case creator remain in place.
    # Only the explicit due date and separate completed-review lineage are added.
    original['Request']['inputs']['completedReview'] = {
        'CaseUID': parent['CaseUID'], 'closedCaseETag': binding['completedCaseETag'],
        'closureCommit': {k: copy.deepcopy(commit[k]) for k in ['metadata', 'SHA256']},
        'preparedScope': copy.deepcopy(origin['preparedScope']), 'issuedFile': copy.deepcopy(origin['issuedFile']),
        'dateEvidence': {k: copy.deepcopy(date[k]) for k in ['metadata', 'SHA256']},
        'reviewDate': "@outputs('Next_date_record')?['reviewDate']",
        'ruleReference': "@outputs('Next_date_record')?['ruleReference']",
        'originalSourceAdoptedFromIssuedRevision': False, 'realPolicyEffects': False}
    work = original['Source_guard']['actions']
    create = work['Verify_request']['actions']
    create['Case_payload']['inputs']['targetDate'] = "@outputs('Next_date_record')?['reviewDate']"
    # Verify_case was emitted before the extension; add its native date equality.
    verify = create['Verify_case']
    verify['expression'] = '@and(' + verify['expression'][1:] + ",equals(first(body('Read_case')?['value'])?['targetDate'],outputs('Case_payload')?['targetDate']))"
    # Complete collection responses and a unique CaseUID are prerequisites, not
    # an assumption based on flow concurrency or a successful single example.
    for action in ['Find_request', 'Find_case', 'Read_case']:
        owner = work if action == 'Find_request' else create
        next_name = 'Ensure_request' if action == 'Find_request' else 'Ensure_case' if action == 'Find_case' else 'Verify_case'
        guard = owner[next_name]
        completeness = ["empty(body('" + action + "')?['odata.nextLink'])", "empty(body('" + action + "')?['@odata.nextLink'])", "lessOrEquals(length(body('" + action + "')?['value']),1)"]
        guard['expression'] = '@and(' + guard['expression'][1:] + ',' + ','.join(completeness) + ')'
    work['Verify_request']['expression'] = '@and(' + work['Verify_request']['expression'][1:] + ",empty(body('Find_request')?['odata.nextLink']),empty(body('Find_request')?['@odata.nextLink']),lessOrEquals(length(body('Find_request')?['value']),1))"
    verify['expression'] = '@and(' + verify['expression'][1:] + ",empty(body('Find_case')?['odata.nextLink']),empty(body('Find_case')?['@odata.nextLink']),lessOrEquals(length(body('Find_case')?['value']),1))"
    # First request creation is create-only; an existing request must match
    # completely before any case action, preserving changed-input refusal.
    folder = "_api/web/GetFolderByServerRelativePath(decodedurl='" + init['evidenceFolder'] + "')"
    intent_name = 'LC02-next-case-intent-' + inputs['text'] + '.json'
    intent_path = folder + "/Files('" + intent_name + "')/$value"
    create['Next_find_intent'] = http(folder + "/Files?$filter=Name eq '" + intent_name + "'", 'Find_case')
    ensure = create['Ensure_case']; ensure['runAfter'] = {'Next_find_intent': ['Succeeded']}
    case_writer = ensure['actions'].pop('Create_case')
    case_writer['inputs']['retryPolicy'] = {'type': 'none'}
    intent = {'kind': 'fictional-next-review-case-intent-v1', 'request': "@outputs('Request')", 'casePayload': "@outputs('Case_payload')"}
    first = {'Next_intent_payload': comp(intent)}
    first['Next_create_intent'] = http(folder + "/Files/add(url='" + intent_name + "',overwrite=false)", 'Next_intent_payload', 'POST', "@string(outputs('Next_intent_payload'))")
    first['Next_read_intent'] = http(intent_path, 'Next_create_intent')
    first['Next_stored_intent'] = comp(parse('Next_read_intent'), 'Next_read_intent')
    first['Next_verify_intent'] = gate([eq("outputs('Next_stored_intent')", "outputs('Next_intent_payload')")],
        {'Create_case': case_writer}, 'Next_hold_corrupt_intent', 'Next_stored_intent')
    ensure['actions'] = {'Next_require_new_intent': gate([
        "equals(length(body('Next_find_intent')?['value']),0)", "empty(body('Next_find_intent')?['odata.nextLink'])",
        "empty(body('Next_find_intent')?['@odata.nextLink'])"], first, 'Next_hold_uncertain_case_create')}
    create['Next_reconcile_intent_read'] = http(intent_path, 'Ensure_case')
    create['Next_reconcile_intent'] = comp(parse('Next_reconcile_intent_read'), 'Next_reconcile_intent_read')
    create['Read_case']['runAfter'] = {'Next_reconcile_intent': ['Succeeded']}
    verify['expression'] = '@and(' + verify['expression'][1:] + ",equals(outputs('Next_reconcile_intent')?['kind'],'fictional-next-review-case-intent-v1'),equals(outputs('Next_reconcile_intent')?['request'],outputs('Request')),equals(outputs('Next_reconcile_intent')?['casePayload'],outputs('Case_payload')))"
    verify['expression'] = '@and(' + verify['expression'][1:] + ",empty(body('Next_find_intent')?['odata.nextLink']),empty(body('Next_find_intent')?['@odata.nextLink']),lessOrEquals(length(body('Next_find_intent')?['value']),1))"
    # Existing intent + missing case is an uncertain create, not permission to
    # repeat POST. Existing matching case can be read/reconciled without POST.
    checked = verify['actions']
    # The nometadata collection has no item ETag. Pin the selected native item
    # through its response header without inventing an odata.etag annotation.
    next_case_uri = "@concat(" + literal(init['caseListUri'] + '(') + ",string(first(body('Read_case')?['value'])?['Id']),')')"
    checked['Next_case_selected'] = http(next_case_uri)
    checked['Recheck_source']['runAfter'] = {'Next_case_selected': ['Succeeded']}
    final_guard = checked['Final_source_guard']
    final = final_guard['actions']
    old_receipt = final.pop('Native_initiation_receipt')
    receipt_name = 'LC02-next-review-receipt-' + inputs['text'] + '.json'
    receipt_path = folder + "/Files('" + receipt_name + "')/$value"
    # Recheck the closed occurrence and retained date/commit before the final
    # source guard. This reuses that existing gate rather than adding nesting.
    checked['Next_parent_final'] = http(uri, 'Recheck_source')
    checked['Next_parent_final']['inputs']['parameters']['parameters/headers'] = {
        'Accept': 'application/json;odata=minimalmetadata'}
    checked['Next_date_final'] = http(file_uri(date) + '?$select=' + ','.join(metadata_fields), 'Next_parent_final')
    checked['Next_commit_final'] = http(file_uri(commit) + '?$select=' + ','.join(metadata_fields), 'Next_date_final')
    checked['Next_find_receipt'] = http(folder + "/Files?$filter=Name eq '" + receipt_name + "'", 'Next_commit_final')
    next_case_collection_uri = create['Read_case']['inputs']['parameters']['parameters/uri']

    def cross_surface_case_equal(collection, item):
        # Measured nometadata collection/item difference: these three system
        # fields are explicit null in the collection and absent/null in the
        # item. Complete comparison copies only; never alter a retained row.
        keys = ['ComplianceAssetId', 'OData__ColorTag', 'ServerRedirectedEmbedUri']
        defaults = "json('" + json.dumps(dict.fromkeys(keys), separators=(',', ':')) + "')"
        def completed(value):
            # Actual values win: a non-null field must never be overwritten by
            # the defaults, even though this bounded null-only exception holds.
            return 'union(' + defaults + ',' + clean(value) + ')'
        checks = [eq(completed(collection), completed(item))]
        for key in keys:
            checks += ["contains(" + collection + ",'" + key + "')",
                       eq(collection + "?['" + key + "']", 'null'),
                       eq(item + "?['" + key + "']", 'null')]
        return allof(checks)[1:]

    def case_snapshot_checks(collection, item):
        # Guard first() lazily: missing, failed or paginated collections cannot
        # supply a case snapshot or permit receipt creation/qualification.
        ready = [eq("outputs('" + name + "')?['statusCode']", '200')
                 for name in [collection, item, 'Next_case_selected']]
        ready += [eq("length(coalesce(body('" + collection + "')?['value'],json('[]')))", '1')]
        ready += ["empty(body('" + collection + "')?['" + key + "'])"
                  for key in ['odata.nextLink', '@odata.nextLink', 'nextLink']]
        selected = "body('Next_case_selected')"
        token = "outputs('Next_case_selected')?['headers']?['ETag']"
        current = "body('" + item + "')"
        checks = [eq(clean("first(body('" + collection + "')?['value'])"), clean("first(body('Read_case')?['value'])")),
                  eq(clean(current), clean(selected)),
                  cross_surface_case_equal("first(body('Read_case')?['value'])", selected),
                  "not(empty(" + token + '))', "not(equals(" + token + ",'*'))",
                  eq("outputs('" + item + "')?['headers']?['ETag']", token),
                  "greater(int(coalesce(" + selected + "?['Id'],0)),0)"]
        for key in ['GUID', 'Created']:
            checks += ["not(empty(" + selected + "?['" + key + "']))",
                       eq(current + "?['" + key + "']", selected + "?['" + key + "']")]
        return '@if(' + allof(ready)[1:] + ',' + allof(checks)[1:] + ',false)'

    checked['Next_case_receipt_before'] = http(next_case_collection_uri, 'Next_find_receipt')
    checked['Next_case_receipt_item_before'] = http(next_case_uri, 'Next_case_receipt_before')
    checked['Next_case_before_stable'] = comp(
        case_snapshot_checks('Next_case_receipt_before', 'Next_case_receipt_item_before'))
    checked['Next_case_before_stable']['runAfter'] = {
        'Next_case_receipt_item_before': ['Succeeded', 'Failed', 'TimedOut', 'Skipped']}
    final_checks = [eq(clean("body('Next_parent_final')"), "outputs('Next_expected_case')"),
        eq("outputs('Next_parent_final')?['headers']?['ETag']", literal(binding['completedCaseETag'])),
        "lessOrEquals(length(body('Next_find_receipt')?['value']),1)",
        "empty(body('Next_find_receipt')?['odata.nextLink'])", "empty(body('Next_find_receipt')?['@odata.nextLink'])"]
    final_checks += [eq("body('Next_" + name + "_final')?['" + k + "']", "body('Next_" + name + "_before')?['" + k + "']") for name in ['date', 'commit'] for k in metadata_fields]
    final_checks += [eq("outputs('Next_case_before_stable')", 'true')]
    final_guard['expression'] = '@and(' + final_guard['expression'][1:] + ',' + ','.join(final_checks) + ')'
    final_guard['runAfter'] = {'Next_case_before_stable': ['Succeeded']}
    final['Next_receipt_payload'] = comp({'kind': 'fictional-next-review-receipt-v1',
        'request': "@outputs('Request')", 'case': '@' + clean("first(body('Read_case')?['value'])"),
        'caseETag': "@outputs('Next_case_selected')?['headers']?['ETag']",
        'closureCommitUniqueId': commit['metadata']['UniqueId'], 'realPolicyEffects': False})
    final['Next_ensure_receipt'] = gate(["equals(length(body('Next_find_receipt')?['value']),0)"],
        {'Next_create_receipt': http(folder + "/Files/add(url='" + receipt_name + "',overwrite=false)", method='POST', body="@string(outputs('Next_receipt_payload'))")},
        'Next_receipt_already_exists', 'Next_receipt_payload')
    final['Next_ensure_receipt']['else']['actions'] = {}
    final['Next_read_receipt'] = http(receipt_path, 'Next_ensure_receipt')
    final['Next_saved_receipt'] = comp(parse('Next_read_receipt'), 'Next_read_receipt')
    final['Next_case_receipt_after'] = http(next_case_collection_uri, 'Next_saved_receipt')
    final['Next_case_receipt_item_after'] = http(next_case_uri, 'Next_case_receipt_after')
    final['Next_case_after_stable'] = comp(
        case_snapshot_checks('Next_case_receipt_after', 'Next_case_receipt_item_after'))
    final['Next_case_after_stable']['runAfter'] = {
        'Next_case_receipt_item_after': ['Succeeded', 'Failed', 'TimedOut', 'Skipped']}
    matches = allof([
        eq("outputs('Next_saved_receipt')", "outputs('Next_receipt_payload')"),
        eq("outputs('Next_case_before_stable')", 'true'),
        eq("outputs('Next_case_after_stable')", 'true'),
        cross_surface_case_equal("outputs('Next_saved_receipt')?['case']", "body('Next_case_selected')"),
        eq("outputs('Next_saved_receipt')?['caseETag']", "outputs('Next_case_selected')?['headers']?['ETag']")])[1:]
    old_receipt['inputs'].update(qualified='@' + matches,
        caseCreatedCount='@if(' + matches + ",if(equals(length(body('Find_case')?['value']),0),1,0),null)",
        requestCreatedCount='@if(' + matches + ",if(equals(length(body('Find_request')?['value']),0),1,0),null)",
        completedCaseUID=parent['CaseUID'], nextReviewDate="@outputs('Next_date_record')?['reviewDate']",
        closureCommitUniqueId=commit['metadata']['UniqueId'], retainedReceipt="@outputs('Next_saved_receipt')",
        recoveredExistingCase='@and(' + matches + ",equals(length(body('Find_case')?['value']),1),equals(length(body('Next_find_receipt')?['value']),0))",
        reconcileBeforeRetry='@not(' + matches + ')')
    old_receipt['runAfter'] = {'Next_case_after_stable': ['Succeeded']}
    final['Native_initiation_receipt'] = old_receipt
    origin_reads['Next_validate_origin'] = gate(checks, original, 'Next_hold_invalid_origin', 'Next_target_date_field')
    outer['actions'] = origin_reads
    # Disable retries on every inherited non-idempotent action too.
    def protect(group):
        for action in group.values():
            if action.get('type') == 'OpenApiConnection' and action['inputs']['parameters']['parameters/method'] != 'GET':
                action['inputs']['retryPolicy'] = {'type': 'none'}
            protect(action.get('actions', {})); protect(action.get('else', {}).get('actions', {}))
    protect(definition['actions'])
    return out

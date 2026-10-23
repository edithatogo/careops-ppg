"""Local composition of the existing fictional case writer's closure projection.

No I/O or deployment. The caller owns the router and must run this component
after selected-case resolution. Only the first-write branch consumes this run's
qualified closure observer; committed replay checks retained evidence directly,
so closing a case does not require reapplying its ownership projection.
"""
import copy
import re
import base64
import hashlib
import datetime


def build_actions(context, binding):
    if binding.get('qualificationOnly') is not True:
        raise ValueError('Fictional qualification binding required')
    for key in ('requestReference', 'expectedCaseUID'):
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', binding.get(key, '')):
            raise ValueError('Explicit bounded identity required: ' + key)
    if not binding['expectedCaseUID'].startswith('LC-FICTIONAL-OP-'):
        raise ValueError('Existing fictional operator occurrence required')
    for key in ('expectedCaseETag', 'expectedCaseStatus'):
        if not isinstance(binding.get(key), str) or not binding[key] or binding[key] == '*':
            raise ValueError('Exact initial case token and status required')
    if not re.fullmatch(r"_api/web/lists\(guid'[0-9a-fA-F-]{36}'\)/items\([1-9][0-9]*\)", binding.get('caseItemUri', '')):
        raise ValueError('Existing literal native case item required')
    folder = binding.get('folderUri', '')
    if not re.fullmatch(r"_api/web/GetFolderByServerRelativePath\(decodedurl='/[^']+'\)", folder):
        raise ValueError('Existing evidence folder required')
    evidence = binding.get('evidenceReads', {})
    required = {'assurance', 'readiness', 'consultation', 'source', 'draft',
                'issued', 'proof', 'date', 'originalSource', 'sourceBaseline', 'template',
                'generationReceipt', 'ownershipCommit', 'dateContent', 'sourceContent', 'issuedContent'}
    if set(evidence) != required:
        raise ValueError('Complete retained history, file, date and byte reads required')
    for key, spec in evidence.items():
        if set(spec) != {'uri', 'collection'} or not isinstance(spec['collection'], bool):
            raise ValueError('Explicit read shape required: ' + key)
        uri = spec['uri']
        if not isinstance(uri, str) or not uri.startswith('_api/web/') or any(x in uri for x in ['@', '\n', '\r']):
            raise ValueError('Literal same-site read required: ' + key)
        if spec['collection'] != (key in {'assurance', 'readiness', 'consultation'}):
            raise ValueError('History collection shape required')
        if spec['collection'] and not re.fullmatch(r"_api/web/lists\(guid'[0-9a-fA-F-]{36}'\)/items", uri):
            raise ValueError('Unfiltered complete history required')
        if not spec['collection'] and not re.fullmatch(r"_api/web/GetFileById\('[0-9a-fA-F-]{36}'\)(?:/\$value|\?\$select=[A-Za-z0-9_,]+)?", uri):
            raise ValueError('Full retained file metadata or content required')
        if uri.endswith('/$value') != key.endswith('Content'):
            raise ValueError('Explicit full metadata/content pairing required')
    for content, metadata in [('dateContent', 'date'), ('sourceContent', 'source'), ('issuedContent', 'issued')]:
        if evidence[content]['uri'] != evidence[metadata]['uri'].split('?')[0] + '/$value':
            raise ValueError('Content must belong to retained metadata identity')
    expected = binding.get('expectedObservation', {})
    for key in ('closureEvidenceConsistent', 'nextReviewDateProvenanceConsistent', 'nextOccurrencePrerequisitesConsistent'):
        if expected.get(key) is not True:
            raise ValueError('Qualified chain and explicit date provenance required')
    if expected.get('preparedScope', {}).get('CaseUID') != binding['expectedCaseUID']:
        raise ValueError('Same occurrence required')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', expected.get('nextReviewDate', '')):
        raise ValueError('Explicit retained review date required; no interval inference')
    if set(expected.get('selectedEvents', {})) != {'committee', 'officer', 'coordinator', 'authorisation', 'publication', 'implementation', 'verification'}:
        raise ValueError('Complete explicit seven-event selection required')
    if evidence['date']['uri'].split('?')[0] != "_api/web/GetFileById('" + expected.get('nextReviewEvidenceFileUID', '') + "')":
        raise ValueError('Observer date-file identity must match actual retained read')

    if not isinstance(expected.get('nextReviewRuleReference'), str) or not expected['nextReviewRuleReference'].strip():
        raise ValueError('Explicit recorded review-rule reference required')
    datetime.date.fromisoformat(expected['nextReviewDate'])
    retained = copy.deepcopy(binding.get('expectedEvidence', {}))
    if set(retained) != required:
        raise ValueError('Exact complete retained native evidence snapshot required')
    for key, spec in evidence.items():
        value = retained[key]
        if spec['collection']:
            if not isinstance(value, list):
                raise ValueError('Exact full history required')
        elif not key.endswith('Content'):
            uid = spec['uri'].split("'")[1]
            if str(value.get('UniqueId', '')).lower() != uid.lower() or value.get('ETag') in (None, '', '*'):
                raise ValueError('Exact file identity and opaque token required: ' + key)
    for key, spec in evidence.items():
        if spec['collection']:
            retained[key] = [{**row, 'odata.id': None} for row in retained[key]]
        elif not key.endswith('Content'):
            projection = spec['uri'].split('?$select=')
            if len(projection) == 2:
                selected = projection[1].split(',')
                observed = {k for k in retained[key] if not k.startswith('odata.')}
                if len(selected) != len(set(selected)) or set(selected) != observed or not {'UniqueId', 'ETag'} <= set(selected):
                    raise ValueError('Exact retained metadata request projection required: ' + key)
                annotation = retained[key].get('odata.metadata', '').split('&$select=')
                if len(annotation) == 2 and selected != annotation[1].split(','):
                    raise ValueError('Exact retained metadata request projection order required: ' + key)
            retained[key]['odata.id'] = None
    def content_bytes(value):
        if not isinstance(value, dict) or not isinstance(value.get('$content'), str):
            raise ValueError('Retained binary-safe native content required')
        return base64.b64decode(value['$content'], validate=True)
    source_bytes = content_bytes(retained['sourceContent'])
    if source_bytes != content_bytes(retained['issuedContent']) or hashlib.sha256(source_bytes).hexdigest() != expected['preparedScope'].get('DocumentSHA256'):
        raise ValueError('Retained exact source/issued bytes and prepared hash required')
    if not isinstance(expected.get('issuedFile'), dict) or any(
            expected['issuedFile'].get(k) != retained['issued'].get(k) for k in ('UniqueId', 'ETag')):
        raise ValueError('Observer and retained issued identity must match')

    # Binary transport content type is not document content. Pin exact base64
    # bytes; parse date JSON using the already qualified native JSON transport.
    for key in ['sourceContent', 'issuedContent']:
        retained[key] = {'$content': retained[key]['$content']}
    if '$content' in retained['dateContent']:
        import json
        retained['dateContent'] = json.loads(content_bytes(retained['dateContent']))
    template = context['properties']['definition']['actions']['Resolve_context']['actions']['Read_selected_case']
    def comp(value, after=None):
        return {'type': 'Compose', 'inputs': value, 'runAfter': {after: ['Succeeded']} if after else {}}
    def http(uri, after=None, method='GET', body=None, headers=None):
        action = copy.deepcopy(template)
        params = action['inputs']['parameters']
        params.update({'parameters/uri': uri, 'parameters/method': method,
                       'parameters/headers': headers or {'Accept': 'application/json;odata=minimalmetadata'}})
        params.pop('parameters/body', None)
        if body is not None:
            params['parameters/body'] = body
        action['inputs']['retryPolicy'] = {'type': 'none'}
        action['runAfter'] = {after: ['Succeeded']} if after else {}
        return action
    def eq(a, b): return 'equals(' + a + ',' + b + ')'
    def literal(v): return "'" + v.replace("'", "''") + "'"
    def allof(parts): return '@and(' + ','.join(parts) + ')'
    hold_number = 0
    def hold(reason):
        nonlocal hold_number
        hold_number += 1
        return {'Cycle_hold_' + str(hold_number): comp({'qualified': False, 'caseWriteCount': None,
            'closurePerformed': False, 'nextOccurrenceCreated': False,
            'reconcileBeforeRetry': True, 'reason': reason, 'realPolicyEffects': False})}
    def gate(checks, yes, reason, after=None):
        return {'type': 'If', 'expression': allof(checks), 'actions': yes,
                'else': {'actions': hold(reason)}, 'runAfter': {after: ['Succeeded']} if after else {}}
    def normalized(body):
        return "union(" + body + ",json('{\"odata.id\":null}'))"
    # These are server-managed changes caused by a successful MERGE. Every other
    # returned case member, including unknown future human fields, is preserved.
    def protected_case(body):
        return "union(" + body + ",json('{\"odata.id\":null,\"odata.etag\":null,\"Modified\":null,\"EditorId\":null,\"OData__UIVersionString\":null,\"caseStatus\":null}'))"
    def snapshots(group, prefix, after=None):
        previous = after
        snapshot = {}
        complete = []
        for key, spec in evidence.items():
            name = prefix + '_' + key
            group[name] = http(spec['uri'], previous)
            previous = name
            if spec['collection']:
                stable = name + '_stable'
                group[stable] = {'type': 'Select', 'inputs': {'from': "@body('" + name + "')?['value']",
                    'select': '@' + normalized('item()')}, 'runAfter': {name: ['Succeeded']}}
                previous = stable
                snapshot[key] = "@body('" + stable + "')"
                complete += ["empty(body('" + name + "')?['" + key + "'])"
                             for key in ('nextLink', 'odata.nextLink', '@odata.nextLink', '@nextLink')]
            elif key in ['sourceContent', 'issuedContent']:
                snapshot[key] = {'$content': "@if(contains(body('" + name + "'),'$content'),body('" + name + "')?['$content'],null)"}
            elif key == 'dateContent':
                snapshot[key] = parse(name)
            else:
                snapshot[key] = '@' + normalized("body('" + name + "')")
        group[prefix + '_snapshot'] = comp(snapshot, previous)
        group[prefix + '_complete'] = comp(allof(complete), prefix + '_snapshot')
        return prefix + '_complete'
    def parse(name):
        return "@if(contains(body('" + name + "'),'$content'),json(base64ToString(body('" + name + "')?['$content'])),json(string(body('" + name + "'))))"
    prefix = 'LC04-closure-' + binding['requestReference']
    paths = {kind: folder + "/Files('" + prefix + '-' + kind + ".json')/$value" for kind in ['before', 'after', 'commit']}
    contract = {'kind': 'fictional-prepared-closure-contract-v1', 'requestReference': binding['requestReference'],
        'CaseUID': binding['expectedCaseUID'], 'caseItemUri': binding['caseItemUri'],
        'initialCaseETag': binding['expectedCaseETag'], 'initialCaseStatus': binding['expectedCaseStatus'],
        'observation': copy.deepcopy(expected), 'evidenceReads': copy.deepcopy(evidence),
        'patch': {'caseStatus': 'Review closed — FICTIONAL'}, 'realPolicyEffects': False}
    group = {'Cycle_contract': comp(contract), 'Cycle_expected_evidence': comp(copy.deepcopy(retained), 'Cycle_contract'), 'Cycle_case': http(binding['caseItemUri'], 'Cycle_expected_evidence')}
    previous = snapshots(group, 'Cycle_current', 'Cycle_case')
    for kind in paths:
        name = 'Cycle_find_' + kind
        group[name] = http(folder + "/Files?$filter=Name eq '" + prefix + '-' + kind + ".json'", previous)
        previous = name
    common = [eq("body('Cycle_case')?['CaseUID']", literal(binding['expectedCaseUID'])),
        "not(empty(outputs('Cycle_case')?['headers']?['ETag']))", "not(equals(outputs('Cycle_case')?['headers']?['ETag'],'*'))",
        eq("outputs('Cycle_current_complete')", 'true'), eq("outputs('Cycle_current_snapshot')", "outputs('Cycle_expected_evidence')")]
    for kind in paths:
        common += ["lessOrEquals(length(body('Cycle_find_" + kind + "')?['value']),1)",
            *["empty(body('Cycle_find_" + kind + "')?['" + key + "'])"
              for key in ('nextLink', 'odata.nextLink', '@odata.nextLink', '@nextLink')]]
    def exists(kind): return eq("length(body('Cycle_find_" + kind + "')?['value'])", '1')
    def absent(kind): return eq("length(body('Cycle_find_" + kind + "')?['value'])", '0')
    def create(kind, value, after=None):
        return http(folder + "/Files/add(url='" + prefix + '-' + kind + ".json',overwrite=false)", after,
            'POST', "@string(outputs('" + value + "'))", {'Content-Type': 'application/json'})
    # A saved after-proof is the only supported recovery point. Without it an
    # existing journal is unknown: never issue MERGE a second time automatically.
    def finish(count, previous=None, proof='Cycle_after_record', before='Cycle_before_record', namespace='Recovery_'):
        actions = {'Cycle_commit_payload': comp({'kind': 'fictional-prepared-closure-commit-v1',
            'contract': "@outputs('Cycle_contract')", 'beforeProof': "@outputs('" + before + "')", 'afterProof': "@outputs('" + proof + "')",
            'runId': "@workflow()?['run']?['name']", 'realPolicyEffects': False}, previous)}
        actions['Cycle_create_commit'] = create('commit', 'Cycle_commit_payload', 'Cycle_commit_payload')
        actions['Cycle_read_saved_commit'] = http(paths['commit'], 'Cycle_create_commit')
        actions['Cycle_saved_commit'] = comp(parse('Cycle_read_saved_commit'), 'Cycle_read_saved_commit')
        saved_matches = eq("outputs('Cycle_saved_commit')", "outputs('Cycle_commit_payload')")
        actions['Native_closure_transition'] = comp({'qualified': '@' + saved_matches,
            'caseWriteCount': '@if(' + saved_matches + ',' + str(count) + ',null)',
            'closurePerformed': '@' + saved_matches, 'nextOccurrenceCreated': False,
            'reconcileBeforeRetry': '@not(' + saved_matches + ')', 'realPolicyEffects': False,
            'actorAuthorityQualified': False, 'commit': "@outputs('Cycle_saved_commit')"}, 'Cycle_saved_commit')
        from build_case_work_router import rename_actions
        return rename_actions(actions, namespace)
    replay = {'Cycle_read_commit': http(paths['commit'])}
    replay['Cycle_commit_record'] = comp(parse('Cycle_read_commit'), 'Cycle_read_commit')
    replay['Cycle_replay_read_before'] = http(paths['before'], 'Cycle_commit_record')
    replay['Cycle_replay_read_after'] = http(paths['after'], 'Cycle_replay_read_before')
    replay['Cycle_replay_before'] = comp(parse('Cycle_replay_read_before'), 'Cycle_replay_read_after')
    replay['Cycle_replay_after'] = comp(parse('Cycle_replay_read_after'), 'Cycle_replay_before')
    commit = "outputs('Cycle_commit_record')"
    def retained_checks(before, after):
        return [eq(before + "?['kind']", "'fictional-prepared-closure-before-v1'"),
            eq(after + "?['kind']", "'fictional-prepared-closure-after-v1'"),
            eq(before + "?['contract']", "outputs('Cycle_contract')"),
            eq(after + "?['contract']", "outputs('Cycle_contract')"),
            eq(before + "?['beforeCaseETag']", "outputs('Cycle_contract')?['initialCaseETag']"),
            eq(before + "?['beforeCase']?['caseStatus']", "outputs('Cycle_contract')?['initialCaseStatus']"),
            eq(before + "?['evidence']", "outputs('Cycle_current_snapshot')"),
            eq(after + "?['afterCase']?['caseStatus']", "'Review closed — FICTIONAL'"),
            eq(protected_case(before + "?['beforeCase']"), protected_case("body('Cycle_case')")),
            "not(equals(" + after + "?['afterCaseETag']," + before + "?['beforeCaseETag']))"]
    replay['Cycle_verify_replay'] = gate(retained_checks("outputs('Cycle_replay_before')", "outputs('Cycle_replay_after')") + [exists('before'), exists('after'),
        eq(commit + "?['kind']", "'fictional-prepared-closure-commit-v1'"),
        eq(commit + "?['contract']", "outputs('Cycle_contract')"),
        eq(commit + "?['beforeProof']", "outputs('Cycle_replay_before')"),
        eq(commit + "?['afterProof']", "outputs('Cycle_replay_after')"),
        eq(commit + "?['afterProof']?['afterCase']", normalized("body('Cycle_case')")),
        eq(commit + "?['afterProof']?['afterCaseETag']", "outputs('Cycle_case')?['headers']?['ETag']"),
        eq(commit + "?['afterProof']?['evidence']", "outputs('Cycle_current_snapshot')")],
        {'Native_closure_replay': comp({'qualified': True, 'caseWriteCount': 0, 'closurePerformed': True,
            'nextOccurrenceCreated': False, 'realPolicyEffects': False, 'actorAuthorityQualified': False,
            'originalCommit': '@' + commit})}, 'Changed request, case or evidence; no replay progression', 'Cycle_replay_after')
    recover = {'Cycle_read_before': http(paths['before']), 'Cycle_read_after': http(paths['after'], 'Cycle_read_before')}
    recover['Cycle_before_record'] = comp(parse('Cycle_read_before'), 'Cycle_read_after')
    recover['Cycle_after_record'] = comp(parse('Cycle_read_after'), 'Cycle_before_record')
    recover['Cycle_verify_recovery'] = gate(retained_checks("outputs('Cycle_before_record')", "outputs('Cycle_after_record')") + [
        eq("outputs('Cycle_after_record')?['afterCase']", normalized("body('Cycle_case')")),
        eq("outputs('Cycle_after_record')?['afterCaseETag']", "outputs('Cycle_case')?['headers']?['ETag']"),
        eq("outputs('Cycle_after_record')?['evidence']", "outputs('Cycle_current_snapshot')")],
        finish(0), 'Partial-effect recovery does not match durable after-proof', 'Cycle_after_record')
    first = {'Cycle_before_payload': comp({'kind': 'fictional-prepared-closure-before-v1',
        'contract': "@outputs('Cycle_contract')", 'beforeCase': '@' + normalized("body('Cycle_case')"),
        'beforeCaseETag': "@outputs('Cycle_case')?['headers']?['ETag']", 'evidence': "@outputs('Cycle_current_snapshot')",
        'runId': "@workflow()?['run']?['name']"})}
    first['Cycle_create_before'] = create('before', 'Cycle_before_payload', 'Cycle_before_payload')
    first['Cycle_first_read_before'] = http(paths['before'], 'Cycle_create_before')
    first['Cycle_first_stored_before'] = comp(parse('Cycle_first_read_before'), 'Cycle_first_read_before')
    after = snapshots(first, 'Cycle_prewrite', 'Cycle_first_stored_before')
    first['Cycle_case_prewrite'] = http(binding['caseItemUri'], after)
    write = {'Cycle_apply_closure': http(binding['caseItemUri'], method='POST',
        body="@string(outputs('Cycle_contract')?['patch'])", headers={'Content-Type': 'application/json;odata=nometadata',
        'X-HTTP-Method': 'MERGE', 'IF-MATCH': "@outputs('Cycle_case_prewrite')?['headers']?['ETag']"})}
    write['Cycle_case_after'] = http(binding['caseItemUri'], 'Cycle_apply_closure')
    last = snapshots(write, 'Cycle_after', 'Cycle_case_after')
    proved = {'Cycle_first_after_record': comp({'kind': 'fictional-prepared-closure-after-v1',
        'contract': "@outputs('Cycle_contract')", 'afterCase': '@' + normalized("body('Cycle_case_after')"),
        'afterCaseETag': "@outputs('Cycle_case_after')?['headers']?['ETag']", 'evidence': "@outputs('Cycle_after_snapshot')",
        'runId': "@workflow()?['run']?['name']"})}
    proved['Cycle_create_after'] = create('after', 'Cycle_first_after_record', 'Cycle_first_after_record')
    proved['Cycle_first_read_after'] = http(paths['after'], 'Cycle_create_after')
    proved['Cycle_first_stored_after'] = comp(parse('Cycle_first_read_after'), 'Cycle_first_read_after')
    proved['Cycle_verify_durable_after'] = gate([eq("outputs('Cycle_first_stored_after')", "outputs('Cycle_first_after_record')")],
        finish(1, proof='Cycle_first_stored_after', before='Cycle_first_stored_before', namespace='First_'),
        'Case effect may exist but durable after-proof readback differs; no qualified commit', 'Cycle_first_stored_after')
    write['Cycle_verify_after'] = gate([
        eq("body('Cycle_case_after')?['caseStatus']", "'Review closed — FICTIONAL'"),
        eq(protected_case("body('Cycle_case_after')"), protected_case("body('Cycle_case')")),
        "not(empty(outputs('Cycle_case_after')?['headers']?['ETag']))",
        "not(equals(outputs('Cycle_case_after')?['headers']?['ETag'],'*'))",
        "not(equals(outputs('Cycle_case_after')?['headers']?['ETag'],outputs('Cycle_case')?['headers']?['ETag']))",
        eq("outputs('Cycle_after_complete')", 'true'),
        eq("outputs('Cycle_after_snapshot')", "outputs('Cycle_current_snapshot')")], proved,
        'Case effect may exist; retain journal and reconcile, never repeat MERGE', last)
    first['Cycle_verify_prewrite'] = gate([
        eq("outputs('Cycle_first_stored_before')", "outputs('Cycle_before_payload')"),
        eq("outputs('Cycle_prewrite_complete')", 'true'),
        eq("outputs('Cycle_prewrite_snapshot')", "outputs('Cycle_current_snapshot')"),
        eq(normalized("body('Cycle_case_prewrite')"), normalized("body('Cycle_case')")),
        eq("outputs('Cycle_case_prewrite')?['headers']?['ETag']", "outputs('Cycle_case')?['headers']?['ETag']")],
        write, 'Concurrent case or evidence change after journal; no case write', 'Cycle_case_prewrite')
    observation = "outputs('Native_closure_observation')"
    initial = gate([absent('before'), absent('after'),
        eq("outputs('Cycle_case')?['headers']?['ETag']", literal(binding['expectedCaseETag'])),
        eq("body('Cycle_case')?['caseStatus']", literal(binding['expectedCaseStatus']))] + [
        eq(observation + "?['" + key + "']", 'true') for key in
        ('closureEvidenceConsistent', 'nextReviewDateProvenanceConsistent', 'nextOccurrencePrerequisitesConsistent')] + [
        eq(observation + "?['" + key + "']", "outputs('Cycle_contract')?['observation']?['" + key + "']")
        for key in ('preparedScope', 'selectedEvents', 'issuedFile', 'nextReviewDate', 'nextReviewEvidenceFileUID', 'nextReviewRuleReference')] + [
        eq(observation + "?['" + key + "']", 'false') for key in
        ('closurePerformed', 'nextOccurrenceCreated', 'progressionGranted', 'actorAuthorityQualified', 'realPolicyEffects')] + [
        eq(observation + "?['writeCount']", '0')],
        first, 'Fresh same-execution closure/date observation and exact initial case required')
    group['Cycle_reads_valid'] = comp(allof(common), previous)
    valid = eq("outputs('Cycle_reads_valid')", 'true')
    def route(checks, actions):
        return {'type': 'If', 'expression': allof([valid] + checks), 'actions': actions,
                'else': {'actions': {}}, 'runAfter': {}}
    # Mutually exclusive routes avoid stacking selector conditions around the
    # write/after-proof guards. This keeps the actual router composition within
    # the native nesting limit, including its existing operation wrapper.
    routes = {
        'Cycle_replay_route': route([exists('commit')], replay),
        'Cycle_choose_recovery': route([absent('commit'), exists('before'), exists('after')], recover),
        'Cycle_choose_initial': route([absent('commit'), absent('before'), absent('after')], {'Cycle_validate_initial': initial}),
        'Cycle_hold_partial': {'type': 'If', 'expression': allof([valid, absent('commit'),
            "or(and(" + exists('before') + ',' + absent('after') + "),and(" + absent('before') + ',' + exists('after') + '))']),
            'actions': hold('Incomplete journal/after-proof pair; retain original run and reconcile, never resubmit MERGE'),
            'else': {'actions': {}}, 'runAfter': {}},
        'Cycle_hold_reads': {'type': 'If', 'expression': "@not(" + valid + ')',
            'actions': hold('Incomplete, ambiguous or changed native evidence; no effects'),
            'else': {'actions': {}}, 'runAfter': {}}}
    group['Cycle_transition_routes'] = {'type': 'Scope', 'actions': routes, 'runAfter': {'Cycle_reads_valid': ['Succeeded']}}
    group['Cycle_unknown_effect'] = comp({'qualified': False, 'caseWriteCount': None,
        'reconcileBeforeRetry': True, 'closurePerformed': False, 'nextOccurrenceCreated': False,
        'realPolicyEffects': False, 'reason': 'Retain original native run and journal paths; do not repeat uncertain effects'})
    group['Cycle_unknown_effect']['runAfter'] = {'Cycle_transition_routes': ['Failed', 'TimedOut', 'Skipped']}
    return group

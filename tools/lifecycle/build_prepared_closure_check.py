"""Assemble a GET-only fictional closure observation; never close or initiate a case.

Requires this execution's qualified prepared reader. Recomputes readiness, then
checks an explicitly selected seven-event retained-issued chain. Extra same-scope
records hold, including parallel adverse or edition scenarios; no newest choice.
An optional retained JSON file supplies next-review provenance independently.
Issued output must be an exact byte copy of the qualified prepared revision;
transformed output needs its own separately qualified input/output binding.
No native integration, authentication, I/O or substantive assessment occurs here.
"""
import copy
import re
from urllib.parse import urlsplit

from build_prepared_readiness_check import build_actions as readiness_actions

SCOPE = ('CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256')
CHAIN = ('committee', 'officer', 'coordinator', 'authorisation',
         'publication', 'implementation', 'verification')


def calendar_date_expression(value):
    """Total WDL predicate for an exact Gregorian YYYY-MM-DD date.

    Do not call formatDateTime on untrusted input: WDL and() evaluates every
    argument, so a length check alongside a parser does not guard that parser.
    Nested if() guards substring/int; arithmetic checks reject impossible days.
    """
    text = 'string(coalesce(' + value + ",''))"
    digits = text
    for digit in '0123456789':
        digits = 'replace(' + digits + ",'" + digit + "','')"
    shape = 'and(equals(substring(' + text + ",4,1),'-'),equals(substring(" + text + ",7,1),'-'),equals(" + digits + ",'--'))"
    year = 'int(substring(' + text + ',0,4))'
    month = 'int(substring(' + text + ',5,2))'
    day = 'int(substring(' + text + ',8,2))'
    leap = 'and(equals(mod(' + year + ',4),0),or(not(equals(mod(' + year + ',100),0)),equals(mod(' + year + ',400),0)))'
    long_month = 'contains(createArray(1,3,5,7,8,10,12),' + month + ')'
    maximum = 'if(equals(' + month + ',2),if(' + leap + ',29,28),if(' + long_month + ',31,30))'
    calendar = 'and(greaterOrEquals(' + year + ',1),greaterOrEquals(' + month + ',1),lessOrEquals(' + month + ',12),greaterOrEquals(' + day + ',1),lessOrEquals(' + day + ',' + maximum + '))'
    return 'if(equals(length(' + text + '),10),if(' + shape + ',' + calendar + ',false),false)'


def build_actions(context, binding):
    """Private selections are reviewed bindings, never caller-entered file pins.

    binding: existing readiness/consultation collections and required fictional
    roles; assuranceCollectionUri (literal GUID collection); selectedEvents (seven
    EventUIDs); purposeReferences (four explicit DecisionReference values);
    optional nextReviewEvidenceFileUID (existing same-site JSON file).
    The single-issued chain is deliberately strict: other scoped edition/scenario
    records need explicit resolution before a future extension can consume them.
    """
    selections = binding.get('selectedEvents', {})
    if (set(selections) != set(CHAIN) or len(set(selections.values())) != len(CHAIN)
            or any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,255}', v)
                   for v in selections.values())):
        raise ValueError('Seven explicit unique safe event selections required')
    purposes = binding.get('purposeReferences', {})
    if (set(purposes) != set(CHAIN[:4]) or any(not isinstance(v, str) or not v.strip()
            or len(v) > 255 for v in purposes.values())):
        raise ValueError('Four explicit purpose references required')
    uri = binding.get('assuranceCollectionUri')
    if not isinstance(uri, str) or not re.fullmatch(
            r"_api/web/lists\(guid'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}'\)/items", uri):
        raise ValueError('Complete literal assurance collection required')
    if uri in (binding['readinessCollectionUri'], binding['consultationCollectionUri']):
        raise ValueError('Separate assurance collection required')
    date_uid = binding.get('nextReviewEvidenceFileUID')
    if date_uid is not None and (not isinstance(date_uid, str) or not re.fullmatch(
            r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', date_uid)):
        raise ValueError('Optional existing next-review evidence file GUID required')

    # Reuse the qualified GET-only readiness implementation, with distinct action
    # names so existing readiness/case-work modes keep their single writer.
    original = readiness_actions(context, binding)
    names = {}
    def collect(group):
        for n, a in group.items():
            names[n] = 'Closure_' + n
            collect(a.get('actions', {})); collect(a.get('else', {}).get('actions', {}))
    collect(original)
    def rename(value):
        if isinstance(value, dict):
            return {names.get(k, k): rename(v) for k, v in value.items()}
        if isinstance(value, list): return [rename(v) for v in value]
        if isinstance(value, str):
            return re.sub(r"\b(body|outputs)\('([^']+)'\)",
                lambda m: m[1] + "('" + names.get(m[2], m[2]) + "')", value)
        return value
    graph = rename(original)
    ready_graph = graph['Closure_Check_prepared_readiness']['actions']
    template = context['properties']['definition']['actions']['Resolve_context']['actions']['Read_selected_case']
    site = template['inputs']['parameters']['dataset']
    parts = urlsplit(site)
    if parts.scheme != 'https' or not parts.netloc or parts.query or parts.fragment:
        raise ValueError('Qualified HTTPS site required')
    origin = parts.scheme + '://' + parts.netloc
    def quote(v): return "'" + v.replace("'", "''") + "'"
    def comp(v, after=None):
        return {'type': 'Compose', 'inputs': v, 'runAfter': {after: ['Succeeded']} if after else {}}
    def http(path, after=None):
        a = copy.deepcopy(template)
        a['inputs']['parameters'].update({'parameters/uri': path,
            'parameters/headers': {'Accept': 'application/json;odata=minimalmetadata'}})
        a['runAfter'] = {after: ['Succeeded']} if after else {}
        return a
    def query(source, checks, after):
        return {'type': 'Query', 'inputs': {'from': source, 'where': '@' + checks},
                'runAfter': {after: ['Succeeded']}}
    def both(checks): return 'and(' + ','.join(checks) + ')'
    def eq(a, b): return 'equals(' + a + ',' + b + ')'
    def present(v): return "not(empty(trim(string(coalesce(" + v + ",'')))))"
    def complete(n):
        return ["empty(body('" + n + "')?['" + key + "'])"
                for key in ('nextLink', 'odata.nextLink', '@odata.nextLink', '@nextLink')]
    def stable(n, previous):
        return {'type': 'Select', 'inputs': {'from': "@body('" + n + "')?['value']",
            'select': "@union(item(),json('{\"odata.id\":null}'))"},
            'runAfter': {previous: ['Succeeded']}}
    prepared = "outputs('Native_prepared_revision')?['preparedRevision']"
    scope = prepared + "?['scope']"
    ready = "outputs('Closure_Native_readiness_observation')"
    work = {'Closure_assurance_before': http(uri)}
    work['Closure_assurance_stable_before'] = stable('Closure_assurance_before', 'Closure_assurance_before')
    work['Closure_scoped_assurance'] = query("@body('Closure_assurance_before')?['value']",
        both([eq("item()?['" + k + "']", scope + "?['" + k + "']") for k in SCOPE]),
        'Closure_assurance_stable_before')
    previous = 'Closure_scoped_assurance'; checks = []
    selected = {}
    for index, role in enumerate(CHAIN):
        name = 'Closure_selected_' + role
        work[name] = query("@body('Closure_assurance_before')?['value']",
            eq("item()?['EventUID']", quote(selections[role])), previous)
        row = "first(body('" + name + "'))"; selected[role] = row
        stage = 'Decision' if index < 4 else role.title()
        clauses = [eq(row + "?['" + k + "']", scope + "?['" + k + "']") for k in SCOPE]
        clauses += [eq(row + "?['FictionalTest']", 'true'), eq(row + "?['Stage']", quote(stage)),
            eq(row + "?['RecordState']", "'Recorded'"), "empty(" + row + "?['SupersedesEventUID'])",
            "contains(createArray('None recorded','Resolved')," + row + "?['ConditionsState'])"]
        clauses += [present(row + "?['" + k + "']") for k in
                    ('GUID', 'odata.etag', 'EventUID', 'ActorName', 'OccurredOn', 'Summary', 'EvidenceReference')]
        clauses += ["not(equals(" + row + "?['odata.etag'],'*'))", "greater(int(coalesce(" + row + "?['Id'],0)),0)"]
        if index < 4:
            clauses += [eq(row + "?['DecisionReference']", quote(purposes[role])),
                eq(row + "?['DecisionOutcome']", quote('Approved (recorded)' if index == 3 else 'Endorsed (recorded)')),
                eq(row + "?['ReadinessEventUID']", ready + "?['selectedEventUID']")]
        if index == 0: clauses += ["empty(" + row + "?['ParentEventUID'])"]
        else: clauses += [eq(row + "?['ParentEventUID']", quote(selections[CHAIN[index - 1]]))]
        if role == 'implementation': clauses += [present(row + "?['ImplementationActions']")]
        if role == 'verification':
            clauses += [eq(row + "?['VerificationResult']", "'Verified (recorded)'"),
                        present(row + "?['VerificationMethod']")]
        valid = name + '_valid'
        clauses += ['if(' + present(row + "?['OccurredOn']") + ',lessOrEquals(ticks(' + row + "?['OccurredOn']),ticks(utcNow())),false)"]
        work[valid] = comp("@if(equals(length(body('" + name + "')),1)," + both(clauses) + ',false)', name)
        checks.append(eq("outputs('" + valid + "')", 'true')); previous = valid
    # Exactly the explicit selected chain, no hidden adverse/extra edition rows.
    checks += complete('Closure_assurance_before') + [eq("length(body('Closure_scoped_assurance'))", '7')]
    for role in CHAIN:
        work['Closure_superseders_' + role] = query("@body('Closure_assurance_before')?['value']",
            eq("item()?['SupersedesEventUID']", quote(selections[role])), previous)
        previous = 'Closure_superseders_' + role
        checks += [eq("length(body('" + previous + "'))", '0')]
    # Date chronology is checked only after every selected row is a valid singleton.
    chronology = ["greaterOrEquals(ticks(" + selected[b] + "?['OccurredOn']),ticks(" + selected[a] + "?['OccurredOn']))"
                  for a, b in zip(CHAIN, CHAIN[1:])]
    chronology += ["greaterOrEquals(ticks(" + selected['committee'] + "?['OccurredOn']),ticks(first(body('Closure_Readiness_scope'))?['AssessedOn']))"]
    work['Closure_chain_consistent'] = comp('@if(' + both(checks) + ',' + both(chronology) + ',false)', previous)
    publication = selected['publication']; url = publication + "?['PublicationURL']"
    issued_uri = "@concat('_api/web/GetFileByServerRelativePath(decodedurl=',decodeUriComponent('%27'),substring(" + url + ',' + str(len(origin)) + "),decodeUriComponent('%27'),')')"
    # URI comes from the unique selected publication, restricted to this site.
    issued_guard = ["startsWith(string(" + url + '),' + quote(site.rstrip('/') + '/') + ')']
    issued_guard += ["not(contains(string(" + url + '),' + quote(v) + '))' for v in ("'", '?', '#')]
    issue = {'Closure_issued_before': http(issued_uri)}
    # Append to the existing concat expression rather than make an executable
    # expression out of a literal URL supplied by the caller.
    issue['Closure_issued_content'] = http(issued_uri[:-1] + ", '/$value')", 'Closure_issued_before')
    draft_uid = prepared + "?['file']?['UniqueId']"
    issue['Closure_draft_content'] = http("@concat('_api/web/GetFileById(',decodeUriComponent('%27')," + draft_uid + ",decodeUriComponent('%27'),')/$value')", 'Closure_issued_content')
    issue['Closure_issued_after'] = http(issued_uri, 'Closure_draft_content')
    work['Closure_issued_guard'] = {'type': 'If', 'expression': '@if(equals(outputs(\'Closure_chain_consistent\'),true),' + both(issued_guard) + ',false)',
        'runAfter': {'Closure_chain_consistent': ['Succeeded']}, 'actions': issue,
        'else': {'actions': {'Closure_issued_held': comp({'issuedEvidenceConsistent': False, 'writeCount': 0})}}}
    file_checks = [eq("body('Closure_issued_before')?['" + k + "']", "body('Closure_issued_after')?['" + k + "']") for k in ('UniqueId', 'ETag')]
    file_checks += [present("body('Closure_issued_after')?['UniqueId']"), present("body('Closure_issued_after')?['ETag']"), "not(equals(body('Closure_issued_after')?['ETag'],'*'))",
        eq(publication + "?['PublishedVersionRef']", "concat('sharepoint:',body('Closure_issued_after')?['UniqueId'],':',body('Closure_issued_after')?['ETag'])")]
    def content(n):
        return "if(contains(body('" + n + "'),'$content'),body('" + n + "')?['$content'],base64(string(body('" + n + "'))))"
    file_checks += [present(content('Closure_issued_content')), present(content('Closure_draft_content')),
                   eq(content('Closure_issued_content'), content('Closure_draft_content'))]
    issue['Closure_issued_consistent'] = comp('@' + both(file_checks), 'Closure_issued_after')

    # Independent optional date provenance. Missing evidence is an explicit false,
    # never targetDate, an upload time or a guessed review interval.
    date_after = 'Closure_issued_guard'
    if date_uid:
        base = "_api/web/GetFileById('" + date_uid + "')"
        work['Closure_date_before'] = http(base, date_after)
        work['Closure_date_content'] = http(base + '/$value', 'Closure_date_before')
        work['Closure_date_record'] = comp("@if(contains(body('Closure_date_content'),'$content'),json(base64ToString(body('Closure_date_content')?['$content'])),json(string(body('Closure_date_content'))))", 'Closure_date_content')
        work['Closure_date_after'] = http(base, 'Closure_date_record')
        date = "outputs('Closure_date_record')"; date_value = date + "?['reviewDate']"
        date_checks = [eq("body('Closure_date_before')?['ETag']", "body('Closure_date_after')?['ETag']"),
            eq("body('Closure_date_before')?['UniqueId']", "body('Closure_date_after')?['UniqueId']"),
            eq("body('Closure_date_after')?['UniqueId']", quote(date_uid)), present("body('Closure_date_after')?['ETag']"),
            "not(equals(body('Closure_date_after')?['ETag'],'*'))", eq(date + "?['FictionalTest']", 'true'),
            eq(date + "?['notOperational']", 'true'), eq(date + "?['policyAuthorityGranted']", 'false'),
            "startsWith(string(coalesce(" + date + "?['ruleReference'],'')),'fictional://')"]
        date_checks += [eq(date + "?['scope']?['" + k + "']", scope + "?['" + k + "']") for k in SCOPE]
        date_checks += [present(date + "?['" + k + "']") for k in ('ruleReference', 'evidenceReference', 'recordedBy')]
        date_checks += [calendar_date_expression(date_value)]
        work['Closure_date_consistent'] = comp('@' + both(date_checks), 'Closure_date_after')
    else:
        work['Closure_date_consistent'] = comp(False, date_after)
    previous = 'Closure_date_consistent'
    work['Closure_assurance_after'] = http(uri, previous)
    work['Closure_assurance_stable_after'] = stable('Closure_assurance_after', 'Closure_assurance_after')
    previous = 'Closure_assurance_stable_after'
    frame_checks = complete('Closure_assurance_after') + [eq("body('Closure_assurance_stable_before')", "body('Closure_assurance_stable_after')")]
    for kind, source in [('readiness', 'Readiness_history_after'), ('consultation', 'Readiness_consultation_after')]:
        name = 'Closure_final_' + kind
        work[name] = copy.deepcopy(ready_graph[names[source]]); work[name]['runAfter'] = {previous: ['Succeeded']}
        work[name + '_stable'] = stable(name, name); previous = name + '_stable'
        frame_checks += complete(name) + [eq("body('" + previous + "')", "body('" + names['Readiness_stable_after' if kind == 'readiness' else 'Readiness_consultation_stable_after'] + "')")]
    for label in ('case', 'draft', 'receipt', 'template', 'source', 'baseline'):
        name = 'Closure_final_' + label; oldname = names['Readiness_' + label + '_final']
        work[name] = copy.deepcopy(ready_graph[oldname]); work[name]['runAfter'] = {previous: ['Succeeded']}; previous = name
        if label == 'case':
            frame_checks += [eq("outputs('" + name + "')?['headers']?['ETag']", "outputs('" + oldname + "')?['headers']?['ETag']"),
                eq("body('" + name + "')?['CaseUID']", scope + "?['CaseUID']"),
                eq("body('" + name + "')?['evidenceDraftLink']", scope + "?['DocumentReference']")]
        else:
            frame_checks += [eq("body('" + name + "')?['" + k + "']", "body('" + oldname + "')?['" + k + "']") for k in ('UniqueId', 'ETag')]
    # Late checks cover the actual issued bytes and optional date provenance too.
    # The issued URL/row must never be evaluated after a skipped selection branch.
    final_issue = {'Closure_final_issued': http(issued_uri)}
    final_issue['Closure_issued_current'] = comp('@' + both([
        eq("body('Closure_final_issued')?['" + k + "']", "body('Closure_issued_after')?['" + k + "']")
        for k in ('UniqueId', 'ETag')]), 'Closure_final_issued')
    work['Closure_final_issued_guard'] = {'type': 'If',
        'expression': "@equals(outputs('Closure_issued_consistent'),true)",
        'runAfter': {previous: ['Succeeded']}, 'actions': final_issue,
        'else': {'actions': {'Closure_final_issued_held': comp(False)}}}
    previous = 'Closure_final_issued_guard'
    frame_checks += [eq("outputs('Closure_issued_current')", 'true')]
    if date_uid:
        work['Closure_final_date'] = http("_api/web/GetFileById('" + date_uid + "')", previous)
        work['Closure_date_current'] = comp('@' + both([
            eq("body('Closure_final_date')?['" + k + "']", "body('Closure_date_after')?['" + k + "']")
            for k in ('UniqueId', 'ETag')]), 'Closure_final_date')
        previous = 'Closure_date_current'
    else:
        work['Closure_date_current'] = comp(False, previous)
        previous = 'Closure_date_current'
    work['Closure_frame_consistent'] = comp('@' + both(frame_checks), previous)
    work['Native_closure_observation'] = comp({
        'closureEvidenceConsistent': "@and(equals(outputs('Closure_chain_consistent'),true),equals(outputs('Closure_issued_consistent'),true),equals(outputs('Closure_frame_consistent'),true))",
        'nextReviewDateProvenanceConsistent': "@and(equals(outputs('Closure_date_consistent'),true),equals(outputs('Closure_date_current'),true))",
        'nextOccurrencePrerequisitesConsistent': "@and(equals(outputs('Closure_chain_consistent'),true),equals(outputs('Closure_issued_consistent'),true),equals(outputs('Closure_frame_consistent'),true),equals(outputs('Closure_date_consistent'),true),equals(outputs('Closure_date_current'),true))",
        'preparedScope': '@' + scope, 'selectedEvents': selections,
        'issuedFile': {'UniqueId': "@body('Closure_final_issued')?['UniqueId']", 'ETag': "@body('Closure_final_issued')?['ETag']"},
        'nextReviewEvidenceFileUID': date_uid,
        'nextReviewDate': "@if(and(equals(outputs('Closure_date_consistent'),true),equals(outputs('Closure_date_current'),true)),outputs('Closure_date_record')?['reviewDate'],null)" if date_uid else None,
        'nextReviewRuleReference': "@if(and(equals(outputs('Closure_date_consistent'),true),equals(outputs('Closure_date_current'),true)),outputs('Closure_date_record')?['ruleReference'],null)" if date_uid else None,
        'writeCount': 0, 'closurePerformed': False, 'nextOccurrenceCreated': False,
        'progressionGranted': False, 'actorAuthorityQualified': False,
        'contentReadinessGranted': False, 'policyApproved': False, 'ordinaryUserAccessQualified': False,
        'realPolicyEffects': False,
        'limits': 'Fictional technical snapshot only; strict retained-issued chain. Mixed/adverse/corrected/extra edition records hold. Date provenance is separate. Revalidate before any separately reviewed write.'}, 'Closure_frame_consistent')
    held = {'closureEvidenceConsistent': False, 'nextReviewDateProvenanceConsistent': False,
        'nextOccurrencePrerequisitesConsistent': False, 'writeCount': 0, 'closurePerformed': False,
        'nextOccurrenceCreated': False, 'progressionGranted': False, 'actorAuthorityQualified': False,
        'contentReadinessGranted': False, 'policyApproved': False,
        'ordinaryUserAccessQualified': False, 'realPolicyEffects': False,
        'reason': 'Qualified prepared readiness and complete stable closure evidence required; no writes.'}
    graph['Closure_check_chain'] = {'type': 'If',
        'expression': '@' + both([eq(ready + "?['readinessEvidenceConsistent']", 'true'),
            eq(ready + "?['nativeContextRevalidated']", 'true')]),
        'runAfter': {'Closure_Check_prepared_readiness': ['Succeeded', 'Failed', 'TimedOut']},
        'actions': work, 'else': {'actions': {'Held_closure_prerequisites': comp(held)}}}
    graph['Held_closure_error'] = {'type': 'Compose', 'inputs': held,
        'runAfter': {'Closure_check_chain': ['Failed', 'TimedOut']}}
    return graph

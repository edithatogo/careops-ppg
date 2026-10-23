"""Prepare one pinned journal-only continuation; no native I/O or approval.

The original journal is never recreated or edited. A changed case token, unknown
field, event, source/baseline pin, journal or existing commit holds before MERGE.
An uncertain earlier case write cannot pass the retained before-token check.
"""
import copy
import hashlib
import json
from uuid import UUID

from build_case_work_router import rename_actions
from build_multisource_case_context import digest, _projection_source_uri
from build_operator_entry import _flatten, _literal, action_references
from build_selected_event_routes import audit_actions


def build(profile, binding, journal_bytes):
    if (set(binding) != {'qualificationOnly', 'approvedDefinitionSHA256', 'journalFile', 'journalSHA256'}
            or binding['qualificationOnly'] is not True
            or digest(profile['properties']['definition']) != binding['approvedDefinitionSHA256']
            or not isinstance(journal_bytes, bytes)
            or hashlib.sha256(journal_bytes).hexdigest() != binding['journalSHA256']):
        raise ValueError('Exact reviewed profile and independently retained journal bytes required')
    journal = json.loads(journal_bytes)
    pin = binding['journalFile']
    if set(pin) != {'UniqueId', 'ETag'} or not isinstance(pin['ETag'], str) or not pin['ETag'] or pin['ETag'] == '*':
        raise ValueError('Exact nonwildcard journal file pin required')
    uid = str(UUID(pin['UniqueId']))
    context = journal.get('context', {})
    before = journal.get('beforeCase', {})
    patch = journal.get('proposedPatch', {})
    offer, response = journal.get('offer', {}), journal.get('response', {})
    if (journal.get('kind') != 'fictional-ownership-projection-before-v1'
            or not isinstance(journal.get('runId'), str) or not journal['runId']
            or not str(context.get('CaseUID', '')).startswith('LC-FICTIONAL-OP-')
            or before.get('CaseUID') != context['CaseUID']
            or type(context.get('nativeItemId')) is not int or context['nativeItemId'] <= 0
            or before.get('Id') != context['nativeItemId']
            or before.get('caseStatus') != 'Initiated — FICTIONAL'
            or not journal.get('beforeCaseETag') or journal['beforeCaseETag'] == '*'
            or journal['beforeCaseETag'] != context.get('caseETag')
            or set(patch) != {'accountableRole', 'caseStatus'}
            or not str(patch.get('accountableRole', '')).startswith('FICTIONAL')
            or patch.get('caseStatus') != 'Ownership accepted — FICTIONAL'
            or before.get('accountableRole') != 'UNACCEPTED — proposed fictional role: ' + patch['accountableRole']
            or offer.get('RecordState') != 'Proposed' or response.get('RecordState') != 'Accepted'
            or response.get('ConditionsState') != 'None recorded'
            or response.get('ParentEventUID') != offer.get('EventUID') or not offer.get('EventUID')
            or any(row.get('FictionalTest') is not True or row.get('SupersedesEventUID')
                   or row.get('SubjectRole') != patch['accountableRole'] for row in (offer, response))):
        raise ValueError('Exact fictional initial case and separate uncorrected acceptance required')
    definition = profile['properties']['definition']
    if definition['triggers']['manual'].get('runtimeConfiguration', {}).get('concurrency', {}).get('runs') != 1:
        raise ValueError('Existing single-run concurrency required')
    nodes = _flatten(definition['actions'])
    if any(name.startswith('JournalRecovery_') for name in nodes):
        raise ValueError('Existing recovery composition must be reviewed separately')
    for name in ('Selected_Projection_before_source', 'Selected_Projection_after_source'):
        if nodes[name]['inputs']['parameters']['parameters/uri'] != _projection_source_uri():
            raise ValueError('Reviewed selected-source projection metadata reads required')
    apply = nodes['Selected_Apply_projection']
    params = apply['inputs']['parameters']
    if (params.get('parameters/method') != 'POST'
            or params['parameters/headers'].get('X-HTTP-Method') != 'MERGE'
            or params['parameters/headers'].get('IF-MATCH') != "@outputs('Selected_Projection_case_before')?['headers']?['ETag']"
            or apply['inputs'].get('retryPolicy') != {'type': 'none'}):
        raise ValueError('Original no-retry conditional case writer required')
    out = copy.deepcopy(profile)
    out['properties']['state'] = 'Stopped'
    actions = out['properties']['definition']['actions']
    site = nodes['Selected_Read_projection_case']['inputs']['parameters']['dataset']
    file_uri = "_api/web/GetFileById('" + uid + "')"
    def compose(value, previous=None):
        return {'type': 'Compose', 'inputs': value, 'runAfter': {previous: ['Succeeded']} if previous else {}}
    def read(uri, previous):
        node = copy.deepcopy(nodes['Selected_Projection_before_source'])
        node['inputs']['parameters'].update({'dataset': site, 'parameters/method': 'GET', 'parameters/uri': uri})
        node['inputs']['parameters'].pop('parameters/body', None)
        node['runAfter'] = {previous: ['Succeeded']}
        return node
    def eq(a, b): return 'equals(' + a + ',' + b + ')'
    def both(checks): return '@and(' + ','.join(checks) + ')'
    def exact(value): return 'union(' + value + ",json('{\"odata.id\":null}'))"
    def data(value):
        if isinstance(value, dict): return {k: data(v) for k, v in value.items()}
        if isinstance(value, list): return [data(v) for v in value]
        return '@' + value if isinstance(value, str) and value.startswith('@') else value
    c = "outputs('Selected_case_context')"
    checks = [eq("triggerBody()?['text']", "'Project ownership'"), eq(c + "?['contextValid']", 'true'),
              eq(c + "?['CaseUID']", _literal(context['CaseUID']))]
    collections = ('Selected_Read_projection_journal', 'Selected_Read_projection_commit',
                   'Selected_Read_projection_offer', 'Selected_Read_projection_responses')
    complete = ["empty(body('" + name + "')?['" + key + "'])" for name in collections
                for key in ('nextLink', '@nextLink', 'odata.nextLink', '@odata.nextLink', '__next')]
    complete += [eq("length(body('Selected_Read_projection_" + name + "')?['value'])", count)
                 for name, count in [('journal', '1'), ('commit', '0'), ('offer', '1'), ('responses', '1')]]
    complete += [eq("body('Selected_Read_projection_case')?['caseStatus']", "'Initiated — FICTIONAL'"),
                 eq("outputs('Selected_Read_projection_case')?['headers']?['ETag']", _literal(journal['beforeCaseETag']))]
    candidate = '@if(' + both(checks)[1:] + ',' + both(complete)[1:] + ',false)'
    work = {'JournalRecovery_expected': compose(data(journal)),
            'JournalRecovery_before': read(file_uri + '?$select=UniqueId,ETag,Length', 'JournalRecovery_expected'),
            'JournalRecovery_content': read(file_uri + '/$value', 'JournalRecovery_before'),
            'JournalRecovery_after': read(file_uri + '?$select=UniqueId,ETag,Length', 'JournalRecovery_content')}
    work['JournalRecovery_parse'] = compose("@if(contains(body('JournalRecovery_content'),'$content'),json(base64ToString(body('JournalRecovery_content')?['$content'])),json(string(body('JournalRecovery_content'))))", 'JournalRecovery_after')
    recheck = copy.deepcopy(nodes['Selected_Read_projection_commit'])
    recheck['runAfter'] = {'JournalRecovery_parse': ['Succeeded']}
    work['JournalRecovery_commit_absent'] = recheck
    expected = "outputs('JournalRecovery_expected')"
    valid = [eq("outputs('JournalRecovery_parse')", expected),
             eq(exact("body('Selected_Read_projection_case')"), exact(expected + "?['beforeCase']")),
             eq("outputs('Selected_Read_projection_case')?['headers']?['ETag']", expected + "?['beforeCaseETag']"),
             eq(exact("first(body('Selected_Read_projection_offer')?['value'])"), exact(expected + "?['offer']")),
             eq(exact("first(body('Selected_Read_projection_responses')?['value'])"), exact(expected + "?['response']")),
             eq("length(body('JournalRecovery_commit_absent')?['value'])", '0')]
    valid += ["empty(body('JournalRecovery_commit_absent')?['" + key + "'])" for key in
              ('nextLink', '@nextLink', 'odata.nextLink', '@odata.nextLink', '__next')]
    for key in ('CaseUID', 'nativeItemId', 'caseETag', 'scope', 'sourcePins', 'baselineReference', 'baselineUniqueId', 'baselineETag'):
        valid.append(eq(c + "?['" + key + "']", expected + "?['context']?['" + key + "']"))
    for name in ('JournalRecovery_before', 'JournalRecovery_after'):
        valid += [eq("toLower(body('" + name + "')?['UniqueId'])", _literal(uid)),
                  eq("body('" + name + "')?['ETag']", _literal(pin['ETag'])),
                  eq("int(body('" + name + "')?['Length'])", str(len(journal_bytes)))]
    listed = "first(body('Selected_Read_projection_journal')?['value'])"
    valid += [eq('toLower(' + listed + "?['UniqueId'])", _literal(uid)), eq(listed + "?['ETag']", _literal(pin['ETag']))]
    # Reuse all canonical fresh reads, before/after guards, conditional MERGE,
    # create-only commit and exact commit readback; never clone journal creation.
    continuation = {'Selected_Projection_journal': compose("@outputs('JournalRecovery_parse')")}
    for name in ('Selected_Projection_case_before', 'Selected_Projection_offer_before',
                 'Selected_Projection_response_before', 'Selected_Projection_before_source',
                 'Selected_Projection_before_baseline', 'Selected_Verify_projection_before'):
        continuation[name] = copy.deepcopy(nodes[name])
    continuation['Selected_Projection_case_before']['runAfter'] = {'Selected_Projection_journal': ['Succeeded']}
    cloned = _flatten(continuation)
    cloned['Selected_Projection_commit']['inputs'].update({
        'recoveredFromRunId': "@outputs('Selected_Projection_journal')?['runId']",
        'beforeJournal': {**pin, 'SHA256': binding['journalSHA256']}})
    receipt = cloned['Selected_Native_projection_receipt']
    receipt['inputs'].update({'recoveredFromRunId': "@outputs('Selected_Projection_journal')?['runId']", 'journalWrites': 0})
    # The original journal must still be retained after the commit is read back.
    committed = cloned['Selected_Verify_projection_after']['actions']
    del committed['Selected_Native_projection_receipt']
    committed['JournalRecovery_final_journal'] = read(file_uri + '?$select=UniqueId,ETag,Length', 'Selected_Parse_saved_projection_commit')
    final = [eq("body('JournalRecovery_final_journal')?['ETag']", _literal(pin['ETag'])),
             eq("toLower(body('JournalRecovery_final_journal')?['UniqueId'])", _literal(uid)),
             eq("int(body('JournalRecovery_final_journal')?['Length'])", str(len(journal_bytes)))]
    receipt['runAfter'] = {}
    committed['JournalRecovery_final_valid'] = {'type': 'If', 'expression': both(final),
        'runAfter': {'JournalRecovery_final_journal': ['Succeeded']},
        'actions': {'Selected_Native_projection_receipt': receipt},
        'else': {'actions': {'JournalRecovery_uncertain': compose({'qualified': False, 'caseWriteCount': None,
            'reconcileBeforeRetry': True, 'realResponsibilityTransferred': False})}}}
    continuation = rename_actions(continuation, 'Continued_')
    work['JournalRecovery_valid'] = {'type': 'If', 'expression': both(valid),
        'runAfter': {'JournalRecovery_commit_absent': ['Succeeded']}, 'actions': continuation,
        'else': {'actions': {'JournalRecovery_changed': compose({'qualified': False, 'caseWriteCount': 0,
            'journalWrites': 0, 'realResponsibilityTransferred': False, 'reason': 'Retained journal or current frame changed; no continuation'})}}}
    actions['JournalRecovery_entry'] = {'type': 'If', 'expression': candidate,
        'runAfter': {'Route_ownership_projection': ['Succeeded']}, 'actions': work,
        'else': {'actions': {'JournalRecovery_not_selected': compose({'qualified': False, 'caseWriteCount': 0,
            'journalWrites': 0, 'realResponsibilityTransferred': False})}}}
    geometry = audit_actions(out['properties']['definition'])
    if geometry['actionCount'] > 500 or geometry['maximumActionDepth'] > 8:
        raise ValueError('Recovery exceeds native action geometry')
    if action_references(actions) - _flatten(actions).keys():
        raise ValueError('Unresolved recovery action reference')
    return out

"""Exercise emitted closure expressions with labelled synthetic native observations.

The small expression harness is test-only: no native calls or replacement runtime.
"""
import base64
import copy
import datetime as dt
import json
import re
import sys
import unittest
from pathlib import Path
from urllib.parse import quote, unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/lifecycle'))
from build_prepared_closure_check import build_actions, CHAIN, calendar_date_expression
from test_selected_event_routes import fixtures

NOW = '2026-10-20T12:00:00Z'
DATE_UID = '00000000-0000-4000-8000-000000000099'
SCOPE = {'CaseUID': 'LC-FICTIONAL-OP-CLOSURE-TEST', 'DocumentReference': 'https://example.invalid/site/prepared.docx',
         'ReviewedVersionRef': 'fictional-prepared-v2', 'DocumentSHA256': 'b' * 64}


class Expressions:
    """Only the WDL subset emitted by this observer; evaluates the actual graph."""
    def __init__(self, bodies=None, outputs=None):
        self.bodies = bodies or {}; self.outputs = outputs or {}; self.current = None

    def evaluate(self, expression):
        if not isinstance(expression, str) or not expression.startswith('@'): return expression
        tokens = re.findall(r"'(?:[^']|'')*'|\?\[|[A-Za-z_][A-Za-z_0-9]*|-?\d+|[(),\]]", expression[1:])
        index = 0
        def parse():
            nonlocal index
            token = tokens[index]; index += 1
            if token.startswith("'"): node = ('literal', token[1:-1].replace("''", "'"))
            elif re.fullmatch('-?\\d+', token): node = ('literal', int(token))
            elif token in ('true', 'false', 'null'): node = ('literal', {'true': True, 'false': False, 'null': None}[token])
            else:
                self_token = tokens[index]; index += 1
                assert self_token == '(', (token, self_token)
                args = []
                while tokens[index] != ')':
                    args.append(parse())
                    if tokens[index] != ')': assert tokens[index] == ','; index += 1
                index += 1; node = ('call', token, args)
            while index < len(tokens) and tokens[index] == '?[':
                index += 1; key = parse(); assert tokens[index] == ']'; index += 1
                node = ('get', node, key)
            return node
        tree = parse(); assert index == len(tokens), tokens[index:]
        def run(node):
            if node[0] == 'literal': return node[1]
            if node[0] == 'get':
                value = run(node[1]); return value.get(run(node[2])) if isinstance(value, dict) else None
            name, args = node[1:]
            if name == 'if': return run(args[1] if run(args[0]) else args[2])
            values = [run(a) for a in args]
            def ticks(v): return dt.datetime.fromisoformat(v.replace('Z', '+00:00')).timestamp()
            def format_date_time(value, fmt):
                if fmt == 'yyyy-MM-dd':
                    return dt.date.fromisoformat(value).isoformat()
                assert fmt == 'yyyy-MM-ddTHH:mm:ssZ', fmt
                parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
                assert parsed.tzinfo is not None
                return parsed.astimezone(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            def native_union(a, b):
                if isinstance(a, dict) and isinstance(b, dict): return {**a, **b}
                if isinstance(a, list) and isinstance(b, list):
                    result = list(a)
                    for value in b:
                        if value not in result: result.append(value)
                    return result
                raise TypeError('union requires two objects or two arrays')
            functions = {
                'body': lambda n: self.bodies.get(n), 'outputs': lambda n: self.outputs.get(n),
                'item': lambda: self.current, 'equals': lambda a, b: a == b,
                'and': lambda *v: all(v), 'or': lambda *v: any(v), 'not': lambda v: not v,
                'empty': lambda v: v is None or v == '' or v == [] or v == {},
                'coalesce': lambda *v: next((x for x in v if x is not None), None),
                'string': lambda v: '' if v is None else str(v), 'trim': lambda v: v.strip(),
                'contains': lambda a, b: b in a, 'createArray': lambda *v: list(v),
                'first': lambda v: v[0], 'last': lambda v: v[-1],
                'split': lambda value, separator: value.split(separator), 'length': len, 'int': int,
                'greater': lambda a, b: a > b, 'lessOrEquals': lambda a, b: a <= b,
                'greaterOrEquals': lambda a, b: a >= b, 'ticks': ticks, 'utcNow': lambda: NOW,
                'json': json.loads, 'union': native_union,
                'setProperty': lambda obj, key, value: {**obj, key: value},
                'concat': lambda *v: ''.join(v), 'startsWith': lambda a, b: a.startswith(b),
                'endsWith': lambda a, b: a.endswith(b), 'toLower': lambda v: v.lower(),
                'substring': lambda value, start, length=None: value[start:] if length is None else value[start:start+length], 'decodeUriComponent': unquote,
                'replace': lambda value, old, new: value.replace(old, new),
                'mod': lambda a, b: a % b,
                'mul': lambda a, b: a * b, 'sub': lambda a, b: a - b,
                'div': lambda a, b: a // b if isinstance(a, int) and isinstance(b, int) else a / b,
                'uriComponent': lambda value: quote(value, safe="~()*!.'-"),
                'triggerBody': lambda: self.outputs.get('Test_trigger'),
                'base64': lambda v: base64.b64encode(v.encode()).decode(),
                'formatDateTime': format_date_time,
            }
            return functions[name](*values)
        return run(tree)


class CalendarDateTests(unittest.TestCase):
    def test_exact_calendar_dates_without_parser_exceptions(self):
        expression = '@' + calendar_date_expression("outputs('Date')")
        for value in ['2099-02-01', '2000-02-29', '2024-02-29', '0001-01-01', '9999-12-31']:
            with self.subTest(value=value):
                self.assertTrue(Expressions(outputs={'Date': value}).evaluate(expression))
        for value in [None, '', '20990201', '2099-W06-7', '2099-02-30',
                      '2099-02-01T00:00:00Z', '1900-02-29', '2100-02-29',
                      '2024-04-31', '0000-01-01', '2099-00-01', '2099-13-01',
                      '2099-01-00', '2099-01-32', '2099-2-001', '2099-aa-01',
                      '2099/02/01', ' 2099-02-01', '2099-02-01 ', '２０９９-02-01']:
            with self.subTest(value=value):
                self.assertFalse(Expressions(outputs={'Date': value}).evaluate(expression))


def fixture(with_date=False):
    context, _, _ = fixtures()
    selected = {role: 'FICTIONAL-' + role for role in CHAIN}
    purpose = {role: 'fictional://purpose/' + role for role in CHAIN[:4]}
    binding = {'readinessCollectionUri': "_api/web/lists(guid'00000000-0000-4000-8000-000000000009')/items",
        'consultationCollectionUri': "_api/web/lists/getbytitle('PPG Consultation and Handoff Events')/items",
        'assuranceCollectionUri': "_api/web/lists(guid'00000000-0000-4000-8000-000000000010')/items",
        'requiredFictionalRoles': ['FICTIONAL test role'], 'selectedEvents': selected, 'purposeReferences': purpose}
    if with_date: binding['nextReviewEvidenceFileUID'] = DATE_UID
    rows = []
    for i, role in enumerate(CHAIN):
        rows.append({**SCOPE, 'Id': i + 1, 'GUID': 'FICTIONAL-row-' + str(i), 'odata.etag': '"1"',
            'EventUID': selected[role], 'Stage': 'Decision' if i < 4 else role.title(),
            'RecordState': 'Recorded', 'FictionalTest': True, 'ConditionsState': 'None recorded',
            'SupersedesEventUID': None, 'ParentEventUID': None if i == 0 else selected[CHAIN[i - 1]],
            'ActorName': 'FICTIONAL test actor', 'OccurredOn': '2026-10-19T12:00:00Z',
            'Summary': 'FICTIONAL technical test only', 'EvidenceReference': 'fictional://evidence',
            'ReadinessEventUID': 'FICTIONAL-ready', 'DecisionReference': purpose.get(role),
            'DecisionOutcome': 'Approved (recorded)' if i == 3 else 'Endorsed (recorded)',
            'ImplementationActions': 'FICTIONAL availability check',
            'VerificationResult': 'Verified (recorded)', 'VerificationMethod': 'FICTIONAL byte check',
            'PublicationURL': 'https://example.invalid/site/issued.docx',
            'PublishedVersionRef': 'sharepoint:FICTIONAL-issued:"1"'})
    return context, binding, rows


def chain_result(rows, binding=None):
    context, default, _ = fixture(); binding = binding or default
    work = build_actions(context, binding)['Closure_check_chain']['actions']
    ev = Expressions({'Closure_assurance_before': {'value': rows},
                      'Closure_Readiness_scope': [{'AssessedOn': '2026-10-18T14:00:00Z'}]}, {
        'Native_prepared_revision': {'preparedRevision': {'scope': SCOPE}},
        'Closure_Native_readiness_observation': {'selectedEventUID': 'FICTIONAL-ready'}})
    for name, action in work.items():
        if name == 'Closure_assurance_before': continue
        if action['type'] == 'Select':
            result = []
            for row in ev.evaluate(action['inputs']['from']):
                ev.current = row; result.append(ev.evaluate(action['inputs']['select']))
            ev.bodies[name] = result
        elif action['type'] == 'Query':
            result = []
            for row in ev.evaluate(action['inputs']['from']):
                ev.current = row
                if ev.evaluate(action['inputs']['where']): result.append(row)
            ev.bodies[name] = result
        elif action['type'] == 'Compose': ev.outputs[name] = ev.evaluate(action['inputs'])
        else: raise AssertionError('Unexpected action before chain result: ' + name)
        if name == 'Closure_chain_consistent': return ev.outputs[name]
    raise AssertionError('Missing chain result')


class PreparedClosureTests(unittest.TestCase):
    def test_issued_metadata_and_content_uris_are_complete_expressions(self):
        context, binding, rows = fixture()
        work = build_actions(context, binding)['Closure_check_chain']['actions']
        actions = {**work['Closure_issued_guard']['actions'],
                   **work['Closure_final_issued_guard']['actions']}
        ev = Expressions({'Closure_selected_publication': [rows[4]]})
        expected = "_api/web/GetFileByServerRelativePath(decodedurl='/site/issued.docx')"
        for name, suffix in [('Closure_issued_before', ''), ('Closure_issued_after', ''),
                             ('Closure_issued_content', '/$value'), ('Closure_final_issued', '')]:
            expression = actions[name]['inputs']['parameters']['parameters/uri']
            with self.subTest(action=name):
                # Reject unmatched quotes or punctuation rather than silently
                # dropping them while tokenising the emitted expression.
                pattern = r"'(?:[^']|'')*'|\?\[|[A-Za-z_][A-Za-z_0-9]*|-?\d+|[(),\]]"
                position = 1
                for token in re.finditer(pattern, expression[1:]):
                    self.assertEqual(expression[position:token.start() + 1].strip(), '')
                    position = token.end() + 1
                self.assertEqual(expression[position:].strip(), '')
                self.assertEqual(ev.evaluate(expression), expected + suffix)

    def test_consistent_explicit_fictional_chain_and_purpose_links(self):
        c, b, rows = fixture(); self.assertTrue(chain_result(rows, b))
        for key in ['ParentEventUID', 'DecisionReference', 'ReviewedVersionRef', 'ReadinessEventUID', 'odata.etag']:
            changed = copy.deepcopy(rows); changed[1][key] = 'FICTIONAL-wrong'
            if key == 'odata.etag': changed[1][key] = '*'
            with self.subTest(key=key): self.assertFalse(chain_result(changed, b))

    def test_actual_producer_shaped_versioned_ids_fit_native_text255(self):
        c, b, rows = fixture()
        # Mirrors the purpose producer's occurrence + physical file + native
        # version + purpose identity. Dots are data in local collection queries,
        # not URL paths; a maximum request reference exceeds the old 128 limit.
        request = 'LC02-OP-' + 'R' * 56
        file_uid = '00000000-0000-4000-8000-000000000011'
        for index, role in enumerate(CHAIN):
            prefix = 'LC03-PURPOSE-' if index < 4 else 'LC04-'
            b['selectedEvents'][role] = prefix + request + '-' + file_uid + '-v2.0-' + role
            rows[index]['EventUID'] = b['selectedEvents'][role]
            rows[index]['ParentEventUID'] = None if index == 0 else rows[index - 1]['EventUID']
        self.assertGreater(max(map(len, b['selectedEvents'].values())), 128)
        self.assertTrue(chain_result(rows, b))
        edge, edge_rows = copy.deepcopy(b), copy.deepcopy(rows)
        edge['selectedEvents']['committee'] = edge['selectedEvents']['committee'].ljust(255, 'X')
        edge_rows[0]['EventUID'] = edge['selectedEvents']['committee']
        edge_rows[1]['ParentEventUID'] = edge['selectedEvents']['committee']
        self.assertTrue(chain_result(edge_rows, edge))
        for unsafe in ['unsafe\'quote', 'unsafe/path', 'unsafe?query', 'unsafe#fragment', 'x' * 256]:
            changed = copy.deepcopy(b); changed['selectedEvents']['committee'] = unsafe
            with self.subTest(unsafe=unsafe), self.assertRaises(ValueError): build_actions(c, changed)

    def test_deferred_case_mixed_history_and_failed_verification_hold(self):
        _, b, rows = fixture()
        for outcome in ['Deferred', 'Rejected']:
            changed = copy.deepcopy(rows); changed[3].update(DecisionOutcome=outcome, ConditionsState='Open')
            self.assertFalse(chain_result(changed, b))
        for finding in ['Failed', 'Inconclusive', 'Not verified']:
            changed = copy.deepcopy(rows); changed[-1]['VerificationResult'] = finding
            self.assertFalse(chain_result(changed, b))
        mixed = rows + [{**rows[3], 'EventUID': 'FICTIONAL-parallel-deferred', 'ConditionsState': 'Open'}]
        self.assertFalse(chain_result(mixed, b))
        edition = rows + [{**rows[3], 'EventUID': 'FICTIONAL-withdrawal-purpose'}]
        self.assertFalse(chain_result(edition, b))

    def test_duplicate_cross_scope_correction_missing_and_future_hold(self):
        _, b, rows = fixture()
        for changed in [rows[:-1], rows + [{**rows[0], 'CaseUID': 'FICTIONAL-other'}],
                        rows + [{**rows[0], 'EventUID': 'FICTIONAL-correction', 'CaseUID': 'FICTIONAL-other',
                                 'SupersedesEventUID': rows[0]['EventUID']}]]:
            self.assertFalse(chain_result(changed, b))
        changed = copy.deepcopy(rows); changed[-1]['OccurredOn'] = '2099-01-01T00:00:00Z'
        self.assertFalse(chain_result(changed, b))

    def test_get_only_distinct_namespace_and_no_caller_scope_or_case_writers(self):
        c, b, _ = fixture(); original = copy.deepcopy((c, b)); graph = build_actions(c, b)
        names = set()
        def walk(group):
            for n, a in group.items():
                self.assertNotIn(n, names); names.add(n)
                if a['type'] == 'OpenApiConnection':
                    self.assertEqual(a['inputs']['parameters']['parameters/method'], 'GET')
                    self.assertNotIn('parameters/body', a['inputs']['parameters'])
                walk(a.get('actions', {})); walk(a.get('else', {}).get('actions', {}))
        walk(graph); self.assertEqual((c, b), original)
        self.assertNotIn('triggerBody(', json.dumps(graph))
        self.assertNotIn('Create_case', names); self.assertNotIn('Apply_projection', names)
        work = graph['Closure_check_chain']['actions']
        self.assertIs(work['Closure_date_consistent']['inputs'], False)
        receipt = work['Native_closure_observation']['inputs']
        for key in ['closurePerformed', 'nextOccurrenceCreated', 'progressionGranted', 'actorAuthorityQualified', 'policyApproved']:
            self.assertIs(receipt[key], False)

    def test_date_provenance_is_separate_scoped_retained_evidence(self):
        c, b, _ = fixture(True); work = build_actions(c, b)['Closure_check_chain']['actions']
        record = {'FictionalTest': True, 'notOperational': True, 'policyAuthorityGranted': False,
                  'scope': SCOPE, 'reviewDate': '2030-10-20',
                  'ruleReference': 'fictional://explicit-test-rule', 'evidenceReference': 'fictional://test-date',
                  'recordedBy': 'FICTIONAL test recorder'}
        meta = {'UniqueId': DATE_UID, 'ETag': '"1"'}
        ev = Expressions({'Closure_date_before': meta, 'Closure_date_after': meta},
            {'Closure_date_record': record, 'Native_prepared_revision': {'preparedRevision': {'scope': SCOPE}}})
        expression = work['Closure_date_consistent']['inputs']; self.assertTrue(ev.evaluate(expression))
        for key in ['ruleReference', 'evidenceReference', 'recordedBy']:
            altered = copy.deepcopy(record); altered[key] = ''; ev.outputs['Closure_date_record'] = altered
            self.assertFalse(ev.evaluate(expression))
        for key, value in [('notOperational', False), ('notOperational', None),
                           ('policyAuthorityGranted', True), ('policyAuthorityGranted', None),
                           ('ruleReference', 'https://example.invalid/operational-rule')]:
            altered = copy.deepcopy(record); altered[key] = value
            ev.outputs['Closure_date_record'] = altered
            self.assertFalse(ev.evaluate(expression), (key, value))
        altered = copy.deepcopy(record); altered['scope']['DocumentSHA256'] = 'c' * 64
        ev.outputs['Closure_date_record'] = altered; self.assertFalse(ev.evaluate(expression))
        self.assertNotIn('targetDate', json.dumps(work))

    def test_issued_bytes_and_late_issued_or_date_drift_hold(self):
        c, b, rows = fixture(True); work = build_actions(c, b)['Closure_check_chain']['actions']
        issue = work['Closure_issued_guard']['actions']
        meta = {'UniqueId': 'FICTIONAL-issued', 'ETag': '"1"'}
        date_meta = {'UniqueId': DATE_UID, 'ETag': '"1"'}
        ev = Expressions({
            'Closure_selected_publication': [rows[4]],
            'Closure_issued_before': meta, 'Closure_issued_after': meta,
            'Closure_final_issued': meta,
            'Closure_issued_content': {'$content': 'RklDVElPTkFM'},
            'Closure_draft_content': {'$content': 'RklDVElPTkFM'},
            'Closure_date_after': date_meta, 'Closure_final_date': date_meta},
            {'Closure_chain_consistent': True, 'Closure_frame_consistent': True,
             'Closure_date_consistent': True, 'Closure_issued_consistent': True})
        self.assertTrue(ev.evaluate(issue['Closure_issued_consistent']['inputs']))
        ev.bodies['Closure_draft_content'] = {'$content': 'RklDVElPTkFMIGVkaXQ='}
        self.assertFalse(ev.evaluate(issue['Closure_issued_consistent']['inputs']))
        ev.bodies['Closure_issued_content'] = {'$content': ''}
        ev.bodies['Closure_draft_content'] = {'$content': ''}
        self.assertFalse(ev.evaluate(issue['Closure_issued_consistent']['inputs']))
        ev.bodies['Closure_issued_content'] = {'$content': 'RklDVElPTkFM'}
        ev.bodies['Closure_draft_content'] = {'$content': 'RklDVElPTkFM'}
        final_issue = work['Closure_final_issued_guard']['actions']['Closure_issued_current']['inputs']
        final_date = work['Closure_date_current']['inputs']
        self.assertTrue(ev.evaluate(final_issue)); self.assertTrue(ev.evaluate(final_date))
        ev.outputs.update(Closure_issued_current=True, Closure_date_current=True)
        ev.outputs['Native_prepared_revision'] = {'preparedRevision': {'scope': SCOPE}}
        frame = work['Closure_frame_consistent']['inputs']
        for name in re.findall(r"body\('([^']+)'\)", frame):
            if 'stable' in name:
                ev.bodies[name] = []
            elif name.endswith('assurance_after') or name.startswith('Closure_final_readiness') or name.startswith('Closure_final_consultation'):
                ev.bodies[name] = {'value': []}
            elif 'case' in name:
                ev.bodies[name] = {'CaseUID': SCOPE['CaseUID'], 'evidenceDraftLink': SCOPE['DocumentReference']}
            else:
                ev.bodies[name] = {'UniqueId': 'FICTIONAL-frame-file', 'ETag': '"1"'}
        for name in re.findall(r"outputs\('([^']+)'\)", frame):
            if 'case' in name: ev.outputs[name] = {'headers': {'ETag': '"FICTIONAL-case-token"'}}
        ev.outputs['Closure_frame_consistent'] = ev.evaluate(frame)
        self.assertTrue(ev.outputs['Closure_frame_consistent'])
        receipt = work['Native_closure_observation']['inputs']
        self.assertTrue(ev.evaluate(receipt['nextOccurrencePrerequisitesConsistent']))
        ev.bodies['Closure_final_issued'] = {**meta, 'ETag': '"2"'}
        self.assertFalse(ev.evaluate(final_issue))
        # The final frame explicitly requires the late issued check.
        self.assertIn("equals(outputs('Closure_issued_current'),true)", work['Closure_frame_consistent']['inputs'])
        ev.outputs['Closure_issued_current'] = ev.evaluate(final_issue)
        ev.outputs['Closure_frame_consistent'] = ev.evaluate(frame)
        self.assertFalse(ev.evaluate(receipt['closureEvidenceConsistent']))
        ev.bodies['Closure_final_issued'] = meta
        ev.outputs['Closure_issued_current'] = ev.evaluate(final_issue)
        ev.outputs['Closure_frame_consistent'] = ev.evaluate(frame)
        ev.bodies['Closure_final_date'] = {**date_meta, 'ETag': '"2"'}
        ev.outputs['Closure_date_current'] = ev.evaluate(final_date)
        self.assertFalse(ev.evaluate(receipt['nextReviewDateProvenanceConsistent']))
        self.assertFalse(ev.evaluate(receipt['nextOccurrencePrerequisitesConsistent']))
        self.assertTrue(ev.evaluate(receipt['closureEvidenceConsistent']))
        # A skipped initial issued branch never evaluates the URL's first(row).
        ev.bodies['Closure_selected_publication'] = []
        ev.outputs['Closure_issued_consistent'] = None
        self.assertFalse(ev.evaluate(work['Closure_final_issued_guard']['expression']))

    def test_unsafe_or_filtered_resources_and_ambiguous_selections_refused(self):
        c, b, _ = fixture()
        for change in ['filter', 'duplicate', 'purpose', 'date', 'write']:
            cc, bb = copy.deepcopy(c), copy.deepcopy(b)
            if change == 'filter': bb['assuranceCollectionUri'] += '?$top=1'
            if change == 'duplicate': bb['selectedEvents']['verification'] = bb['selectedEvents']['implementation']
            if change == 'purpose': bb['purposeReferences']['authorisation'] = ''
            if change == 'date': bb['nextReviewEvidenceFileUID'] = 'arbitrary-path'
            if change == 'write': cc['properties']['definition']['actions']['Resolve_context']['actions']['Read_selected_case']['inputs']['parameters']['parameters/method'] = 'POST'
            with self.subTest(change=change), self.assertRaises(ValueError): build_actions(cc, bb)


if __name__ == '__main__': unittest.main()

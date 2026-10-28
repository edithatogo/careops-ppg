"""Additional roles must not collide with retained consultation request keys."""
import unittest
from build_prepared_consultation_events import build
from test_prepared_consultation_events import composed, branch, URI, ROLE


class ConsultationRoleIdentityTests(unittest.TestCase):
    def expression(self, kind, role, **options):
        out = build(kind, composed(kind), URI, role, **options)
        work = branch(out)['actions']
        if kind == 'request':
            return work['Consultation_payload']['inputs']['EventUID']
        return work['Read_consultation_request']['inputs']['parameters']['parameters/uri']

    def test_legacy_identity_is_unchanged_unless_explicitly_selected(self):
        old = self.expression('request', ROLE)
        self.assertEqual(old, self.expression('request', ROLE, role_scoped_identity=False))
        self.assertNotIn("'-r", old)

    def test_role_identity_is_stable_distinct_and_shared_by_request_and_parent(self):
        roles = ('FICTIONAL unanswered qualification role', 'FICTIONAL declined qualification role')
        expressions = []
        for role in roles:
            req = self.expression('request', role, role_scoped_identity=True)
            self.assertEqual(req, self.expression('request', role, role_scoped_identity=True))
            self.assertIn(req[1:], self.expression('response', role, role_scoped_identity=True))
            self.assertNotEqual(req, self.expression('request', ROLE))
            expressions.append(req)
        self.assertNotEqual(*expressions)

    def test_truthy_non_boolean_cannot_change_existing_identity(self):
        for value in (1, 'true', None):
            with self.assertRaises(ValueError):
                self.expression('request', ROLE, role_scoped_identity=value)

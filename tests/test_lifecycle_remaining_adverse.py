"""Exercise emitted purpose predicates; local evidence only, never native acceptance."""
import copy
import unittest
from test_prepared_purpose_events import history_result, rows


class RemainingPurposeAdverseTests(unittest.TestCase):
    def test_cancelled_or_expired_assertions_block_each_downstream_purpose(self):
        for state in ('Cancelled', 'Expired'):
            for selected in range(4):
                history = rows()[:selected + 1]
                history[-1]['RecordState'] = state
                with self.subTest(state=state, selected=selected):
                    self.assertFalse(history_result(history, selected))

    def test_superseding_cancellation_cannot_leave_old_assertion_usable(self):
        original = rows()
        for ordinal in range(4):
            for state in ('Cancelled', 'Expired'):
                cancellation = copy.deepcopy(original[ordinal])
                cancellation.update(EventUID='FICTIONAL-cancellation', RecordState=state,
                    SupersedesEventUID=original[ordinal]['EventUID'], Id=100,
                    GUID='FICTIONAL-cancellation-guid')
                with self.subTest(ordinal=ordinal, state=state):
                    self.assertFalse(history_result(original + [cancellation]))

    def test_wrong_scope_terminal_record_does_not_cancel_current_scope(self):
        for field, value in (('CaseUID', 'FICTIONAL-other-case'),
                             ('ReviewedVersionRef', 'FICTIONAL-other-version'),
                             ('DocumentSHA256', 'c' * 64)):
            terminal = copy.deepcopy(rows()[0])
            terminal.update(EventUID='FICTIONAL-other-terminal', RecordState='Cancelled',
                SupersedesEventUID=None, Id=100, GUID='FICTIONAL-other-guid')
            terminal[field] = value
            with self.subTest(field=field):
                self.assertTrue(history_result(rows() + [terminal]))


if __name__ == '__main__':
    unittest.main()

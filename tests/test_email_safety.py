import unittest
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from scripts.check_email_safety import email_actions


class EmailSafety(unittest.TestCase):
    def test_nested_send_action_is_refused_even_behind_condition(self):
        flow={'actions':{'gate':{'type':'If','actions':{'send':{'type':'OpenApiConnection','inputs':{'host':{'operationId':'SendEmailV2','apiId':'shared_office365'}}}}}}}
        self.assertEqual(len(email_actions(flow)),1)
    def test_graph_mail_and_approval_notifications_are_detected(self):
        for action in [
            {'type':'Http','inputs':{'method':'POST','uri':'https://graph.microsoft.com/v1.0/me/sendMail'}},
            {'type':'OpenApiConnection','inputs':{'host':{'apiId':'shared_approvals','operationId':'StartAndWaitForAnApproval'}}},
            {'type':'OpenApiConnection','inputs':{'host':{'operationId':'SharedMailboxSendEmailV2'}}},
            {'type':'OpenApiConnection','inputs':{'host':{'operationId':'SendMessage','apiId':'shared_gmail'}}}]:
            self.assertEqual(len(email_actions({'actions':{'step':action}})),1)
    def test_nonmail_reads_and_definition_prose_do_not_imply_send(self):
        flow={'description':'Do not SendEmailV2','actions':{'read':{'type':'Http','inputs':{'method':'GET','uri':'https://example.invalid/read'}}}}
        self.assertEqual(email_actions(flow),[])
        self.assertEqual(email_actions({'actions':{'step':{'type':'OpenApiConnection','inputs':{'host':{'apiId':'shared_slack','operationId':'SendMessage'}}}}}),[])

    def test_stopped_flow_with_no_email_actions_can_have_owner_failure_emails(self):
        flow = {'properties': {'state': 'Stopped', 'definition': {'actions': {}},
                               'flowFailureAlertSubscribed': True}}
        findings = email_actions(flow)
        self.assertEqual([x['reason'] for x in findings],
                         ['owner-failure-email-subscription-enabled'])
        flow['properties']['flowFailureAlertSubscribed'] = False
        self.assertEqual(email_actions(flow), [])

    def test_subscription_metadata_must_be_explicit_boolean_false(self):
        for observed in (None, 'false', 0):
            with self.subTest(observed=observed):
                self.assertTrue(email_actions({'properties': {
                    'flowFailureAlertSubscribed': observed}}))
        self.assertEqual(email_actions({'properties': {'definition': {'actions': {}}}}), [])

    def test_strict_native_cli_refuses_unknown_but_preserves_source_inventory(self):
        script = Path(__file__).resolve().parents[1] / 'scripts' / 'check_email_safety.py'
        with tempfile.TemporaryDirectory() as directory:
            flow = Path(directory) / 'flow.json'
            for properties, strict, expected in [
                    ({'definition': {'actions': {}}}, False, 0),
                    ({'definition': {'actions': {}}}, True, 1),
                    ({'flowFailureAlertSubscribed': True}, True, 1),
                    ({'flowFailureAlertSubscribed': False}, True, 0),
                    ({'flowFailureAlertSubscribed': 'false'}, True, 1)]:
                with self.subTest(properties=properties, strict=strict):
                    flow.write_text(json.dumps({'properties': properties}))
                    command = [sys.executable, str(script), '--flow', str(flow)]
                    if strict:
                        command.append('--require-native-alerts-off')
                    result = subprocess.run(command, capture_output=True, text=True, check=False)
                    self.assertEqual(result.returncode, expected, result.stderr)
                    report = json.loads(result.stdout)
                    self.assertEqual(report['strictNativePreflight'], strict)
                    self.assertEqual(report['nativeOwnerAlertsVerifiedOff'],
                                     properties.get('flowFailureAlertSubscribed') is False)


if __name__=='__main__':unittest.main()

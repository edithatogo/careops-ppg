import unittest
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


if __name__=='__main__':unittest.main()

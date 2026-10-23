"""Refuse email-capable actions in a supplied native flow definition; no network."""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

SEND = re.compile(r'(?:send.*(?:e?mail)|smtp|sendmail)', re.I)
MAIL_URL = re.compile(r'(?:/sendMail(?:[/?#\s]|$)|smtp[s]?://|api\.(?:sendgrid|mailgun)\.)', re.I)


def email_actions(flow):
    """Inventory concrete actions recursively; do not infer safety from flow name/state."""
    findings = []
    def visit(value, path):
        if isinstance(value, list):
            for i, child in enumerate(value): visit(child, path + [str(i)])
        elif isinstance(value, dict):
            inputs = value.get('inputs', {})
            host = inputs.get('host', {}) if isinstance(inputs, dict) else {}
            if not isinstance(host, dict): host = {}
            operation = str(host.get('operationId', ''))
            api = str(host.get('apiId', host.get('connectionName', '')))
            uri = (str(inputs.get('uri', '')) + ' ' + str(inputs.get('path', ''))) if isinstance(inputs, dict) else ''
            parameters = inputs.get('parameters', {}) if isinstance(inputs, dict) else {}
            if isinstance(parameters, dict):
                uri += ' ' + str(parameters.get('parameters/uri', ''))
            # Approval actions can deliver invitations without a SendEmail action.
            approval = 'approvals' in api.lower() and not operation.lower().startswith(('get', 'list'))
            mail_send = any(k in api.lower() for k in ('gmail', 'outlook', 'office365', 'smtp', 'mailgun', 'sendgrid')) and operation.lower().startswith('send')
            if value.get('type') and (SEND.search(operation) or MAIL_URL.search(uri) or approval or mail_send):
                findings.append({'actionPath': '/'.join(path), 'operationId': operation,
                                 'reason': 'approval-notification-capable' if approval else 'email-capable-action'})
            for key, child in value.items(): visit(child, path + [key])
    visit(flow, [])
    return findings


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--flow', type=Path, required=True)
    args = p.parse_args()
    flow = json.loads(args.flow.read_text())
    if not isinstance(flow, dict) or not flow:
        raise ValueError('Complete nonempty flow object required')
    findings = email_actions(flow)
    print(json.dumps({'emailCapableActions': findings, 'automaticEmailAllowed': False,
                      'scope': 'Supplied definition only; no native state or external code audit',
                      'writesPerformed': 0}))
    return 1 if findings else 0


if __name__ == '__main__':
    raise SystemExit(main())

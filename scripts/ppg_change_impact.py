"""Offline change-summary snapshot. Does not write, approve or issue documents."""
import argparse
import html
import json
from pathlib import Path


def validate(record, contract):
    for field in contract['fields']:
        value = record.get(field['name'])
        if field['required'] and (value is None or value == '' or value == {'results': []}):
            raise ValueError('Missing ' + field['name'])
        if value is not None and field['type'] in ('Text', 'Note', 'Choice', 'DateTime'):
            if not isinstance(value, str):
                raise ValueError('Expected text: ' + field['name'])
        if field['type'] in ('Choice', 'MultiChoice') and value is not None:
            from xml.etree import ElementTree
            choices = [node.text for node in ElementTree.fromstring(field['schemaXml']).findall('./CHOICES/CHOICE')]
            values = value.get('results') if isinstance(value, dict) else [value]
            if not isinstance(values, list) or any(v not in choices for v in values):
                raise ValueError('Invalid choice: ' + field['name'])
    if record.get('RecordState') == 'Decision recorded' and not record.get('DecisionEvidence', '').strip():
        raise ValueError('Decision evidence missing; status is not approval')
    if (record.get('ApprovedEdition') or record.get('EffectiveDate')) and not record.get('DecisionEvidence', '').strip():
        raise ValueError('Approval assertions need actual decision evidence')
    if record.get('EffectiveDate') and not record.get('ApprovedEdition'):
        raise ValueError('Effective date needs approved edition')
    return record


def render(record, contract, version):
    validate(record, contract)
    if not version.strip():
        raise ValueError('Snapshot needs explicit record version')
    escape = html.escape
    out = '<h2>Change and impact summary</h2><p>Snapshot of record version ' + escape(version) + '. Open the live record for later edits. This summary does not approve or issue a policy.</p>'
    labels = {'Title': 'Review', 'RecordState': 'Record state', 'FromEdition': 'Reviewed edition', 'ProposedEdition': 'Proposed edition', 'ReviewTriggers': 'Why this review started', 'ChangeMagnitude': 'Change magnitude', 'Urgency': 'Urgency', 'MajorChanges': 'Proposed major changes', 'MinorChanges': 'Proposed minor changes', 'Rationale': 'Reasons and evidence', 'Interactions': 'Related requirements and documents', 'ImplementationActions': 'Implementation actions', 'UnresolvedQuestions': 'Unresolved questions', 'DecisionEvidence': 'Recorded decision evidence', 'ApprovedEdition': 'Approved edition', 'EffectiveDate': 'Effective date'}
    for name, label in labels.items():
        value = record.get(name)
        if isinstance(value, dict):
            value = '; '.join(value['results'])
        out += '<h3>' + escape(label) + '</h3>'
        if name in ('MajorChanges', 'MinorChanges') and value:
            bullets = [part.strip() for part in value.replace('\n', '; ').split('; ') if part.strip()]
            out += '<ul>' + ''.join('<li>' + escape(part) + '</li>' for part in bullets) + '</ul>'
        else:
            out += '<p>' + escape(value or 'Not recorded') + '</p>'
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('record', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--record-version', required=True)
    parser.add_argument('--contract', type=Path, default=Path('config/change-impact-register.json'))
    args = parser.parse_args()
    content = render(json.loads(args.record.read_text()), json.loads(args.contract.read_text()), args.record_version)
    with args.output.open('x', encoding='utf-8') as output:
        output.write(content)


if __name__ == '__main__':
    main()

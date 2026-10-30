"""Build narrow, incoming-only Outlook routing rules; never send or enrol mail."""

def routing_rule(key, binding, *, sequence):
    senders = binding.get('senders')
    subject = binding.get('subjectContains')
    folder = binding.get('folderId')
    if not key or not senders or not all(isinstance(s, str) and '@' in s for s in senders):
        raise ValueError('Verified exact senders required')
    if not isinstance(subject, str) or not subject.strip() or not isinstance(folder, str) or not folder:
        raise ValueError('Verified subject and destination folder required')
    if not isinstance(sequence, int) or sequence < 1:
        raise ValueError('Positive rule sequence required')
    return {'displayName': 'PPG | Source updates | ' + key + ' | Routing',
            'sequence': sequence, 'isEnabled': True,
            'conditions': {'fromAddresses': [{'emailAddress': {'address': s}} for s in senders],
                           'subjectContains': [subject]},
            'exceptions': {'subjectContains': ['RE:', 'FW:', 'FWD:']},
            'actions': {'moveToFolder': folder, 'stopProcessingRules': True}}

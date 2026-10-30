"""Pure current-row reconciliation; native writers must reconcile uncertain sends."""
from copy import deepcopy


def reconcile(response, existing, *, namespace, key_fields, fields):
    """Return bounded source-owned patches without modifying supplied records.

    Call only with a complete destination read. Capture provenance is attached by
    the writer only to changed rows; unchanged rows retain their earlier capture.
    """
    result = response.get('result', {})
    rows = result.get('records')
    if response.get('success') is not True or not isinstance(rows, list) or result.get('total') != len(rows):
        raise ValueError('Incomplete source response')
    if not namespace or not key_fields or not set(key_fields) <= set(fields):
        raise ValueError('Explicit namespace, keys and source fields required')
    if set(fields) & {'ID', 'SourceKey', 'SourcePresent'}:
        raise ValueError('Reserved destination field')
    def key(row):
        values = [row.get(field) for field in key_fields]
        if any(value is None or isinstance(value, (bool, dict, list)) or str(value) == '' or ':' in str(value) for value in values):
            raise ValueError('Missing or ambiguous source key')
        value = namespace + ':' + ':'.join(map(str, values))
        if len(value) > 255:
            raise ValueError('Oversized source key')
        return value
    incoming = {}
    for row in rows:
        identity = key(row)
        if identity in incoming or any(field not in row for field in fields):
            raise ValueError('Duplicate identity or missing source field')
        incoming[identity] = {**{field: deepcopy(row[field]) for field in fields}, 'SourceKey': identity, 'SourcePresent': True}
    current = {}
    for row in existing:
        identity = row.get('SourceKey')
        if not isinstance(identity, str) or not identity.startswith(namespace + ':') or identity in current or not row.get('ID'):
            raise ValueError('Invalid or duplicate destination identity')
        current[identity] = row
    operations = []
    for identity, payload in incoming.items():
        old = current.get(identity)
        if old is None:
            operations.append({'kind': 'create', 'key': identity, 'fields': payload})
        else:
            changed = {field: value for field, value in payload.items() if field not in old or old[field] != value}
            if changed:
                operations.append({'kind': 'update', 'key': identity, 'id': old['ID'], 'fields': changed})
    for identity, old in current.items():
        if identity not in incoming and old.get('SourcePresent') is not False:
            operations.append({'kind': 'update', 'key': identity, 'id': old['ID'], 'fields': {'SourcePresent': False}})
    return [operations[start:start + 20] for start in range(0, len(operations), 20)]

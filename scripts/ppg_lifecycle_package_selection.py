"""Read-only admission of an explicitly selected fictional lifecycle revision.

This separate adapter does not weaken the catalogue-backed case selector. The
caller must read/pin/recheck the native case, event sets and files around freezing.
"""
import hashlib
import io
import json
import zipfile
from xml.etree import ElementTree as ET
from ppg_full_document import SCALARS, GROUPS, W

NS = '{' + W + '}'


def reconcile_initiated(case, request, source_pin, source_bytes, event_sets):
    """A new fictional occurrence needs no inherited draft or business finding."""
    r = request['request']
    if not case['CaseUID'].startswith('LC-FICTIONAL-') or not r.get('qualificationOnly') or r.get('realPolicyEffects') is not False:
        raise ValueError('fictional_selection_required')
    if case['CaseUID'] != r['CaseUID'] or json.loads(case['linkedDocumentUIDs']) != [r['DocumentUID']]:
        raise ValueError('occurrence_or_source_mismatch')
    if not case['caseStatus'].startswith('Initiated') or case['evidenceDraftLink'] != r['DocumentReference']:
        raise ValueError('initiated_source_only_case_required')
    if r['ReviewedVersionRef'] != 'sharepoint:' + source_pin['UniqueId'] + ':' + source_pin['ETag'] or hashlib.sha256(source_bytes).hexdigest() != r['DocumentSHA256']:
        raise ValueError('original_source_mismatch')
    for collection in event_sets.values():
        if collection.get('value') != [] or any(collection.get(k) for k in ['nextLink', '@odata.nextLink', 'odata.nextLink']):
            raise ValueError('new_occurrence_has_events_or_incomplete_read')
    return {'kind': 'fictional-initiated-source-selection-v1', 'CaseUID': case['CaseUID'],
            'occurrenceReference': r['occurrenceReference'], 'caseVersion': case['OData__UIVersionString'],
            'sourceDocumentUID': r['DocumentUID'], 'originalSourceScope': {k: r[k] for k in ['CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256']},
            'scope': 'current initiated fictional occurrence; source-only draft preparation',
            'includedEvents': {}, 'reviewFindingsRecorded': False, 'ownershipAcceptanceRecorded': False,
            'currentPolicyClaim': False, 'nextOccurrenceFindingsInherited': False,
            'caseWrites': False, 'sourceWrites': False}


def reconcile(case, request, prepared, candidate_pin, candidate_bytes, event_sets):
    uid = case['CaseUID']
    r = request['request']
    f = prepared['file']
    if not uid.startswith('LC-FICTIONAL-') or not r.get('qualificationOnly') or r.get('realPolicyEffects') is not False:
        raise ValueError('fictional_selection_required')
    if uid != r['CaseUID'] or uid != prepared['CaseUID'] or r['occurrenceReference'] != prepared['occurrenceReference']:
        raise ValueError('occurrence_mismatch')
    if case['evidenceDraftLink'] != f['DocumentReference'] or f['UniqueId'].lower() != candidate_pin['UniqueId'].lower() or f['ETag'] != candidate_pin['ETag'] or f['nativeVersion'] != candidate_pin['UIVersionLabel'] or f['SHA256'] != hashlib.sha256(candidate_bytes).hexdigest():
        raise ValueError('candidate_revision_mismatch')
    original = prepared['originalSourceScope']
    if any(r[k] != original[k] for k in ['CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256']):
        raise ValueError('original_source_mismatch')
    if json.loads(case['linkedDocumentUIDs']) != [r['DocumentUID']]:
        raise ValueError('source_identity_mismatch')
    selected, historical = {}, {}
    version = 'sharepoint:' + f['UniqueId'] + ':' + f['ETag']
    for kind, collection in event_sets.items():
        if any(collection.get(k) for k in ['nextLink', '@odata.nextLink', 'odata.nextLink']):
            raise ValueError('event_set_incomplete')
        rows = collection['value']
        if any(row['CaseUID'] != uid or row.get('FictionalTest') is not True for row in rows):
            raise ValueError('event_occurrence_mismatch')
        # Never treat an earlier candidate's ready/decision records as evidence
        # for this candidate merely because the case identity matches.
        selected[kind] = [row for row in rows if row['DocumentReference'] == f['DocumentReference'] and row['ReviewedVersionRef'] == version and row['DocumentSHA256'] == f['SHA256']]
        historical[kind] = [row for row in rows if row not in selected[kind]]
    return {'kind': 'fictional-lifecycle-revision-selection-v1', 'CaseUID': uid,
            'occurrenceReference': r['occurrenceReference'], 'caseVersion': case['OData__UIVersionString'],
            'originalSourceScope': original, 'candidate': f, 'sourceDocumentUID': r['DocumentUID'],
            'includedEvents': selected, 'otherRevisionEvents': historical,
            'scope': 'historical completed fictional technical qualification only',
            'currentPolicyClaim': False, 'nextOccurrenceFindingsInherited': False,
            'caseWrites': False, 'sourceWrites': False}


def read_candidate_values(raw, allow_omitted_groups=False):
    """Preserve recorded template content and edits; supply no new findings."""
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    def name(control):
        tag = control.find(NS+'sdtPr/'+NS+'tag')
        return tag.get(NS+'val') if tag is not None else ''
    def text(node):
        if node.tag == NS+'t': return node.text or ''
        if node.tag == NS+'br': return '\n'
        value = ''.join(text(child) for child in node)
        return value + ('\n' if node.tag == NS+'p' else '')
    values = {}
    for control in root.iter(NS+'sdt'):
        key = name(control)
        if key in SCALARS:
            if key in values: raise ValueError('duplicate_candidate_scalar')
            values[key] = text(control.find(NS+'sdtContent')).rstrip('\n')
        elif key in GROUPS:
            rows = []
            for item in control.find(NS+'sdtContent').findall(NS+'sdt'):
                row = {name(c): text(c.find(NS+'sdtContent')).rstrip('\n') for c in item.iter(NS+'sdt') if name(c)}
                if sorted(row) != sorted(GROUPS[key]): raise ValueError('candidate_repeat_shape')
                rows.append(row)
            values[key] = rows
    if allow_omitted_groups:
        for key in GROUPS:
            values.setdefault(key, [])
    if set(values) != set(SCALARS + list(GROUPS)):
        raise ValueError('candidate_control_inventory')
    values['includedRecordIDs'] = [v.strip() for v in values['includedRecordIDs'].split(';') if v.strip()]
    return values

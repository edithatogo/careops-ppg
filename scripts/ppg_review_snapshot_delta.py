"""Separate unchanged prior annotations from an unchanged complete export."""
import hashlib
import json
from scripts.ppg_annotation_adapter import annotations_from_export


def compare_exports(before_bytes, after_bytes, document_uid):
    if not isinstance(document_uid, str) or not document_uid:
        raise ValueError('Document identity required')
    before, after = json.loads(before_bytes), json.loads(after_bytes)
    if before['listId'] != after['listId'] or before['binding'] != after['binding']:
        raise ValueError('Annotation resource/binding changed; reconcile first')

    def selected(export):
        rows = annotations_from_export(export)  # Requires complete original history.
        ids = [r['annotationId'] for r in rows]
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate annotation identity')
        return {r['annotationId']: r for r in rows if r['documentUID'] == document_uid}

    old, new = selected(before), selected(after)
    added, missing = sorted(new.keys()-old.keys()), sorted(old.keys()-new.keys())
    changed = sorted(key for key in old.keys() & new.keys() if old[key] != new[key])
    before_sha = hashlib.sha256(before_bytes).hexdigest()
    after_sha = hashlib.sha256(after_bytes).hexdigest()
    return {'beforeExportSHA256': before_sha, 'afterExportSHA256': after_sha,
            'wholeExportUnchanged': before_sha == after_sha,
            'subjectCountBefore': len(old), 'subjectCountAfter': len(new),
            'addedAnnotationIds': added, 'missingAnnotationIds': missing,
            'changedAnnotationIds': changed,
            'previousSubjectRowsUnchanged': not missing and not changed,
            'currentSubjectRowsUnchanged': not added and not missing and not changed}


def require_whole_export_claim(delta, claim):
    if not isinstance(claim, bool) or claim != delta['wholeExportUnchanged']:
        raise ValueError('Whole-export claim differs from actual snapshot hashes')
    return True

"""Prepare version-bound plain-text notes for the supported manual SharePoint/web route.

This helper never generates or modifies Word. Its output contains real records
and must stay in private/native storage.
"""
import hashlib
import io
from collections import Counter
from zipfile import ZipFile
import xml.etree.ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
MARKER = 'DEVELOPMENT REVIEW NOTES — HISTORICAL V6 — NOT APPROVED CLINICAL CONTENT'


def prepare(pack, annotations, evidence_url):
    if annotations != pack['currentSubjectAnnotations']:
        raise ValueError('Reviewer state changed; reconcile a successor pack first')
    if pack['humanDecision'] is not None or pack['policyApproved'] or pack['publicationAuthorised']:
        raise ValueError('Expected unapproved development pack')
    if not evidence_url.startswith('https://'):
        raise ValueError('Expected qualified evidence URL')
    ids = [a['annotationId'] for a in annotations]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate annotation identity')
    lines = [MARKER, 'Separate version-bound review companion; current-version verification is open and nonblocking.',
             'The maintained historical procedure and saved edits remain separate and unchanged. These notes are suggestions, not decisions.',
             'Complete review pack, comparison matrix, citations, retained files and histories: '+evidence_url,
             'Inspection SHA-256: '+pack['inspectedSourceSha256'],
             'Criteria version: '+str(pack['preparation']['criteriaVersion']),
             'Catalogue identities accounted: '+str(pack['preparation']['catalogueCount']),
             'Provisional retained comparisons: '+str(len(pack['comparisonBatch']['pairAssessments'])),
             'Source-only reviews: '+str(len(pack['sourceOnlyReviews'])),
             'No current V7 comparison, accepted template mapping, approval, issuance or notification is implied.',
             'All comparison findings remain in the linked full pack; none are excluded by this notes view.', '']
    for a in annotations:
        if a['documentUID'] != pack['requestedSubject']['documentUID']:
            raise ValueError('Annotation belongs to another subject')
        lines += ['Annotation '+a['annotationId'], 'Recorded state: '+a['status'],
                  'Document version: '+str(a['documentVersion']), 'Section: '+str(a['sectionId']),
                  'Contributor: '+str(a['contributorId'])+'; created: '+str(a['createdAt']),
                  'Original suggestion:', a['originalText']]
        if a.get('latestAddition') and a['latestAddition'] != a['originalText']:
            lines += ['Latest recorded addition:', a['latestAddition']]
        lines += ['Evidence reference: '+str(a.get('evidenceRef') or 'Unknown'),
                  'Recorded rationale: '+str(a.get('decisionRationale') or 'No rationale recorded'),
                  'Incorporated version: '+str(a.get('incorporatedVersion') or 'Not recorded'), '']
    lines += ['Next actions for an authorised reviewer:',
              'Assess the suggested changes and full comparison evidence; record decisions separately.',
              'Reconcile unresolved template, conversion and coverage gaps; preserve source and human edits.',
              'Current procedure/template/control-authority verification stays open and nonblocking.',
              'END OF DEVELOPMENT REVIEW NOTES']
    return '\n'.join(lines)


def verify_append(before, after, notes):
    """Qualify saved append-only text and preserved structures, not regeneration."""
    def read(raw):
        with ZipFile(io.BytesIO(raw)) as archive:
            if (len(archive.namelist()) != len(set(archive.namelist()))
                    or sum(p.file_size for p in archive.infolist()) > 100_000_000
                    or archive.testzip() is not None):
                raise ValueError('Invalid Word package')
            parts = {n: archive.read(n) for n in archive.namelist()}
        for value in parts.values():
            if b'<!DOCTYPE' in value or b'<!ENTITY' in value:
                raise ValueError('Unsupported XML declaration')
        body = ET.fromstring(parts['word/document.xml']).find(W+'body')
        text = ''.join(n.text or '' for n in body.iter() if n.tag in {W+'t', W+'delText'})
        revisions = Counter((n.tag, tuple(sorted(n.attrib.items())),
                             ''.join(t.text or '' for t in n.iter() if t.tag in {W+'t', W+'delText'}))
                            for n in body.iter() if n.tag in {W+'ins', W+'del'})
        return parts, body, text, revisions
    old, old_body, old_text, old_revisions = read(before)
    new, new_body, new_text, new_revisions = read(after)
    # Native paragraph boundaries are not text nodes. Only known newline input
    # characters are removed; no whitespace/fuzzy match can hide changed words.
    expected = notes.replace('\r', '').replace('\n', '')
    if MARKER in old_text or new_text != old_text+expected or new_text.count(MARKER) != 1:
        raise ValueError('Saved text is not the exact append-only proposal')
    protected = [n for n in old if n.startswith(('word/media/', 'word/header', 'word/footer', 'word/comments'))]
    if any(new.get(n) != old[n] for n in protected):
        raise ValueError('Protected graphics/header/footer/comment part changed')
    if old_revisions-new_revisions:
        raise ValueError('Prior tracked revision changed or missing')
    for name, raw in old.items():
        if not name.endswith('.rels'):
            continue
        if name not in new:
            raise ValueError('Prior relationship part missing')
        prior = list(ET.fromstring(raw))
        current = list(ET.fromstring(new[name]))
        ids = [n.get('Id') for n in current]
        if len(ids) != len(set(ids)) or any(not n.get('Id') for n in current):
            raise ValueError('Ambiguous relationship identity')
        by_id = {n.get('Id'): n.attrib for n in current}
        if any(by_id.get(n.get('Id')) != n.attrib for n in prior):
            raise ValueError('Prior link/relationship changed')
    instructions = lambda body: [n.text or '' for n in body.iter(W+'instrText')]
    old_fields, new_fields = instructions(old_body), instructions(new_body)
    if new_fields[:len(old_fields)] != old_fields:
        raise ValueError('Prior field instruction changed')
    old_tables = [ET.tostring(n) for n in old_body.iter(W+'tbl')]
    new_tables = [ET.tostring(n) for n in new_body.iter(W+'tbl')]
    if old_tables != new_tables:
        raise ValueError('Prior table XML changed')
    return dict(beforeSHA256=hashlib.sha256(before).hexdigest(), afterSHA256=hashlib.sha256(after).hexdigest(),
                exactPriorTextAndNotes=True, protectedParts=len(protected), priorRevisionsPreserved=True,
                tablesPreserved=len(old_tables), generationPerformed=False, savedFieldRefreshVerified=False,
                scope='Saved manual append-only proposal; not complete visual or structured regeneration parity')

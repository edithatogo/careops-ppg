"""Validate loss-aware editorial proposals and bound companion-guide snapshots.

No native calls, Word generation, source mutation or clinical approval.
Real proposal content belongs in approved private evidence, not Git.
"""
import hashlib
import html
import json


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def prepare(source, template, proposal):
    import re
    if (any(not proposal.get(k, '').strip() for k in ['documentUID', 'revision', 'guideVersion'])
            or not re.fullmatch('[0-9a-f]{64}', proposal.get('originalSourceSHA256', ''))):
        raise ValueError('Persistent identity and original-source pin required')
    if proposal.get('status') != 'unapproved_review_draft' or proposal.get('clinicalApproval') is not False:
        raise ValueError('Unapproved editorial draft required')
    if proposal.get('currentVersionVerified') is not False or proposal.get('notificationsEnabled') is not False:
        raise ValueError('No current-authority or notification assertion permitted')
    if (source['sourceSha256'], template['sourceSha256']) != (proposal['sourceSHA256'], proposal['templateSHA256']):
        raise ValueError('Source/template pin mismatch')
    originals = {e['elementId']: e for e in source['elements']}
    candidates = {e['elementId']: e for e in template['elements']}
    if not originals or not candidates or len(originals) != len(source['elements']) or len(candidates) != len(template['elements']):
        raise ValueError('Duplicate inventory identity')
    sections = proposal['sections']
    by_id = {s['sectionId']: s for s in sections}
    if not sections or len(by_id) != len(sections):
        raise ValueError('Missing or duplicate proposal section')
    covered = {}
    for s in sections:
        if not s.get('text', '').strip() or not s.get('sourceElements') or not s.get('templateElements'):
            raise ValueError('Text and source/template evidence required')
        if set(s['sourceElements']) - originals.keys() or set(s['templateElements']) - candidates.keys():
            raise ValueError('Unknown evidence element')
        if s['basis'] not in {'editorial_paraphrase', 'retained_historical_reference'}:
            raise ValueError('Unsupported clinical-content assertion')
        for element in s['sourceElements']:
            covered.setdefault(element, []).append(s['sectionId'])
    retention = proposal['retention']
    if set(retention) != originals.keys() - covered.keys():
        raise ValueError('Every source element needs a proposal destination or explicit retention')
    if any(not reason.strip() for reason in retention.values()):
        raise ValueError('Retention rationale required')
    hashes = {k: digest(v) for k, v in by_id.items()}
    guides = proposal['guideSections']
    if not guides or len({g['sectionId'] for g in guides}) != len(guides):
        raise ValueError('Missing or duplicate guide section')
    for g in guides:
        refs = g['procedureSections']
        if not refs or set(refs) - by_id.keys() or not g['text'].strip():
            raise ValueError('Guide section has no valid procedure binding')
        if g['procedureHashes'] != {key: hashes[key] for key in refs}:
            raise ValueError('Guide alignment needs reconciliation')
    ledger = [dict(elementId=k, sourceLocator=e['sourceLocator'], sourceText=e.get('text', ''),
                   sourceXMLSHA256=e.get('xmlSha256'), proposalSections=covered.get(k, []),
                   retention=retention.get(k), originalPreserved=True)
              for k, e in originals.items()]
    return dict(schemaVersion=1, proposal=proposal, procedureHashes=hashes,
                proposalSHA256=digest(proposal), coverage=ledger,
                sourceElementCount=len(ledger), templateElementCount=len(candidates),
                templateRetention=[dict(elementId=k, sourceLocator=e['sourceLocator'],
                                        disposition='Candidate reference only; requiredness unverified')
                                   for k, e in candidates.items()],
                approval=False, currentAuthorityVerified=False,
                alignment='Bound draft snapshot; later edits require reconciliation')


def reconcile_native(prepared, rows):
    expected = prepared['proposal']['sections']
    if len(rows) != len(expected) or len({r['SectionId'] for r in rows}) != len(rows):
        raise ValueError('Incomplete or ambiguous native sections')
    by_id = {r['SectionId']: r for r in rows}
    if set(by_id) != {s['sectionId'] for s in expected}:
        raise ValueError('Unknown native section')
    for s in expected:
        r = by_id[s['sectionId']]
        if (r['ProposalRevision'] != prepared['proposal']['revision'] or r['ProposedText'] != s['text']
                or r['DocumentUID'] != prepared['proposal']['documentUID']
                or json.loads(r['SectionJSON']) != s):
            raise ValueError('Native edit retained; guide alignment needs reconciliation')
    return True


def render(prepared, kind, links):
    p = prepared['proposal']; esc = html.escape
    rows = p['sections'] if kind == 'procedure' else p['guideSections']
    if kind not in {'procedure', 'guide'}:
        raise ValueError('Unknown presentation')
    from urllib.parse import urlsplit
    for target in links.values():
        uri = urlsplit(target)
        if uri.scheme != 'https' or not uri.netloc or uri.username or uri.password:
            raise ValueError('Unsafe evidence link')
    title = 'Simplified procedure proposal' if kind == 'procedure' else 'Doctor guide draft 2'
    out = ['<h2>'+title+'</h2>', '<p><strong>UNAPPROVED REVIEW DRAFT. Historical V6 and unverified template candidate; not issued clinical instructions.</strong></p>',
           '<p>Proposal '+esc(p['revision'])+'. Current-version verification remains open and nonblocking for development. Use current authorised instructions for patient care.</p>']
    for s in rows:
        out += ['<h3>'+esc(s['title'])+'</h3>', '<p>'+esc(s['text']).replace('\n', '<br/>')+'</p>']
        refs = s.get('procedureSections', s.get('sourceElements', []))
        labels = ({e['elementId']: e['sourceLocator'] for e in prepared['coverage']}
                  if kind == 'procedure' else {x['sectionId']: x['title'] for x in p['sections']})
        out += ['<p><em>Source: '+esc('; '.join(labels.get(ref, ref) for ref in refs))+'</em></p>']
        if s.get('questions'):
            out += ['<p><strong>Open:</strong> '+esc(s['questions'])+'</p>']
    out += ['<h3>Alignment and preservation</h3><p>This is a version-bound snapshot, not automatic synchronisation. Inspect the matching revision and native section versions. Preserve human edits; changes require a reconciled guide successor.</p>',
            '<p>Every source element and candidate-template element has an accounted disposition in the linked package. Original complex content, comments, revisions and historical approvals remain evidence; no current authority or full conversion fidelity is inferred.</p>',
            '<ul>'+''.join('<li><a href="'+esc(v, quote=True)+'">'+esc(k)+'</a></li>' for k,v in links.items())+'</ul>']
    return '\n'.join(out)


def reconcile_successor(source, template, previous, rows, revision, guide_version,
                        guide_texts, rationale):
    """Prepare an explicit successor from web text edits; never modify native rows.

    All guide wording must be explicitly supplied after review. Source bindings and
    section definitions are retained; metadata edits need separate reconciliation.
    """
    import copy
    p = previous['proposal']
    if (not revision.strip() or revision == p['revision']
            or not guide_version.strip() or guide_version == p['guideVersion']
            or not rationale.strip()):
        raise ValueError('New procedure/guide revisions and reconciliation rationale required')
    if prepare(source, template, p) != previous:
        raise ValueError('Previous snapshot differs from pinned evidence')
    expected = {s['sectionId']: s for s in p['sections']}
    if len(rows) != len(expected) or {r['SectionId'] for r in rows} != expected.keys():
        raise ValueError('Complete unique native revision required')
    if set(guide_texts) != {g['sectionId'] for g in p['guideSections']}:
        raise ValueError('Explicit wording for every guide section required')
    successor = copy.deepcopy(p)
    changed = {}
    for row in rows:
        original = expected[row['SectionId']]
        if (row['DocumentUID'] != p['documentUID'] or row['ProposalRevision'] != p['revision']
                or json.loads(row['SectionJSON']) != original):
            raise ValueError('Native scope/definition edit requires separate reconciliation')
        if not row['ProposedText'].strip():
            raise ValueError('Edited text cannot be empty')
        changed[row['SectionId']] = row['ProposedText']
    for section in successor['sections']:
        section['text'] = changed[section['sectionId']]
    hashes = {s['sectionId']: digest(s) for s in successor['sections']}
    for guide in successor['guideSections']:
        guide['text'] = guide_texts[guide['sectionId']]
        guide['procedureHashes'] = {key: hashes[key] for key in guide['procedureSections']}
    successor.update(revision=revision, guideVersion=guide_version,
                     reconciliation=dict(previousProposalSHA256=previous['proposalSHA256'],
                                         previousRevision=p['revision'], rationale=rationale))
    return prepare(source, template, successor)


def main():
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description='Reconcile an exported web edit into a separate draft successor')
    for name in ['source', 'template', 'previous', 'rows', 'guide-texts', 'output',
                 'revision', 'guide-version', 'rationale']:
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    read = lambda path: json.loads(Path(path).read_text())
    result = reconcile_successor(read(args.source), read(args.template), read(args.previous),
                                 read(args.rows), args.revision, args.guide_version,
                                 read(args.guide_texts), args.rationale)
    # A distinct file is mandatory; existing reviewer work is never overwritten.
    with Path(args.output).open('x') as target:
        json.dump(result, target, indent=2, ensure_ascii=False)
        target.write('\n')


if __name__ == '__main__':
    main()

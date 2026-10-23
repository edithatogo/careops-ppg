"""Publishable technical results from pinned lifecycle proof, never user benefits."""
import argparse
import hashlib
import html
import json
from pathlib import Path

from ppg_observation_measures import observation_report

ROOT = Path(__file__).resolve().parents[1]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def result(manifest_raw, assurance_raw, checks_raw, source_commit):
    manifest, assurance, checks = map(json.loads, (manifest_raw, assurance_raw, checks_raw))
    if not manifest.get('qualified') or not assurance.get('qualified') or not checks.get('passed'):
        raise ValueError('Qualified evidence and passing local checks required')
    if manifest['technicalAssurance']['SHA256'] != digest(assurance_raw):
        raise ValueError('Pinned technical assurance differs')
    runs = manifest['qualifiedCycleRunIds']
    profiles = manifest['currentNineRawProfiles']
    geometry = assurance['nativeGeometry']
    if (not runs or len(runs) != len(set(runs))
            or len(runs) != assurance['qualifiedDistinctCycleRuns']
            or len(profiles) != len(geometry)
            or {p['stage'] for p in profiles} != {p['stage'] for p in geometry}
            or len({p['stage'] for p in profiles}) != len(profiles)):
        raise ValueError('Duplicate or inconsistent run/profile accounting')
    if (manifest['qualifiedFullCycles'] != assurance['qualifiedFullCycles']
            or manifest['cycleCompleteActionRecords'] != assurance['cycleCompleteActionRecords']
            or manifest['counts'] != assurance['counts']
            or manifest.get('realPolicyEffects') is not False
            or assurance.get('realPolicyEffects') is not False
            or manifest.get('activeNativeRuns') != 0 or assurance.get('activeNativeRuns') != 0
            or assurance.get('allRefusalWritersSkippedAndFourListsFourFoldersPreserved') is not True
            or assurance.get('twentyArtifactMetadataFramesAndOriginalEditedIssuedBytesPreserved') is not True
            or assurance.get('allNineExactStarted') is not True):
        raise ValueError('Incomplete or inconsistent technical safety evidence')
    refusals = assurance['sixFreshNativeSafeRefusalRuns']
    if (manifest['safeRefusalRuns'] != refusals
            or sum(r['actions'] for r in refusals.values()) != assurance['refusalCompleteActionRecords']
            or manifest['refusalCompleteActionRecords'] != assurance['refusalCompleteActionRecords']
            or len({r['runId'] for r in refusals.values()}) != len(refusals)):
        raise ValueError('Refusal accounting differs')
    if any(p.get('state') != 'Started' or p.get('definitionReferencesModificationTimeExact') is not True
           for p in profiles):
        raise ValueError('Unverified installed profile')
    if any(g['actionCount'] > 500 or g['maximumActionDepth'] > 8
           or g['maximumExpressionCharacters'] > 8192 for g in geometry):
        raise ValueError('Native geometry exceeds qualified bounds')
    if not source_commit or any(c not in '0123456789abcdef' for c in source_commit) or len(source_commit) != 40:
        raise ValueError('Exact source commit required')
    observation = observation_report((ROOT/'templates/operator-usability/operator-observation.csv').read_text())
    if observation['summary']['attemptedTasks'] != 0:
        raise ValueError('Unobserved template unexpectedly contains observations')
    return {
        'schemaVersion': 1, 'kind': 'fictional-technical-usability-result',
        'asOfUTC': manifest['observedUTC'], 'sourceCommit': source_commit,
        'evidenceSHA256': {'manifest': digest(manifest_raw), 'assurance': digest(assurance_raw),
                           'localChecks': digest(checks_raw)},
        'technical': {'configuredCycles': manifest['qualifiedFullCycles'], 'qualifiedCycleRuns': len(runs),
                      'cycleActionRecords': assurance['cycleCompleteActionRecords'],
                      'safeRefusalRuns': len(refusals), 'refusalActionRecords': assurance['refusalCompleteActionRecords'],
                      'frozenStartedProfiles': len(profiles), 'activeRuns': 0,
                      'localTests': checks['tests'], 'preservationVerified': True},
        'observation': {'actualUserSampleCount': 0, 'handsOnSeconds': None, 'timeSavedSeconds': None,
                        'reviewerBenefit': 'not measured', 'ordinaryUserAccess': 'user-deferred',
                        'existingTemplateSummary': observation['summary']},
        'limits': {'clinicalApproval': False, 'operationalRollout': False,
                   'nativeGenerationQualified': assurance['nativeGenerationQualified'],
                   'solutionMembership': 'unresolved; raw service exports are not solution exports',
                   'freshLaterConflictBranchReached': False,
                   'refusalEvidence': 'Fresh native early holds; exact frozen source/conflict predicates and historical direct conflict proof remain separate.'},
    }


def render(report):
    t = report['technical']
    rows = [('Configured fictional cycles', t['configuredCycles']), ('Qualified cycle runs', t['qualifiedCycleRuns']),
            ('Complete cycle action records', t['cycleActionRecords']), ('Safe refusal attempts', t['safeRefusalRuns']),
            ('Refusal action records', t['refusalActionRecords']), ('Unchanged, Started native profiles', t['frozenStartedProfiles']),
            ('Native runs in flight at readback', t['activeRuns']), ('Focused local tests passed', t['localTests'])]
    title = 'Technical usability result — fictional qualification'
    intro = 'Both configured lifecycle routes work through closure and a distinct next review. Replay, recovery and preservation evidence is retained. These are technical results, not measured user benefits.'
    limits = 'Real-user sample: 0. Hands-on time, time saved, reviewer effort and clinical benefit are not measured. Third-party access testing remains user-deferred. No clinical approval or operational rollout is implied.'
    boundaries = 'Fresh refusal attempts held safely with zero writers. Some requests stopped at earlier prerequisites; exact frozen source/conflict checks and historical direct conflict-branch proof are identified separately. Native generation and managed-solution packaging retain their recorded qualification limits.'
    md = '# '+title+'\n\n'+intro+'\n\n| Technical measure | Verified result |\n|---|---:|\n'
    md += ''.join('| '+label+' | '+format(value, ',')+' |\n' for label, value in rows)
    md += '\n'+limits+'\n\n'+boundaries+'\n\nEvidence as of '+report['asOfUTC']+'. Source commit `'+report['sourceCommit']+'`.\n'
    table = '<table><thead><tr><th>Technical measure</th><th>Verified result</th></tr></thead><tbody>'
    table += ''.join('<tr><td>'+html.escape(label)+'</td><td>'+format(value, ',')+'</td></tr>' for label, value in rows)+'</tbody></table>'
    body = '<h2>'+title+'</h2><p>'+intro+'</p>'+table+'<h3>Not measured or conferred</h3><p>'+limits+'</p><p>'+boundaries+'</p>'
    body += '<p>Evidence as of '+html.escape(report['asOfUTC'])+'. Source commit '+report['sourceCommit']+'.</p>'
    return md, body


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['manifest', 'assurance', 'local-checks', 'output']:
        parser.add_argument('--'+name, required=True, type=Path)
    parser.add_argument('--source-commit', required=True)
    args = parser.parse_args()
    report = result(args.manifest.read_bytes(), args.assurance.read_bytes(), args.local_checks.read_bytes(), args.source_commit)
    md, body = render(report)
    args.output.mkdir(parents=True, exist_ok=False)
    outputs = {'report.json': json.dumps(report, indent=2)+'\n', 'report.md': md, 'page-body.html': body,
               'operator-observation.csv': (ROOT/'templates/operator-usability/operator-observation.csv').read_text()}
    for name, text in outputs.items():
        with (args.output/name).open('x') as stream:
            stream.write(text)
    hashes = {name: digest((args.output/name).read_bytes()) for name in outputs}
    (args.output/'output-hashes.json').write_text(json.dumps(hashes, indent=2)+'\n')
    print('Sanitised technical result generated; actual user benefits remain unmeasured; native publication not claimed.')


if __name__ == '__main__':
    main()

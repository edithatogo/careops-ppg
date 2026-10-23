"""Prepare manual checklist records; never execute prompts or change earlier runs."""
import copy
import hashlib
import json
from scripts.ppg_review_intelligence import validate_review_run

MODULES = ('classification', 'duplication', 'document-type', 'external-changes',
           'applicability', 'content-quality', 'implementation')


def prepare(pack_bytes, template_bytes, prompts):
    pack = json.loads(pack_bytes)
    if (pack.get('developmentEligible') is not True or pack.get('humanDecision') is not None
            or any(pack.get(k) is not False for k in
                   ['policyApproved', 'publicationAuthorised', 'notificationsEnabled'])):
        raise ValueError('Explicit unapproved interim development pack required')
    if set(prompts) != set(MODULES):
        raise ValueError('All seven separately versioned modules required')
    sha = lambda raw: hashlib.sha256(raw).hexdigest()
    basis = pack['developmentBasis']
    if sha(template_bytes) != basis['templateSha256']:
        raise ValueError('Template bytes differ from authorised interim basis')
    if basis['inspectionSha256'] != pack['inspectedSourceSha256']:
        raise ValueError('Inspected source pin differs')
    prior = copy.deepcopy(pack['preparedReviewRuns'])
    for row in prior['runs']:
        validate_review_run(row)
    pack_sha = sha(pack_bytes)
    pack_ref = 'historical-pack11@' + pack_sha
    runs = []
    for module in MODULES:
        prompt = prompts[module]
        if prompt['version'] != '1.0.0' or not isinstance(prompt['bytes'], bytes):
            raise ValueError('Qualified draft module bytes/version required')
        prompt_sha = sha(prompt['bytes'])
        if prompt.get('sha256') != prompt_sha:
            raise ValueError('Prompt bytes differ from qualified module pin')
        key = sha(('manual-preparation-v1\n' + pack_sha + '\n' + module + '\n' + prompt_sha).encode())
        row = dict(runId='prepared-interim-' + key,
            documentUID=pack['requestedSubject']['documentUID'],
            documentVersion='historical-inspection:' + basis['inspectionSha256'],
            documentSha256=basis['inspectionSha256'],
            templateVersion='retained-candidate-unverified', templateSha256=basis['templateSha256'],
            criteriaVersion=pack['preparation']['criteriaVersion'], promptId=module,
            promptVersion=prompt['version'], promptSha256=prompt_sha,
            promptDefinitionsStatus='draft-pilot-assets', productionPromptApproved=False,
            promptApplication='Manual checklist preparation only; no prompt invocation',
            evidenceSnapshots=[dict(sourceId='subject-inspection', sourceVersion='historical-inspection:' + basis['inspectionSha256'], sourceSha256=basis['inspectionSha256']),
                               dict(sourceId='prepared-pack', sourceVersion=pack_ref, sourceSha256=pack_sha)],
            coverageManifestRef=pack_ref + '#preparation.comparisonMatrix',
            runtimeIdentity=dict(executionMode='manual_preparation', provider='local_python',
                model=None, modelVersion=None,
                versionAvailability='No AI invocation; original finding runtime remains in the referenced pack'),
            startedAt=None, completedAt=None, status='prepared',
            findings=[dict(findingId='unexecuted-' + module, claimType='unknown',
                statement='Module prepared, not executed. Existing findings and passages remain in the referenced pack; reviewer assessment is outstanding.',
                sourceCitations=[], suggestedAction='seek_further_evidence')],
            limitations=['Historical V6 and template candidate only; current authority unverified/nonblocking.',
                         'Preparation does not complete substantive review, approve prompt definitions or execute native AI.',
                         'No new clinical findings; use existing passage-backed findings with their original provenance.'],
            humanDisposition=None, policyApproved=False, publicationAuthorised=False,
            notificationsEnabled=False, preparedEvidenceRef=pack_ref,
            priorHeldRunIds=[r['runId'] for r in prior['runs']])
        validate_review_run(row)
        runs.append(row)
    return dict(schemaVersion=1, kind='interim_manual_checklist_preparation',
                nativeAIInvocations=0, manualReviewCompleted=False, runs=runs,
                priorRuns=prior, sourcePackSHA256=pack_sha,
                inputOrPriorRunsModified=False)

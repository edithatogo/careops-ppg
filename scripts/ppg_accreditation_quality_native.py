# Copyright 2026 PPG Workbench contributors
# SPDX-License-Identifier: Apache-2.0
"""Pure native-row projection for a bounded fictional quality example."""
from copy import deepcopy
from hashlib import sha256
import json
from urllib.parse import urlsplit
from uuid import UUID
from scripts.ppg_accreditation_quality_example import validate_example, freeze_example


def project_example(package, graph, source_bytes, file_receipt):
    validate_example(package, graph)
    source = json.loads(source_bytes)
    if not isinstance(source, dict) or not isinstance(file_receipt, dict):
        raise ValueError('Source and file receipt must be objects')
    if (source.get('fixtureOnly') is not True or source.get('realServiceActivity') is not False
            or source.get('humanReviewClaimed') is not False):
        raise ValueError('Explicit fictional source required')
    digest = sha256(source_bytes).hexdigest()
    if digest != file_receipt.get('sha256'):
        raise ValueError('Native source bytes mismatch')
    UUID(file_receipt['uniqueId'])
    uri = urlsplit(file_receipt['url'])
    if uri.scheme != 'https' or not uri.hostname or uri.username or uri.password or uri.fragment:
        raise ValueError('Exact HTTPS source URL required')
    if not isinstance(file_receipt.get('version'), str) or not file_receipt['version'].strip():
        raise ValueError('Exact native version required')
    observation = package['indicatorObservation']
    if source.get('observation') != observation:
        raise ValueError('Observation differs from captured source')
    context = next(c for c in graph['contexts'] if c['ReviewContextKey'] == package['ReviewContextKey'])
    assessments = [a for a in graph['assessments'] if a['ReviewContextKey'] == context['ReviewContextKey']
                   and a['RequirementKey'] in (package['QualityStatementKey'], package['NSQHSRequirementKey'])]
    scopes = {a['ScopeKey'] for a in assessments}
    if len(scopes) != 1:
        raise ValueError('One explicit scope required')
    ev = next(e for e in graph['evidenceVersions'] if e['EvidenceVersionKey'] == package['EvidenceVersionKey'])
    context_row = dict(Title='SYNTHETIC cycle-free quality example', ReviewContextKey=context['ReviewContextKey'],
                       ScopeKey=next(iter(scopes)), ScopeDescription='Fictional non-personal technical example only.',
                       Purpose=context['purpose'], PeriodStart=observation['PeriodStart']+'T00:00:00Z',
                       PeriodEnd=observation['PeriodEnd']+'T00:00:00Z', ContextState='Open')
    evidence = dict(Title='SYNTHETIC observation; no service activity', EvidenceKey=ev['EvidenceKey'],
                    EvidenceVersionKey=ev['EvidenceVersionKey'], SourceSystem='SharePoint',
                    SourceItemKey='fileUniqueId:'+file_receipt['uniqueId'],
                    ExactVersion='SharePoint file version '+file_receipt['version']+'; SHA-256 '+digest,
                    SourceURI=file_receipt['url'])
    mappings, assessment_rows = [], []
    for a in assessments:
        mapping = next(m for m in graph['mappings'] if m['MappingKey'] in a['MappingKeys']
                       and m['EvidenceVersionKey'] == ev['EvidenceVersionKey'])
        mappings.append(dict(Title='SYNTHETIC proposed relevance only', MappingKey=mapping['MappingKey'],
                             DocumentUID=ev['EvidenceKey'], DocumentVersion=file_receipt['version'],
                             RequirementKey=a['RequirementKey'], ReviewContextKey=context['ReviewContextKey'],
                             EvidenceVersionKey=ev['EvidenceVersionKey'], MappingState='Proposed', Rationale=mapping['rationale']))
        assessment_rows.append(dict(Title='SYNTHETIC independent unknown assessment', AssessmentKey=a['AssessmentKey'],
                                    ReviewContextKey=context['ReviewContextKey'], RequirementKey=a['RequirementKey'],
                                    Applicability='Unknown', Outcome='Unknown', AssessmentRationale=a['narrative'], AssessedAt=None))
    selected = next(a for a in assessments if a['RequirementKey'] == package['QualityStatementKey'])
    case = dict(Title='SYNTHETIC cycle-free observation; no clinical judgement',
                ImprovementCaseKey=observation['ObservationKey']+':case', ReviewContextKey=context['ReviewContextKey'],
                AssessmentKey=selected['AssessmentKey'], RequirementKey=selected['RequirementKey'], ScopeKey=selected['ScopeKey'],
                ObsEvidenceVersionKey=ev['EvidenceVersionKey'], IndicatorVersionKey=observation['IndicatorDefinitionVersionKey'],
                ObservationKey=observation['ObservationKey'], EffectivenessOutcome='unknown', ActorIdentityRef=None,
                JudgedAt=None, Rationale='Fictional counts only; no effectiveness or clinical assessment performed.',
                CaseDetailsJSON=json.dumps(dict(kind='cycle-free-quality-example', fixtureOnly=True, realServiceActivity=False,
                                              humanReviewClaimed=False, observation=deepcopy(observation),
                                              sourceSHA256=digest), sort_keys=True),
                ContractCaseJSON=json.dumps(freeze_example(package, graph), sort_keys=True))
    return dict(context=[context_row], evidence=[evidence], mappings=mappings, assessments=assessment_rows,
                cases=[case], nativeWrites=0, nativeWorkflowQualified=False)


def main():
    """Prepare create-only private row payloads; never authenticate or send."""
    import argparse
    import os
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True,
                        help='JSON object containing package and graph')
    parser.add_argument('--source', type=Path, required=True,
                        help='Exact fictional source bytes named by the file receipt')
    parser.add_argument('--file-receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True,
                        help='New JSON file; existing outputs are never replaced')
    args = parser.parse_args()
    try:
        fixture = json.loads(args.fixture.read_text())
        result = project_example(fixture['package'], fixture['graph'], args.source.read_bytes(),
                                 json.loads(args.file_receipt.read_text()))
        # O_EXCL also refuses symlinks. Mode is private from the first byte.
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(json.dumps(result, indent=2) + '\n')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, 'Projection failed: ' + str(exc) + '\n')
    print(json.dumps(dict(counts={key: len(result[key]) for key in
                                 ('context', 'evidence', 'mappings', 'assessments', 'cases')},
                          nativeWrites=0, nativeWorkflowQualified=False)))


if __name__ == '__main__':
    main()

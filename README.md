# careops-ppg

Portable tools for policies, procedures and guidelines: draft package assembly,
source reconciliation, identity exceptions, consultation records, readiness,
assurance evidence and process measures.

This repository contains reusable code and explicitly fictional examples. It has
fresh Git history and no organisation-specific deployment records, policy texts,
source-register extracts, tenant bindings or deployment claims. Native workbook
and flow adapters, operational plans and status manifests are excluded. No native
Microsoft deployment is configured or implied by the local checks.

## Run locally

Requires Python 3.11+ and Node.js 22+; the retained tools use their standard libraries.

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
node tests/test_submission_assembler.cjs
node tests/test_metadata_prefill.cjs
python3 scripts/build_submission_assembler.py
```

Open `.local/submission-package/PPG-submission-assembler.html` to prepare a draft
package locally. Generated files stay ignored. Source reconciliation requires an
explicit source field contract, identity ledger and a separately qualified target
adapter. It never interprets missing rows as automatic retirement. See individual
scripts' `--help` where available. Human findings, acceptance, publication and
approval remain explicit operational decisions.

## Document generation

Evaluate [SharePoint structured document generation](https://learn.microsoft.com/en-us/sharepoint/copilot-in-sharepoint-structured-document-generation)
first for maintained document structures. Reuse authoritative records and Word
templates; preserve human edits, source/template versions and output revisions.
Confirm actual entitlement, repeating/optional content, links, editing, access and
retry/recovery through output readback before migration. The included local/manual
assembler is a fallback; it does not establish native-route availability or approve
content. No licence, consent or settings changes are included.

## Security and publishing boundary

[Gitleaks](https://github.com/gitleaks/gitleaks) scans full Git history on pushes,
pull requests and manual runs. The CLI version, download checksum and checkout
Action are pinned. The workflow uses read-only permissions and requires no scanner
licence key. A separate content check rejects organisation-specific identifiers,
non-example SharePoint bindings and operational export formats.

Install Gitleaks 8.30.1, then enable the repository's local commit hook:

```sh
git config core.hooksPath .githooks
gitleaks git --redact --log-opts=--all .
python3 scripts/check_portable_content.py
```

The hook scans staged changes for secrets and checks staged content before commit.
CI is the shared check for clones where the hook has not been enabled. A clean
scanner result is evidence about the committed material, not a guarantee about
future files. Keep source records, credentials, real correspondence, private
bindings and receipts outside Git, including for private repositories.

No public licence is granted by this repository.


## Source CI and updates

Security calls the shared CareOps source checks at the immutable revision
`1373e971013724dfaa268e215a45505bb89300cd`, with read-only permissions and no
inherited secrets. Full-history Gitleaks, immutable action references, actionlint
and zizmor supplement this repository's portable-content check and PPG tests.
Tests exercise both the minimum supported Python/Node versions and a separate
current-runtime candidate. A green source check does not establish native M365
operation or policy approval.

Dependabot proposes weekly GitHub Actions updates. Shared-workflow changes must
update the workflow reference and `policy-revision` together, then pass every
current-head check. These tools have no third-party Python or Node package
runtime dependencies, so there is no application dependency lock to regenerate.
A separate weekly/manual development canary resolves a hash-locked preview CI
tool candidate, runs the PPG tests and keeps exact-version receipts. It also freezes
the official Python runtime manifest and tests a newer compatible preview when one
exists. An unavailable preview is recorded as unavailable with tests skipped; a
green discovery job does not qualify that runtime. Candidate results never modify
the working runtime or promote an update. Propose exact-version changes in a PR
and pass every current-head required check before promotion. No package release,
SBOM or attestation is implied by the canary alone.

## Portable package candidates

The package workflow builds the existing fallback assembler and bundles it with
exact committed scripts, source, templates and fictional test fixtures. It
refuses dirty source and existing output revisions. An independent unpacked
consumer runs the Python and JavaScript suites and rebuilds the identical HTML.
The actual archive receives an SPDX file inventory; main-only OIDC jobs download
the same bytes and verify exact source, workflow and signer attestations. No
public licence is granted, no release is published, and no policy content or
native service is processed. SharePoint remains the preferred structured-document
route; packaging does not replace that preference or establish its availability.

Development CI tools use an isolated exact Python3.14.8 environment with integrity
hashes and wheels only, while PPG behaviour still runs on Python3.15.0 and
Node26.12.0. Tool versions, lock digest and terminal qualification are retained;
no missing or failed qualification is promoted. Existing minimum-runtime tests
remain. Source packages and canaries do not establish operational acceptance.

## Fixed cover and bounded package source

The [fixed-cover toolkit](templates/unattended-package/README.md) adds independent
saved-property/text inspection, a seven-field snapshot fallback and bounded
Office Script ZIP assembly. It preserves template/evidence bytes and explicit
DRAFT provenance. Its fictional tests run in source CI and in the unpacked source
package; no tenant binding, document, native deployment or entitlement is included.
SharePoint remains the preferred route to qualify first. Actual layout,
editing/reopening, access and native retry/recovery require target-specific proof.

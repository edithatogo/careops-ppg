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
`953eba2d4427bc5c35252b589f51c6414d4f717c`, with read-only permissions and no
inherited secrets. Full-history Gitleaks, immutable action references, actionlint
and zizmor supplement this repository's portable-content check and PPG tests.
Tests exercise both the minimum supported Python/Node versions and a separate
current-runtime candidate. A green source check does not establish native M365
operation or policy approval.

Dependabot proposes weekly GitHub Actions updates. Shared-workflow changes must
update the workflow reference and `policy-revision` together, then pass every
current-head check. These tools have no third-party Python or Node package
runtime dependencies, so there is no application dependency lock to regenerate.
No package release, SBOM, attestation or development-canary qualification is
claimed by this source-CI adoption.

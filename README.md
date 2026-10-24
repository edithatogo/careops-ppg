# careops-ppg

Portable tools for policies, procedures and guidelines: draft package assembly,
source reconciliation, identity exceptions, consultation records, readiness,
assurance evidence and process measures.

This repository contains reusable code and explicitly fictional examples. It has
fresh Git history and no organisation-specific deployment records, policy texts,
source-register extracts, tenant bindings or deployment claims. Parameterised workbook and native adapter source is included with fictional inputs;
real deployment bindings, operational plans and status manifests are excluded.
Pure flow-definition builders make no API calls. Native adapters require explicit
configuration and separate permission/output/recovery qualification. No native
Microsoft deployment is configured or implied by the local checks.

## Run locally

The default uses explicitly selected repo-local Python 3.15.1 and Node.js 22 or
26.12.1. Every active Python profile uses 3.15.1, including the isolated Atlas
integration profile. Qualify the newest suitable dependencies on that runtime.
The document qualification suite additionally requires the pinned .NET 10.0.402 SDK.
Create and verify the repo-local environment before running Python tools:

```sh
uv venv --python 3.15.1 .venv
.venv/bin/python -VV
.venv/bin/python -c 'import sys; assert sys.version_info[:3] == (3, 15, 1)'
```

Restore the locked .NET dependencies from `tools/native-document-template` before
running `.venv/bin/python scripts/run_portable_tests.py`. Operating a selected
Python/Node module does not require the optional document-authoring utility.
The optional, read-only XLSB extraction paths are pinned in
[`requirements-xlsb.lock`](requirements-xlsb.lock); install them into the selected
repo-local interpreter only when those paths are needed:

```sh
uv pip install --python .venv/bin/python --require-hashes --only-binary=:all: -r requirements-xlsb.lock
```

The optional read-only Atlas adapter uses an isolated `.venv-atlas` profile on
Python 3.15.1, with hash-locked runtime/test dependencies. The helper checks the
explicit profile flag, actual interpreter, source commit, clean source/fixtures,
declared runtime constraint and contract hash before executing Atlas. It never
implicitly selects an external `ATLAS/.venv`.

Use a clean Atlas checkout at `21f7721a8971ca6c9e704924503eebdd75356dce`:

```sh
uv venv --python 3.15.1 .venv-atlas
.venv-atlas/bin/python -VV
uv pip install --python .venv-atlas/bin/python --require-hashes --only-binary=:all: -r requirements-atlas.lock
.venv-atlas/bin/python scripts/qualify_atlas_adapter.py --atlas-root .local/atlas-python315-pin --atlas-profile
```

Regenerate the optional universal lock from that checkout's `pyproject.toml` and
`requirements-atlas-qualification.in` using explicitly selected Python 3.15.1;
the lock header records the command. The existing evidence API supplies assertion
rows; the comparison API supplies actual unknown/not-covered conclusions with
null statuses. Preserve those responses separately, without inventing missing
cells or changing Atlas's schema. See [the adapter guide](docs/atlas-supporting-evidence.md).
The fictional API/package check does not establish hosted/native deployment,
real-source integrity or clinical acceptance.

```sh
.venv/bin/python scripts/run_portable_tests.py
.venv/bin/python scripts/build_submission_assembler.py
```

For focused Python checks, pass exact module names, for example
`.venv/bin/python scripts/run_portable_tests.py --python-only test_workbench_cli`.
The full runner includes all maintained Node tests; use it after the locked SDK
restore at a coherent integration milestone.

Open `.local/submission-package/PPG-submission-assembler.html` to prepare a draft
package locally. Generated files stay ignored. Source reconciliation requires an
explicit source field contract, identity ledger and a separately qualified target
adapter. It never interprets missing rows as automatic retirement. See individual
scripts' `--help` where available. Human findings, acceptance, publication and
approval remain explicit operational decisions.

For a runnable offline first operation, follow the [guided CLI walkthrough](docs/guided-cli.md#first-run-an-offline-fictional-reference).
See the [CLI audit](docs/cli-operability-audit.md) for source status, fixes and remaining qualification boundaries.

## Document generation

Evaluate [SharePoint structured document generation](https://learn.microsoft.com/en-us/sharepoint/copilot-in-sharepoint-structured-document-generation)
first for maintained document structures. Reuse authoritative records and Word
templates; preserve human edits, source/template versions and output revisions.
Verify the template creator's Copilot entitlement, target-library edit access and
DOCX template before qualification. Each submission creates a new output with its
own reference, so link revision references to a stable case/occurrence identity
and retain prior files and human edits. Confirm repeating/optional content, links,
editing, access and retry/recovery through output readback before migration. The
included local/manual assembler is a fallback; it does not establish native-route
availability or approve content. No licence, consent or settings changes are
included.

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
.venv/bin/python scripts/check_portable_content.py
```

The hook scans staged changes for secrets and checks staged content before commit.
CI is the shared check for clones where the hook has not been enabled. A clean
scanner result is evidence about the committed material, not a guarantee about
future files. Keep source records, credentials, real correspondence, private
bindings and receipts outside Git, including for private repositories.

No public licence is granted by this repository.


## Source CI and updates

Security calls the shared CareOps source checks at the immutable revision pinned
in [the Security workflow](.github/workflows/security.yml), with read-only
permissions and no inherited secrets. Full-history Gitleaks, immutable action references, actionlint
and zizmor supplement this repository's portable-content check and PPG tests.
Tests exercise Python 3.15.1 across the supported Node lanes and a separate
current-tooling candidate. A green source check does not establish native M365
operation or policy approval.

Dependabot proposes weekly GitHub Actions updates. Shared-workflow changes must
update the workflow reference and `policy-revision` together, then pass every
current-head check. The core tools have no third-party Python or Node application runtime
dependencies; optional parsers and document tooling retain their separate locks.
A separate weekly/manual development canary resolves a hash-locked preview CI
tool candidate and runs the PPG tests on the exact qualified Python and Node
runtime pins. It retains exact-version receipts and does not install or execute
unqualified Python previews. Propose runtime changes as exact-version changes in
a PR and pass every current-head required check before promotion. No package
release, SBOM or attestation is implied by the canary alone.

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

Development CI tools use an isolated exact Python3.15.1 environment with integrity
hashes and wheels only, while PPG behaviour also runs on Python3.15.1 and
Node26.12.1. Tool versions, lock digest and terminal qualification are retained;
no missing or failed qualification is promoted. The Node22 compatibility lane
remains. Source packages and canaries do not establish operational acceptance.

## Fixed cover and bounded package source

The [fixed-cover toolkit](templates/unattended-package/README.md) adds independent
saved-property/text inspection, a seven-field snapshot fallback and bounded
Office Script ZIP assembly. It preserves template/evidence bytes and explicit
DRAFT provenance. Its fictional tests run in source CI and in the unpacked source
package; no tenant binding, document, native deployment or entitlement is included.
SharePoint remains the preferred route to qualify first. Actual layout,
editing/reopening, access and native retry/recovery require target-specific proof.

The same toolkit now includes native request-to-job preparation and a pure
manual-flow definition builder for a fixed cover plus an existing frozen pack,
with optional separate PDF processing. Private target bindings and actual native
qualification remain outside this repo. The source and unpacked-package CI run
the native-request regression alongside existing Python/JavaScript checks.


## Solution packaging

The [solution admission and recovery procedure](conductor/suite-delivery.md#solution-admission-and-recovery)
reuses existing native objects, verifies connection-reference conversion and tests
recovery on a reserved Stopped copy. Reuse retained target-specific evidence; this
portable repository does not contain tenant exports or establish deployment.

## Canonical source and consolidation

See [consolidation](docs/consolidation.md), the [guided CLI](docs/guided-cli.md)
and [technical assurance report](docs/cli-assurance-report.md). Native evidence,
source policy texts and historical delivery records remain outside this toolkit.

## Standard selected-source evidence reader

The [offline source discovery parser](docs/source-discovery.md) observes RSS,
sitemap occurrences and known publication download links. It preserves duplicate
discovery provenance and refuses incomplete/error inputs without assigning
publication identity, advancing a baseline or making native writes. Native remote
acquisition and persistence require separate qualification.

The [Power Automate reader guide](docs/power-automate-cited-reader.md) describes a
fixed-source, read-only Standard SharePoint graph generator. Raw native reads,
independent hash/extraction, caller permissions and conversational assistant
qualification remain separate. Existing CLI evidence/citation tools remain usable.

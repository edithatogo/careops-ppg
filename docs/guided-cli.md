# Guided portable CLI

Use repo-local Python 3.15.1 and a supported Node runtime. All commands require
explicit inputs; retain private plans, outputs, journals and bindings under
ignored `.local/`. Run `.venv/bin/python scripts/ppg_workbench.py --help` for the
fixed supported stages and plan format. It composes existing source preparation,
evidence lookup/excerpt/validation, case selection, package assembly/publication
and assurance commands. Plans cannot supply arbitrary executables or shell code.

For a guided operation, supply `--plan PLAN.json --state NEW_PRIVATE_JOURNAL.jsonl`.
Resume with the same plan and `--resume` only at a verified completed-stage
boundary. Changed outputs, incomplete writes, changed scope and failed reads
remain holds. Inspect native receipts separately from local completion.

Every native adapter requires an explicitly selected existing target, qualified
current account/client and source pins. Offline checks do not supply native
permission, premium entitlement, authority to send email or clinical approval.
Review the adapter's `--help` and source contract before any live operation.

## First run: an offline fictional reference

Start in the repository root. Create `.venv` and verify Python 3.15.1 using the
[setup instructions](../README.md#run-locally). This example uses only the standard
library: no Microsoft login, Node, .NET, optional parser or premium connector is
needed. It prepares a fictional text reference and reports its preparation status;
it does not generate a Word package or qualify retrieval.

```sh
mkdir -p .local/cli-walkthrough
.venv/bin/python scripts/ppg_workbench.py --plan templates/operator-usability/cli-walkthrough/plan.json --state .local/cli-walkthrough/run.jsonl
.venv/bin/python scripts/ppg_workbench.py assurance-report --input .local/cli-walkthrough/run.jsonl --output .local/cli-walkthrough/run-status.md
```

Expected results:

| File | Meaning |
|---|---|
| `.local/cli-walkthrough/prepared/manifest.json` | Source edition, original hash and preparation provenance |
| `.local/cli-walkthrough/prepared/sources/fictional-cli-r1-reference-one.txt` | Byte-exact copy; the original training text stays unchanged |
| `.local/cli-walkthrough/source-status.md` | Preparation succeeded; conversational retrieval remains unqualified |
| `.local/cli-walkthrough/run.jsonl` | Two completed stages and their output fingerprints |
| `.local/cli-walkthrough/run-status.md` | The plan's recorded completion; human acceptance remains unassessed |

Progress is written to stderr; the child report is printed to stdout as well as
saved. Exit 0 means the selected command completed. Read the report's qualification
flags before deciding what that result establishes.

To check an already completed run without regenerating its outputs:

```sh
.venv/bin/python scripts/ppg_workbench.py --plan templates/operator-usability/cli-walkthrough/plan.json --state .local/cli-walkthrough/run.jsonl --resume
```

This verifies fingerprints and reports that all stages are already complete. It
adds no journal events. Keep the original plan bytes and working directory.
For another fresh example, copy the plan privately and change every output path,
child output argument and journal path to a new revision. Do not delete prior
outputs simply to make an exclusive-create check pass.

## Plans and recovery

The [example plan](../templates/operator-usability/cli-walkthrough/plan.json) shows
`schemaVersion`, ordered `steps`, an allowlisted `step`, literal `arguments` and
nonempty `outputs`. An optional `stdoutArtifact` must also appear in `outputs`.
Plan/output paths are relative to the working directory, not the plan's folder.
Create parent directories first. Keep live plans and journals private; only this
fictional example belongs in source control. Do not store a new journal inside a
fingerprinted output tree: appending to it would change that tree's fingerprint.

| Observed condition | Required next action |
|---|---|
| Stopped after a recorded completed stage | Resume the identical plan from the same working directory; completed output fingerprints must still match |
| Last stage is started, failed or refused | Inspect its child receipts and any native result; preserve partial output; use a fresh bounded plan/journal after reconciliation |
| Output changed or disappeared | Preserve edits/history and investigate; do not replace fingerprints to force resume |
| Output/report/journal already exists | Use resume only for a clean completed boundary; otherwise select a new revision after checking existing evidence |
| Missing runtime, input or parent directory | Correct the specific prerequisite; if an attempt was started, retain it and start a new reconciled attempt |
| Native read/write is denied or times out | Reconcile through the existing qualified route and exact operation identity; no automatic retries, new consent or permission changes |

Use `--receipt NEW.jsonl` before a single stage to retain its attempt and exit
code. This receipt is not a replacement for the child's output/native receipt.
Use `STEP --help` to inspect required inputs before selecting a live stage.

## Selecting the next route

| Route | Execution boundary |
|---|---|
| `prepare-sources` | Local input copies and extraction; optional parsers only for the selected formats |
| `publish-sources`, `lookup` | Native SharePoint operations; explicit existing bindings and separately qualified access |
| `excerpt` | Reads a retained local bundle using its supplied scope contract |
| `validate`, `evaluate-sources` | Use `--offline` for retained evidence only; default modes perform native reads |
| `select-case`, `prepare-package`, `assemble-package` | Existing case selection and draft package tools; inspect each child's contract and Node requirements |
| `publish-package` | Native publication; explicit target, preimages and native readback required |
| `assurance-report` | Reads only named local receipts and creates a new report |

SharePoint maintained templates remain the preferred structured-document route.
The parallel native qualification owns proof for that route. A successful offline
walkthrough does not replace output, edit, access or recovery qualification.

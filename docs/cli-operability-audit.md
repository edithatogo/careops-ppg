# CLI operability audit — 24 October 2026

This audit covers portable source at the post-consolidation baseline, including
PRs 29–33. It uses a separate checkout and fictional local inputs. The native
Word/edit/recovery qualification and PR34 retain their existing owner. No native
objects, browser/authentication sessions, private handoffs or scheduled runtimes
were changed by this work.

| Area | Observed status | Action and remaining boundary |
|---|---|---|
| Reusable source consolidation | Complete in merged source and disposition manifest | Reuse the existing consolidation evidence; no second port or history import |
| Source runtime | Module profile marks complete; runtime track retains broader conditional closure | Reuse the selected Python 3.15.1 environment; leave the owning runtime/template plan untouched |
| Guided CLI operation | Delivered; lacked a runnable first-use example | Added a two-stage fictional source-preparation/report plan and operating instructions |
| Single-step assurance | Defect: actual `state=command-exited` receipts were not recognised | Now checks both receipt forms and requires exit 0 |
| Multi-stage assurance | Defect: an intermediate completed stage could imply whole-plan success | New journals retain total stage count; report requires all sequential stages; legacy count-free journals remain incomplete |
| Completed-plan resume | Correctly avoided child replay; displayed stage beyond plan length | Now states that all stages are complete after verifying output fingerprints |
| Local recovery/refusal | Source checks and actual subprocess walkthrough pass | Tested interrupted completed boundary, unknown outcome, changed output, existing output and missing input; no native restore claim |
| Native template/package generation | Qualification in progress in another chat | Do not infer native completion from local tests or amend its evidence |
| Human adoption and benefits | Deferred | Keep third-party testing and measured benefits outside technical completion |

## Verification

Focused checks exercise actual source preparation and report subprocesses with a
repo-local Python 3.15.1. They verify original and copied source bytes, manifest
qualification flags, journal stage accounting, completed-plan replay without
writes, partial-plan reporting, missing input and edited-output refusal. Existing
unit coverage supplies completed-boundary interruption, unknown-outcome and
existing-output cases. The unmodified documented example was also run directly,
then resumed and summarised successfully. Private generated files remain ignored.

The report summarises recorded evidence; it is not an authenticity verifier or a
fresh native/output-byte audit. Human acceptance and substantive decisions remain
separate. Follow the [operating guide](guided-cli.md) and [report scope](cli-assurance-report.md).

## Dependency and security triage

The toolkit's core Python/Node routes have no third-party application runtime
dependencies. Optional XLSB parsing and document tooling retain their existing
hash/lock qualification; this audit changes neither dependencies nor pins.
Existing security, package and runtime CI remain the release gates.

The authenticated GitHub Dependabot-alert endpoint returned HTTP403 (alerts
disabled and insufficient scope), and code-scanning alerts returned HTTP404
(no analysis found, with an additional scope diagnostic). These responses do not
establish zero vulnerabilities. No scope refresh, alert-setting change or admin
operation was attempted. Retain the existing Gitleaks, portable-content and
shared source-security checks; inspect any available CI findings on this PR.
No verified dependency advisory was available to fix from those endpoints.

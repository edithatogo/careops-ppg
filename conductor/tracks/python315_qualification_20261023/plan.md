# Plan

## Phase 1 — Inventory

- [x] P1.1 Inventory every active Python surface and distinguish historical/version-test fixtures.
- [x] P1.2 Verify repo-local interpreter version and safe environment handover.
- [x] P1.3 Review phase evidence and checkpoint under the repo workflow.

## Phase 2 — Qualification

- [x] P2.1 Reuse [merged migration](https://github.com/edithatogo/careops-ppg/pull/25) without repeating unchanged tests.
- [x] P2.2 Close remaining runtime, lock, dependency and current setup-document gaps with focused checks.
- [x] P2.3 Verify phase evidence and checkpoint.

## Phase 3 — Integration

- [x] P3.1a Run affected structure/privacy checks and exact-head required checks.
- [ ] P3.1b Integrate the eligible PR and verify the merged main state.
- [x] P3.2 Audit every acceptance requirement and explicit external blocker.
- [ ] P3.3 Record actual goal-tool result; close only when full evidence supports completion.

## Current boundary

A track or prompt is not an armed goal or completed runtime migration. Shared chat goal creation was rejected due to its unfinished goal.

## Evidence checkpoint — 2026-10-24

- Runtime inventory: `.python-version` is `3.15.1`; README, CI, canary and Git hook select and verify that runtime. The Atlas qualification helper now refuses any interpreter other than the repo's `.venv` Python 3.15.1. Historical 3.11/3.14 references and version-test literals remain historical or deliberate fixtures; no active local runner selects those versions.
- Dependency qualification: the optional XLSB path is hash-locked to `pyxlsb==1.0.10`. An isolated Python 3.15.1 run parsed the attributed pandas v2.2.3 workbook fixture, checking sheets, dimensions, cached values and unchanged input bytes. The exact-head hosted development canary passed the same parser test and the optional lock audit. The fixture is Base64 text so the portable-content gate continues rejecting tracked spreadsheet binaries.
- Focused local checks passed for the XLSB parser, runtime guard, canary qualification, release-candidate packaging and DOCX revision preservation. `actionlint` and the staged portable-content check passed. Exact-head hosted canary, package, security, content and Python 3.15.1/Node 22 and 26.12.1 checks passed on `fdab652`.
- External runtime blocker: the pinned Global Medicines Atlas source declares `requires-python = ">=3.14,<3.15"`; its integration helper is now restricted to PPG's required Python 3.15.1 and will fail closed rather than use `ATLAS/.venv`. No compatible Atlas source/runtime is available in this checkout. This repository's Atlas integration remains unqualified.
- Native template blocker: read-only Microsoft 365 license enumeration for the connected user showed PBI Premium per User, Power BI Standard, Teams Audio Conferencing and SPE E3, with no Copilot SKU. SharePoint structured-document generation remains unqualified; no license or tenant setting was changed.
- Last verified head before this evidence update: PR #32 was open and draft at `a3a326df4bbf9d654118ceb1076db970b9690ef9`. Exact-head portable content, Python 3.15.1 with Node 22 and 26.12.1, compatibility canary, package candidate and shared-source security checks passed; package attestation was skipped by its configured condition. The tracked-content check and Gitleaks passed before push. P3.1a is complete; P3.1b remains open because the draft PR has not been integrated. No merged-main evidence is claimed.
- Template fallback evidence: the fictional three-row DOCX rendered in LibreOffice 26.8 to a three-page A4 PDF. Each comparison row remained together across page breaks, the source snapshot rendered as a clickable HTTPS link, and the empty optional section was omitted. Revision-preservation tests passed. Microsoft Word opened a separate copy and saved a fictional title edit. The edited copy's hash changed and its saved XML contains the new title, while the original generated DOCX hash remained unchanged.
- Current native blocker: a fresh read-only license enumeration returned PBI Premium per User, Power BI Standard, Teams Audio Conferencing and SPE_E3; it returned no Copilot SKU. No license, tenant setting or site permission was changed. SharePoint structured-document generation remains unqualified.
- External runtime blocker: both the pinned Global Medicines Atlas source and the current upstream `main` still declare `requires-python = ">=3.14,<3.15"` ([upstream project metadata](https://github.com/edithatogo/global-medicines-atlas/blob/main/pyproject.toml)); this repo's integration remains unqualified under the mandatory Python 3.15.1 runtime. P3.3 remains open until full-scope evidence and the actual goal-tool result support closure.

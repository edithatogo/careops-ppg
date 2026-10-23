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

- [ ] P3.1 Run affected structure/privacy checks and exact-head required checks; merge eligible work and verify main.
- [ ] P3.2 Audit every acceptance requirement and explicit external blocker.
- [ ] P3.3 Record actual goal-tool result; close only when full evidence supports completion.

## Current boundary

A track or prompt is not an armed goal or completed runtime migration. Shared chat goal creation was rejected due to its unfinished goal.

## Evidence checkpoint — 2026-10-24

- Inventory: `.python-version` and documented/CI runtime selectors resolve to Python 3.15.1. Active repository Python entry points use the explicit `.venv/bin/python`; CI and hook setup verify the selected interpreter's actual version. Historical 3.11/3.14 references are dated history, while version literals in tests are deliberate compatibility fixtures.
- Local runtime: `.venv/bin/python -VV` reports Python 3.15.1. The existing environment was already at a terminal point before qualification; no running environment was replaced.
- Dependency gap: optional read-only XLSB adapters now have `requirements-xlsb.lock`, pinned to `pyxlsb==1.0.10` with PyPI artifact hashes. The documented install uses hash and wheel-only enforcement. An isolated Python 3.15.1 environment installed the lock and verified the package version and `open_workbook` import. Actual XLSB workbook parsing remains to be exercised.
- Focused local tests passed: `test_release_candidate.py`, `test_canary_qualification.py`, and `test_manual_docx_population.py`; `actionlint` passed for the canary, package, and security workflows. The hosted development canary (including the lock vulnerability audit), portable package check, both Python 3.15.1/Node matrix legs, portable content checks, and shared-source security checks passed on code commit `5f37336`.
- PR #32 remains draft and open. No merge or post-merge evidence is claimed. Actual XLSB workbook parsing remains untested locally; that optional adapter is now hash-locked and install/import-qualified.

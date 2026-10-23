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
- [x] P3.1b Integrate the eligible PR and verify the merged main state.
- [x] P3.2 Audit every acceptance requirement and explicit external blocker.
- [ ] P3.3 Record actual goal-tool result; close only when full evidence supports completion.

## Current boundary

A track or prompt is not an armed goal or completed runtime migration. Shared chat goal creation was rejected due to its unfinished goal.

The library-column route below is the selected next implementation approach. The
earlier Atlas upstream blocker is superseded: Atlas PR #1295 merged its Python
3.15.1 migration. Qualification of PPG's pinned Atlas integration remains a
separate task; neither that pin nor its runtime evidence changes in this plan PR.

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

## Integration checkpoint — 2026-10-24

- PR #32 (`c959a39f1e4c43932007b9c62dad713f6c1b7da3`) passed its exact-head required checks and was clean/mergeable. Repository branch protection required zero approving reviews. The PR was marked ready and merged with a merge commit; GitHub reports merged state at `957943e3b3aaaea9575082a89a256ddc2da6ecb9`.
- Readback confirmed `main` at `957943e3b3aaaea9575082a89a256ddc2da6ecb9`, matching the PR merge commit. The local tracking ref `origin/main` was fetched to the same SHA; the worktree was clean at verification.
- P3.1b is complete. P3.3 remains open: Atlas integration is blocked by its Python `<3.15` metadata, and native SharePoint structured-document generation remains unqualified without the required Copilot entitlement. Do not report the broader qualification as complete.

## Phase 4 — Library columns and document templates without additional premium subscriptions

- [x] P4.1 Record the selected alternatives and exclude routes requiring additional premium subscriptions or usage billing.
- [x] P4.2 Inventory the selected library's existing columns, content types, templates and existing flow connector references. Map exact internal names/types to authoritative inputs; reuse existing fields before proposing additions. Record ownership and recoverable preimages in existing evidence. This read-only inventory does not replace the execution/entitlement checks in P4.4.
- [ ] P4.3 Qualify one fictional policy/review package with a maintained Word library/content-type template. Where supported, link simple document properties to visible fields using document-property controls/Quick Parts. Verify actual property values and body rendering separately in the selected desktop and browser clients, including Mac where used; retain manual entry on a documented refresh or editing gap.
- [ ] P4.4 Qualify only the necessary standard SharePoint Power Automate actions for copying the template, creating files and updating metadata. Confirm existing entitlement, connections and policy access first; use serial conditional writes/readback and guard modification-trigger loops. The connector's Standard classification does not make its separately licensed generation actions eligible.
- [ ] P4.5 Verify saved file identity, links, metadata, editing and recovery for the selected package. Preserve earlier outputs, human edits, issued history and source/template revisions. Record a failed or interrupted operation before retrying; verify retries do not create duplicate revisions. Do not close native acceptance from source CI alone.

### Selected alternatives

1. **Library columns and content types — first choice:** store structured metadata, required fields and document-kind templates; support filtering, grouping and routing without relying on Word-body generation.
2. **Maintained Word library/content-type templates:** create documents from an approved layout; link supported scalar document properties where verified, and keep manual content entry for narrative, conditional sections and variable-length tables until their behavior is qualified.
3. **Power Automate with standard SharePoint actions:** copy/create files and update library properties using existing qualified connections and entitlement. No automatic Word-body merge is implied by a successful metadata update.
4. **Existing Standard Office Script fixed-cover route:** reuse the maintained snapshot compiler and packaging runtime for its qualified scalar-cover shape. Standard Excel Online (Business) executes the existing script; Standard SharePoint stores the files/metadata, with Standard OneDrive conversion only where separately qualified. This is a bounded fallback after property-refresh failure, not a new generator or proof of arbitrary narrative, repeating-table or conditional-section support.

Exclude Copilot document-generation forms, Word Online (Business) template-population/PDF actions classified as Premium in Power Automate, paid content assembly/Syntex, and third-party paid generators from this implementation route. No additional subscription, usage billing, consent, connection or tenant setting is authorised by this plan.

For the fictional policy package, map DocumentUID, policy identifier, document kind,
source edition, source URL, capture date, review status and related register/case
reference. Retain template revision, output revision and the unresolved-items
indicator where applicable. Keep source edition and capture date distinct from
SharePoint file-history version. Retain distinguishable copies of different
source editions; file history records edits to each copy. Preserve the existing
register as the source of identity and status rather than creating another register.

### Inventory outcome and implementation constraints

The read-only schema/template and current flow-definition inventory is complete;
exact bindings, field mappings and raw responses remain in private evidence.
Reuse existing identity, edition, capture-provenance and scalar-cover fields.
Do not substitute a capture classification for document kind or policy currency
for review status. Keep unmatched semantics in the existing authoritative
catalogue, review queue or paired generation receipt rather than inventing a
matching library column or duplicating status authority.

Shared-library schema changes can propagate Office custom XML into existing
documents and change their bytes independently of visible version labels.
**Do not add columns to the shared evidence/issued-document library.** A folder
does not isolate schema. If the selected template needs new fields, qualify a
dedicated generation library with its schema established before pinning files;
reuse the current fixed-cover/manual fallback while that remains unqualified.

Metadata persistence is not proof of Word-body refresh. Reuse the recorded
property-refresh failure and the existing snapshot fallback rather than
repeating the unchanged failing route. Current readback of the retained
fictional cover/package confirms their recorded byte hashes and identities,
stable reads, ZIP integrity and member hashes; it is preservation evidence,
not a new generation, rendering or edit/recovery trial. P4.3–P4.5 remain open for
their complete selected-shape requirements. The current flow graph and connection
reference snapshot differ from the older output's qualification snapshot; inspect
the current owned operation and its runtime evidence before reusing that proof
for P4.4. Do not overwrite or rerun an in-flight implementation to reproduce old
evidence. No cloud schema, files, flow settings
or connection state changed during the inventory.

### Native saved-body qualification continuation — 24 October 2026

An isolated, manually triggered copy of the maintained Standard SharePoint/Excel
route executed the existing saved-body candidate. Native publication readback
matched the complete intended graph and connection references. The original
working flow was preserved. Detailed bindings and receipts remain private.

- Two fresh fictional revisions completed generation. Independent downloads
  verified all five ZIP members and CRCs, receipt/job hashes, both claims and the
  exact saved Word bytes. Generated and saved Word hashes differed, demonstrating
  that finalisation handled the native Office metadata rewrite.
- An unchanged replay succeeded with all five files and native pins identical.
  Complete action pagination confirmed the document/package writers were skipped
  and claim/receipt actions used GETs.
- A deliberate edit in Word for the web changed exactly one paragraph. The same
  revision then refused with `saved_output_edited_requires_reconciliation`.
  Complete action history confirmed the downstream output writers were skipped;
  the edited document, ZIP, both claims and receipt remained unchanged by refusal.
  The original Word revision was downloaded from native history and matched its
  original hash. The edited current revision remains retained.
- A separate Word-open/resave during an earlier replay triggered the late
  saved-byte guard. Paragraph text was unchanged, but native bytes/pins changed;
  that run is drift-refusal evidence, not an unchanged-replay pass.

Interrupted recovery remains unqualified. A controlled post-claim interruption
profile was prepared and its CLI draft response matched the intended change, but
the native designer exposed only the earlier published version with Publish
disabled. No interruption-profile run was submitted. The normal draft was
restored; fresh active readback matched its complete graph and references and
confirmed Stopped state. Recheck state before resuming. Reconcile the
draft/publication mismatch before attempting the controlled interruption, then
restore the normal profile and prove same-revision recovery and unchanged replay.
Do not replace the working flow or mark P4.3–P4.5 complete from these partial
results. No arbitrary new document shape, PDF route or operational approval is
established by this continuation.

References: [SharePoint column types](https://support.microsoft.com/en-us/sharepoint/lists/data-and-lists/list-and-library-column-types-and-options),
[library templates](https://support.microsoft.com/en-us/sharepoint/documents-and-library/set-a-custom-template-for-a-sharepoint-library),
[Office document properties](https://support.microsoft.com/en-us/office/collab-files/view-or-change-the-properties-for-an-office-file),
[Quick Parts](https://support.microsoft.com/en-us/word/quick-parts),
[SharePoint connector classification and actions](https://learn.microsoft.com/en-us/connectors/sharepointonline/),
[Word connector classification](https://learn.microsoft.com/en-us/connectors/wordonlinebusiness/),
[Excel Online connector classification](https://learn.microsoft.com/en-us/connectors/excelonlinebusiness/),
[OneDrive connector classification](https://learn.microsoft.com/en-us/connectors/onedriveforbusinessconnector/),
[content assembly billing](https://learn.microsoft.com/en-us/microsoft-365/documentprocessing/content-assembly),
[Atlas Python migration](https://github.com/edithatogo/global-medicines-atlas/pull/1295).

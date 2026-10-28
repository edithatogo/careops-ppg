# Owner-controlled guide preparation

This portable route prepares a separate proposed edition of a project-owned
Workbench guide, records a five-area evidence review and records an externally
supplied user's exact-revision decision. It never supplies institutional policy
approval, clinical assurance or permission to issue, circulate or notify.

The source uses Python 3.15.1 standard library and Node's built-in modules.
Native definition builders make no service calls. Filing requires the caller's
already-qualified SharePoint request adapter, target permissions and notification
checks. No premium connector, Copilot, new identity, licence or service is needed
by the portable tools; a reader's native destination remains unqualified.

## Preparation, review and decision

`scripts/ppg_owner_master.py` supports four operations:

| Operation | Required private inputs | Result |
|---|---|---|
| `prepare` | Job, pinned source bytes, proposed candidate | Create-only preparation receipt |
| `consume-request` | Same inputs and retained native request | Preparation bound to the exact native request |
| `review` | Preparation, unchanged candidate, findings for every rubric area | Evidence-linked review; missing/open/high findings hold acceptance |
| `record-decision` | Review, unchanged candidate, actual user instruction | Exact-revision accept/revise/return record; no issuance |

Use `--input`, `--candidate` and `--output` for each operation. Preparation also
requires `--source`; request consumption requires `--record` containing the native
request; review/decision require `--record` containing findings or the supplied
user decision. Inspect `--help` and the fictional tests for the complete contracts.
All records and real input documents stay outside Git.

A job binds persistent document, occurrence and request identities, a distinct
proposed edition, a change summary and project-owned Workbench scope. Its source
pin includes the reference, edition, native identity, native file version, opaque
ETag and SHA-256. Source release, business edition and native version are distinct.
No planning date is inferred. Review uses the maintained rubric in
`config/lifecycle-owner-review-rubric-v1.json`: provenance, content, lifecycle,
safety and saved output. Each area needs evidence references, locators, hashes,
rationale, uncertainty, severity and disposition.

A decision requires the exact reviewed candidate and review hashes, a real user
instruction reference, UTC recorded time and an explicit effective date for
acceptance. Recording a decision cannot verify the instruction's authenticity;
the caller must retain and verify the actual human instruction. Hashes bind bytes,
not people or access rights. Preparation and review never manufacture acceptance.

## Native entry and filing

`tools/lifecycle/build_owner_guide_entry.py` builds a manual button definition
from supplied qualified source/site/connection bindings. It performs two pinned
source metadata reads, then composes a queue request for an authorised agent
session. It does not launch an unattended reviewer. It saves its proposed
configuration Stopped with owner alerts Off; deployment and activation are
separate operations, not performed by this builder.

`tools/lifecycle/file_owner_guide.mjs` exports `fileDraft` and `fileAcceptance`.
The caller supplies its qualified `req(method, url, options)` adapter and an
exclusive durable `checkpoint(event)` function. Journal intents before transport;
retain readback receipts privately. Do not automatically retry uncertain writes.
The destination must be a separate folder under the selected site's existing
`PPG Review Evidence` library, with source reference on the same origin. Validate
permissions, library rules, alerts and indirect effects before any real write.
The module validates target arguments before authenticated reads or writes.

Draft filing stores a request, candidate and preparation receipt using
`overwrite=false`, actual download parity and source pins. Acceptance filing
requires matching review/decision/candidate bindings and checks the accepted
artifact's native identity, version, length, ETag and bytes before and after
filing a separate review, decision and controlled-master record. Acceptance keeps
institutional issued/current flags false. Edits require a new review and decision;
they are never silently overwritten. The stable `-draft-r1.md` storage suffix
belongs to a request; business edition and exact content hash remain authoritative.
Use a new request for a different candidate.

On replay, reconcile existing files before creating anything. Identical records
are preserved; changed content refuses replacement. After a known interruption,
only missing files may be created. A final verification failure means hold and
reconcile; it is not a completed operation. Keep original guides, previous drafts,
accepted content and issued history. A metadata-token change is distinct from a
content or edition change: retain the difference and inspect actual bytes/version,
while preserving exact guards on the selected source and accepted artifact.

## Output and qualification boundaries

Evaluate the preferred SharePoint structured-document route for the selected
shape and existing entitlements first. If the maintained guide is Markdown or
that route lacks required behavior under existing rights, retain an explicit
editable Markdown/manual fallback. Qualify actual output, links, editing,
recovery and exact native targets separately. This source package contains no
real guide, approval, native receipt, deployment binding or runtime acceptance.
Its fictional tests do not establish real policy authority or operational benefit.

```sh
.venv/bin/python -VV
.venv/bin/python scripts/ppg_owner_master.py --help
.venv/bin/python scripts/run_portable_tests.py --python-only test_owner_master
node --test tests/test_owner_guide_files.mjs
```

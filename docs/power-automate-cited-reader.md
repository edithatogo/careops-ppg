# Selected-source reader in Power Automate

The portable source now prepares an ordinary manually triggered Power Automate
cloud flow using only the existing Standard SharePoint connection reference.
This is a bounded read backend, not a published conversational evidence assistant.
Source tests do not establish deployment, actual native readback, caller permission
trimming or assistant acceptance. Retain the original Studio draft and evidence;
this increment does not convert, rebill, activate or delete it.

## Fixed contract

The initial profile reads **one fixed operator-selected source**. It accepts no
caller URL, file identity, query, folder, path or source-selection argument. The
broader evidence contract still caps a selected set at five sources; that ceiling
does not imply five-source execution is implemented by this one-source profile.
Reuse the [existing evidence contract](../config/cited-evidence.json) and the
[three-source preparation fixture](../templates/cited-evidence/source-preparation-job.json)
for wider CLI evaluation, without expanding this native scope silently.

A private binding supplies `siteUrl`, `folder`, `sourceId`, `authorityLabel` and
all eight native `pin` fields: `UniqueId`, `Name`, `Length`, `ETag`, `MajorVersion`,
`MinorVersion`, `TimeLastModified`, `ServerRelativeUrl`. The generator requires
an HTTPS SharePoint site, exact selected-folder/file containment, a nonzero
UUID, a timezone-aware timestamp, valid versions, a file-length pin of at most 2,000,000 bytes
and a TXT/MD file. Native file identity, semantic source identity, printed edition,
file-version label, ETag and hashes remain distinct.

The [fictional binding](../templates/cited-evidence/power-automate-binding.json)
is an authoring example only. Its identities, path and ETag are not deployable
bindings or proof that a source exists. Obtain exact current pins through the
native owner's qualified read route; keep them and generated definitions private.
The maintained `archive-v1.txt` fixture is 220 UTF-8 bytes; its known hash belongs
to the existing preparation job, never a fabricated native calculation.

The six top-level actions are serial:

1. `Metadata_before`: GET the allowlisted file identity and all expected pin fields.
2. `Require_expected_source`: terminate on any missing or mismatching field.
3. `Read_content`: Standard SharePoint file-content read at the bound path.
4. `Metadata_after`: GET the same file identity again.
5. `Require_unchanged_source`: terminate unless all expected fields still match.
6. `Selected_source_result`: compose raw connector content plus provenance only
   after the guards pass.

All connector retry policies are `none`. Missing/denied connector reads fail the
chain and cannot produce an accepted result; stale/changed pins terminate before
an accepted result. Source content is data and is never evaluated as instructions.
Expression-looking metadata is escaped as a literal. Old actions, schedules,
agents, mail connections and billing-plan fields are not copied from the supplied
existing profile. The generated profile is Stopped and retains only SharePoint.

## Result and evidence limits

`Selected_source_result` includes `sourceId`, `canonicalUrl`, `nativeUniqueId`,
`nativeVersionRef` (the native major.minor label), full `nativePin`, `authorityLabel`,
`retrievedAtUtc`, `content` and `status=selected-source-read`. `content` is the opaque
native connector result, not an assumed string, decoded PDF or DOCX paragraphs.
The canonical URL is constructed from the bound site and pinned path.

`sha256` and `binarySHA256` are **null**. `textExtractionQualified` and
`nativeAssistantRuntimeQualified` are **false**. There are no line/page locators,
claims or citations. Expected metadata length is checked; actual returned byte
length and SHA-256 must be independently verified from the captured native output.
No unsupported Power Automate hash expression or echoed expected digest is used.
A repeated read may create another run log but has no file/record write operation.

This partial result is not directly a complete CLI citation receipt. Keep using
`scripts/ppg_evidence_cli.py` for its separately qualified extraction, original-file
`binarySHA256`, extracted-text `sha256` and exact locators. TXT/MD byte equality
must still be verified before claiming the text and binary digests coincide.
Do not claim runtime parity for DOCX, PDF, scanned or captured formats.

An owner connection can read with the owner's rights. A fixed source allowlist is
not caller permission trimming. Keep this initial route owner-only; no sharing or
assistant attachment follows from successful reads. Denied/stale outcomes must
not return cached content. Native action-history access remains a separate access
boundary, and no source data or signed action links belong in Git.

## Prepare and qualify

Use the repo-local Python runtime and an existing private snapshot of the **new
reader** profile, not the Studio draft. The generator itself makes no network or
file write calls:

```python
import json, sys
from pathlib import Path
sys.path.insert(0, 'scripts')
from ppg_cited_reader_flow import build_flow
existing = json.loads(Path('.local/reader/existing.json').read_text())
binding = json.loads(Path('.local/reader/binding.json').read_text())
prepared = build_flow(existing, binding)
output = Path('.local/reader/candidate.json')
with output.open('x', encoding='utf-8') as stream:
    json.dump(prepared, stream, ensure_ascii=False, indent=2)
output.chmod(0o600)
```

Run `.venv/bin/python scripts/run_portable_tests.py --python-only test_cited_reader_flow`
for fixed-scope, pin, path, version, format, expression and no-effect controls.
The source package automatically includes tracked scripts/tests/templates/docs;
there is no separate source-file allowlist to duplicate.

The native owner must save/publish through the already qualified route, reread the
actual graph/reference/state, inspect email safety and use the exact stopped
solution-aware target. Retain an operation handle before monitoring. Independently
compare actual returned bytes, length and SHA-256 to the selected fictional source;
retain all native pages and output identities privately. Qualify missing/denied,
stale and changed-during-read outcomes before broadening runtime acceptance.
Reconcile unknown results instead of submitting duplicate operations. Leave the
reader Stopped after the bounded qualification and preserve the original source,
existing working routes and Studio draft.

Actual successful readback is separate from recovery/negative-path qualification,
permission trimming, semantic evaluation and human adoption. Track these in the
existing cited-evidence workstream rather than creating another framework or
readiness ledger.

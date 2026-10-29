# Cycle-free quality example

A quality-improvement context can use requirements from two frameworks without
creating an accreditation cycle, assessor or award. Shared evidence has separate
proposed mappings and independent unknown assessments; acceptance does not
transfer between requirements.

`project_example(package, graph, source_bytes, file_receipt)` in
`scripts/ppg_accreditation_quality_native.py` returns context, evidence, mapping,
assessment and case payloads for a native adapter. It does not write records.
The source must be explicitly fictional, its hash must match the supplied native
file receipt, and its observation must match the selected package exactly.
The receipt provides `sha256`, `uniqueId`, `version` and an HTTPS `url`.

The bundled `tests/fixtures/accreditation/second-example.json` is fictional.
Its source identifiers and repeated placeholder digests are not publisher or
native evidence. A real deployment must bind verified source identities before
using the projected records. Measurements preserve exact definition versions,
periods, units, counts and limitations. Missing counts remain null with a reason;
no target, compliance rating or accreditation decision is generated.

The local validator and frozen snapshot remain explicitly local. A native
adapter must separately establish exact destination permissions/effects, unique
keys, parent lookup IDs, conditional writes, readback, replay and isolated recovery.
Keep records, captures, native bindings and execution receipts outside this repo.

For an eventual move to another Microsoft 365 organisation, use the
[cross-tenant binding preparation](cross-tenant-recovery-preparation.md). An offline
plan is not native restore proof.

## Prepare row payloads with the CLI

Run from the repository root with its qualified Python environment:

```sh
.venv/bin/python -m scripts.ppg_accreditation_quality_native \
  --fixture /private/example.json \
  --source /private/fictional-source.json \
  --file-receipt /private/file-receipt.json \
  --output /private/new-row-payloads.json
```

The fixture contains `package` and `graph`, as in the bundled fictional example.
The source JSON contains `fixtureOnly: true`, `realServiceActivity: false`,
`humanReviewClaimed: false` and an `observation` equal to the package observation.
The file receipt must describe those exact bytes and their existing native file.
Synthetic receipts are suitable only for local exercises.

The output contains seven row payloads and remains private (mode 0600 on POSIX).
An existing output is refused; use a new filename for each revision. Validation
failures return exit code 2 without creating the output. Standard output contains
only collection counts and local qualification flags. No authentication or native
write occurs; use the existing qualified adapter for persistence and readback.

The selected evidence must be fictional. Existing reviewed, rejected, superseded
or needs-review mappings are refused instead of silently being reset to Proposed.
Retain those decisions and use a separately identified fictional example when
needed. Unknown assessments and missing counts retain their existing semantics.

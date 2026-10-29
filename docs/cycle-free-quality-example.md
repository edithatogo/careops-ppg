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

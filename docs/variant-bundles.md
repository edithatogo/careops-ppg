# Unordered source variants within an observed edition

`scripts/ppg_variant_bundle.py` prepares a derived ZIP containing every distinct
original member from verified source capsules for one established document
identity and one exact printed edition label. It preserves all input occurrence
receipts in `manifest.json`, including the original capsule hashes, paths and
identity evidence. Original captures must remain separately retained.

The bundle records unresolved variant order, no canonical variant and no
authority assertion. SHA256 member ordering and normalized ZIP timestamps serve
reproducible packaging only; they do not supply source chronology or native
timestamps. Reversing input order yields identical output bytes. Capsule/member
hashes, lengths and CRCs are verified with bounded input/output sizes before a
result is returned. Unknown identities, mixed labels, missing bytes and repeated
identical-only inputs fail closed.

For an established family with two distinct printed editions, the existing
native-history writer can retain one observed edition followed by an unordered
variant bundle for another observed edition. Each native version then represents
the corresponding captured source set. The representation preserves every
variant without selecting a preferred policy or inventing a revision number.
It does not establish order between the variants inside that set. A single
printed edition must not be presented as multiple policy editions.

The builder performs no I/O outside memory, native publication or record edits.
Before using its output natively, the existing owner must verify current source
identity/edition metadata and byte pins, create a separately labelled derived
artifact without overwriting originals, and retain its manifest/hash mapping.
Qualify actual native historical/current downloads, repeat/recovery behavior and
source preservation for the selected use. Keep original planner holds and
frozen evidence; source tests alone do not establish native acceptance. This is
source-preservation packaging, not structured policy generation, editing,
approval, currency or permission to circulate.

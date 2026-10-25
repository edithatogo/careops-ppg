# Supplied-byte integrity helper

`tools/source-integrity/hash_supplied_bytes.ts` adapts the existing pure SHA-256
implementation from `tools/roles/role_projection.ts` without changing that script
or its workbook/native bindings. It accepts supplied Base64 bytes; it does not
fetch URLs, read/write workbook cells, evaluate content or select policy identity.
This is acquisition integrity work, not document generation.

The `main(workbook, requestJson)` entry returns a JSON string. The exact request
has six fields: `kind` (`ppg-supplied-byte-hash-v1`), `qualificationId`, `sourceKey`,
`expectedBytes`, `expectedSHA256` and `contentBase64`. Qualification identifiers
use 1–80 ASCII letters/digits/hyphens; source keys use lowercase letters/digits/
hyphens. Length is an integer from zero to 3 MiB; the expected digest is 64
lowercase hexadecimal characters. Empty bytes are supported for hash qualification;
a publication acquisition profile must still enforce its positive expected length.

Decoding requires the exact encoded length, standard alphabet, correct terminal
padding and zero unused bits. It rejects whitespace and URL-safe variants. The
request string is bounded before JSON parsing. A single pass avoids recursive
multi-megabyte regular-expression matching. Invalid requests throw without echoing
content. A digest mismatch returns the computed digest with `integrityMatches:false`;
the consumer must hold persistence/promotion/checkpoints on that result.

The compact result binds the supplied qualification/source labels and reports
actual length, actual digest and comparison against the separately supplied pin.
Those labels and the expected digest are caller input, not authenticated source
provenance. Both `sourceProvenanceAuthenticated` and `nativeAcquisitionQualified`
remain false. A caller comparing its own invented pin does not authenticate a
publisher; retain the independently qualified profile, native invocation and raw
source receipts. No bytes are returned in the result and no prior capture changes.

## Offline verification and native contract

Run the exact offline tests with explicitly selected repo-local Python 3.15.1:

```sh
.venv/bin/python -m unittest discover -s tests -p test_supplied_byte_hash.py -v
```

The test uses the existing Node TypeScript stripping/VM harness pattern. Its VM
has no workbook, network, Buffer or crypto API. Node crypto outside that VM supplies
independent expected digests. Vectors include empty/one/two/three-byte input,
SHA-256 padding/block boundaries, arbitrary binary and the 3 MiB maximum. Malformed
profiles/Base64, excess fields, wrong expected length, request limits and same-size
corruption are exercised. Source CI proves offline behavior only.

Before native acceptance, bind the existing owned script/workbook and qualify
the existing Standard Excel operation and connection. Reuse the verified Office
Script packaging route: its connector return metadata describes an object with
string `result` and string-array `logs`, even though the TypeScript main returns a
string. Do not infer that a raw TypeScript upload is a valid hosted script. Verify
stored source/metadata, actual invocation at the representative payload size,
computed native output and independent byte parity. Preserve bindings and prior
captures, inspect indirect effects and actual owner-alert state before execution,
and reconcile uncertain writes before retrying. No connection, subscription,
consent, send, schedule or native mutation is introduced by this source increment.

Native runtime hash, authenticated provenance, redirect/final-URL evidence,
durable replay/concurrency, conditional persistence and recovery remain separate
FS-03/04 requirements. None is closed by the offline helper.

## Preservation and qualification records

Retain target-specific run outcomes, dates, source sizes, native version changes,
state records and detailed receipts privately. Inspect actual workbook versions
and bytes before and after invocation, even when the helper contains no workbook
calls. If the provider saves a normalised revision, preserve both versions and
all original bytes; do not silently replace a working fixture or human edits.
Read back the hosted script/package, connection references, complete native
inputs/output and actual owner-alert setting. Finish an owned qualification flow
in its intended stopped state. A selected positive case does not establish every
payload size, negative-case handling or full acquisition acceptance.

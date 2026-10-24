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

## Verification and remaining native work

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

A private retained 2,794,382-byte PDF also passed offline comparison against its
independent hash. Its operational profile and bytes remain outside this repository.
The existing acquisition flow stays stopped; this helper does not modify it.

Before native acceptance, allocate a separately owned script/workbook and qualify
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

## Native checkpoint — 24 October 2026

The separately owned Standard OneDrive/Excel flow completed one manual run on the
retained 2,794,382-byte public original. Native action records prove that its
actual Base64 content became the script request, and the hosted script returned
the same SHA-256 as the independently downloaded original. Exact script source,
hosted packaging, connection bindings and saved source metadata were verified.
The run succeeded in about 18 seconds. The test flow is Off, actual owner failure
alerts are disabled, and its graph/bindings and single-run history are preserved.
This qualifies the supplied-byte helper for that selected positive native case;
it does not qualify every payload size or the native negative-case matrix.

Excel saved a normalised workbook revision even though the script made no workbook
calls. The new workbook is version 2.0 and remains empty, without external links
or macros. Native version 1.0 was downloaded and hash-verified against the original
local fixture; both native versions and both local byte streams are retained.
The hosted script, existing PDF and destination rules/settings/subscriptions are
unchanged. Operational bindings and full native receipts remain private.

The earlier preparation requirements above remain applicable to another target.
This checkpoint closes the selected native hash gap only. Redirect/final-URL
observability, the consumer promotion contract, durable replay/concurrency,
conditional persistence, recovery and broader error cases remain unqualified.
No catalogue row, source-register field, checkpoint or clinical status changed.

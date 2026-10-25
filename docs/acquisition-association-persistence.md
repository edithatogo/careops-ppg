# Append-only acquisition association persistence

`tools/source-integrity/association.mjs` persists the existing acquisition handoff
as source observations in the evidence library. It changes no catalogue row,
publication/edition identity, retained original, clinical status or source register.
It is the source-side persistence step; catalogue promotion remains with its owner.
The prepared handoff remains non-authorising.

## Protocol and native boundary

`planAssociation(handoff)` accepts an exact-edition `reuse-existing-capture`
handoff from the existing v1 interface. It checks selected endpoints, hashes,
occurrence pins, deterministic keys and non-promotion flags. Held/unverified inputs,
key drift, unsupported values and an occurrence larger than 1 MiB refuse planning.
It retains all selected source assertions and earlier acquisition details.

`persistAssociation({handoff, client, verifyBindings, journal})` requires an
explicitly assigned destination and qualified runtime implementations:

- `client.get(name)` returns null or exact bytes plus native UniqueId, ETag,
  UIVersionLabel, Length and ServerRelativeUrl after a stable metadata/content/
  metadata read.
- `client.create(name, bytes)` makes one server-side create-only request with
  overwrite=false, no redirect and no automatic mutation retry.
- `verifyBindings(handoff)` verifies the actual account/client, assigned namespace,
  selected current catalogue record hashes and human state, qualified source-file
  identity/version/ETag, native execution receipt and independent original bytes.
  It returns exactly `{selectedRecordJSON: {recordKey: rawNativeRecordJSON}}`
  for the three selected records. The component hashes each actual UTF-8 JSON
  string and compares parsed content with the copied handoff record before any
  receipt read or journal event, before each create and before final completion.
  Preserve the native numeric/whitespace representation for hashing; do not
  reserialise copied objects as a substitute for current native JSON.
  Missing proof, changed native hashes or altered copied payloads hold the attempt.
  The callback still performs all the account, namespace, original and human-state
  checks above; returning snapshots alone is insufficient.
  Supplied JSON flags never replace those authenticated native checks.
- `journal(event)` durably records intent before a mutation and verified outcomes.
  Keep credentials, bindings and operational receipts private. A test transport or
  successful source CI does not establish these native capabilities.

The three immutable files are:

| File | Purpose |
|---|---|
| `source-replay-<replayKey>.json` | Bind the existing publication/edition/capture and byte digest to the selected record hashes and original link |
| `source-occurrence-<occurrenceKey>.json` | Retain this exact flow/run/file occurrence and its complete prepared handoff |
| `source-commit-<occurrenceKey>.json` | Written last; bind the first two file names, sizes and hashes |

All members are checked before the first write. Existing different bytes hold the
whole attempt. Existing exact bytes are reused with stable native pins. After each
create and again after the source guard, complete readback must match bytes and
pins. Only then is `associationCommitVerified` reported. The marker concerns this
association only; `checkpointAdvanced` and `fullAcquisitionQualified` stay false.
A new occurrence can retain its own evidence while reusing the same capture claim;
it never replaces earlier editions or capture history.

Any failed create is uncertain, including a same-name race. The library never
converts a generic HTTP status into success and never retries the mutation.
Read the actual namespace and source bindings before an explicit later invocation.
A partial set can then resume from its existing exact members. A commit marker
alone cannot hide missing, altered or differently pinned member files. If the
marker exists but a member is missing, hold the set for explicit recovery; do not
recreate a potentially human-deleted file. Partial publication without a commit
can resume after readback.

## Verification

```sh
node --test tests/test_acquisition_association.mjs
```

Sixteen focused tests exercise same-input replay, a new occurrence sharing a claim,
all-member conflict preflight, response loss and explicit resumption, source changes
before/among writes, overlapping creates, changed native pins, late member changes,
held/altered inputs, receipt limits, missing guards and unrelated HTTP 500 refusal.
Three additional cases reject altered copied records and missing/invalid native
record proof while accepting equivalent native numeric/formatting representations.
Fixtures are fictional. Tests never authenticate or mutate native services.

## Native qualification and recovery

Use the existing qualified account and exact assigned namespace. Before any
publish, verify current library configuration and relevant accessible triggers,
current native records and human state, source pins and independent original
bytes. Keep actual dates, identities, execution/collision results, versions and
readback receipts in private evidence. Source tests do not supply these checks.

Exercise an initial publish, unchanged replay, overlapping create, lost-response
reconciliation and partial-set recovery in an assigned isolated namespace. A
file-exists response is uncertain until exact native readback proves what exists;
never infer success from a generic status. Preserve prior member bytes and native
histories. A read-only replay must disable create at the transport boundary.

Runtime adapters written for the former callback contract must now return the
three raw current RecordJSON snapshots after their existing guards. They must
hold until this contract is qualified; copied objects or hash assertions cannot
substitute for native reads. This strengthens payload binding without changing
existing receipt bytes or deterministic keys. Preserve earlier receipts and
qualification drivers rather than rewriting historical evidence.

CLI persistence does not itself qualify an integrated producer/browser path,
final-URL or redirect observability, all interruption cases, isolated restore,
catalogue promotion, clinical applicability or full acquisition.

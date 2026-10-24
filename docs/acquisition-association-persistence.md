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
  It runs before preparation, before each create and before final completion.
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

Thirteen focused tests exercise same-input replay, a new occurrence sharing a claim,
all-member conflict preflight, response loss and explicit resumption, source changes
before/among writes, overlapping creates, changed native pins, late member changes,
held/altered inputs, receipt limits, missing guards and unrelated HTTP 500 refusal.
Fixtures are fictional. Tests never authenticate or mutate native services.

## Selected native qualification — 24 October 2026

An isolated source-owned folder in the existing evidence library was qualified
with inherited access. Current library versioning, rules, subscriptions, receivers,
current-user alerts and accessible Default flow triggers were inspected. The
existing account, application, permissions and bindings were retained.

Two deliberately overlapping CLI publishers used the same real handoff. One
created and verified all three files; the other reported an uncertain same-name
create. On this endpoint the native response was HTTP 500 with the specific
file-exists HRESULT `0x80070050`, rather than HTTP 409. The error was inspected
alongside actual file readback; it was not treated as generic success. An explicit
readback/replay then verified the complete set and made zero create calls. All
three files stayed at native version 1.0 with no older versions, so the overlapping
request did not overwrite the winner. Destination configuration, selected catalogue
rows and original-file pins/bytes remained unchanged. Every occurrence and receipt
is retained; no failed-attempt evidence was deleted.

The combined driver initially found that repeated SDK client initialisation left
its later account list unhydrated. Standalone client and first-account checks
worked. Qualification kept one existing same-client source transport for both
source guards and scoped file operations, preserving the shared publisher adapter
and its strict identity checks unchanged. No login, consent, account/client switch
or credential copying was used. Folder request representation was corrected only
after a native read proved the initial rejected create left no folder.

Detailed identity, transport, guard, collision, file-history and replay receipts
remain private under the assigned qualification namespace. This proves CLI
observation-association persistence and selected same-occurrence overlap/replay.
It does not prove the integrated Power Automate producer/web path, final-URL or
redirect observability, all native interruption cases, broader recovery, catalogue
promotion, clinical applicability or the full sourcing track. Existing successful
transport/hash/replay flows remain separate qualified components.

References: [SharePoint folder/file REST operations](https://learn.microsoft.com/en-us/sharepoint/dev/sp-add-ins/working-with-folders-and-files-with-rest),
[Windows file-exists error code](https://learn.microsoft.com/en-us/windows/win32/debug/system-error-codes--0-499-).

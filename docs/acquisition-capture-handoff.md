# Acquisition handoff to an existing catalogue capture

`scripts/ppg_acquisition_handoff.py` prepares a source-side association between an
acquisition occurrence and a consumer-selected existing capture. It reuses the
catalogue's Publication, Edition and Capture records and existing framework keys.
It does not create a second catalogue, infer identity from a title/URL/hash,
replace a retained original or change the historical acquisition route/time.
The catalogue remains the sole native record writer.

The selected record shape is the existing external catalogue v1 shape. The source
helper checks the endpoint/byte boundaries it consumes; the catalogue owner still
runs its full schema/business validation before any persistence. Keep the exact
selected native rows, current item ETags, RecordJSON/payload hashes and original
file readback beside the private handoff. A local copied selection is not a fresh
native record read or authority to overwrite a correction.

## Input and output

Supply four JSON inputs, the independently verified original, and optionally
explicit URL byte-evidence entries. JSON inputs are limited to 1 MiB each and
reject duplicate keys and nonfinite numbers. Original bytes use the existing
3 MiB acquisition qualification limit. The current transport profile validator
is reused; no alternate source allowlist or connection policy is introduced.

- `selection`: complete `publication`, `edition` (or null), `capture` and
  `knownFrameworkKeys`. Preserve the exact source assertions, original nativeURL,
  capture time, source status, role and source/template/history distinctions.
- `profile`: the existing fixed acquisition qualification profile, including
  expected source URL, framework, length and digest.
- `native-result`: the exact supplied-byte helper result. Its qualification and
  source labels, actual/expected digests and actual length must agree with the
  profile, selected capture and independent bytes. Premature provenance or full
  acquisition assertions refuse the handoff.
- `observation`: `observedAt`, `workflowId`, `runId`, `receiptSHA256` and
  `sourceFile` (`uniqueId`, `nativeVersion`, `etag`, `url`, `bytes`). Native file
  version is an occurrence pin, separate from the selected publication edition.
- `url-evidence`: at most eight entries with `url`, `sha256`, `bytes` and
  `receiptSHA256`. Distinct requested/catalogue URLs require matching entries for
  both exact locators. Pin and verify the referenced actual receipts separately;
  supplied JSON does not authenticate the observations.

Equal bytes at a single-slash and double-slash path do not normalise the URLs.
Without explicit evidence for both, the result is `held-locator-evidence`.
An explicitly unverified edition remains `held-edition-unverified`; no latest
edition is inferred. Conflicting endpoints, frameworks, bytes or native-result
labels refuse preparation. A valid selected exact-edition match returns
`reuse-existing-capture` and retains both the staging occurrence URL and existing
catalogue original URL.

The `replayKey` hashes the selected publication/edition/capture, literal requested
source URL and content digest. It excludes run time and qualification UUID, so a
new run of unchanged content does not require a duplicate capture. The separate
`occurrenceKey` includes flow/run and observed native file pins; each actual source
occurrence can remain traceable. Identical bytes in different consumer-selected
editions retain different replay keys. Neither key is a durable claim, a saved
checkpoint, a publication identity or proof of concurrent native execution safety.

The result retains the complete selected records and their canonical SHA-256
values. `originalFilesToCreate` and `catalogueEdits` are empty. Native mutation,
checkpoint, provenance-authentication, full acquisition and clinical acceptance
flags remain false. Qualified native receipts can support the owning consumer's
next operation; this CLI never upgrades a caller-supplied JSON claim into native
runtime proof.

## CLI and focused checks

Use the explicitly selected repo-local Python 3.15.1:

```sh
.venv/bin/python scripts/ppg_acquisition_handoff.py \
  --selection PRIVATE_SELECTION.json --profile PRIVATE_PROFILE.json \
  --native-result PRIVATE_HASH_RESULT.json --observation PRIVATE_OCCURRENCE.json \
  --original PRIVATE_ORIGINAL.pdf --url-evidence PRIVATE_URL_EVIDENCE.json \
  --output NEW_PRIVATE_HANDOFF.json
.venv/bin/python -m unittest discover -s tests -p test_acquisition_handoff.py -v
```

Output is create-only with mode 0600. An existing path is refused, preserving
prior handoffs and human work. This is metadata preparation, not document-body
generation or a replacement for the maintained SharePoint document route.

## Persistence boundary

Before persistence, the owning catalogue route validates its complete manifest,
re-reads selected rows and exact originals, checks current ETags and preserves
human edits and earlier assertions. An uncertain write requires readback before
retry. Apply only the specifically assigned observation/association fields through
the existing writer; do not rewrite a historical capture as newly acquired by a
flow merely because a later flow retrieved equal bytes. Keep every occurrence and
source receipt. Persist/read back a claim and association before advancing any
checkpoint; native replay/concurrency and recovery still require actual proof.
This helper alone closes none of those native persistence gates.

## Native interface qualification

The catalogue owner supplies the selected publication, exact edition and existing
capture. Read back their current RecordJSON, hashes, endpoints and human review
state; retain HTTP and item-metadata ETags separately. Download the retained
original with stable pins and compare it with the independently verified source.
Run the owner's complete schema/business validator without broadening its scope.
Keep selected-cohort completeness separate from whole-catalogue coverage.

Retain source and catalogue URLs as distinct locators. When they differ, supply
explicit byte-evidence receipts for both rather than deriving equivalence from
an equal digest. Preserve the capture's earlier route/time and original link.
Store target-specific dates, outcomes, bindings and detailed receipts privately.
This preparation contract never creates a native record/file or closes durable
claim, conditional-write, replay or recovery gates.

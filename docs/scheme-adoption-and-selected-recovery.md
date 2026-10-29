# Scheme adoption and selected recovery

Use the existing framework register for versioned scheme configuration. Keep the
framework key stable. Scheme authority, external decision authority and internal
review states are separate; a quality-improvement framework need not have a scheme,
cycle, assessor or award. Retain old contract versions and source captures.

Prepare a configuration with the repo-local Python environment:

```sh
.venv/bin/python -m scripts.ppg_scheme_adoption \
  --framework-key nsqhs-2-2021 --scheme-key scheme:ahssqa \
  --contract config/accreditation-contract-v2.json \
  --vocabularies config/accreditation-scheme-vocabularies-v1.json \
  --output /private/new-scheme-configuration.json
```

Omit `--scheme-key` for a cycle-free quality framework. `--existing` accepts a
previous configuration: identical content reuses it, conflicting content is refused.
The output file is create-only and private. Configuration generation does not prove
publisher authority, native adoption or permission to rate/award accreditation.
The bundled vocabulary is a retained versioned source reference, not a latest-edition
claim. A native adapter must verify the exact captured source and record the actual
field internal name returned by SharePoint before conditional persistence.

Reconcile a complete selected recovery snapshot:

```sh
.venv/bin/python -m scripts.ppg_selected_recovery \
  --snapshot /private/selected-native-snapshot.json \
  --output /private/new-recovery-reconciliation.json
```

The snapshot has `pairs`, `snapshots`, `referenceBindings`, `files` and optional
`captures`. Each pair declares its source/target list IDs, stable `key` field and
complete selected source/target rows. `snapshots` maps list IDs to native `fields`
and `rows`; references declare source/target IDs and the destination key. File
proofs bind each evidence key to its exact source version, expected SHA-256, size
and distinct source/recovery file identities. Source rows must name the proved source object.
Recovered rows must link to the proved independent copy through `RecoveryCopyURI`
or their relocated `SourceURI`, even when their origin identity is retained.
Historical source URLs must match the exact version in the file-history proof. Capture proofs bind guidance capture
keys to two independently read objects and hashes. The tests demonstrate a minimal
fictional shape; actual records and readback proofs stay outside Git.

Every declared key and editable source field must reconcile. Lookups must resolve
to the same logical identity in a different list. Existing human text and missing
values are preserved. Only explicit lossless archival Choice-to-Text and Text-to-Note
representations are allowed; values still obey the original choice vocabulary.
Original schemas, nullable archival constraints, source missing values and existing
recovery annotations are reported explicitly. Source history is retained as exact
provenance; never impersonate original authors or creation times in restored native
objects. Native restoration must separately verify schemas, versions, file bytes,
relationships, permissions and zero-write replay.

Both commands perform zero native writes and never authenticate. Add their outputs,
exact schema snapshots, file bytes and source/recovery histories as another sealed
extension of the existing reconstruction chain. Use the maintained unpacker on an
independent extraction, and again on native-downloaded bytes. Preserve earlier
manifests and deployed records; no new recovery framework is required.

These helpers establish declared-snapshot consistency only. They do not claim
whole-library, whole-tenant, cross-tenant, publisher-history or clinical acceptance.

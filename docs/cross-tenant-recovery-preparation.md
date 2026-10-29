# Cross-tenant recovery preparation

Cross-tenant recovery restores into a different Microsoft 365 organisation.
Separate lists within one organisation prove isolated same-tenant recovery only.

The offline helper `scripts/ppg_tenant_recovery.py` prepares explicit destination
bindings for a sealed selected-record export. It performs no authentication,
provisioning, uploads, record writes, permission copying or automation activation.
A prepared plan is not evidence of destination access or a successful restore.

```sh
.venv/bin/python scripts/ppg_tenant_recovery.py \
  --export private/export.json --destination private/destination.json \
  --output private/transfer-plan.json
```

Omit `--destination` to record the destination-required hold. Outputs are
create-only and private. Keep exports, bindings and real records outside Git.

The export envelope contains `payload` and its canonical JSON SHA-256: UTF-8,
sorted keys, compact separators, unescaped Unicode, and no non-finite numbers.
The payload has `schemaVersion: 1`, `sourceTenantId`, `entities` and `files`.
Each entity contains field contracts (`name`, `type`) and records (`key`, `values`,
`references`). File entries declare SHA-256 and byte length; actual bytes remain
in the sealed source archive and must be independently verified after upload.

References are explicit per-field: `lookup` uses an `entity:key`; `identity` uses
a source identity key; `file` uses a file key and part `url`, `sourceItemKey` or
`exactVersion`. Lookups must stay within the declared export. Non-null Lookup/User
fields require remapping. Original platform IDs, authors and timestamps belong
in retained provenance, not copied writable fields.

The destination declares `tenantId`, `siteUrl`, entity-to-list UUIDs in `lists`,
logical-record-to-item IDs in `items`, identity mappings in `identities`, and file
bindings in `files` (`url`, `uniqueId`, `version`, `sha256`, `bytes`). It must be a
different tenant. File locations must be inside the exact destination site and
match declared source hashes and lengths. Missing bindings are explicit holds;
source physical references are not silently reused. Credentials and permissions
are not part of this format.

`readyForNativeQualification` means only that supplied bindings reconcile offline.
The caller still needs a designated destination, supported destination-specific
login, exact target/effects qualification, schema preparation, native readback,
version/history handling and unchanged replay. Export adapters must declare all
native references; this is not a blind search-and-replace tool for arbitrary JSON.

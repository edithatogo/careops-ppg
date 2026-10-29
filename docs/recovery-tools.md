# Recover a pinned evidence packet

The recovery tools verify and unpack an existing reconstruction packet into a
new local directory. They preserve the input archive and refuse an existing
output directory. Use the archive SHA-256 and chain-head SHA-256 from the
independently retained packet receipt; computing a new expected hash from an
untrusted archive does not establish its identity.

From the repository root, with its Python 3.15.1 environment:

```sh
.venv/bin/python -m scripts.ppg_reconstruction_unpack \
  /private/path/packet.tar /private/path/new-recovery \
  --archive-sha256 "$ARCHIVE_SHA256" --chain-head "$CHAIN_HEAD_SHA256"
```

The packet must use the existing `reconstruction-package-v1` and numbered
extension manifests. Extraction rejects links, duplicate paths, traversal and
undeclared members. Chain hashes, selected record pointers, workflow lookups,
requirement membership and custody navigation are checked before delivery.
Files are created with private permissions. A failure removes the temporary
extraction and leaves the original archive unchanged.

For an already extracted packet, inspect the available checks with:

```sh
.venv/bin/python -m scripts.ppg_reconstruction_chain_audit --help
```

`tools/accreditation/ordered-history-state.mjs` supplies a separate pure decision
function for a two-version native restore. It returns `create`, conditional
`update`, or `noop` only for exact expected states, and refuses conflicting
histories. It makes no requests. Any native writer must retain its own exact
target binding, conditional writes, durable send journal and readback.

Local reconstruction does not restore original native authors or timestamps,
deploy a tenant object, or establish substantive policy acceptance. Keep real
packets and receipts outside this public source repository.

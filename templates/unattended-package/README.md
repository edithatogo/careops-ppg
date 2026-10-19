# Fixed cover and existing-package toolkit

This source-only slice supports a seven-field DRAFT cover and bounded ZIP
assembly. It contains no tenant configuration, operational documents, native
receipts, deployed flow or entitlement claim. The tests use fictional XML
fixtures; they do not prove Word layout or tenant behaviour.

Evaluate SharePoint structured document generation first. A property-bound
cover must pass **both** saved custom-XML property and saved visible-text checks;
property success alone does not qualify Word or PDF output. If the selected
native route fails saved-text persistence, the bounded snapshot fallback below
can be qualified in an existing Office Script packaging runtime. A successful
source test does not qualify that runtime or its connector/licensing prerequisites.

## Template and accepted inputs

Use a maintained blank Word template with seven uniquely tagged, correctly bound
plain-text controls and a fixed DRAFT label. The supported tags are:

| Tag | Recorded value |
| --- | --- |
| `PPGCoverTitle` | Document title |
| `PPGCoverCaseUID` | Existing case identity |
| `PPGDocumentUID` | Document identity |
| `PPGPolicyEdition` | Source version |
| `PPGCoverRecordedOwner` | Recorded owner |
| `PPGCoverReviewDate` | ISO review date |
| `PPGCoverOutputRevision` | New output revision |

Each accepted value is nonblank text up to 255 characters. Represent missing
facts explicitly as `Unresolved`; do not invent ownership, review or approval.
The current template shape requires a single `[Unresolved]` cached text run per
control. Other document shapes, repeating tables and conditional narratives are
outside this route. No Windows-only authoring method is imposed by this source;
qualify the available authoring and user clients for the actual template.

`ppg_sharepoint_cover.inspect_cover` checks actual property-store relationships,
binding paths and saved text independently. `ppg_cover_snapshot.compile_cover`
prepares pinned template parts once for a maintained revision; it refuses a
rendered or edited output used as a blank template. Keep this preparation and all
real values/private native bindings outside Git.

## Existing two-parameter script interface

The Office Script `main(workbook, jobJson, membersJson)` retains its existing
parameters. The workbook only hosts the action; the script performs no workbook
or network reads/writes. Normal packaging accepts a versioned job and ordered
`{path, base64}` members. Schema 2 is specifically existing-artifact assembly:
its historical authoring remains unknown and Word generation is false.

For a cover, pass this explicit JSON envelope as `jobJson`:

```json
{"kind":"standard-cover-input-v1","jobJson":"<serialized frozen job>","coverJson":"<serialized compiled cover>"}
```

The inner schema-1 job records source/template identities, versions and hashes,
included record IDs, output revision and expected member bytes/hashes. Its
`coverSnapshot` contains `route: standard-office-script-fixed-cover-v1`, the exact
`manifestSHA256` of `coverJson`, `templateSHA256`, and the output member `path`.
Cover case/revision must match the job. `membersJson` contains only the other
selected evidence members; the script generates and inserts the expected cover.
The example envelope above is documentation, not an executable job.

At runtime the script validates pinned parts and values, escapes XML text and
replaces the seven cached values. It detaches **only the output's** property
bindings, producing a snapshot that later library metadata cannot rebind. It
preserves the maintained template and every other template part. The same
invocation assembles the new cover with unchanged evidence bytes and DRAFT
provenance. It reports the generated cover and package hashes/base64 separately.
The conservative complete-raw limit is 2 MB and the serialized wire limit 4 MB;
these are application guards, not provider maximums.

## Native qualification and recovery

These pure functions do not perform native persistence. An integrating flow must
pin its actual template, frozen selection, script and evidence before/after reads;
source assertions in a job are not self-authenticating. Use its existing job
identity, exclusive claim, staging, non-overwriting output revision and receipt-last
commit. Same-job replay verifies saved bytes and reuses them. Changed inputs or
edited outputs require a new revision. Verify actual native file identity and
package/receipt bytes after commit; never replace an edited or issued file.

Independently download and inspect the saved DOCX with `inspect_snapshot`, the
package ZIP CRC/membership, unchanged evidence and the actual native output
identity. Check long/Unicode text, explicit unresolved values, dates, links,
layout, client editing/reopening, retry and interrupted-run recovery. PDF is a
separate qualification; failure must leave the DOCX and package usable. This
fixed-cover route neither produces a combined full document nor confers approval
or permission to issue it. Preserve the working route until replacement parity is
proved. Reuse library-column guidance in `conductor/suite-delivery.md`; do not add
schema to a shared library incidentally.

## Portable checks

```sh
python -m unittest discover -s tests -p 'test_*cover*.py'
node tests/test_cloud_package.cjs
```

The Node check uses built-in TypeScript stripping (Node 22.13+ or the repository's
qualified current runtime). Python independently verifies ZIP bytes and CRCs.
No third-party runtime packages, cloud calls or credentials are needed.

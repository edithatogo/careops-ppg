# Fixed-source URL acquisition qualification

`scripts/ppg_url_acquisition_qualification.py` prepares one stopped, manual
OneDrive for Business qualification graph. It does not create a connection,
save/enable/run a flow, download a source or promote catalogue records. This is
preparation for the first owned transport experiment, not the final resumable
acquisition producer or full acquisition acceptance.

Use the explicitly selected repository-local Python 3.15 runtime at its qualified
patch. The CLI verifies the actual interpreter, repository pin and local prefix.
Bound definitions stay under `.local`; output creation is exclusive with mode
0600 and never replaces an earlier output.

```sh
.venv/bin/python -m scripts.ppg_url_acquisition_qualification \
  --profile .local/sourcing/allocated-qualification-profile.json \
  --output .local/sourcing/stopped-qualification-flow.json
```

A real profile requires `qualificationId` (a nonzero UUID), a literal `sourceKey`,
the existing `frameworkEditionId`, fixed `sourceURL`, exact HTTPS `allowedOrigins`,
an allocated `stagingRoot`, an `ownershipEvidence` pointer, one existing embedded
OneDrive `connectionReference`, and `expectedBytes`/`expectedSHA256`. A nonempty
ownership pointer is input validation, not proof of permission or an object lease.
The native owner must check its actual evidence before using the result. Unallocated
roots/owners, dynamic expressions, arbitrary connectors and unsafe URLs/paths refuse.
No publication identity is created by accepting an opaque existing key.

The selected experiment envelope is at most 3 MiB. This is a local qualification
scope, not a discovered provider maximum. Stage identity is the frozen UUID under
the allocated folder, with a `.captured` suffix; different acquisitions retain
distinct targets. Do not regenerate the UUID merely to retry an uncertain operation.

## Graph behavior

Only the fixed source key is accepted by the manual trigger. All connector actions
use the exact existing OneDrive reference with automatic retries disabled.

1. Inspect the staging path. An existing object enters readback without an upload.
   Only an actual 404 permits one `CopyFile` URL-upload attempt, with explicit
   `overwrite=false`. Other failures hold the operation.
2. After the upload acknowledgment, poll metadata with a twelve-iteration/two-minute
   configuration and five-second waits. Success requires expected size, a file
   rather than a folder, and nonempty identity/ETag. A pending 404 may be observed
   again; other failures set the error flag and stop polling. Those are configured
   limits, not a native timing guarantee established by source tests.
3. Read metadata and require the expected size, a file and nonempty identity/ETag
   before requesting any content. Then read content and metadata again.
   Identity/ETag must be unchanged, both sizes must match the expected size, and
   both observations must describe a file. Known wrong-sized or folder targets
   stop before a content request; changed objects are held and never overwritten.
   A hard transfer-byte ceiling under concurrent mutation remains a native
   transport requirement, not something the metadata check proves by itself.
4. Report content and its two metadata observations as **awaiting independent
   verification**. The expected digest is retained separately from the null actual
   digest. Byte integrity, representation, redirects, final source URL, checkpoint
   advancement, native qualification and clinical applicability remain unproved.

The [OneDrive connector reference](https://learn.microsoft.com/en-us/connectors/onedriveforbusinessconnector/)
warns that URL upload can acknowledge success before the transfer outcome is known.
Acknowledgment is not completion. The current environment's actual operation
schema, connection and policy access must be inspected separately.

## Native owner prerequisites and required follow-through

Before the first native invocation, allocate the unused staging namespace and
qualification flow, verify the current source/profile and existing connection,
and inspect complete native run history to prove zero earlier invocations. Save
Stopped, read back the exact graph/bindings/state, and verify the **actual** owner
failure-alert setting is false. The generated desired setting is not native proof.
Use the existing strict email preflight on the actual native readback. There is no
outbound action or scheduler in this graph, and no new mail connection is needed.

Invoke once through the supported web surface, retain the exact run handle and
complete actions, then stop the qualification flow. Do not automatically resubmit
or retry. If the action times out, fails or leaves an uncertain outcome, inspect
the existing run, outstanding transfer and staging state before another submission.
A currently absent file does not prove that an asynchronous transfer cannot finish
later. This graph has no durable cross-run claim; a second queued/manual run is
outside its accepted experiment scope. Qualify claims and uncertain-write recovery
before making it a repeatable producer or claiming safe replay.

Download the stored bytes independently and verify length, raw SHA256,
representation and source identity against the retained authoritative observations.
Resolve redirect/final-URL observability and qualify the required native hashing
and parsing route. If the transport does not expose a required property, retain the
specific gap; do not substitute the requested URL or expected hash as observed truth.
A matching metadata size or a successful local verifier does not prove all of those
native requirements. Preserve staging originals, earlier editions and all evidence.

Only after those steps, the agreed FS/EC field ownership and the required
persistence/readback/replay/recovery checks may the full acquisition task close.
This component supplies no catalogue writer, source-register change, approval,
publication, schedule, subscription, notification or production readiness.

Focused offline check:

```sh
.venv/bin/python -m unittest discover -s tests -p test_url_acquisition_qualification.py -v
```

The private repository's existing standard-only sourcing gate can additionally
inspect the prepared definition. Passing that gate establishes the supplied action
surface only; it does not establish native operation, tenant DLP or entitlement.

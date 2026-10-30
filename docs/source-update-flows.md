# Simple source-update flows

The generator prepares three stopped Power Automate definitions: Commission RSS,
folder-triggered Commission newsletters, and a blocked METEOR preparation. RSS,
SharePoint and Office 365 Outlook use their standard connectors. No AI, premium
HTTP action, outgoing email, automatic publication decision or new runtime is added.

## Bootstrap and generate

Use the existing qualified CLI workload and bootstrap route. Reuse a review-lead
destination with the supplied field contract; otherwise create one companion list
from `config/source-update-leads.json` in the existing workbench site. Do not store
signals as publication/edition/capture identities or manufacture policy decisions
to fit a change register. Preserve inherited access and existing list data. The
contract uses plain Note fields for fingerprints, observations and long links.

Keep a private binding containing `site`, `listId`, and `sharepoint`; RSS also
requires `rss`, and newsletters require `outlook`, `folderId` and exact `senders`.
Each connection reference contains its actual `id`, `source: Embedded` and
`connectionName`. Resolve them from qualified existing connections, not guesses.
METEOR preparation instead requires an explicit `indicatorIds` array.

```sh
.venv/bin/python -m scripts.ppg_source_update_flows \
  --channel rss --binding /private/rss-binding.json \
  --output /private/rss-stopped.json
```

Use `--manual` to prepare the same collector for a bounded native test. After a
successful run and unchanged replay, replace its manual trigger with the generated
daily definition on that same owned flow. Daily time is 07:00 Brisbane using the
Windows `E. Australia Standard Time` identifier. Save and read back definitions,
connection references and native states before enabling.

New flows can subscribe the owner to failure emails even when the submitted
`flowFailureAlertSubscribed` is false. Inspect the returned native setting and
use the native Repair tips off control if necessary. Verify the actual returned
value is false before any run or activation. The generator flag is intended
configuration, not a native subscription receipt.

## Collection behavior

Each observed identity is queried within its channel. Identical fingerprints create
no additional record; changed observations append Proposed leads, preserving prior
records and human edits. Fingerprints retain the native RSS item's observed data;
they are not transport-byte hashes or publisher edition assertions. Missing/oversized
identities and incomplete history queries fail before persistence. Failed collection
writes a Failed lead and leaves the flow failed, without copying protected errors.
The collector is stateless, rereads the available source window, and advances no
catalogue checkpoint. Persisted observations are its replay evidence.

Trigger and loop concurrency are one; connector actions have zero retries. There
are no updates/deletes, source-document downloads, mail sends, message moves,
forwarding rules or recurring notifications. Workflow histories and the Failed
lead view provide operator-visible failures. Retain existing official-index
reconciliation because RSS is a rolling window, not complete source history.

## Newsletter readiness

Use the existing work mailbox and a dedicated `Policy newsletters` folder. Resolve
its actual ID and verify the Outlook connection account. Identify exact sender
addresses from suitable existing newsletter messages. A normal generated trigger
filters those senders, excludes attachments and leaves messages in place. Records
retain message identity, subject, received time, message link and observed direct
Commission links; tracking links are not followed. HTML-link extraction is bounded
and can return no publisher links, which does not establish absence of a publication.

If sender evidence is unavailable, set `senders: []` and add
`--prepare-newsletter`. This produces a stopped folder-bound definition with an
explicit terminating guard, not an active collector. Remove that mode only after
verifying the sender, delivery into that folder and an appropriate native run.
Subscription enrolment and automatic filing are separate operations. Folder creation
alone does not route newsletters there. Do not send test email or claim arrival
runtime from a saved trigger or a read-only mailbox inspection.

## METEOR preparation

```sh
.venv/bin/python -m scripts.ppg_source_update_flows \
  --channel meteor --binding /private/meteor-selection.json \
  --output /private/meteor-stopped.json
```

This is a saved preparation shell: a daily trigger, explicit selected indicator
URLs and a terminating access guard. HTTP/HMAC execution and result persistence
remain unimplemented until approved access, private signing instructions, supported
connection storage and an allowed licensed runtime are qualified. It makes no API
calls and contains no credential placeholders. Do not replace the guard with guessed
headers or introduce a premium integration under a standard-only scope.

The [official API guide](https://meteor.aihw.gov.au/content/811642) specifies
registration/subscription and per-request HMAC authentication. The
[endpoint inventory](https://meteor.aihw.gov.au/content/811645) documents read-only
`/api/v1.0/Indicators` search and `/Indicators/{meteorIdentifier}` item access.
Retain the existing public-page fallback. Publisher revision-history and source
status limitations remain explicit; cross-tenant recovery is separate.

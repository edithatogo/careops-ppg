# Reusable PPG source collectors

Use `scripts/ppg_source_update_flows.py` with a small source profile and a private
binding. The committed profile catalogue contains Commission and individual TGA
RSS endpoints, plus a fictional newsletter preparation profile. Endpoint availability is not
proof of subscription, tenant permission or native runtime behaviour.

```sh
.venv/bin/python scripts/ppg_source_update_flows.py \
  --channel rss --source-key tga-safety-alerts \
  --binding .local/qualified-rss-binding.json \
  --output .local/tga-safety-alerts-stopped.json \
  --manifest .local/tga-safety-alerts-manifest.json \
  --source-commit "$(git rev-parse HEAD)"
```

Use repo-local Python 3.15.1. Outputs are create-only, mode 0600 and always stopped.
The private binding supplies `site`, `listId` and existing `sharepoint`/`rss`
connection references. Each reference has `id`, `source: Embedded` and
`connectionName`; this is a connection binding, not a credential. The destination
uses the schema in `config/source-update-leads.json`.

For newsletters, use `--channel newsletter --source private-source.json` with a
verified profile (`key`, `publisher`, `name`, `fallbackUrl`, `linkDomains`). Bind
`outlook`, `folderId`, exact `senders` and `subjectContains`. Candidate public link
hosts are not qualification of a particular message. Put verified internal hosts
in private configuration. For read-only qualification against one existing message,
add `--manual` and a private `messageId`; no message is sent, moved or marked read.
The manual path uses the standard Outlook connector's HTTP request operation.
It requires that exact operation and mailbox access to be qualified in the target.

Normal newsletter collection uses folder-bound OnNewEmailV3. Folder creation does
not route messages: establish delivery before activation. Replies/forwards and
unrelated subjects are excluded. Receipt time is retained separately from unknown
publication time. Only configured HTTPS publisher links are extracted; redirect
hosts, unusual HTML and attachment-only newsletters require sample qualification.
No subscriptions, filing rules or email notifications are installed by the generator.

Deduplication is source-specific. Existing Commission RSS retains its legacy `rss`
namespace and observation shape; other sources use `channel:catalogue-key`.
Unchanged observations create no leads, changed observations append, and human
processing state remains untouched. Empty GUIDs fall back to links; absent/oversized
identifiers and incomplete deduplication queries fail before persistence. Failure
records are written to the lead destination; destination outages remain visible in
native run history. No automatic mutation retries or clinical decisions.

Run only one collector per source namespace: concurrency one is per flow, not a
cross-flow lock. Use individual TGA feeds or the aggregate, never both as independent
copies. Stop a manual qualifier before enabling its scheduled/arrival replacement.
Daily schedules default to 07:00 Australia/Brisbane.

Names follow `PPG | Source updates | Publisher | Channel | Type`; definition version
is 1.1.0.0. Preparation manifests bind the exact source commit, configuration,
definition and connection-reference hashes without claiming native verification.
Reuse an existing solution/export route where supported. Verify actual solution
membership, references and environment variables; direct-created flow metadata or
Git versioning alone does not prove solution-aware ALM. No new environment or
pipeline is required by this feature.

Before native deployment, verify existing object identity and ownership, preserve
its definition, and reconcile uncertain sends rather than creating another copy.
Save stopped; read back definitions, bindings and actual owner-alert suppression.
Qualify one collection and unchanged replay, then enable only qualified sources.
Natural schedule and email arrival proof remain distinct from manual tests.
Keep internal sources, private manifests, bindings, messages and receipts out of Git.

Focused source checks:

```sh
.venv/bin/python -m unittest tests.test_source_update_flows -v
```

# Integrated transport, hashing and association handoff

`scripts/ppg_integrated_acquisition.py` connects the existing fixed-source
OneDrive transport to the already qualified supplied-byte Office Script hash
action. It prepares a stopped definition and validates exact saved readback;
it never authenticates, deploys or invokes a flow itself.

The selected Standard OneDrive and Excel connections, script and workbook are
explicit inputs. Dynamic runtime bindings refuse preparation. Script source and
package hashes bind the candidate to the qualification evidence; actual native
script bytes and workbook state must still be checked before execution. Passing
the supplied JSON gate alone does not authenticate those files or a run.

The graph retains the original source allowlist, size limits, manual source-key
selection, no-overwrite upload, bounded polling and metadata/content/metadata
checks. Its original transport qualification annotations remain retained with
that component's evidence. After stable content readback, the graph passes those
exact bytes to the hash action, parses its result and re-reads file metadata.
Changed identity, ETag, size, digest, hash-request identity or acceptance flags
hold the run before the integrated report. Connector retry policies remain None.

The general sourcing preflight still rejects arbitrary script actions. The
integrated validator accepts only the exact graph reconstructed from the selected
profile and qualified runtime. It checks action expressions and bindings, allows
only the existing native authentication annotation, and requires Stopped plus
actual owner failure alerts Off. Creator, run history and native side effects
need their own current readback. Preserve the existing flow identity, restore
definition, connection references and earlier execution receipts when saving.

`verify_observation(profile, runtime, report, independent_bytes)` compares the
supplied output with independent original bytes. It checks the nested transport
report, digest, length, run identity,
script pins and post-hash metadata. It intentionally does not authenticate native
execution or claim persistence, source currency or full acquisition acceptance.
Runtime qualification must additionally bind that report to the actual native
input/output artifacts and authenticated action records.

## Selected native qualification — 24 October 2026

The existing source-owned transport flow was updated in place through one guarded
save, with exact native graph/reference readback, preserved creator/history and
actual failure alerts Off. Its separate hash helper was neither modified nor
invoked. The already qualified script, workbook and captured original were reused.

The in-app Power Automate session required sign-in and returned an expired-token /
MSAL PKCE cache error. No credential cache was reset or transferred. The supported
CLI `flow run resubmit` route submitted the existing selected input once, through
an exact-target guard allowing one mutation send and no redirects or retry. This
is CLI execution evidence; the new integrated web invocation remains unqualified.

The new run succeeded. All 40 native action records were read. The upload was
Skipped; the content read, script execution and post-hash metadata check succeeded.
Nine run-bound artifacts were downloaded without forwarding a bearer token and
verified against their native size/MD5 framing. The script's actual input equalled
the downloaded content, and its actual output digest matched an independent
2,794,382-byte original. Script, workbook and source-file bytes and native pins
remained unchanged. The flow was returned to Stopped, alerts stayed Off, and both
earlier successful runs remained intact.

The verified occurrence was then passed through the existing consumer-selected
capture handoff and [association persistence](acquisition-association-persistence.md).
CLI persistence reused the existing replay claim and created only the new
occurrence and commit files. Explicit readback/replay made zero creates. All five
receipt files, including the earlier occurrence and commit, remained at native
version 1.0 with unchanged earlier bytes and pins. Current catalogue rows, human
state and retained original were checked by the persistence guards and unchanged.

This qualifies the selected combined transport/hash run followed by guarded CLI
association persistence and replay. It does not establish a single cloud producer
transaction, integrated web operation, fresh remote retrieval on every replay,
redirect/final-URL observability, changed-source handling or broader producer
recovery. No catalogue promotion, checkpoint advancement, clinical applicability,
schedule, notification, new connection or permission is implied. Full FS-04 stays
open; its next step is to join persistence/recovery to the owned producer path.

Detailed preimages, failed browser renewal, single-send journals, native action
artifacts, byte proofs and association receipts remain private with the source
owner. Preserve every earlier edition and occurrence. Seven focused integration
tests passed on actual repo-local Python 3.15.1; the 32 existing transport/preflight
tests also passed. Run the affected selectors during edits:

```sh
.venv/bin/python -m unittest -q tests.test_integrated_acquisition
```

Hosted source/package checks and native runtime proof have separate scopes.

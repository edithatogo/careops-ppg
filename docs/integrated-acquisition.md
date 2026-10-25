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

The integration does not widen a generic connector allowlist. Its validator
accepts only the exact graph reconstructed from the selected
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

## Native execution and recovery qualification

Before saving, freeze the complete previous definition, flow identity, creator,
connections and earlier run history. Check the selected native script, workbook,
source and original bytes/pins, destination configuration and relevant accessible
triggers. Keep actual native receipts and target-specific outcomes private.

Save with a single guarded request and read back the complete graph, references,
stopped state and actual failure-alert setting. A provider validation response
alone is insufficient. Invoke only the exact selected input through an existing
qualified route; retain its native run ID, action records and bound artifacts.
Verify artifact size/digest framing, actual content parity, script input/output
and post-hash metadata against independent bytes. Preserve any provider-generated
file revisions and return the maintained flow to its required terminal state.

Pass a verified occurrence through the consumer-selected existing-capture handoff
and append-only association protocol. Require the current callback contract's raw
native RecordJSON proof and independent original verification. Replays reuse exact
members without overwriting their bytes or native history. An uncertain operation
must be reconciled before another explicit invocation.

Qualify browser execution, source drift holds, interruption recovery, same-object
definition restoration and isolated-target restore separately. Keep producer-side
persistence, final-URL/redirect observability and source currency explicit. Neither
a combined transport/hash run nor a following CLI association establishes every
full-acquisition or clinical gate. Source CI is separate from native acceptance.

Run affected integration checks with the explicitly selected local interpreter:

```sh
.venv/bin/python -m unittest -q tests.test_integrated_acquisition
```

# Cloud source-observation receipts and recovery

`scripts/ppg_cloud_observation.py` extends the existing integrated acquisition/hash
graph with create-only observation receipts in its assigned evidence folder. The
builder and validator perform no authentication, deployment or native execution.
Use exact private bindings and current readback before saving or invoking a flow.

The graph reuses the existing Standard SharePoint receipt pattern: a narrowly
bound REST create with `overwrite=false`, followed by binary content and native
metadata readback. It retains the qualified OneDrive/Excel transport and hash
components. No generic REST or script-execution allowlist is widened. Existing
connections, native-object owners and the catalogue's writer remain authoritative.

## What the graph checks

- Verify the qualified script's path, name, size and ETag before executing it.
  Recheck it during the initial, pre-write and final source guards. A declared
  script hash alone does not authenticate the native script file.
- Bind all three consumer-selected publication/edition/capture records to their
  exact current RecordJSON, digest and human review state. Check original-file,
  existing capture-claim and staging pins during those same guards.
- Require the original capture claim's exact canonical bytes. It is reused and
  never overwritten or recreated by this graph. Catalogue preimages and the
  claim's selected-record hashes must agree before preparation.
- Persist one self-contained `ppg-native-acquisition-observation-v1` receipt under
  `source-native-run-<originRunId>.json`. It contains capture endpoints, source
  pins, hash output, source/runtime pins and the original observation time.
- Refuse unknown read failures. A normal invocation may create only after an
  actual 404. No retry is configured for connector operations. An uncertain
  create stops the path; it is not converted into completion.
- Read back exact UTF-8 bytes, native ID, ETag, version, length and path; recheck
  the source context, then repeat metadata/content/metadata receipt readback.
  Compare the earlier and final receipt pins and bytes before reporting the
  final native pin. An edit, deletion or replacement during the source checks
  must stop completion. Missing IDs, empty ETags and wildcard ETags also hold;
  equality between incomplete metadata snapshots is insufficient. An existing receipt must stay
  at version 1.0 and retain its prior pins. Human-edited or different bytes hold.

Each new invocation normally retains its own observation. The selected capture
and original are reused, so a new observation is not another source edition or
capture. Native receipt history, source edition and capture time remain distinct.

## Explicit resume

The optional manual `resumeRunId` selects an existing observation from an earlier
run in the same assigned namespace. Characters and length are bounded before
constructing a path. The flow verifies current source/hash context, reconstructs
the expected receipt using the original recorded time and requires exact saved
bytes and stable native pins. Resume never creates a missing earlier receipt.
If the target is absent, edited or the source context changed, preserve evidence
and reconcile before choosing a new invocation.

`resumeRunIdDefault` is an explicit private binding for bounded qualification of
that same branch when a manual input cannot be supplied. Normal operation uses
an empty default. Any qualification override requires its own saved-definition
readback and restoration; it is not a hidden runtime fallback.

The native receipt is an atomic observation file. It is separate from the
[existing three-member association commit](acquisition-association-persistence.md).
The result explicitly keeps `associationCommitVerified`, checkpoint advancement,
full acquisition qualification and clinical applicability false. Persisting an
observation never promotes catalogue identity, changes human state or proves
publication currency, final-URL/redirect observation or whole-track recovery.

## Current evidence and next native operation

Twelve focused offline tests passed on actual repo-local Python 3.15.1. They exercise
emitted guard predicates against changed records/script pins, failed reads,
missing resume targets, UTF-8 byte lengths/padding, altered saved pins, unsafe
bindings, late receipt edits/replacements during source checks and unexpected
actions. They do not authenticate or mutate native data.

```sh
.venv/bin/python -m unittest -q tests.test_cloud_observation
```

The selected candidate has 98 actions, seven action nesting levels and a longest
expression of 6,779 characters. Native save exposed a provider rule missed by the
pre-validator: Request trigger schemas reject `pattern`/`patternProperties` when
schema validation applies. The trigger retains its string type and length bound;
`Require_safe_resume` checks every character and the length before constructing
an observation path. Focused emitted-predicate checks reject traversal, quoting,
spaces, non-ASCII characters, encoded separators and overlong input. No runtime
path guard or connector boundary was relaxed.

## Selected native qualification — 25 October 2026

Same-client renewal completed and fresh native preflight verified the selected
catalogue records, original, capture claim, staging file and script. Existing
library rules/subscriptions/receivers and current-user alerts were inspected; an
accessible Default-environment inventory found no relevant active file trigger.
That inventory has the scope of the accessible environment, not tenant-wide proof.

- The corrected graph saved to the same owned flow and passed exact native
  definition/reference/creator readback with actual owner failure alerts Off.
- One CLI invocation succeeded, skipped the original upload and created one
  3,087-byte observation at native version 1.0. Seventeen downloaded action
  artifacts passed native size/hash checks. Independent receipt readback matched
  exact expected bytes, native pins and the hash computed from the retained source.
- The existing operator invoked an explicit resume through the web Run form.
  It succeeded with no receipt/capture creation or catalogue-row change. Sixteen
  action artifacts verified the original observation time, origin run and exact
  saved bytes. All six receipt files retained their native IDs, ETags and versions.
- A deliberately missing resume target stopped at the intended hold with an
  actual 404. Creation and result-reporting actions were skipped. Four action
  artifacts and independent folder readback proved the held result and unchanged
  receipt set. The expected held run is preserved alongside successful runs.
- With all runs terminal, the flow was stopped. Its earlier integrated definition
  was restored and independently read back, then the qualified observation graph
  was reapplied and read back. Definition recovery used the same native object
  and preserved its identity, creator, prior runs and failure-alert setting,
  matching each version's exact connection references.

A further guarded CLI resubmit of the qualified web-resume input succeeded through
the restored graph. The flow was stopped again, with all seven runs retained and
actual owner failure alerts Off. This exercises same-object definition recovery
and runtime resumption; it is not an isolated-target deployment or full recovery
of the catalogue.

The three selected catalogue records, original source bytes/pins, capture claim,
script, workbook and staging file were rechecked without changes. Native
observation persistence is separate from the CLI association-commit protocol:
`associationCommitVerified` and checkpoint advancement remain false. Final-URL and
redirect observability, changed-source/interrupted-create scenarios, isolated
target restoration and wider catalogue/clinical acceptance remain unqualified.
These selected native checks do not close the full sourcing track.

Before later invocation, verify the exact current definition, account, source
pins, destination effects, connections and actual owner-alert setting. Preserve
failed attempts, raw artifacts, source/file versions and restore preimages
privately. Do not enable schedules, sends, permissions, connections or billing as
a qualification shortcut. Keep the graph stopped at a terminal handover.

Connector operations and binary content parameters: [SharePoint connector reference](https://learn.microsoft.com/en-us/connectors/sharepointonline/).

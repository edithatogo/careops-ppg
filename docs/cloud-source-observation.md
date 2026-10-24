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
  must stop completion. An existing receipt must stay
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

Eleven focused offline tests passed on actual repo-local Python 3.15.1. They exercise
emitted guard predicates against changed records/script pins, failed reads,
missing resume targets, UTF-8 byte lengths/padding, altered saved pins, unsafe
bindings, late receipt edits/replacements during source checks and unexpected
actions. They do not authenticate or mutate native data.

```sh
.venv/bin/python -m unittest -q tests.test_cloud_observation
```

The selected private candidate has 98 actions, seven action nesting levels and a
longest expression of 6,779 characters. It was prepared from retained qualification
checkpoints. A fresh native preflight stopped at an expired resource token before
any new native write. Supported renewal reached a user credential step. The new
cloud definition has not been saved or executed and its native recovery remains
unqualified. The earlier integrated transport/hash and CLI association receipts
retain their original qualified scopes.

After authentication completes, first repeat the exact client/account/site read,
then reconcile the selected records, original, claim, engine and library effects.
Preserve the current stopped flow's definition, references, creator and run history.
Save once through the existing guarded route and inspect native readback before
bounded initial/replay/resume qualification. Actual owner failure alerts must be
Off; inspect direct and indirect effects before invoking. Retain failed attempts,
raw run artifacts, file versions and the restore preimage privately. Do not enable
scheduling, sends, new permissions, connections or billing to qualify this path.

Connector operations and binary content parameters: [SharePoint connector reference](https://learn.microsoft.com/en-us/connectors/sharepointonline/).

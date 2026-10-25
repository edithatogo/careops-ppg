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

## Focused offline verification

The source tests evaluate emitted guards for changed record/script pins, failed
reads, missing resume targets, UTF-8 byte lengths/padding, altered saved pins,
late receipt edits/replacements, unsafe bindings and unexpected actions. They
perform no authentication or native mutation.

```sh
.venv/bin/python -m unittest -q tests.test_cloud_observation
```

## Native trigger compatibility

Request trigger schemas reject `pattern`/`patternProperties` when native schema
validation applies. Keep the resume input's string type and length bound, and
check every character and the length in `Require_safe_resume` before constructing
an observation path. Emitted-predicate tests reject traversal, quotes, spaces,
non-ASCII characters, encoded separators and overlong inputs. Do not remove the
runtime guard to make a definition save.

## Native qualification and recovery

Keep target bindings, dates, run outcomes, downloaded originals, screenshots,
service-state records and detailed preservation receipts outside portable Git.
A source test or pre-validator pass does not prove that a provider accepts a save
or that a native run produced the intended result.

1. Refresh exact account/client/target reads, selected records and original,
   claim, staging, script and workbook pins/bytes. Inspect destination effects,
   connections and actual owner failure alerts before invoking anything.
2. Preserve the stopped definition, creator, references and run history. Save
   once through the existing guarded route; inspect exact native readback before
   activation. After an uncertain outcome, reconcile native state before retrying.
3. Qualify a selected normal invocation with independent receipt bytes, native
   identity/version and supplied-source hash checks. Distinguish an expected
   handled 404 for a new receipt from an unknown read failure.
4. Use the existing web Run form to resume that exact observation. Require zero
   receipt/capture creation, unchanged prior files and preserved observation time.
   Exercise a missing target: it must hold before any create or result report.
5. With all runs terminal, stop the flow. Restore a retained definition, inspect
   native readback, reapply the qualified graph and exercise bounded resumption
   through it. Recheck files, records, references, creator, history and actual
   alert settings. Finish in the intended stopped state.
6. Export only non-secret recovery projections, source/config pins and selected
   retained evidence to a private package. Verify member hashes and clean-directory
   reconstruction, including changed/missing-member refusal. An offline verifier
   makes no native calls. Same-object restoration does not qualify an isolated
   target deployment or a complete catalogue restore.

Retain every failed attempt and prior source edition. Keep observation persistence,
association-commit verification, checkpoint advancement, final-URL/redirect evidence,
source currency and clinical applicability as separate assertions. Do not close
broader acquisition, changed-source/interrupted-create or consumer requirements
from a selected successful run. Never enable schedules, sends, permissions,
connections or billing as a qualification shortcut.

Connector operations and binary content parameters: [SharePoint connector reference](https://learn.microsoft.com/en-us/connectors/sharepointonline/).

# PPG catalogue and selected-case commissioning

Cross-tenant recovery was removed from commissioned scope on 31 October 2026.
Clean installation and isolated recovery in the existing tenant remain supported.
Power BI remains a roadmap item. Historical recovery evidence is retained.

## Catalogue baseline

Use the last accepted checkpoint, its exact candidate and the native catalogue
readback. `ppg_catalogue_baseline` verifies unique persistent UUIDs, ledger coverage,
source-owned field equality and complete accounting of active and retained-absent
identities. It does not invent aliases, renew absence acknowledgements or assert
that an old baseline is current. Human fields and existing records are preserved.

```sh
.venv/bin/python -m scripts.ppg_catalogue_baseline \
  --rows .local/catalogue.json --checkpoint .local/checkpoint.json \
  --candidate .local/candidate.json --output .local/baseline-plan.json
node scripts/ppg_catalogue_baseline.mjs .local/adapter.mjs \
  .local/baseline-plan.json .local/destination.json .local/baseline-receipt.json
```

The destination JSON supplies the existing isolated catalogue's `id` and `title`.
Reuse the qualified adapter's `connect`, `get`, `all` and journalled `send` methods.
The loader uses batches of at most 20, spaces batches by ten seconds, checks every
operation response and compares all selected rows after loading. It creates absent
identities only. Conflicting existing rows stop rather than overwriting human work.
An uncertain batch stops: respect Retry-After, read/reconcile persisted rows, and
use an explicit new journal attempt before resuming only the missing identities.
No write is retried automatically and no incomplete load is marked complete.

The selected installation baseline retains the original accepted date and missing
source identities. A stale source-absence acknowledgement remains a current-source
hold, even after the historical baseline is installed. The original collector,
source workbook and source catalogue are not changed by commissioning.

## Selected case and document inputs

Use an existing explicitly fictional case whose catalogue UUIDs and baseline
match. Freeze the current baseline, draft and file versions, the maintained
review template and its hash, and the case/catalogue selection. Record the output
revision and retained provenance in an explicit job, then run the existing CLI:

```sh
node tools/unattended-package/run.cjs .local/job.json .local/inputs .local/output
node tools/unattended-package/publish-sharepoint.mjs .local/destination.json \
  .local/output/JOB_ID .local/new-publish-journal.jsonl
```

This produces a usable package containing the selected existing draft and exact
source/template inputs. It does not claim new Word authoring, clinical review,
role acceptance or approval. Missing business evidence remains visible in the
package's completeness report. The selected case can be copied create-only to the
isolated review queue while retaining its logical identity and original baseline.
Source records and earlier drafts are never repinned or overwritten.

## External dependencies: exact remaining inputs

| Source | Remaining dependency | Existing behavior |
|---|---|---|
| METEOR | Human-created account; approved API registration and subscription; privately stored key/secret; authenticated HMAC specification; permitted execution/connector route | Disabled preparation; public metadata fallback retained |
| Ahpra PIE | Approved organisation, application and commercial agreement; issued test credentials, interface details and permitted connector route | No enabled collector; public register is reference-only |
| AusUDID | Stable supported automated release/download manifest, incremental semantics and a permitted flow route | Full/periodic downloads documented; no qualified unattended importer |
| Unqualified newsletters | Genuine original issue, exact sender/subject and existing delivery; specific National Boards where applicable | Existing qualified channels continue; no subscriptions or historical mail moves |
| Unresolved internal sources | Accessible exact structured list/library and stable change/identity fields | Qualified patient-safety register remains usable; inaccessible candidates remain unresolved |

Checked against publisher documentation on 31 October 2026:
[METEOR API guide](https://meteor.aihw.gov.au/content/811642),
[METEOR access page](https://meteor.aihw.gov.au/MyApiSubscriptions),
[Ahpra exchange](https://www.ahpra.gov.au/Registration/Employer-Services/External-data-exchange-services),
[TGA healthcare model](https://www.tga.gov.au/sites/default/files/2026-08/ausudid-conceptual-model-for-healthcare.pdf)
and [AusUDID downloads](https://ausudid.tga.gov.au/downloads).
Public documentation does not establish this tenant's credentials or connector
entitlement. These dependencies are blocked, not completed or silently deferred.

For the user's METEOR application, a prepared purpose statement is: “Use METEOR
metadata and selected indicator definitions in PPG, a reusable policy, procedure
and guideline workbench, preserving identifiers, versions and provenance for
human review. No patient data will be submitted.” The person submitting supplies
their actual organisation, checks the terms and completes the registration; no
account, subscription, credential or outbound message is created by this package.

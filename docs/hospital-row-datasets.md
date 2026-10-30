# Hospital current-row datasets

The three destination contracts are in `config/hospital-datasets.json`.
Facilities and current metrics use the exact text FacilityCode; trends use
FacilityCode, DayOfWeekNo and TimeBandNumber. Preserve leading zeros and the
publisher's text-valued metrics and timestamp strings. Do not infer timezones,
units, missing values or clinical meaning.

Create versioned generic SharePoint lists with indexed FacilityCode and, for
trends, DayOfWeekNo. Add a unique indexed Text SourceKey, Boolean SourcePresent,
Note CapturePath and SourceLink, DateTime ObservedAt, Text Attribution and Note
Notes. Map `_id` to SourceRecordId; it is not the logical key. Title is the
facility name where available, otherwise the source key. Long alert messages
use plain multiline text. Tenant IDs and captures stay private.

`ppg_dataset_rows.reconcile` prepares source-owned changes in groups of twenty.
It requires complete source and destination reads; incomplete responses and
duplicate/missing keys fail before returning mutations. Native adapters must
read and reconcile uncertain effects before resuming, inspect each batch child
status, use conditional updates, and preserve Notes and other human fields.
Missing records are marked absent, not deleted. Unchanged rows keep their prior
capture reference. SharePoint ObservedAt readback has whole-second precision;
retain the original full timestamp in the immutable capture index/payload.

`ppg_dataset_refresh.extend(flow, binding, contracts)` adds current-row refresh
to the existing capture collector. Supply the capture `listId`, exact `site`,
`rowLists` keyed by contract key, and publisher `attribution` privately. Each
dataset captures first, pages existing rows, validates source keys and totals,
then serially submits batches of twenty conditional updates or creates. Batch
updates use the MERGE verb and each decoded multipart child status is checked.
Only successful synchronisation advances the capture state to Synchronised.
Failed datasets remain visible while independent datasets continue. Reconcile
uncertain effects before another run; batches are not atomic.

Use `ppg_source_environment.parameterise` for literal bindings, including quoted
WDL expression literals, then package the definitions with the existing solution
connection references and environment variables. Preserve existing flow IDs.
Keep native exports, deployment hashes, bindings and run receipts private.
Qualify a manual run and destination readback before restoring the daily 07:00
Brisbane trigger; newsletter collectors retain their normal arrival trigger.
These source tools do not establish another tenant's runtime acceptance or
resolve publisher/access blockers. Cross-tenant recovery remains deferred.

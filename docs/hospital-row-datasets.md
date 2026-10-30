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

Initial population uses the retained successful native API captures. This does
not yet establish recurring row synchronisation: the existing enabled daily
collector still captures JSON and writes the capture index. Wiring its output
to these row datasets and adopting the two newest collectors into the existing
solution remain unfinished. No newsletter, API-access or cross-tenant blocker is
resolved by creating these lists. Cross-tenant recovery remains deferred.

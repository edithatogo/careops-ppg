# Install the PPG source-collection module

The installer builds one versioned solution containing the selected RSS, newsletter,
internal-list and hospital collectors, plus a companion contract for all five
SharePoint destinations. It reuses the existing collector builders. It does not
install the rest of the PPG workbench, migrate existing flows, restore records,
create tenants, authenticate new clients or activate collectors.

SharePoint lists are external solution dependencies, not Dataverse solution
components. Their versioned schemas and provisioning command ship with this module;
solution environment variables bind their actual IDs. The internal source register
is an external input, never a destination created or copied by this installer.

## CLI installation

1. Use the repository's qualified Python 3.15.1 interpreter and the existing
   destination-specific CLI/PAC authentication. Keep bindings under `.local`.
   Copy `config/source-installation.example.json` there and replace fictional
   values. The example covers nine public RSS profiles, three fictional newsletter
   profiles, an internal list and one collector for all three hospital datasets.
   Remove unqualified sources rather than enabling a guessed binding.
2. Emit the destination schemas and provision missing objects through the existing
   qualified SharePoint adapter. The default command is read-only verification;
   `--apply` creates only missing lists, fields and named views. Existing incompatible schemas
   stop the affected installation; records, annotations and permissions are retained.

   ```sh
   .venv/bin/python scripts/ppg_source_installation.py --schemas > .local/source-schemas.json
   node scripts/ppg_source_provision.mjs \
     --adapter .local/qualified-sharepoint-adapter.mjs \
     --schemas .local/source-schemas.json \
     --receipt .local/source-provisioned.json --apply
   ```

   The adapter exports `connect()` returning `all(route)`, `get(route)`, `send(operation)` and
   `authorizeSchema(scope)`. Reuse the existing workload's authenticated adapter;
   do not copy credentials or start a second authentication owner. `all` must read
   all pages within its pinned site. `send` must retain an exclusive one-send
   journal keyed by `key`, validate `payloadSHA256`, and never blindly retry.
   `authorizeSchema` checks the exact site/list's receivers, subscriptions and rules
   before writes (including `create-view`); unknown notification effects must stop. This adapter is
   destination-specific private configuration, not supplied authentication.
   A failed/uncertain send stops immediately. Reinvoke only after readback reconciles
   it: existing matching lists/fields are reused and are not sent again.
   For isolated qualification, add `--list-suffix "Clean install example"` when
   emitting schemas and set the same `listSuffix` in private installation settings.
   Use a distinct solution name and publisher prefix so existing objects are untouched.

3. Insert the returned list IDs into the private settings `bindings.lists`, and
   supply the qualified connection names. Keep a stable `solutionName` and
   `publisherPrefix` for upgrades: component IDs derive from solution and collector
   keys. Do not import this clean-install solution over existing direct-created
   collectors; adopt those original identities into their existing solution instead.

   ```sh
   .venv/bin/python scripts/ppg_source_installation.py \
     --settings .local/source-installation.json --output .local/source-solution
   pac solution pack --folder .local/source-solution \
     --zipfile .local/source-solution.zip --packagetype Unmanaged
   pac solution import --path .local/source-solution.zip \
     --settings-file .local/source-solution-deployment-settings.json
   ```

4. Read back actual solution membership, connection references, environment values,
   stopped states and owner failure-alert settings. A package flag alone does not
   establish native alert suppression. Qualify each selected source with one manual
   triggered run and exact dataset readback, then enable its daily/arrival trigger.
   No natural-run wait is required. Do not run two collectors for the same source
   namespace against the same dataset. Preserve the Commission legacy namespace.

Newsletter installation requires genuine sender/subject qualification, an existing
folder, publisher-link hosts and separately established narrow incoming routing.
The installer does not enrol subscriptions, send messages, move historical mail or
install routing rules. Source API endpoints and attribution are explicit settings.
OneDrive capture storage is through the selected destination account, using the
existing immutable per-run file naming. Preserve its captures with recovery data.

## Versioning and boundaries

Installer release **1.1.0.0** emits deterministic component IDs, definition versions,
list schema versions, deployment settings and a SHA-256 file manifest. Commit
reusable code/configuration; retain generated bindings, ZIPs and receipts privately.
Record the Git commit alongside each private deployment manifest. All flows start
stopped, with no send/notification actions. Lists are versioned; current hospital
rows preserve source keys, original timestamp text, nulls, annotations and capture
links. Trends use indexed facility/day fields and a unique SourceKey. Named paged views expose source columns; trends use a bounded day filter.

Keep the three hospital APIs together: they share schedule and capture handling,
while each dataset has an independent failure scope. Split only if ownership,
permissions or refresh cadence actually diverge. Three collectors now would add
administrative overhead without improving the current behavior.

Clean installation creates empty destinations. Clean recovery restores a selected
sealed package into isolated objects. Cross-tenant recovery adds destination
mapping and permissions qualification; it can coexist with both modes and remains
**deferred**. Another available account is not a designated restore destination.
Never transfer credentials or automatically copy source permissions.

METEOR, unqualified newsletters, unavailable internal inputs and API agreement or
release-interface dependencies remain blocked. These are not installed working
sources. Broader PPG modules retain their existing release/recovery routes; this
module is not a claim that the entire product is a one-command clean installation.

## Verification recorded for this release

Focused tests cover deterministic stopped packages, binding replacement, schema
preservation, duplicate keys, create/replay and reconciliation after uncertain
writes. On 30 October 2026, a fresh isolated installation in the existing tenant
created five lists, 72 fields and five paged views. Provisioning replay created
zero lists, fields or views. Native solution export verified version 1.1.0.0,
14 workflows and 11 environment-variable definitions.

All 14 qualification collectors passed one triggered run. Exact readback found
427 proposed source leads, three synchronised capture records and two fictional
rows in each hospital dataset. Source fields, nulls, leading-zero keys and capture
references matched the fixtures. Newsletter proof used three existing genuine
messages; it did not test a new arrival or send mail. Hospital qualification used
immutable fictional responses rather than copying the production dataset again.

Qualification copies retain their normal recurrence/arrival definitions and are
stopped to avoid duplicate collection. The 14 qualified production collectors
remain enabled; two blocked preparations remain stopped. These results prove the
source module in isolated objects in the existing tenant, not a whole-product
installation or a cross-tenant restore. See [artefact scope](solution-artifact-scope.md).

# Install the PPG workbench

Release 1.0.0.0 extends the [source module](source-installation.md) with the maintained workbench schemas, libraries, templates and workflows. It installs 51 SharePoint objects, 676 owned fields, 25 lookup relationships, 66 template assets and 18 core workflows alongside the selected source collectors (14 in the qualified profile). SharePoint objects remain external dependencies of the Power Platform solution; they are versioned by the accompanying contract, not represented as Dataverse tables.

## CLI sequence

Use repo-local Python 3.15.1, the qualified Node runtime, PAC and the existing destination-specific authentication adapter. Keep all generated settings, packages and receipts under `.local`. No credentials belong in the package.

1. Provision isolated schemas with `node scripts/ppg_product_provision.mjs --adapter .local/adapter.mjs --contract config/whole-product-installation.json --suffix "Product install example" --receipt .local/product-objects.json --apply`. The adapter contract is described in the source-module guide; it additionally supports schema MERGE operations. Create scalar fields before lookups, preserve title requirements and validation formulas, and install paged views. Existing incompatible objects stop installation; records and permissions are not replaced. Reconcile uncertain sends from native readback before resuming with a new journal attempt.
2. Build the existing `tools/native-document-template` project using the qualified .NET SDK (`dotnet restore --locked-mode`, then `dotnet build --no-restore`). Run `.venv/bin/python scripts/ppg_product_assets.py --output .local/product-assets --dotnet /path/to/qualified/dotnet`. Upload with `node scripts/ppg_product_assets.mjs --adapter .local/adapter.mjs --folder /sites/example/TemplateLibrary --assets .local/product-assets --receipt .local/product-assets-receipt.json`. The private adapter must authorize the exact library through `authorizeFiles(folder)`. Uploads are create-only; differing existing content stops. Word readback permits only SharePoint property stamping while preserving original document parts and controls.
3. Prepare private settings with `solutionName`, `publisherPrefix`, `site`, `objects` from the provisioning receipt, `sources` using `config/source-installation.example.json`, and `connections` keyed by connector API name. The core workflows use SharePoint, OneDrive for Business and Excel Online Business connections. Supply `runtimeBindings` for every non-derived token in `config/product-workflows.json`. The manifest records each token's exact workflow and JSON location. List IDs/paths, site and working-library paths are derived from the new objects. Source register/workbook URLs, script IDs, source hashes, operator request pins and destination-specific identities require explicit destination values. They are not copied from another installation.
4. Build and import:

   ```sh
   .venv/bin/python scripts/ppg_product_installation.py --settings .local/product-settings.json --output .local/product-solution
   pac solution pack --folder .local/product-solution --zipfile .local/product-solution.zip --packagetype Unmanaged
   pac solution import --path .local/product-solution.zip --settings-file .local/product-solution-deployment-settings.json
   ```

   Keep the solution name/prefix stable for upgrades; component IDs are deterministic. All flows import stopped. Record the source commit, package hash, import result and actual solution export privately. A PAC wait timeout is not proof of failed import: inspect the exact server import job before sending again.
5. Read back schemas, connections, definition bindings, solution membership, stopped states and owner failure-alert settings. Use one fictional isolated reporting run and inspect actual output. Activate only workflows whose destination inputs have been qualified; never activate two collectors against the same source namespace/dataset. Do not wait for natural scheduling as an additional release gate.

## Qualification and remaining setup

The isolated installation completed on 30 October 2026 with 51 objects and 66 assets. The monthly report produced and read back its CSVs and summary against one fictional overdue record. This exposed and fixed null readback for an empty retained-record CSV. Existing source-module runtime evidence is reused for unchanged collectors.

Installation is not operational acceptance of all business workflows. The lifecycle templates retain their explicit request/record/hash guards. Destination source baselines, Office Script hosts, institutional workbook references, role identities and operator requests must be supplied and qualified before those workflows run. No real records, permissions, subscriptions or credentials are migrated. Existing production collectors retain their identities and settings.

METEOR access/signing and permitted connector route, Ahpra exchange agreement/interface, AusUDID automated release semantics, missing genuine newsletter samples and inaccessible structured internal sources remain external blockers. Blocked preparations are excluded from the active collector package. Cross-tenant recovery is removed from commissioned scope (31 October 2026); clean same-tenant installation/recovery remains supported. A Power BI dashboard remains on the roadmap; this release includes the existing CSV/reporting flows, not a dashboard.


## Office Script and source bindings (1.0.1)

Build the seven maintained Office Script packages and six detached hosts with
`.venv/bin/python scripts/ppg_office_runtime.py --output .local/office-runtime`.
For a real catalogue source, pass its explicit `--source-system` identity; the
fictional default is not a tenant identity. The catalogue script reads a newly
acquired source copy, not a blank workbook. The other six profiles do not read or
write workbook cells. Preserve the original script revisions and hosts.

`config/product-office-scripts.json` identifies each script's source, parameter
schema, hash and action names. Install `.osts` and `.xlsx` assets create-only in
the qualified destination library; resolve its drive and exact item IDs through
SharePoint's supported v2 drive read. The executable command is
`node scripts/ppg_office_provision.mjs --adapter .local/adapter.mjs --site https://example.sharepoint.com/sites/ppg --folder /sites/ppg/Runtime --assets .local/office-runtime --catalogue-drive EXPLICIT_COPY_DRIVE --receipt .local/office-bindings.json`.
It verifies exact script bytes and an empty Runtime sheet in scratch workbooks,
allowing only service metadata/formatting parts. Added cells, formulas, external
relationships or extra sheets stop installation; files are never overwritten. Keep these IDs in private settings under
`officeScripts`, keyed by profile. Each profile supplies `source`, `drive`, `file`,
`scriptSource`, `scriptDrive`, `scriptId`; catalogue may retain its dynamic copy
filename, but its workbook drive must be the copy's destination drive. The package
builder binds nested actions without replacing inputs or connection references.
Site-relative library paths are rebound too, including connector folder paths and
provenance links; already isolated paths remain unchanged.

The existing-tenant qualification installed all seven scripts and six new hosts.
Role projection, standards context and digest preview completed with fictional
inputs. The standards source now includes the maintained relationship/dependency
behavior. Existing institutional source metadata was read successfully. Native
script/content hashes and bindings remain private.

New Button flows require a first-run Logic Flows connection separate from solution
connection references. The current CLI runner returned connection-not-found; the
native Run form established it and submitted each fictional request. Subsequent
results, definition edits and exports use CLI. A management trigger invocation
without the required payload is not a successful run.

Document generation remains guarded by a selected document/case request and its
version-bound package/template evidence. Catalogue reconciliation still needs the
new installation's reviewed identity ledger and matching catalogue baseline; the
installation's one fictional report row is not that baseline. Neither imports
real records or accepts publisher assertions merely because source access works.
These are explicit commissioning inputs, separate from external API/access blockers.

See [catalogue and selected-case commissioning](product-commissioning.md) for the usable CLI routes and exact external dependencies.

## Native document and identity commissioning (1.0.3)

Private `documentGeneration` settings may select the maintained saved-body builder
for the existing document flow. Supply its qualified engine pins, script-library
binding, isolated workbook host and explicit request item. Set
`savedBodyFinalisation: true`; site, output library, review queue and catalogue
must belong to this installation. Script storage and workbook storage can be
separate drives: preserve both bindings. This uses the existing standard
SharePoint/Excel route and adds no connector or generation framework.

Compile the **actual saved maintained template bytes** with
`ppg_full_document.compile_template` before creating a new request. SharePoint can
stamp metadata after an earlier compilation. Compare document parts and controls;
never replace a mismatched hash without explaining the difference. Keep the old
compiled asset and request, create a new version and use a `saved-` revision. The
native flow retains input pins, preserves edits and packages the exact saved Word
body. Confirm the saved DOCX, package member and receipt hashes; a submitted run
or a populated request is not generation proof.

`identityApplicationFile` selects a separately retained, source-bound application
compiled with `ppg_identity_application.py`. Preserve the prior application and
checkpoint. Unknown aliases require explicit evidenced decisions; missing rows
require exact-snapshot retain-unchanged acknowledgements. These do not constitute
policy approval or retirement. Accepted/uploaded, applied and checkpoint-verified
remain separate states.

An installation may retain its original fictional reporting row alongside a
commissioned catalogue. `catalogueFixtureDocumentUIDs` excludes only explicitly
verified fixture UUIDs from the reconciliation's before/after reads. Inspect each
row before configuring it; never use this setting to hide an unresolved source
identity. All other unexpected identities still fail the existing guards. The
fixture remains intact and visible for its reporting purpose.

## Production commissioning and bounded catalogue updates (1.0.4)

An isolated installation proves the installation route; it does not promote its
bindings, checkpoint or activation state into the existing operational solution.
For production, export the existing solution, preserve workflow identities and
connection references, and update only the selected definitions. Retain previous
requests and outputs; create a new version-bound request using the actual saved
template bytes. Prove the document and packaged Word member match before closeout.

The catalogue builder batches existing-identity source updates in groups of 20,
with conditional ETags, concurrency one and a ten-second inter-batch delay. It
persists the pending operation record before sending, disables mutation retries,
and checks every embedded response. A partial/uncertain batch stops later batches
and leaves the successful checkpoint unchanged. Reconcile actual records before
resuming; batches are not atomic. The full source-field, retained-absence and
source-pin readback still precedes the completion receipt and checkpoint. New
identities retain the existing explicitly authorised serial creation path.

An absence acknowledgement applies only to its reviewed source snapshot and base
identity ledger. Verify both against production before selecting the application;
never promote an isolated checkpoint as if production rows had been refreshed.
A successful CLI recovery is separate from a successful flow-owned refresh.

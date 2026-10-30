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

METEOR access/signing and permitted connector route, Ahpra exchange agreement/interface, AusUDID automated release semantics, missing genuine newsletter samples and inaccessible structured internal sources remain external blockers. Blocked preparations are excluded from the active collector package. Cross-tenant recovery remains deferred. A Power BI dashboard remains on the roadmap; this release includes the existing CSV/reporting flows, not a dashboard.

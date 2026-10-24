# External publication catalogue — implementation and operation

The external catalogue extends the existing SharePoint workbench. It keeps
publication, edition, capture, collection, reference and resolution records
separate, while reusing existing framework keys and the evidence library.
Detailed source selections, native bindings, manifests and receipts remain private.
Catalogue ingestion never accepts clinical applicability or changes local PPGs.

## Maintained libraries and runtime

HTML inspection uses Beautiful Soup 4.15.0. Structure and format validation use
JSON Schema 4.26.0 with its non-GPL format dependencies. These candidates were
resolved with prereleases allowed and actually exercised on Python 3.15.1.
`requirements-external-catalogue.lock` pins and hashes the complete dependency
closure. An import alone is insufficient: validation requires the date-time and
URI checkers, and a negative test proves malformed timestamps are refused.

Create a new repo-local qualification profile using the already qualified Python;
never replace another operation's environment. For example, from the project root:

```sh
uv venv --python .venv/bin/python .local/external-catalogue-profile
uv pip sync --python .local/external-catalogue-profile/bin/python --require-hashes requirements-external-catalogue.lock
.local/external-catalogue-profile/bin/python -VV
.local/external-catalogue-profile/bin/python -c 'import sys; from jsonschema import FormatChecker; assert sys.version_info[:3] == (3,15,1); assert sys.version_info.releaselevel == "final"; assert {"date-time", "uri"} <= FormatChecker.checkers.keys()'
```

Use that explicitly selected interpreter for `scripts/ppg_external_catalogue.py`.
The base stdlib environment remains supported for unrelated tools. Its optional
catalogue tests report a capability skip if these libraries/formats are absent;
the dedicated CI job installs and verifies the required profile before testing.

## Private handoff contract

`config/external-publication.schema.json` defines the envelope. Each record has a
stable key, kind, title, issuer, optional publication/edition endpoints, existing
framework keys, publisher-status assertion, source role, capture requirement,
field provenance and kind-specific data. Unknown and conflicting source states
remain distinct. Publication-only matches do not acquire a latest edition.

The Python validator adds the business invariants that a schema cannot supply:
unique identities, known endpoints/frameworks, collection-denominator parity,
source URL boundaries, original-byte hashes and refusal of clinical acceptance.
Capture records with an unverified edition must explicitly say so. They do not
establish complete exact-edition coverage. Link occurrences do not mint publication
identity. Unlinked textual entries, such as a publisher's rescinded list, need
separate accounting; a links-only scrape is not a complete collection inventory.

The current source-specific adapter accepts Commission publisher URLs. Onboarding
another issuer or local PPG citation provenance requires its explicit trusted
source contract and fixtures; do not broaden the allowlist opportunistically.
Reference/Resolution records are supported structurally, but a zero-row reference
view means no references are recorded, not that local PPGs contain none.

## Preparation and native operations

Python commands are `inventory`, `validate`, `payloads`, `compare`, `snapshot` and
`reconstruct`. All output paths must be new. Use `--help` for arguments. `compare`
creates review leads; a missing observation or failed retrieval never withdraws a
publication or promotes a baseline automatically.

`tools/external-catalogue/native.mjs` uses the installed M365 CLI SDK and existing
saved account. A private config supplies the site, SDK path, connection name,
expected username/tenant/application/object identity and exact list binding.
No new authentication client or permission is introduced. It accepts:

```text
node tools/external-catalogue/native.mjs MODE PRIVATE_CONFIG INPUT NEW_OUTPUT NEW_JOURNAL
```

| Mode | Effect |
|---|---|
| `bootstrap` | Provision/read back only the named external catalogue or its isolated recovery List; verify versioning and the unique indexed record key |
| `plan` | Read the complete native population and produce the difference; changes to existing managed records refuse the plan |
| `persist` | Recompute the difference, create serially, read back by indexed key and journal each verified item |
| `export` | Export all current rows through complete pagination |
| `views` | Create or verify the five owned views, including queries, fields, paging and row limits |
| `configure` | Verify source/evidence/navigation link formatters and the related-record default view; preserve unknown human presentation changes |

Prepare a full dry run first. Persistence repeats the read to detect intervening
changes. Record JSON and its hash bind the prepared business content. Existing
rows are preserved; this initial implementation refuses corrections rather than
silently applying them. Metadata-change promotion and conditional human correction
remain later required work, not an implied capability of create-only replay.

The direct SDK request instance bypasses the CLI's generic mutation-retry wrapper;
redirects are disabled and requests are bounded. An intent without a verified
result is uncertain. Read current native state before deciding how to resume;
never use a test runner to retry a mutation. MSAL/keychain persistence errors are
client/cache failures, not proof of permission denial. Preserve shared credentials,
serialise new client initialisation and retain the failing receipt.

Original file publication/retrieval reuses the existing
`tools/unattended-package/sharepoint-client.mjs`: server-side create-only writes
and stable metadata/content/metadata reads. Qualified existing files are reused;
different bytes at the same managed name stop the operation. No Office conversion
or replacement of older source editions is involved.

## Web operator route

Open **PPG External Publications**, then choose **Publication catalogue**,
**Exact editions**, **Retained source captures**, **Reference occurrences**, or
**Source inventory and gaps**. Use the native search, filter, group and sort
controls. **Official source** opens the publisher evidence. **Related records**
opens the linked publication's editions and captures; **Retained original** opens
that row's saved file. A publication without a direct file uses **Related evidence**.
Unknown publisher status and Proposed review state do not mean approved/current.

The initial catalogue does not yet expose every requested topic/jurisdiction/
profession/acquisition filter or integrate local PPG reverse navigation. Those
remain explicit EC work. Source inventory gaps remain open rather than vanishing
from denominators. Access proof is limited to the actual tested operator account;
other-principal acceptance is not inferred.

## Export and recovery

1. Export current native rows and all available item versions into private storage.
2. Download each selected original, verifying its hash and stable native identity.
3. Run `snapshot` with the manifest, native rows, downloaded originals and known
   framework keys. Include native history as provenance in the recovery package.
4. Save/download the package through the existing create-only library route and
   verify its actual bytes. Validate the entire ZIP membership and sizes before
   reconstructing; do not extract arbitrary archive members.
5. `reconstruct` verifies the export and bytes before optional explicit rebinding.
   Recover into the separate recovery List and a new file namespace. Original
   native links remain recorded as provenance; source/edition assertions and
   business keys remain unchanged. New native item IDs/times are not fabricated
   historical versions.
6. Read back every reconstructed record/file, compare complete keys/counts/links,
   exercise unchanged replay and inspect representative web navigation. Recheck
   the source population so recovery cannot conceal a source edit.

Same-site isolated reconstruction is not cross-environment migration, retention
policy qualification, recovery of unexported future fields or proof of clinical
acceptance. Keep original history, issued content and human decisions intact.

## Verification and CI

Focused tests use the selected catalogue profile:

```sh
.local/external-catalogue-profile/bin/python -m unittest -q tests.test_external_catalogue
node --test tests/test_external_catalogue.mjs
```

The dedicated workflow pins GitHub Actions by SHA, selects Python 3.15.1 and Node
26.12.1, restores the existing .NET kernel from its lock, installs hash-locked
runtime/CI dependencies, checks formats, runs focused and full Python integration
checks, exercises the exactly-once Node adapter, lints with Ruff, audits workflow
security with Zizmor and audits the complete locked dependency set with pip-audit.
All jobs use read-only repository permission and no native tenant credentials.
There are no automatic test retries or native deployment steps. Workflow presence,
local qualification, successful hosted execution and required-check enforcement
are reported separately.

The complete local Python suite also needs `tools/policy-editions:tests:.` on
`PYTHONPATH`; the acquisition CLI tests intentionally select the primary `.venv`.
For isolated optional libraries, a process-local path to the qualified profile's
site-packages can be supplied without replacing the primary environment. CI
installs the same lock directly into its fresh primary `.venv`.

Sources: [Beautiful Soup](https://pypi.org/project/beautifulsoup4/),
[JSON Schema](https://python-jsonschema.readthedocs.io/en/stable/),
[JSON Schema format validation](https://python-jsonschema.readthedocs.io/en/stable/validate/#validating-formats).

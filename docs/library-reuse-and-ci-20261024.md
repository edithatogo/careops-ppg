# Library reuse and CI review — 24 October 2026

Apply maintained libraries where they remove parsing/validation infrastructure,
while keeping domain identity, provenance, preservation and approval rules in
small reviewed application code. Existing native/file owners retain their work.
This review does not replace an environment under a running operation.

| Area inspected | Decision and remaining qualification |
|---|---|
| HTML parsing in `scripts/ppg_source_discovery.py` and new catalogue work | New catalogue inspection uses Beautiful Soup rather than another custom HTMLParser subclass. The active sourcing owner's existing parser is preserved; migrate it only after output/URL/occurrence parity against retained fixtures. |
| Metadata structure checks | New handoffs use JSON Schema with verified format dependencies. Keep cross-record identity, version and coverage invariants in application code. Do not label schema success as native or clinical acceptance. |
| M365 access | Reuse the installed M365 CLI SDK and existing saved connection, plus the qualified same-client file adapter. Retain exact identity checks and bounded/no-retry mutation transport; do not add another OAuth library/client. |
| Source XML and recovery schema XML | Consider defusedxml for external XML parsing after Python 3.15 and DTD/entity/encoding fixture qualification. Keep current owner code and existing explicit guards until parity is proven; this is a candidate, not a demonstrated vulnerability or completed migration. |
| Hierarchy/cycle validation | Consider stdlib graphlib for the acyclic subproblem only. Keep typed/version-bound graph rules: reciprocal references and operational cycles differ from prohibited governing/supersession cycles. A generic graph package does not replace those rules. |
| DOCX/PDF handling | Reuse the existing Open XML SDK and qualified PDF text tool. Preserve original-byte and package-part controls. The preferred SharePoint document-generation route remains first for future maintained document outputs; a new local generator is unnecessary for this dataset. |
| ZIP/JSON/hash handling | Keep Python/Node standard libraries and bounded domain checks. Replacing straightforward standard-library operations with another dependency would add little value. |
| Command harness | Reuse the guided runner's allowlist/receipt patterns. The catalogue has explicit fixed CLI operations; no new shell-capable generic orchestrator, agent service or retry framework is introduced. |

## Candidate and promotion evidence

The runtime lock selects Beautiful Soup 4.15.0, JSON Schema 4.26.0 and their exact
transitive closure, with prerelease candidates permitted during resolution. Actual
Python 3.15.1 execution, malformed-input tests and downloaded source reconstruction
qualify the selected profile. Optional format checks initially proved absent;
adding the format dependency closure and a negative timestamp test closed that
specific gap. An installed distribution alone would not have detected it.

CI tools are exact-pinned Ruff 0.17.2, pip-audit 2.10.1 and Zizmor 1.32.0rc1. Runtime
and CI dependencies are hash-locked and audited together. No known vulnerabilities
were reported by that dated audit; it is not a permanent vulnerability guarantee.

The installed M365 CLI is a qualified v12 development build. The registry's dated
`latest` tag is 11.11.0 while `next` is 12.0.0-beta.4ac11a7. A tag named latest would
therefore downgrade that major development line. Do not change the shared client
under active native operations; qualify the newer development build in isolation
before promotion, preserving the current route and its receipts.

## CI and context improvements implemented

The dedicated source workflow uses immutable action pins, exact runtimes,
hash-locked installation, the existing locked .NET document-kernel restore,
explicit format-capability checks, focused refusals/recovery tests, full Python
integration, Node transport tests, Ruff, workflow-security analysis and dependency
auditing. Repository permissions are read-only, checkout credentials are not
persisted and no native credentials or operational artefacts enter CI. Cancellation
applies to code checks, never to native operations. No retry plugin is adopted.

A scoped `tools/external-catalogue/AGENTS.md` points to the operation guide and
private manifest/checkpoint. It specifies the required context, fixed tools,
owner boundaries, uncertain-outcome handling and exact verification steps without
loading the historical archive or adding another agent framework.

Source publication uses the approved sanitised source repository. The working
checkout's configured remote is archived; do not unarchive it, change its remote,
push private history or claim hosted CI from local checks. Source-only export,
confidential-content review and existing publication gates still apply.

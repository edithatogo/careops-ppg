# Bounded source discovery observations

`scripts/ppg_source_discovery.py` parses retained RSS 2.0, namespaced sitemap XML
and one explicitly titled HTML publication shape. It performs no network calls,
file writes, catalogue promotion, baseline advancement or notifications. Existing
capture/compare and catalogue/native owners retain their responsibilities.

Callers must first qualify the acquisition response: actual status, final URL,
redirects, representation, capture time and raw-byte hash. A successful parse is
not a transport receipt or proof of native flow access. Pass exact allowed HTTPS
origins and retain the returned source hash with the original capture.

- `parse_rss(raw, source_url, allowed_origins)` retains each occurrence, GUID,
  raw/parsed date and parsed-item fingerprint. Duplicate GUIDs and non-monotonic
  dates remain visible; neither ordering nor an empty feed establishes complete
  history or the absence of changes. The item fingerprint hashes parsed XML
  serialization; the envelope hash separately identifies the exact raw bytes.
- `reconcile_rss(previous_raw, current_raw, source_url, allowed_origins)` compares
  two retained captures of the same feed, with `None` permitted only for the first
  capture's missing predecessor. Groups use feed-scoped GUIDs or, when absent,
  the exact observed locator including any fragment. Reordering and repeated
  identical occurrences do not create another group; every ordinal/occurrence
  remains available. These keys never assign publication or edition identity.
  Changed item fingerprints are candidates even when the publication date is old
  or unchanged. Simultaneous differing variants for a GUID/locator in either
  capture are held as `conflicting-observations`; no variant is selected.
  Disappearing entries are `not-observed-in-current-feed`, never deleted,
  retired or classified as withdrawn. New GUIDs at the same URL remain separate
  discovery observations for the catalogue owner to reconcile. A failed parse
  refuses comparison; an empty feed cannot prove complete history. Parsed XML
  formatting changes may change an item fingerprint and require inspection.
  The result retains both raw-capture hashes and all prior/current occurrences;
  it does not persist a checkpoint or accept a baseline. Use existing capture
  storage and explicitly selected prior receipts rather than a new source ledger.
- `parse_sitemap(raw, source_url, allowed_origins)` retains locator and raw
  last-modification assertions. Those dates do not establish source editions.
- `reconcile_sitemaps(index_raw, child_payloads, index_url, allowed_origins)`
  requires the declared child scope, preserves repeated URL occurrences and their
  parent/hash provenance, and reports missing or malformed children. A complete
  retrieval of declared children still does not prove catalogue completeness.
  This helper never authorises removals or withdrawal decisions.
- `compare_sitemaps(previous_index_raw, previous_children, current_index_raw,
  current_children, index_url, allowed_origins, path_terms)` compares the retained
  inventories within one explicit scope. Supply one to twenty unique lowercase
  literal path terms: matching is case-insensitive against the escaped URL path,
  without decoding aliases or matching query strings. Queries remain part of each
  exact locator. The returned scope records those terms; they select discovery
  candidates and do not establish complete publication coverage.
  First observations, index omissions, raw `lastmod` changes and changes to the
  child-map occurrence sources are separate statuses. Every occurrence is retained.
  Conflicting nonempty `lastmod` assertions remain held, not resolved by choosing
  the latest-looking date. A missing/malformed current child reports an incomplete
  scope instead of a missing URL; incomplete predecessor coverage also prevents a
  confident first-observation conclusion. Even two complete declared inventories
  do not authorise removal, infer an edition date or advance a checkpoint.
- `parse_publication(raw, source_url, allowed_origins, expected_title)` requires
  one complete main region, the expected title and at least one PDF link. It
  excludes navigation/script/template links and refuses observed access/error
  representations, password inputs and off-origin PDF links. Download labels and
  preceding headings remain publisher assertions, not identity/edition decisions.
  Navigation subtrees inside the main region are also excluded. A document with
  a `base href` is an unsupported layout and is refused; its relative links are
  never silently resolved against a different base.
- `parse_resource_index(raw, source_url, allowed_origins, expected_title)` reuses
  the checked HTML shape without requiring a PDF link. It accounts for each
  anchor in the main region, including duplicates and anchors without locators.
  Main-region navigation remains visible with an `inNavigation` marker; `rel`
  values and next/previous hints are retained without following them. Scripts,
  styles, templates and outside-main navigation cannot supply resource entries.
  Same-page anchors, allowed links, missing locators and held external/unsupported
  locators are distinct observations. A held link is retained with its reason;
  it is never requested or silently dropped. Keep original href, text, heading,
  ordinal and resolved URL/fragment provenance. Pagination completeness and
  publication coverage remain false, even when no pagination hint is found;
  dynamic filters or unrecognised page controls require separate qualification.
  This helper does not create publication identities or advance a checkpoint.

Relative link resolution removes dot segments while preserving empty path
segments, including doubled slashes. The original `href`, observed URL, fetch URL
and any fragment are retained separately. A fragment is not part of the HTTP
request. No URL alias, redirect equivalence or publication identity is inferred.

Inputs are UTF-8 and at most 5 MiB per source. DTD/entity declarations, unexpected
XML structures and duplicated scalar fields refuse. Sitemap reconciliation has
at most 100 declared child sources, 50 MiB aggregate payload and 100,000 aggregate
entries; individual sources have at most 50,000 entries. Limits fail visibly.
Unrequested children are refused; missing/failed children remain incomplete.

These are offline source/parser checks. Cloud parsing/hashing, native connector
entitlement and policy access, persistence/readback, replay/conflict/recovery and
web operation must be qualified separately before claiming acquisition delivery.
No source content executes as instructions and no applicability or clinical state
is set by the parser. Unsupported source layouts stay held for explicit review.

Focused check on the repository's explicitly selected Python 3.15.1:

```sh
.venv/bin/python -m unittest discover -s tests -p test_source_discovery.py -v
```

Reuse the existing source-surveillance capture/compare helpers for retained byte
observations. Parser output is not a replacement capture or a new source register.

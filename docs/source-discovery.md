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
- `parse_sitemap(raw, source_url, allowed_origins)` retains locator and raw
  last-modification assertions. Those dates do not establish source editions.
- `reconcile_sitemaps(index_raw, child_payloads, index_url, allowed_origins)`
  requires the declared child scope, preserves repeated URL occurrences and their
  parent/hash provenance, and reports missing or malformed children. A complete
  retrieval of declared children still does not prove catalogue completeness.
  This helper never authorises removals or withdrawal decisions.
- `parse_publication(raw, source_url, allowed_origins, expected_title)` requires
  one complete main region, the expected title and at least one PDF link. It
  excludes navigation/script/template links and refuses observed access/error
  representations, password inputs and off-origin PDF links. Download labels and
  preceding headings remain publisher assertions, not identity/edition decisions.
  Navigation subtrees inside the main region are also excluded. A document with
  a `base href` is an unsupported layout and is refused; its relative links are
  never silently resolved against a different base.

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

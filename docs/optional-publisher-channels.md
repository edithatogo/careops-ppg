# Optional publisher-channel selection

Use this guide when choosing supplementary discovery or import routes. It does
not establish native adapter support, subscriptions, mailbox access, catalogue
coverage or authority to change accepted editions. Keep the core publication/page
acquisition route independent of optional channels. References checked 25 October
2026; inspect the selected endpoint again before implementation.

## Public newsletters: supplementary discovery

The Commission's [newsletters page](https://www.safetyandquality.gov.au/news-and-media/newsletters)
links “NSQHS Standards News” to a
[keyword-filtered news collection](https://www.safetyandquality.gov.au/news-and-media/latest-news?keywords=%22NSQHS+Standards+News%22).
The captured collection reported three results: December 2025, November 2024 and
June 2024. A separately verified official
[National Standards News announcement for August 2026](https://www.safetyandquality.gov.au/news-and-media/latest-news/national-standards-news-august-2026)
is outside that older title filter. The filter therefore cannot establish complete
newsletter coverage or absence of later changes. This is an observed retrieval
gap, not proof of a formal newsletter rename.

The August announcement links its issue body through an external mailing-service
host. That link is a discovery locator; it does not extend the existing publisher
origin allowlist. Do not automatically follow mailing-service tracking links or
interpret a newsletter as an authoritative publication or edition decision.

Selection: retain official announcement pages as optional leads alongside the
existing scoped sitemap/index reconciliation. Do not build another newsletter
adapter or make archive completeness a core-flow prerequisite. Any future
selection must cover the actual titles, pagination and linked origins explicitly;
verify each resulting source against its authoritative publication page.

## Incoming email: require an exact existing read route

Select the exact existing mailbox, folder, sender filter, connection and
per-caller read scope before adding an ingestion adapter. An attachment-search
authorisation does not by itself establish bindings for a new ongoing ingestion
flow. Public announcements provide a fallback without creating subscriptions,
forwarding, triggers or outbound messages.
Reconsider an incoming-mail adapter only with a selected existing mailbox route
and exact read scope; first inspect notification and indirect delivery effects.

## Publisher spreadsheet: verified file, unqualified import

The official [hospital monitoring-tool page](https://www.safetyandquality.gov.au/resources/nsqhs-standards-monitoring-tool-hospitals)
offers an XLSX, describes implementation tracking and records publication year
2021. Its exact linked download, including the doubled path slash, returned
918,182 bytes. Bounded ZIP/CRC and OOXML checks found 27 worksheet declarations,
no VBA project part and no external-link parts. No formulas, macros or workbook
automation were executed. Retain raw bytes, capture time, response headers and SHA-256 privately.

This qualifies the spreadsheet as a supplementary publisher file candidate. It
does not prove a complete, current machine-readable catalogue/action export,
stable row identity, normative text parity or compatibility with the existing
consumer schema. Do not relabel local CSV derived from it as a publisher feed.
Selection: defer import until the catalogue owner selects a bounded scope and
checks exact edition, cells, omissions and provenance against accepted originals.
Keep the PDF/page acquisition path and all prior source editions intact.

## Public API and other exports: deferred

Bounded official-site searches and the inspected pages did not verify a supported
NSQHS publication/edition/action API or a complete CSV/XML export. This is a scoped
negative finding, not proof that none exists. The official
[NHHI LMS API description](https://www.safetyandquality.gov.au/resources/national-hand-hygiene-initiative-learning-management-system-lms-api-technical-specifications)
concerns learning modules and learner history with an API token; it is a different
data contract and supplies no standards-catalogue API qualification. Do not probe
guessed CMS endpoints, obtain a token or create a connection for this route.

Selection: no API adapter; use the qualified core publication/page capture
components in their recorded scope. Reconsider only a documented, selected
endpoint with exact schema, access and coverage evidence. Optional deferral does
not close core acquisition, discovery, recovery or consumer acceptance.

## Qualification boundaries

Retain bounded response receipts and original bytes outside Git. Verify actual
status, requested/final URL, redirects, representation, size and integrity before
parsing. Never infer native connector eligibility from a local HTTPS success.
Record explicit deferral reasons for unselected channels; their absence must not
block the qualified core path. Preserve every prior source edition, human edit
and native receipt. No feed, news title, worksheet count or search result proves
complete standards coverage or clinical applicability.

import hashlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import ppg_source_discovery as discovery
from ppg_source_discovery import parse_rss, parse_sitemap, reconcile_sitemaps, reconcile_rss, compare_sitemaps, parse_publication

ORIGINS = ['https://publisher.example']
BASE = ORIGINS[0]
NS = 'http://www.sitemaps.org/schemas/sitemap/0.9'


def sitemap(kind, links):
    tag = 'sitemap' if kind == 'sitemapindex' else 'url'
    return ('<'+kind+' xmlns="'+NS+'">'+''.join(
        '<'+tag+'><loc>'+url.replace('&', '&amp;')+'</loc><lastmod>publisher-raw-date</lastmod></'+tag+'>'
        for url in links)+'</'+kind+'>').encode()


def rss(items):
    return ('<rss version="2.0"><channel><title>Fictional feed</title>' + ''.join(
        '<item><title>'+title+'</title><link>'+BASE+'/publication</link><guid>same-guid</guid>'
        + ('<pubDate>'+date+'</pubDate>' if date else '')+'</item>'
        for title, date in items) + '</channel></rss>').encode()


def publication(body=''):
    return ('<!doctype html><html><nav><a href="/unrelated.pdf">outside</a></nav><main>'
            '<h1>Fictional framework</h1><p>Publisher source observations.</p>'+body+'</main></html>').encode()


class SourceDiscoveryTests(unittest.TestCase):
    def test_scoped_sitemap_comparison_accounts_for_unchanged_and_new_observations(self):
        child = BASE+'/map-1'; index = sitemap('sitemapindex', [child])
        old = {child: sitemap('urlset', [BASE+'/topic/kept', BASE+'/topic/old', BASE+'/other'])}
        new = {child: sitemap('urlset', [BASE+'/topic/kept', BASE+'/topic/new', BASE+'/other'])}
        result = compare_sitemaps(index, old, index, new, BASE+'/maps', ORIGINS, ['topic/'])
        statuses = {r['fetchURL'].rsplit('/', 1)[1]: r['status'] for r in result['comparisons']}
        self.assertEqual(statuses, {'kept':'unchanged', 'old':'not-observed-in-current-index', 'new':'first-observed'})
        self.assertEqual((result['previousScopedURLCount'], result['currentScopedURLCount']), (2, 2))
        self.assertTrue(result['declaredScopeInventoryComparable'])
        for key in ('catalogueCoverageComplete', 'editionDatesInferred', 'removalDecisionsAllowed',
                    'identityEstablished', 'checkpointAdvanced', 'sourceWrites'):
            self.assertIs(result[key], False)

    def test_missing_child_cannot_prove_addition_or_omission(self):
        a, b = BASE+'/map-1', BASE+'/map-2'; index = sitemap('sitemapindex', [a, b])
        complete = {a: sitemap('urlset', [BASE+'/topic/first']), b: sitemap('urlset', [BASE+'/topic/second'])}
        partial = {a: complete[a]}
        for old, new, expected in [(complete, partial, 'current-scope-incomplete'),
                                   (partial, complete, 'previous-scope-incomplete')]:
            result = compare_sitemaps(index, old, index, new, BASE+'/maps', ORIGINS, ['topic/'])
            row = next(r for r in result['comparisons'] if r['fetchURL'].endswith('/second'))
            self.assertEqual(row['status'], expected)
            self.assertFalse(result['declaredScopeInventoryComparable'])

    def test_lastmod_changes_remain_publisher_assertions_and_variants_are_held(self):
        a, b = BASE+'/map-1', BASE+'/map-2'; index = sitemap('sitemapindex', [a, b])
        original = sitemap('urlset', [BASE+'/topic/item'])
        changed = original.replace(b'publisher-raw-date', b'different-publisher-date')
        old = {a: original, b: sitemap('urlset', [])}
        for new, expected in [({a: changed, b: sitemap('urlset', [])}, 'publisher-metadata-changed'),
                              ({a: original, b: changed}, 'conflicting-lastmod-assertions')]:
            result = compare_sitemaps(index, old, index, new, BASE+'/maps', ORIGINS, ['topic/'])
            self.assertEqual(result['comparisons'][0]['status'], expected)
            self.assertFalse(result['editionDatesInferred'])

    def test_same_locator_moving_between_maps_keeps_all_source_provenance(self):
        a, b = BASE+'/map-1', BASE+'/map-2'; index = sitemap('sitemapindex', [a, b])
        item, empty = sitemap('urlset', [BASE+'/topic/item']), sitemap('urlset', [])
        result = compare_sitemaps(index, {a:item, b:empty}, index, {a:item, b:item},
                                  BASE+'/maps', ORIGINS, ['topic/'])
        row = result['comparisons'][0]
        self.assertEqual(row['status'], 'discovery-provenance-changed')
        self.assertEqual(len(row['previousOccurrences']), 1)
        self.assertEqual({r['discoveredIn'] for r in row['currentOccurrences']}, {a, b})
        self.assertEqual(result['currentScopedURLCount'], 1)

    def test_scope_is_explicit_literal_path_matching_not_query_or_identity_matching(self):
        a=BASE+'/map'; index=sitemap('sitemapindex', [a])
        child=sitemap('urlset', [BASE+'/TOPIC/item', BASE+'/other?topic=yes',
                                 BASE+'/topic/item?v=1', BASE+'/topic/item?v=2'])
        result=compare_sitemaps(index, {a:child}, index, {a:child}, BASE+'/maps', ORIGINS, ['topic'])
        self.assertEqual(result['currentScopedURLCount'], 3)
        self.assertFalse(any('/other?' in r['fetchURL'] for r in result['comparisons']))
        for terms in (None, [], [''], ['.*'], ['Topic'], ['topic']*2, ['x']*21, [True]):
            with self.subTest(terms=terms), self.assertRaises(ValueError):
                compare_sitemaps(index, {a:child}, index, {a:child}, BASE+'/maps', ORIGINS, terms)

    def test_malformed_current_child_does_not_report_false_missing_source(self):
        a=BASE+'/map'; index=sitemap('sitemapindex', [a]);old={a:sitemap('urlset',[BASE+'/topic/item'])}
        result=compare_sitemaps(index,old,index,{a:b'<html>outage</html>'},BASE+'/maps',ORIGINS,['topic/'])
        self.assertEqual(result['comparisons'][0]['status'],'current-scope-incomplete')
        self.assertEqual(result['current']['failures'][0]['status'],'parse_failed')

    def test_rss_reconciliation_retains_repeats_without_creating_new_publications(self):
        raw = rss([('same', ''), ('same', '')])
        result = reconcile_rss(raw, raw, BASE+'/rss', ORIGINS)
        self.assertEqual(result['groupCount'], 1)
        self.assertEqual(result['currentOccurrenceCount'], 2)
        group = result['comparisons'][0]
        self.assertEqual(group['status'], 'unchanged')
        self.assertEqual([r['ordinal'] for r in group['currentOccurrences']], [0, 1])
        for flag in ('identityEstablished', 'applicabilityAccepted', 'checkpointAdvanced',
                     'feedHistoryComplete', 'removalDecisionsAllowed', 'sourceWrites'):
            self.assertIs(result[flag], False)

    def test_rss_changed_old_item_is_detected_without_date_watermark(self):
        date = 'Thu, 22 Oct 2026 00:00:00 GMT'
        before, after = rss([('old text', date)]), rss([('revised text', date)])
        result = reconcile_rss(before, after, BASE+'/rss', ORIGINS)
        self.assertEqual(result['comparisons'][0]['status'], 'changed-observation')
        self.assertEqual(result['previous']['sourceSHA256'], hashlib.sha256(before).hexdigest())
        self.assertEqual(result['current']['sourceSHA256'], hashlib.sha256(after).hexdigest())

    def test_rss_description_change_is_detected_with_same_title_guid_and_date(self):
        base = rss([('same title', 'Thu, 22 Oct 2026 00:00:00 GMT')])
        before = base.replace(b'</item>', b'<description>old content</description></item>')
        after = base.replace(b'</item>', b'<description>revised content</description></item>')
        result = reconcile_rss(before, after, BASE+'/rss', ORIGINS)
        self.assertEqual(result['comparisons'][0]['status'], 'changed-observation')

    def test_reordered_feed_and_new_guid_do_not_merge_by_title_or_url(self):
        first = rss([('same title', '')]).replace(b'same-guid', b'first-guid')
        second = rss([('same title', '')]).replace(b'same-guid', b'second-guid')
        def combine(a, b):
            return a.replace(b'</channel>', b[b.index(b'<item>'):b.index(b'</channel>')] + b'</channel>')
        before, after = combine(first, second), combine(second, first)
        result = reconcile_rss(before, after, BASE+'/rss', ORIGINS)
        self.assertEqual([r['status'] for r in result['comparisons']], ['unchanged', 'unchanged'])
        self.assertEqual(result['groupCount'], 2)
        changed_guid = reconcile_rss(first, second, BASE+'/rss', ORIGINS)
        self.assertEqual({r['status'] for r in changed_guid['comparisons']},
                         {'first-observed', 'not-observed-in-current-feed'})

    def test_rss_conflicting_guid_keeps_every_variant_and_never_selects_one(self):
        raw = rss([('first variant', ''), ('second variant', '')])
        for before, after in [(raw, raw), (raw, rss([('first variant', '')])), (None, raw)]:
            result = reconcile_rss(before, after, BASE+'/rss', ORIGINS)
            self.assertEqual(result['comparisons'][0]['status'], 'conflicting-observations')
            self.assertEqual(result['currentOccurrenceCount'], len(result['current']['items']))

    def test_truncated_or_empty_feed_does_not_retire_previous_observations(self):
        before = rss([('first', ''), ('second', '')]).replace(b'same-guid', b'first-guid', 1)
        # Distinct GUIDs, both pointing at the same observed publication locator.
        for after in (rss([('second', '')]), rss([])):
            result = reconcile_rss(before, after, BASE+'/rss', ORIGINS)
            missing = [r for r in result['comparisons'] if r['status']=='not-observed-in-current-feed']
            self.assertGreaterEqual(len(missing), 1)
            self.assertTrue(all(r['previousOccurrences'] and not r['currentOccurrences'] for r in missing))
            self.assertFalse(result['removalDecisionsAllowed'])

    def test_first_capture_is_first_observed_not_proof_of_new_publication(self):
        result = reconcile_rss(None, rss([('source item', '')]), BASE+'/rss', ORIGINS)
        self.assertFalse(result['baselineSupplied'])
        self.assertIsNone(result['previous'])
        self.assertEqual(result['comparisons'][0]['status'], 'first-observed')
        self.assertFalse(result['identityEstablished'])

    def test_missing_guid_uses_exact_locator_with_fragment(self):
        raw = rss([('first', ''), ('second', '')]).replace(b'<guid>same-guid</guid>', b'')
        raw = raw.replace(b'/publication</link>', b'/publication#section-a</link>', 1)
        result = reconcile_rss(None, raw, BASE+'/rss', ORIGINS)
        self.assertEqual(result['groupCount'], 2)
        self.assertEqual({r['keyKind'] for r in result['comparisons']}, {'observed-locator'})
        self.assertEqual({r['keyValue'] for r in result['comparisons']},
                         {BASE+'/publication', BASE+'/publication#section-a'})

    def test_failed_current_or_previous_parse_refuses_comparison(self):
        valid = rss([('source item', '')])
        for before, after in [(valid, b'<html>outage</html>'), (b'bad XML', valid),
                              (valid, b''), (None, None)]:
            with self.subTest(before=before), self.assertRaises(ValueError):
                reconcile_rss(before, after, BASE+'/rss', ORIGINS)

    def test_rss_retains_duplicate_guid_and_old_date_content_change(self):
        raw = rss([('one', 'Fri, 23 Oct 2026 00:00:00 GMT'),
                   ('two', 'Thu, 22 Oct 2026 00:00:00 GMT'),
                   ('changed old item', 'Sat, 24 Oct 2026 00:00:00 GMT')])
        r = parse_rss(raw, BASE+'/rss.xml', ORIGINS)
        self.assertFalse(r['datesMonotonicallyDescending'])
        self.assertEqual([x['guid'] for x in r['items']], ['same-guid']*3)
        self.assertEqual(len({x['itemSHA256'] for x in r['items']}), 3)
        self.assertEqual(r['sourceSHA256'], hashlib.sha256(raw).hexdigest())
        self.assertFalse(r['coverageComplete'])
        self.assertFalse(r['identityEstablished'])

    def test_missing_feed_date_stays_unknown_and_bad_date_refuses(self):
        r = parse_rss(rss([('one', '')]), BASE+'/rss', ORIGINS)
        self.assertIsNone(r['items'][0]['pubDateISO'])
        self.assertFalse(r['datesMonotonicallyDescending'])
        for date in ['not-a-date', 'Fri, 23 Oct 2026 00:00:00']:
            with self.assertRaisesRegex(ValueError, 'date'):
                parse_rss(rss([('one', date)]), BASE+'/rss', ORIGINS)

    def test_empty_feed_never_establishes_full_history(self):
        r = parse_rss(rss([]), BASE+'/rss', ORIGINS)
        self.assertEqual(r['itemCount'], 0)
        self.assertFalse(r['coverageComplete'])
        self.assertFalse(r['datesMonotonicallyDescending'])

    def test_xml_rejects_entities_utf16_bad_declarations_and_html(self):
        for raw in [b'<!DOCTYPE rss [<!ENTITY x "value">]><rss version="2.0"><channel/></rss>',
                    rss([]).decode().encode('utf-16'),
                    b'<?xml version="1.0" encoding="iso-8859-1"?><rss version="2.0"><channel/></rss>',
                    b'<html><body>Service unavailable</body></html>', b'<rss>']:
            with self.assertRaises(ValueError):
                parse_rss(raw, BASE+'/rss', ORIGINS)

    def test_missing_duplicate_and_nested_scalar_fields_refuse(self):
        for raw in [rss([('one', '')]).replace(b'<link>', b'<link/><link>'),
                    rss([('one', '')]).replace(b'<title>one</title>', b'<title><b>one</b></title>'),
                    rss([('one', '')]).replace(b'<link>'+BASE.encode()+b'/publication</link>', b'')]:
            with self.assertRaises(ValueError):
                parse_rss(raw, BASE+'/rss', ORIGINS)

    def test_cross_origin_insecure_credential_control_and_port_urls_refuse(self):
        for url in ['https://other.example/a', 'http://publisher.example/a',
                    'https://user:password@publisher.example/a', BASE+':444/a',
                    BASE+'/bad\npath', BASE+'/bad\\path']:
            with self.assertRaises(ValueError):
                parse_sitemap(sitemap('urlset', [url]), BASE+'/map', ORIGINS)
        with self.assertRaises(ValueError):
            parse_sitemap(sitemap('urlset', [BASE+'/a']), BASE+'/map', [BASE+'/path'])

    def test_sitemap_namespace_unknown_elements_and_fragment_refuse(self):
        for raw in [b'<urlset/>', sitemap('urlset', [BASE+'/a#fragment']),
                    ('<urlset xmlns="'+NS+'"><unknown/></urlset>').encode()]:
            with self.assertRaises(ValueError):
                parse_sitemap(raw, BASE+'/map', ORIGINS)

    def test_raw_dates_and_query_locators_are_not_editions(self):
        r = parse_sitemap(sitemap('sitemapindex', [BASE+'/map?page=1&a=2']), BASE+'/map', ORIGINS)
        self.assertEqual(r['entries'][0]['fetchURL'], BASE+'/map?page=1&a=2')
        self.assertEqual(r['entries'][0]['lastmodRaw'], 'publisher-raw-date')
        self.assertFalse(r['editionDatesInferred'])

    def test_cross_map_duplicates_keep_each_source_occurrence(self):
        a, b = BASE+'/map?page=1', BASE+'/map?page=2'
        index = sitemap('sitemapindex', [a, b])
        children = {a: sitemap('urlset', [BASE+'/one', BASE+'/same']),
                    b: sitemap('urlset', [BASE+'/same', BASE+'/two'])}
        r = reconcile_sitemaps(index, children, BASE+'/map', ORIGINS)
        self.assertTrue(r['allDeclaredChildrenParsed'])
        self.assertEqual((r['occurrenceCount'], r['URLCount'], r['repeatedOccurrences']), (4, 3, 1))
        same = next(x for x in r['observations'] if x['fetchURL'].endswith('/same'))
        self.assertEqual({x['discoveredIn'] for x in same['occurrences']}, {a, b})
        self.assertFalse(r['catalogueCoverageComplete'])
        self.assertFalse(r['removalDecisionsAllowed'])

    def test_missing_failed_child_never_advances_complete_or_removal(self):
        a, b = BASE+'/first', BASE+'/second'
        index = sitemap('sitemapindex', [a, b])
        for children in [{a: sitemap('urlset', [BASE+'/kept'])},
                         {a: sitemap('urlset', [BASE+'/kept']), b: b'<html>error</html>'},
                         {a: sitemap('urlset', [BASE+'/kept']), b: sitemap('sitemapindex', [a])}]:
            r = reconcile_sitemaps(index, children, BASE+'/index', ORIGINS)
            self.assertFalse(r['allDeclaredChildrenParsed'])
            self.assertFalse(r['removalDecisionsAllowed'])
            self.assertEqual(r['parsedChildren'], 1)
            self.assertEqual(len(r['failures']), 1)

    def test_unrequested_child_and_empty_index_refuse(self):
        for index, children in [(sitemap('sitemapindex', [BASE+'/first']), {BASE+'/extra': b'data'}),
                                (sitemap('sitemapindex', []), {})]:
            with self.assertRaises(ValueError):
                reconcile_sitemaps(index, children, BASE+'/index', ORIGINS)

    def test_publication_preserves_relative_double_slash_and_fragment(self):
        raw = publication('<h2>Downloads</h2><h3>Original published edition</h3>'
                          '<a href="../files//original.pdf#page=2">Download <span>PDF</span></a>'
                          '<h3>Updated edition</h3><a href="/files/update.pdf">New PDF</a>')
        r = parse_publication(raw, BASE+'/resources/page', ORIGINS, 'Fictional framework')
        self.assertEqual(len(r['downloads']), 2)
        first = r['downloads'][0]
        self.assertEqual(first['fetchURL'], BASE+'/files//original.pdf')
        self.assertEqual(first['fragment'], 'page=2')
        self.assertEqual(first['precedingHeading'], 'Original published edition')
        self.assertEqual(first['text'], 'Download PDF')
        self.assertFalse(r['publicationIdentityAssigned'])
        self.assertFalse(r['rawEditionDatesInferred'])

    def test_absolute_doubled_path_slash_is_retained(self):
        url = BASE+'/files//original.pdf'
        r = parse_publication(publication('<a href="'+url+'">PDF</a>'), BASE+'/page', ORIGINS, 'Fictional framework')
        self.assertEqual(r['downloads'][0]['fetchURL'], url)
        self.assertEqual(r['downloads'][0]['href'], url)

    def test_navigation_script_template_downloads_are_excluded(self):
        raw = publication('<script>fake <a href="/script.pdf">PDF</a></script>'
                          '<template><a href="/template.pdf">PDF</a></template>'
                          '<a href="/real.pdf">Actual PDF</a>')
        r = parse_publication(raw, BASE+'/page', ORIGINS, 'Fictional framework')
        self.assertEqual([x['fetchURL'] for x in r['downloads']], [BASE+'/real.pdf'])

    def test_navigation_inside_main_is_excluded_through_nested_subtrees(self):
        nav = ('<nav><h2>Navigation</h2><div><a href="/other.pdf">Other PDF</a></div>'
               '<nav><span><a href="/nested.pdf">Nested PDF</a></span></nav>'
               '<a href="/still-navigation.pdf">Still navigation</a></nav>')
        raw = publication(nav+'<h2>Downloads</h2><a href="/actual.pdf">Actual PDF</a>')
        r = parse_publication(raw, BASE+'/page', ORIGINS, 'Fictional framework')
        self.assertEqual([x['fetchURL'] for x in r['downloads']], [BASE+'/actual.pdf'])
        with self.assertRaisesRegex(ValueError, 'no publication PDF'):
            parse_publication(publication(nav), BASE+'/page', ORIGINS, 'Fictional framework')

    def test_base_urls_are_an_explicit_unsupported_layout(self):
        raw = publication('<a href="edition.pdf">PDF</a>')
        for href in [BASE+'/files/', 'https://other.example/files/', '/files/', '']:
            with self.assertRaisesRegex(ValueError, 'shape'):
                parse_publication(raw.replace(b'<html>', ('<html><head><base href="'+href+'"></head>').encode()),
                                  BASE+'/resources/page', ORIGINS, 'Fictional framework')
        r = parse_publication(raw.replace(b'<html>', b'<html><head><base target="_blank"></head>'),
                              BASE+'/resources/page', ORIGINS, 'Fictional framework')
        self.assertEqual(r['downloads'][0]['fetchURL'], BASE+'/resources/edition.pdf')

    def test_layout_error_login_title_and_missing_download_refuse(self):
        good = publication('<a href="/real.pdf">PDF</a>')
        for raw in [good.replace(b'<main>', b'<section>').replace(b'</main>', b'</section>'),
                    good.replace(b'Fictional framework', b'Wrong publication'),
                    good.replace(b'</main>', b'<input type="password"></main>'),
                    good.replace(b'</main>', b'Access denied</main>'),
                    good.replace(b'</main>', b''), publication(),
                    good.replace(b'</main>', b'<h1>duplicate</h1></main>')]:
            with self.assertRaises(ValueError):
                parse_publication(raw, BASE+'/page', ORIGINS, 'Fictional framework')

    def test_external_pdf_is_held_instead_of_silently_ignored(self):
        with self.assertRaisesRegex(ValueError, 'allowlist'):
            parse_publication(publication('<a href="https://other.example/original.pdf">PDF</a>'),
                              BASE+'/page', ORIGINS, 'Fictional framework')

    def test_byte_and_entry_limits_precede_use(self):
        for raw in [b'', 'not bytes', b'x'*(discovery.MAX_BYTES+1)]:
            with self.assertRaises(ValueError):
                parse_sitemap(raw, BASE+'/map', ORIGINS)
        with patch.object(discovery, 'MAX_ENTRIES', 1):
            with self.assertRaises(ValueError):
                parse_sitemap(sitemap('urlset', [BASE+'/a', BASE+'/b']), BASE+'/map', ORIGINS)
            with self.assertRaises(ValueError):
                parse_rss(rss([('one', ''), ('two', '')]), BASE+'/rss', ORIGINS)

    def test_aggregate_sitemap_limits_refuse_before_complete_claim(self):
        index = sitemap('sitemapindex', [BASE+'/child'])
        child = {BASE+'/child': sitemap('urlset', [BASE+'/one', BASE+'/two'])}
        with patch.object(discovery, 'MAX_CHILD_BYTES', 5):
            with self.assertRaisesRegex(ValueError, 'aggregate child byte'):
                reconcile_sitemaps(index, child, BASE+'/index', ORIGINS)
        with patch.object(discovery, 'MAX_TOTAL_ENTRIES', 1):
            with self.assertRaisesRegex(ValueError, 'aggregate sitemap entry'):
                reconcile_sitemaps(index, child, BASE+'/index', ORIGINS)

    def test_relative_reference_resolution_preserves_path_segments(self):
        for href, expected in [('./a/../b//c.pdf', '/resources/b//c.pdf'),
                               ('/a//b/../c.pdf', '/a//c.pdf'),
                               ('../a.pdf?edition=1&amp;x=2', '/a.pdf?edition=1&x=2'),
                               ('//publisher.example/a//b.pdf', '/a//b.pdf')]:
            r = parse_publication(publication('<a href="'+href+'">PDF</a>'),
                                  BASE+'/resources/page', ORIGINS, 'Fictional framework')
            self.assertEqual(r['downloads'][0]['fetchURL'], BASE+expected)


if __name__ == '__main__':
    unittest.main()

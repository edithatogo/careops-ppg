"""Bounded offline discovery observations; no network, identity promotion or writes."""
from __future__ import annotations

import hashlib
import re
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit, urldefrag
from xml.etree import ElementTree as ET

MAX_BYTES = 5 * 1024 * 1024
MAX_ENTRIES = 50000
MAX_CHILD_BYTES = 50 * 1024 * 1024
MAX_TOTAL_ENTRIES = 100000
NS = '{http://www.sitemaps.org/schemas/sitemap/0.9}'


def _text(data):
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_BYTES:
        raise ValueError('bounded nonempty source bytes required')
    try:
        text = data.decode('utf-8-sig')
    except UnicodeError as exc:
        raise ValueError('UTF-8 source required') from exc
    if '\x00' in text:
        raise ValueError('NUL source refused')
    return text


def _origin(url):
    try:
        u = urlsplit(url)
        if (u.scheme != 'https' or not u.hostname or u.username or u.password
                or u.port not in (None, 443)):
            raise ValueError()
        return 'https://' + u.hostname.lower()
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError('HTTPS source origin required') from exc


def _remove_dot_segments(path):
    # RFC 3986 section 5.2.4: remove dot segments, retain empty path segments.
    output = ''
    while path:
        if path.startswith(('../', './')):
            path = path.partition('/')[2]
        elif path.startswith('/./') or path == '/.':
            path = '/' + path[3:]
        elif path.startswith('/../') or path == '/..':
            path = '/' + path[4:]
            output = output.rsplit('/', 1)[0] if '/' in output else ''
        elif path in ('.', '..'):
            path = ''
        else:
            stop = path.find('/', 1 if path.startswith('/') else 0)
            if stop < 0:
                output, path = output + path, ''
            else:
                output, path = output + path[:stop], path[stop:]
    return output


def _resolve(url, base):
    target, origin = urlsplit(url), urlsplit(base)
    if target.scheme:
        return url
    if target.netloc:
        return urlunsplit((origin.scheme, target.netloc, _remove_dot_segments(target.path),
                           target.query, target.fragment))
    path = target.path
    if path:
        if not path.startswith('/'):
            path = (origin.path.rsplit('/', 1)[0] + '/' if '/' in origin.path else '/') + path
        path, query = _remove_dot_segments(path), target.query
    else:
        path = origin.path
        query = target.query if '?' in url.split('#', 1)[0] else origin.query
    return urlunsplit((origin.scheme, origin.netloc, path, query, target.fragment))


def _url(url, allowed_origins, base=None):
    if (not isinstance(url, str) or not url
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url)
            or '\\' in url):
        raise ValueError('invalid source URL')
    allowed = set()
    for value in allowed_origins:
        origin = _origin(value)
        if value != origin:
            raise ValueError('exact HTTPS origin allowlist required')
        allowed.add(origin)
    resolved = _resolve(url, base) if base else url
    if _origin(resolved) not in allowed:
        raise ValueError('source URL outside allowlist')
    fetch, fragment = urldefrag(resolved)
    return {'observedURL': resolved, 'fetchURL': fetch, 'fragment': fragment or None}


def _xml(data):
    text = _text(data)
    if re.search(r'<!\s*(DOCTYPE|ENTITY)\b', text, re.I):
        raise ValueError('DTD/entity declarations refused')
    declaration = re.match(r'\s*<\?xml\b([^?]*)\?>', text)
    if declaration:
        encoding = re.search(r'encoding\s*=\s*[\"\x27]([^\"\x27]+)', declaration[1], re.I)
        if encoding and encoding[1].lower() not in ('utf-8', 'utf8', 'us-ascii'):
            raise ValueError('UTF-8 XML declaration required')
    try:
        return ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError('malformed XML source') from exc


def _envelope(kind, data, source_url, allowed):
    url = _url(source_url, allowed)
    if url['fragment']:
        raise ValueError('source capture URL must be fragment-free')
    return {'kind': kind, 'sourceURL': source_url,
            'sourceSHA256': hashlib.sha256(data).hexdigest(),
            'sourceBytes': len(data), 'identityEstablished': False,
            'applicabilityAccepted': False, 'sourceWrites': False}


def _scalar(node, tag, required=False):
    values = node.findall(tag)
    if len(values) > 1 or (required and len(values) != 1):
        raise ValueError('missing or duplicate XML field')
    if not values:
        return None
    if list(values[0]):
        raise ValueError('scalar XML field required')
    value = (values[0].text or '').strip()
    if required and not value:
        raise ValueError('nonempty XML field required')
    return value or None


def parse_rss(data, source_url, allowed_origins):
    root = _xml(data)
    if root.tag != 'rss' or root.get('version') != '2.0' or len(root.findall('channel')) != 1:
        raise ValueError('RSS 2.0 channel required')
    channel = root.find('channel')
    items = channel.findall('item')
    if len(items) > MAX_ENTRIES:
        raise ValueError('RSS item limit exceeded')
    rows, dates = [], []
    for ordinal, item in enumerate(items):
        link = _url(_scalar(item, 'link', True), allowed_origins)
        date = _scalar(item, 'pubDate')
        parsed = None
        if date:
            try:
                parsed = parsedate_to_datetime(date)
                if parsed.tzinfo is None or parsed.utcoffset() is None:
                    raise ValueError()
            except (ValueError, TypeError, OverflowError) as exc:
                raise ValueError('invalid RSS publication date') from exc
        dates.append(parsed)
        # A GUID or date is an observation, not a publication identity/edition.
        rows.append({'ordinal': ordinal, 'title': _scalar(item, 'title', True),
                     **link, 'guid': _scalar(item, 'guid'), 'pubDateRaw': date,
                     'pubDateISO': parsed.isoformat() if parsed else None,
                     'itemSHA256': hashlib.sha256(ET.tostring(item, encoding='utf-8')).hexdigest(),
                     'itemHashRepresentation': 'parsed XML serialization, not raw source bytes'})
    result = _envelope('rss-observations-v1', data, source_url, allowed_origins)
    result.update(items=rows, itemCount=len(rows), coverageComplete=False,
                  datesMonotonicallyDescending=(bool(dates) and all(a is not None for a in dates)
                    and all(a >= b for a, b in zip(dates, dates[1:]))))
    return result


def parse_sitemap(data, source_url, allowed_origins):
    root = _xml(data)
    if root.tag not in (NS + 'sitemapindex', NS + 'urlset'):
        raise ValueError('namespaced sitemap index or urlset required')
    index = root.tag == NS + 'sitemapindex'
    tag = NS + ('sitemap' if index else 'url')
    if len(root) > MAX_ENTRIES or any(child.tag != tag for child in root):
        raise ValueError('unexpected sitemap entries or limit exceeded')
    rows = []
    for ordinal, node in enumerate(root):
        link = _url(_scalar(node, NS + 'loc', True), allowed_origins)
        if link['fragment']:
            raise ValueError('fragment in sitemap locator')
        rows.append({'ordinal': ordinal, **link,
                     'lastmodRaw': _scalar(node, NS + 'lastmod')})
    result = _envelope('sitemap-index-v1' if index else 'sitemap-urlset-v1',
                       data, source_url, allowed_origins)
    result.update(entries=rows, entryCount=len(rows), editionDatesInferred=False)
    return result


def reconcile_sitemaps(index_bytes, child_bytes, index_url, allowed_origins):
    """Keep occurrences; a failed/missing child cannot establish removals."""
    index = parse_sitemap(index_bytes, index_url, allowed_origins)
    if index['kind'] != 'sitemap-index-v1' or not isinstance(child_bytes, dict):
        raise ValueError('sitemap index and explicit child payloads required')
    expected = {r['fetchURL'] for r in index['entries']}
    if not expected or len(expected) > 100 or set(child_bytes) - expected:
        raise ValueError('bounded declared child scope required')
    if (any(not isinstance(v, bytes) for v in child_bytes.values())
            or sum(len(v) for v in child_bytes.values()) > MAX_CHILD_BYTES):
        raise ValueError('aggregate child byte limit exceeded')
    children, observations, failures = [], {}, []
    for url in sorted(expected):
        if url not in child_bytes:
            failures.append({'sourceURL': url, 'status': 'not_supplied'})
            continue
        try:
            child = parse_sitemap(child_bytes[url], url, allowed_origins)
            if child['kind'] != 'sitemap-urlset-v1':
                raise ValueError('child urlset required')
        except ValueError as exc:
            failures.append({'sourceURL': url, 'status': 'parse_failed', 'reason': str(exc)})
            continue
        children.append(child)
        if sum(c['entryCount'] for c in children) > MAX_TOTAL_ENTRIES:
            raise ValueError('aggregate sitemap entry limit exceeded')
        for entry in child['entries']:
            observations.setdefault(entry['fetchURL'], []).append({**entry,
                'discoveredIn': url, 'discoverySHA256': child['sourceSHA256']})
    occurrence_count = sum(len(v) for v in observations.values())
    return {'kind': 'sitemap-discovery-reconciliation-v1', 'index': index,
            'children': children, 'failures': failures,
            'allDeclaredChildrenParsed': not failures,
            'expectedUniqueChildren': len(expected), 'parsedChildren': len(children),
            'URLCount': len(observations), 'occurrenceCount': occurrence_count,
            'repeatedOccurrences': occurrence_count - len(observations),
            'observations': [{'fetchURL': k, 'occurrences': v} for k, v in sorted(observations.items())],
            'catalogueCoverageComplete': False, 'removalDecisionsAllowed': False,
            'identityEstablished': False, 'sourceWrites': False}


class _Publication(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.main_count = 0
        self.in_main = False
        self.main_closed = False
        self.ignore = None
        self.ignore_depth = 0
        self.base_url_present = False
        self.heading = None
        self.heading_text = []
        self.headings = []
        self.last_heading = None
        self.link = None
        self.links = []
        self.text = []
        self.password = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'base' and 'href' in attrs:
            self.base_url_present = True
        if self.ignore:
            if tag == self.ignore:
                self.ignore_depth += 1
            return
        if tag == 'main':
            self.main_count += 1
            if self.in_main or self.main_count != 1:
                raise ValueError('one publication main region required')
            self.in_main = True
        if not self.in_main:
            return
        if tag in ('script', 'style', 'template', 'nav'):
            self.ignore = tag
            self.ignore_depth = 1
            return
        if tag == 'input' and attrs.get('type', '').lower() == 'password':
            self.password = True
        if tag in ('h1', 'h2', 'h3', 'h4'):
            if self.heading:
                raise ValueError('malformed publication heading')
            self.heading, self.heading_text = tag, []
        if tag == 'a':
            if self.link is not None:
                raise ValueError('nested publication anchor')
            self.link = {'href': attrs.get('href'), 'text': [],
                         'precedingHeading': self.last_heading}

    def handle_data(self, data):
        if not self.in_main or self.ignore:
            return
        self.text.append(data)
        if self.heading:
            self.heading_text.append(data)
        if self.link is not None:
            self.link['text'].append(data)

    def handle_endtag(self, tag):
        if self.ignore:
            if tag == self.ignore:
                self.ignore_depth -= 1
                if self.ignore_depth == 0:
                    self.ignore = None
            return
        if not self.in_main:
            return
        if tag == self.heading:
            text = ' '.join(' '.join(self.heading_text).split())
            self.headings.append((tag, text))
            self.last_heading, self.heading = text, None
        if tag == 'a' and self.link is not None:
            self.link['text'] = ' '.join(' '.join(self.link['text']).split())
            self.links.append(self.link)
            self.link = None
            if len(self.links) > MAX_ENTRIES:
                raise ValueError('publication link limit exceeded')
        if tag == 'main':
            self.main_closed, self.in_main = True, False


def parse_publication(data, source_url, allowed_origins, expected_title):
    """Inspect one known HTML shape; headings are publisher assertions only."""
    text = _text(data)
    if not isinstance(expected_title, str) or not expected_title.strip():
        raise ValueError('expected publication title required')
    parser = _Publication()
    parser.feed(text)
    parser.close()
    titles = [t for tag, t in parser.headings if tag == 'h1']
    normalize = lambda x: ' '.join(x.split()).casefold()
    main = ' '.join(' '.join(parser.text).split())
    if (parser.base_url_present or parser.main_count != 1 or not parser.main_closed or parser.ignore
            or parser.link is not None or parser.heading or len(titles) != 1
            or normalize(titles[0]) != normalize(expected_title)
            or parser.password or re.search(r'access denied|verify you are human|page not found|captcha', main[:500], re.I)):
        raise ValueError('publication shape, title or access/error representation differs')
    links = []
    for link in parser.links:
        href = link['href']
        if not href or not urlsplit(href).path.lower().endswith('.pdf'):
            continue
        resolved = _url(href, allowed_origins, source_url)
        links.append({**link, **resolved, 'publisherAssertionOnly': True})
    if not links:
        raise ValueError('no publication PDF download links found')
    result = _envelope('publication-download-observations-v1', data, source_url, allowed_origins)
    result.update(title=titles[0], downloads=links, downloadOccurrences=len(links),
                  rawEditionDatesInferred=False, publicationIdentityAssigned=False)
    return result

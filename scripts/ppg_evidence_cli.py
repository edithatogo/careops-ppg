"""Bounded delegated SharePoint lookup and exact-excerpt validation; no AI or writes."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import posixpath
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import quote, urlsplit, unquote
from uuid import UUID
import xml.etree.ElementTree as ET
import zipfile
from ppg_evidence_check import check_answer, in_scope

MAX_BYTES = 2_000_000
MAX_TEXT = 2_000_000
LABELS = {'captured-reference-unconfirmed', 'draft-unapproved'}
META = 'UniqueId,Name,Length,ETag,MajorVersion,MinorVersion,TimeLastModified,ServerRelativeUrl'


class EvidenceError(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise EvidenceError(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')
    Path(path).chmod(0o600)


def config_checked(config):
    site = config.get('siteUrl', '').rstrip('/')
    u = urlsplit(site)
    require(u.scheme == 'https' and u.hostname and u.hostname.endswith('.sharepoint.com') and
            not u.username and not u.password and not u.query and not u.fragment and
            re.fullmatch(r'/(teams|sites)/[^/%]+', u.path), 'invalid_site_binding')
    folder = config.get('folder', '')
    require(isinstance(folder, str) and folder.startswith(u.path + '/') and
            not re.search(r'["?#%\\\x00-\x1f]', folder) and
            all(p not in {'.', '..', ''} for p in folder.split('/')[1:]), 'invalid_folder_binding')
    identity = config.get('identity', {})
    require(all(isinstance(identity.get(k), str) and identity[k] for k in ('username', 'tenantId', 'appId')) and
            config.get('connectionName'), 'existing_client_binding_required')
    return {**config, 'siteUrl': site, 'folder': folder.rstrip('/'),
            'prefix': u.scheme + '://' + u.netloc + folder.rstrip('/') + '/'}


class Client:
    """Only existing CLI status and explicit GET requests; no auth mutation commands."""
    def __init__(self, config):
        self.config = config
        p = subprocess.run(['m365', 'status', '--output', 'json'], capture_output=True, timeout=30)
        require(p.returncode == 0, 'saved_client_unavailable')
        status = json.loads(p.stdout)
        expected = config['identity']
        require(status.get('connectionName') == config['connectionName'] and
                all(str(status.get(a, '')).lower() == expected[b].lower() for a, b in
                    [('connectedAs', 'username'), ('appTenant', 'tenantId'), ('appId', 'appId')]),
                'saved_client_identity_mismatch')

    def get(self, url, binary=False):
        site = urlsplit(self.config['siteUrl'])
        target = urlsplit(url)
        require(target.scheme == site.scheme and target.netloc == site.netloc and
                target.path.startswith(site.path + '/_api/'), 'request_outside_bound_site')
        with tempfile.TemporaryDirectory(prefix='ppg-evidence-get-') as tmp:
            out = Path(tmp) / 'response'
            try:
                p = subprocess.run(['m365', 'request', '--method', 'get', '--url', url,
                                    '--accept', 'application/octet-stream' if binary else 'application/json;odata=nometadata',
                                    '--filePath', str(out), '--output', 'json'],
                                   capture_output=True, timeout=60)
            except subprocess.TimeoutExpired:
                raise EvidenceError('native_read_timeout') from None
            if p.returncode:
                # Keep response bodies/errors private; only classify known HTTP statuses.
                message = (p.stderr + p.stdout).decode('utf-8', errors='replace')
                code = re.search(r'(?:status(?: code)?[ :]+|\bHTTP[ /])([45]\d\d)\b', message, re.I)
                status = int(code.group(1)) if code else None
                raise EvidenceError('denied' if status in {401, 403} else 'missing' if status == 404 else 'native_read_failed')
            require(out.is_file() and out.stat().st_size <= MAX_BYTES, 'native_response_limit')
            raw = out.read_bytes()
            if binary:
                return raw
            try:
                return json.loads(raw)
            except ValueError:
                raise EvidenceError('native_response_invalid') from None


def root_json(value):
    require(isinstance(value, dict), 'native_response_invalid')
    return value.get('d', value)


def endpoint(config, file_path):
    canonical = urlsplit(config['siteUrl'])._replace(path=file_path, query='', fragment='').geturl()
    require(in_scope(canonical, config['prefix']) and '%' not in file_path and
            not re.search(r'[?#\\\x00-\x1f]', file_path) and
            all(p not in {'.', '..'} for p in file_path.split('/')), 'source_outside_selected_folder')
    escaped = quote(file_path.replace("'", "''"), safe='/')
    return config['siteUrl'] + "/_api/web/GetFileByServerRelativePath(decodedurl='" + escaped + "')", canonical


def pin(metadata):
    require(isinstance(metadata, dict), 'invalid_native_metadata')
    try:
        require(UUID(metadata['UniqueId']).int != 0, 'invalid_native_identity')
        n = metadata['Length']
        require(type(n) is int or isinstance(n, str) and re.fullmatch(r'\d+', n), 'invalid_native_size')
        require(0 <= int(n) <= MAX_BYTES, 'native_source_size_limit')
        require(all(type(metadata[k]) is int and metadata[k] >= 0 for k in ('MajorVersion', 'MinorVersion')),
                'invalid_native_version')
        require(all(isinstance(metadata[k], str) and metadata[k].strip() for k in
                    ('Name', 'ETag', 'TimeLastModified', 'ServerRelativeUrl')), 'incomplete_native_pin')
        time = datetime.fromisoformat(metadata['TimeLastModified'].replace('Z', '+00:00'))
        require(time.utcoffset() is not None, 'invalid_native_time')
        return {k: str(metadata[k]) for k in META.split(',')}
    except (KeyError, TypeError, ValueError):
        raise EvidenceError('invalid_native_metadata') from None


def search(client, config, query):
    require(isinstance(query, str) and 0 < len(query.strip()) <= 200 and
            not re.search(r'["\\\x00-\x1f]', query), 'literal_query_required')
    kql = '"' + query.strip() + '" AND Path:"' + config['prefix'] + '"'
    literal = quote(kql.replace("'", "''"), safe='')
    url = (config['siteUrl'] + "/_api/search/query?querytext='" + literal +
           "'&rowlimit=20&trimduplicates=false&selectproperties='Title,Path,FileExtension,UniqueId,LastModifiedTime'")
    try:
        data = root_json(client.get(url))
        data = data.get('query', data)
        relevant = data['PrimaryQueryResult']['RelevantResults']
        rows = relevant['Table']['Rows']
        if isinstance(rows, dict):
            rows = rows['results']
        hits = []
        for row in rows:
            cells = row['Cells']
            if isinstance(cells, dict):
                cells = cells['results']
            hit = {c['Key']: c.get('Value') for c in cells}
            # Even a search response must remain inside the selected folder.
            if in_scope(hit.get('Path', ''), config['prefix']):
                hits.append({k: hit.get(k) for k in ('Title', 'Path', 'FileExtension', 'UniqueId', 'LastModifiedTime')})
        return {'status': 'results' if hits else 'no-indexed-matches', 'query': query,
                'hits': hits, 'rowLimit': 20, 'reportedTotalRows': relevant.get('TotalRows'),
                'limitation': 'Search discovery only; absence from this result is not source absence or proof of indexing failure.'}
    except (EvidenceError, KeyError, TypeError, ValueError) as e:
        return {'status': str(e) if isinstance(e,EvidenceError) else 'error', 'query': query, 'hits': [], 'limitation': 'Search unavailable or response unsupported; explicitly selected direct reads remain separate.'}


def extract(raw, name, pdf_tool=None):
    suffix = Path(name).suffix.lower()
    lines, locations, warnings = [], [], []
    if suffix in {'.txt', '.md'}:
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            raise EvidenceError('unsupported_non_utf8') from None
        require(not any(ord(c) < 32 and c not in '\t\n\r' for c in text), 'unsupported_binary_text')
        return text, [{'sourceLine': n} for n, _ in enumerate(text.splitlines(), 1)], 'utf8-v1', warnings
    if suffix == '.docx':
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                require(len(z.namelist()) == len(set(z.namelist())) and len(z.namelist()) <= 500 and
                        sum(x.file_size for x in z.infolist()) <= 20_000_000, 'unsupported_docx_expansion')
                require({'_rels/.rels', '[Content_Types].xml'} <= set(z.namelist()), 'unsupported_docx_parts')
                def xml_part(name):
                    require(z.getinfo(name).file_size <= MAX_TEXT, 'unsupported_docx_text_limit')
                    xml = z.read(name).decode('utf-8-sig')
                    require('\x00' not in xml and not re.search(r'<!\s*(DOCTYPE|ENTITY)', xml, re.I), 'unsupported_docx_xml')
                    return ET.fromstring(xml)
                relationships=xml_part('_rels/.rels')
                main=[r for r in relationships if r.get('Type') in {
                    'http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument',
                    'http://purl.oclc.org/ooxml/officeDocument/relationships/officeDocument'}]
                require(len(main)==1 and main[0].get('TargetMode','Internal')=='Internal', 'unsupported_docx_main_relationship')
                target=main[0].get('Target','');u=urlsplit(target)
                require(not u.scheme and not u.netloc and not u.query and not u.fragment and
                        '..' not in unquote(target).split('/'), 'unsupported_docx_main_target')
                part=posixpath.normpath(unquote(target).lstrip('/'))
                types=xml_part('[Content_Types].xml')
                require(any(t.get('PartName')=='/'+part and t.get('ContentType')==
                            'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'
                            for t in types), 'unsupported_docx_content_type')
                document=xml_part(part)
            namespace=document.tag.split('}')[0].lstrip('{')
            require(namespace in {'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
                                  'http://purl.oclc.org/ooxml/wordprocessingml/main'}, 'unsupported_docx_namespace')
            w='{'+namespace+'}'
            body = document.find(w + 'body')
            require(body is not None, 'unsupported_docx_body')
            def inline(node):
                if node.tag in {w+'del', w+'drawing', w+'pict'}:
                    return ''
                if node.tag == w+'t':
                    return node.text or ''
                if node.tag == w+'tab':
                    return '\t'
                if node.tag in {w+'br', w+'cr'}:
                    return '\n'
                return ''.join(inline(c) for c in node)
            def paragraphs(node):
                if node.tag in {w+'del', w+'drawing', w+'pict'}:
                    return
                if node.tag == w+'p':
                    yield node
                else:
                    for child in node:
                        yield from paragraphs(child)
            for n, paragraph in enumerate(paragraphs(body), 1):
                for j, line in enumerate(inline(paragraph).splitlines(), 1):
                    lines.append(line)
                    locations.append({'bodyParagraph': n, 'paragraphLine': j})
            method = 'docx-body-paragraphs-v1'
            warnings = ['Body text and table paragraphs only; no pagination, headers, footnotes, comments, image/OCR or complete layout proof. Cached field/inserted text may be present; no acceptance of tracked changes is inferred.']
        except (zipfile.BadZipFile, KeyError, UnicodeDecodeError, ET.ParseError, RuntimeError):
            raise EvidenceError('unsupported_docx') from None
    elif suffix == '.pdf':
        require(pdf_tool and Path(pdf_tool).is_absolute() and Path(pdf_tool).is_file(), 'unsupported_pdf_extractor_unavailable')
        require(raw.startswith(b'%PDF-'), 'unsupported_pdf_signature')
        with tempfile.TemporaryDirectory(prefix='ppg-evidence-pdf-') as tmp:
            source, target = Path(tmp)/'source.pdf', Path(tmp)/'text.txt'
            source.write_bytes(raw)
            try:
                p = subprocess.run([str(pdf_tool), '-enc', 'UTF-8', '-layout', str(source), str(target)], capture_output=True, timeout=20)
            except subprocess.TimeoutExpired:
                raise EvidenceError('unsupported_pdf_extraction_timeout') from None
            require(p.returncode == 0 and target.is_file() and target.stat().st_size <= MAX_TEXT, 'unsupported_pdf_extraction_failed')
            pages = target.read_text(encoding='utf-8').split('\f')
            if pages and not pages[-1].strip():
                pages.pop()
            empty = []
            for page, text in enumerate(pages, 1):
                if not text.strip():
                    empty.append(page)
                for n, line in enumerate(text.splitlines(), 1):
                    lines.append(line)
                    locations.append({'page': page, 'pageLine': n})
            method = 'pdftotext-layout-utf8-v1'
            warnings = ['PDF text extraction only; no OCR, reading-order, visual-layout or complete-content assurance.', 'Pages without extractable text: '+str(empty)]
    else:
        raise EvidenceError('unsupported_format')
    text = '\n'.join(lines)
    require(bool(text.strip()), 'unsupported_no_extractable_text')
    require(len(text.encode()) <= MAX_TEXT, 'unsupported_extracted_text_limit')
    return text, locations, method, warnings


def retrieve(client, config, selected, output):
    file_api, canonical = endpoint(config, selected['path'])
    if selected.get('nativeUniqueId'):
        file_api = config['siteUrl']+"/_api/web/GetFileById('"+selected['nativeUniqueId']+"')"
    fail = lambda status, reason: {'sourceId': selected['sourceId'], 'status': status, 'reason': reason}
    try:
        before = pin(root_json(client.get(file_api+'?$select='+META)))
        if selected.get('nativeUniqueId'):
            require(before['UniqueId'].lower()==selected['nativeUniqueId'].lower(), 'native_identity_mismatch')
            _, canonical = endpoint(config, before['ServerRelativeUrl'])
        else:
            require(before['ServerRelativeUrl'] == selected['path'], 'native_path_mismatch')
        require(before['Name'] == Path(before['ServerRelativeUrl']).name, 'native_name_mismatch')
        if Path(before['Name']).suffix.lower() not in {'.txt', '.md', '.docx', '.pdf'}:
            return fail('unsupported', 'unsupported_format')
        raw = client.get(file_api+'/$value', binary=True)
        require(len(raw) == int(before['Length']), 'changed-during-read')
        after = pin(root_json(client.get(file_api+'?$select='+META)))
        require(before == after, 'changed-during-read')
        text, line_map, method, warnings = extract(raw, before['Name'], config.get('pdfTextExecutable'))
        raw_file = selected['sourceId']+'.raw'
        (output/raw_file).write_bytes(raw)
        (output/raw_file).chmod(0o600)
        return {'sourceId': selected['sourceId'], 'status': 'retrieved', 'canonicalUrl': canonical,
                'nativeUniqueId': before['UniqueId'], 'nativeVersionRef': before['MajorVersion']+'.'+before['MinorVersion']+' '+before['ETag'],
                'nativePin': before, 'retrievedAtUtc': datetime.now(timezone.utc).isoformat(),
                'authorityLabel': selected['authorityLabel'], 'sha256': digest(text.encode()),
                'binarySHA256': digest(raw), 'rawFile': raw_file, 'text': text, 'lineMap': line_map,
                'extraction': method, 'extractionWarnings': warnings}
    except EvidenceError as e:
        reason = str(e)
        status = reason if reason in {'denied', 'missing', 'changed-during-read'} else 'unsupported' if reason.startswith('unsupported_') or reason=='native_source_size_limit' else 'error'
        return fail(status, reason)


def lookup(config, query, selected, output, client=None):
    config = config_checked(config)
    require(isinstance(selected, list) and len(selected) <= 5, 'select_at_most_five_sources')
    ids = set()
    for source in selected:
        require(isinstance(source, dict) and isinstance(source.get('sourceId'),str) and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', source['sourceId']) and
                source['sourceId'] not in ids and source.get('authorityLabel') in LABELS, 'invalid_selected_source')
        ids.add(source['sourceId'])
        endpoint(config, source['path'])
        if source.get('nativeUniqueId'):
            require(isinstance(source['nativeUniqueId'],str) and
                    re.fullmatch(r'[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}', source['nativeUniqueId']) and
                    UUID(source['nativeUniqueId']).int != 0, 'invalid_selected_native_identity')
    require(not Path(output).exists(), 'new_output_directory_required')
    client = client or Client(config)
    Path(output).mkdir(mode=0o700)
    discovery = search(client, config, query)
    write(Path(output)/'search.json', discovery)
    sources = []
    paths = {unquote(urlsplit(h['Path']).path) for h in discovery['hits']}
    for selected_source in selected:
        result = retrieve(client, config, selected_source, Path(output))
        actual_path = urlsplit(result.get('canonicalUrl','')).path or selected_source['path']
        result['searchVisibility'] = ('returned-by-this-query' if unquote(actual_path) in paths else
                                      'not-returned-by-this-query; indexing-unconfirmed')
        sources.append(result)
    write(Path(output)/'sources.json', sources)
    report = {'schemaVersion': 1, 'kind': 'cli-evidence-lookup', 'scope': config['prefix'],
              'searchStatus': discovery['status'], 'selected': len(sources),
              'retrieved': sum(s['status']=='retrieved' for s in sources),
              'writesPerformed': 0, 'paidAIRuntimeUsed': False,
              'boundary': 'Captured evidence only; no native AI assistant, operative currency or lower-privilege access proof.'}
    write(Path(output)/'run.json', report)
    return report


def excerpts(sources, needle, context=1):
    require(isinstance(needle, str) and needle.strip() and len(needle) <= 500 and 0 <= context <= 3, 'bounded_literal_needle_required')
    claims = []
    for s in sources:
        if s['status'] != 'retrieved':
            continue
        lines = s['text'].splitlines()
        matches = [n for n, line in enumerate(lines) if needle.casefold() in line.casefold()]
        for n in matches[:3]:
            start, end = max(0, n-context), min(len(lines), n+context+1)
            citation = {k:s[k] for k in ('sourceId', 'canonicalUrl', 'nativeUniqueId', 'nativeVersionRef', 'sha256', 'binarySHA256', 'authorityLabel', 'extraction')}
            citation.update(startLine=start+1, endLine=end, quote='\n'.join(lines[start:end]), sourceLocators=s['lineMap'][start:end])
            claims.append({'claimId':'excerpt-'+str(len(claims)+1), 'kind':'exact-excerpt', 'text':citation['quote'],
                           'assertsCurrentAuthority':False, 'citations':[citation]})
    return {'status': ('partial' if any(s['status']!='retrieved' for s in sources) else 'supported') if claims else 'unknown',
            'claims':claims, 'actionsPerformed':[], 'policyApproved':False,
            'limitations':['Literal matches from captured extracted text only; relevance, semantic entailment and operative authority are not assessed. No match is not proof of absence.',
                           *[s['sourceId']+': '+s['status']+'; '+s.get('reason', '') for s in sources if s['status']!='retrieved']]}


def validate(answer, sources, scope, directory, config=None, client=None):
    result = check_answer(answer, sources, scope)
    issues = result['issues']
    indexed = {s['sourceId']:s for s in sources}
    for s in sources:
        if s['status'] != 'retrieved':
            continue
        try:
            require(Path(s['rawFile']).name == s['rawFile'], 'invalid_raw_path')
            p = Path(directory)/s['rawFile']
            require(p.is_file() and not p.is_symlink() and p.stat().st_size <= MAX_BYTES, 'raw_source_unavailable')
            raw = p.read_bytes()
            require(digest(raw) == s['binarySHA256'], 'binary_source_hash_mismatch')
            native = s['nativePin']
            require(s['nativeUniqueId'] == native['UniqueId'] and
                    s['nativeVersionRef'] == native['MajorVersion']+'.'+native['MinorVersion']+' '+native['ETag'] and
                    len(raw) == int(native['Length']) and
                    unquote(urlsplit(s['canonicalUrl']).path) == native['ServerRelativeUrl'], 'source_receipt_native_pin_mismatch')
            tool = config.get('pdfTextExecutable') if config else None
            if s['extraction'].startswith('pdftotext') and not tool:
                raise EvidenceError('pdf_revalidation_requires_configured_extractor')
            text, locators, method, _ = extract(raw, s['nativePin']['Name'], tool)
            require(text == s['text'] and locators == s['lineMap'] and method == s['extraction'], 'extraction_mismatch')
            if client:
                api, _ = endpoint(config, urlsplit(s['canonicalUrl']).path)
                require(pin(root_json(client.get(api+'?$select='+META))) == s['nativePin'], 'native_version_changed')
        except (EvidenceError, KeyError, OSError) as e:
            issues.append('source_validation_failed:'+s['sourceId']+':'+(str(e) if isinstance(e, EvidenceError) else 'artifact_invalid'))
    for claim in answer.get('claims', []):
        for c in claim.get('citations', []):
            s = indexed.get(c.get('sourceId'))
            if not s or s.get('status')!='retrieved':
                continue
            for key in ('nativeUniqueId', 'binarySHA256', 'extraction'):
                if c.get(key)!=s.get(key):
                    issues.append('citation_receipt_mismatch:'+key)
            a,b = c.get('startLine'), c.get('endLine')
            if type(a) is int and type(b) is int and c.get('sourceLocators')!=s['lineMap'][a-1:b]:
                issues.append('citation_native_locator_mismatch')
    result.update(mechanicallyValid=not issues, liveVersionCheck='performed' if client else 'not requested; captured consistency only', paidAIRuntimeUsed=False)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command', required=True)
    look=sub.add_parser('lookup');look.add_argument('--config', type=Path, required=True);look.add_argument('--query', required=True);look.add_argument('--selected', type=Path, required=True);look.add_argument('--output', type=Path, required=True)
    ex=sub.add_parser('excerpt');ex.add_argument('--bundle', type=Path, required=True);ex.add_argument('--config', type=Path, required=True);ex.add_argument('--needle', required=True);ex.add_argument('--context', type=int, default=1);ex.add_argument('--output', type=Path, required=True)
    val=sub.add_parser('validate');val.add_argument('--bundle', type=Path, required=True);val.add_argument('--answer', type=Path, required=True);val.add_argument('--config', type=Path, required=True);val.add_argument('--offline', action='store_true');val.add_argument('--output', type=Path, required=True)
    a=p.parse_args()
    try:
        if a.command=='lookup':
            report=lookup(json.loads(a.config.read_text()), a.query, json.loads(a.selected.read_text()), a.output)
        elif a.command=='excerpt':
            sources=json.loads((a.bundle/'sources.json').read_text());config=config_checked(json.loads(a.config.read_text()))
            run=json.loads((a.bundle/'run.json').read_text());require(run['scope']==config['prefix'], 'bundle_scope_mismatch')
            check=validate({'status':'unknown','claims':[],'actionsPerformed':[],'policyApproved':False},sources,run['scope'],a.bundle,config)
            require(check['mechanicallyValid'], 'captured_source_validation_failed')
            answer=excerpts(sources,a.needle,a.context);write(a.output,answer);report={'status':answer['status'],'excerpts':len(answer['claims'])}
        else:
            config=config_checked(json.loads(a.config.read_text()));run=json.loads((a.bundle/'run.json').read_text())
            require(run['scope']==config['prefix'], 'bundle_scope_mismatch')
            report=validate(json.loads(a.answer.read_text()),json.loads((a.bundle/'sources.json').read_text()),run['scope'],a.bundle,config,None if a.offline else Client(config));write(a.output,report)
        print(json.dumps(report))
        return 1 if report.get('mechanicallyValid') is False else 0
    except (EvidenceError, OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        print(json.dumps({'status':'failed','reason':'Lookup configuration, native read or local artifact validation failed; no SharePoint writes performed.'}))
        return 1


if __name__=='__main__':
    raise SystemExit(main())

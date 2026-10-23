"""Render existing historical findings without appraising or changing them."""
import hashlib
import html
import json
from urllib.parse import urlsplit


def text(value):
    raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    # The native page parser removes literal CR/LF/TAB. Normalise them before
    # serialisation so separate words never become joined in displayed evidence.
    return html.escape(' '.join(raw.split()))


def render(pack, evidence_url):
    uri = urlsplit(evidence_url)
    if uri.scheme != 'https' or not uri.netloc or uri.username or uri.password:
        raise ValueError('Expected safe qualified evidence link')
    if any(pack.get(k) is not False for k in ['policyApproved', 'publicationAuthorised', 'notificationsEnabled']) or pack.get('humanDecision') is not None:
        raise ValueError('Expected unapproved suggestion pack')
    pairs = pack['comparisonBatch']['pairAssessments']
    reviews = pack['sourceOnlyReviews']
    groups = []
    for pair in pairs:
        comparator = pair['comparator']
        groups.append((comparator['title'], 'Provisional catalogue comparison; recorded comparator version: '+str(comparator['documentVersion']), pair['findings']))
    for review in reviews:
        groups.append(('Source-only review '+str(review['sourceIndex']), 'Catalogue identity unresolved; historical source assertions retained in the complete pack.', review['findings']))
    findings = [f for _, _, values in groups for f in values]
    ids = [f['findingId'] for f in findings]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate finding identity')
    parts = ['<p><strong>Unapproved historical V6 review. Current procedure/template verification is open and nonblocking. Suggestions are not decisions.</strong></p>',
             '<h2>Historical discharge-summary review findings</h2>',
             '<p>Passage whitespace is normalised for web display. The complete pack retains the original quotations and source pins.</p>',
             '<p>This page presents the existing findings without a new appraisal. Comparator identities/versions remain provisional; source-only reviews do not establish catalogue membership. Read missing evidence and uncertainty with each finding.</p>',
             '<p>'+str(len(pairs))+' provisional comparisons; '+str(len(reviews))+' source-only reviews; '+str(len(findings))+' retained findings. The complete pack accounts for '+str(pack['preparation']['catalogueCount'])+' catalogue identities, including metadata-only and held items.</p>',
             '<p><a href="'+html.escape(evidence_url, quote=True)+'">Complete version-bound pack, coverage, source files and recovery</a></p>']
    for number, (title, scope, values) in enumerate(groups, 1):
        parts.extend(['<h3>'+str(number)+'. '+text(title)+'</h3>', '<p>'+text(scope)+'</p>'])
        if not values:
            parts.append('<p>No retained finding in this group. This does not establish completeness or compliance.</p>')
        for finding in values:
            if finding.get('humanDecision') is not None or finding['claimType'] not in {'evidence', 'inference', 'unknown'}:
                raise ValueError('Unexpected finding decision or claim type')
            if finding['claimType'] != 'unknown' and not finding['citations']:
                raise ValueError('Substantive finding lacks evidence')
            parts.append('<p><strong>'+text(finding['findingId'])+'</strong> — '+text(finding['claimType'])+'; criterion '+text(finding['criterionId'])+'</p>')
            for key, label in [('statement','Finding'),('suggestedAction','Suggested action'),('benefit','Benefit'),('effort','Effort'),('dependencies','Dependencies'),('uncertainty','Uncertainty')]:
                parts.append('<p><strong>'+label+':</strong> '+text(finding[key])+'</p>')
            if finding.get('scope'):
                parts.append('<p><strong>Scope:</strong> '+text(finding['scope'])+'</p>')
            for citation in finding['citations']:
                if not citation.get('sourceId') or not citation.get('locator') or not citation.get('sourceSha256'):
                    raise ValueError('Citation lacks version-bound source/locator')
                parts.append('<p><strong>Evidence:</strong> '+text(citation['sourceId'])+'; '+text(citation['locator'])+'; SHA-256 '+text(citation['sourceSha256'])+'</p>')
                if citation.get('quote'):
                    parts.append('<blockquote>'+text(citation['quote'])+'</blockquote>')
                extra = {k:v for k,v in citation.items() if k not in {'sourceId','locator','sourceSha256','quote'}}
                if extra:
                    parts.append('<p><strong>Evidence context:</strong> '+text(extra)+'</p>')
    parts.append('<p>Use the existing annotation and case records for human contributions and decisions. This page changes no policy, source mapping, approval, publication, responsibility, notification or access.</p>')
    result = '\n'.join(parts)
    return result, dict(schemaVersion=1, kind='existing_findings_web_view',
                        sourcePackCanonicalSHA256=hashlib.sha256(json.dumps(pack, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest(),
                        comparisons=len(pairs), sourceOnlyReviews=len(reviews), findings=len(findings),
                        citations=sum(len(f['citations']) for f in findings),
                        outputHTMLSHA256=hashlib.sha256(result.encode()).hexdigest(),
                        newAppraisal=False, humanDecision=None, policyApproved=False,
                        publicationAuthorised=False, notificationsEnabled=False)

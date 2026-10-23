"""Local-only binary transport preparation and downloaded-byte verification.

No network, native save/copy, approval, event write or fixture creation. Transport
fragments are deliberately not deployable flows: the purpose owner must compose
its reviewed same-execution authorisation/readiness/history guard around them.
"""
import copy
import hashlib
import json
import re
from urllib.parse import unquote, urlsplit

SCOPE = ('CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256')
PIN = ('UniqueId', 'ETag', 'nativeVersion', 'Length', 'DocumentReference')
PUBLICATION_INPUT_FIELDS = frozenset(('FictionalTest', 'EventUID', 'OccurredOn', 'Title',
                                    'ActorName', 'Summary', 'EvidenceReference', 'NextAction'))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def require(value, reason):
    if not value:
        raise ValueError(reason)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def token(value):
    return text(value) and value != '*'


def metadata(value):
    require(isinstance(value, dict), 'Missing native file metadata')
    require(all(text(value.get(k)) for k in PIN if k != 'Length'), 'Incomplete native file pins')
    require(token(value['ETag']), 'Missing or wildcard opaque ETag')
    require(isinstance(value['Length'], int) and not isinstance(value['Length'], bool)
            and value['Length'] > 0, 'Positive integer byte length required')
    require(bool(re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', value['UniqueId'])),
            'Native file UID required')
    return {k: value[k] for k in PIN}


def normalize_sharepoint_file(raw, origin):
    """Explicit mapping of the selected native SP.File fields; no token parsing."""
    parsed = urlsplit(origin)
    require(parsed.scheme == 'https' and parsed.netloc and not parsed.path and not parsed.query
            and not parsed.fragment and not parsed.username and not parsed.password,
            'Literal HTTPS origin without path required')
    require(isinstance(raw, dict) and isinstance(raw.get('Length'), str)
            and re.fullmatch(r'[1-9][0-9]*', raw['Length']), 'Native positive decimal string Length required')
    path = raw.get('ServerRelativeUrl')
    require(text(path) and path.startswith('/') and not path.startswith('//')
            and all(x not in path for x in ('..', '?', '#', '%', '\\')),
            'Exact canonical native server-relative file path required')
    return metadata({'UniqueId': raw.get('UniqueId'), 'ETag': raw.get('ETag'),
                     'nativeVersion': raw.get('UIVersionLabel'), 'Length': int(raw['Length']),
                     'DocumentReference': origin + path})


def complete(collection):
    require(isinstance(collection, dict) and isinstance(collection.get('value'), list), 'Missing complete collection')
    require(not any(collection.get(k) for k in ('nextLink', '@nextLink', 'odata.nextLink', '@odata.nextLink')),
            'Incomplete collection; never choose a favorable page')
    return collection['value']


def assess_current_case(preparation):
    """Conservative actual-scope preparation only, never an authorisation resolver."""
    case = preparation.get('currentCase', {})
    decision = case.get('retainedAdverseDecision', {})
    blocked = decision.get('DecisionOutcome') in ('Deferred', 'Rejected', 'Return for changes') or decision.get('ConditionsState') == 'Open'
    return {'kind': 'local-binary-publication-candidate-v1', 'phase': 'held', 'deployable': False,
            'nativeWrites': 0, 'copyActions': [], 'publicationActions': [],
            'preparedScope': case.get('currentPreparedScope'), 'blockingRetainedEvent': decision or None,
            'reason': ('Retained adverse decision/open conditions; no copy or publication' if blocked else
                       'Await exact retained final-purpose authorisation and reviewed runtime composition'),
            'nativeBinaryCopyQualified': False, 'historicalTextProofReusedForBinary': False}


def copy_fragment(site, source, target_path, qualification_folder, reference):
    """Prepare the smallest body-free same-site server-copy action; does not run it."""
    source = metadata(source)
    parsed = urlsplit(site)
    require(parsed.scheme == 'https' and parsed.netloc and not parsed.query and not parsed.fragment,
            'Literal HTTPS site required')
    require(site == site.rstrip('/'), 'Use canonical site URL without trailing slash')
    src = urlsplit(source['DocumentReference'])
    require((src.scheme, src.netloc) == (parsed.scheme, parsed.netloc) and not src.query and not src.fragment,
            'Same-site source required')
    require(src.path.startswith(parsed.path + '/') and unquote(src.path) == src.path,
            'Canonical decoded same-site source path required')
    require(isinstance(target_path, str) and isinstance(qualification_folder, str), 'Explicit destination required')
    require(qualification_folder.startswith(parsed.path + '/') and target_path.startswith(qualification_folder + '/FICTIONAL-'),
            'Explicit isolated fictional same-site destination required')
    require(target_path.rsplit('/', 1)[0] == qualification_folder and target_path.lower().endswith('.docx'),
            'One exact DOCX destination, not a subfolder or transformed rendition')
    require(target_path != src.path and all('..' not in p and '%' not in p and '\\' not in p and '?' not in p and '#' not in p
                                          for p in (target_path, qualification_folder)), 'Unsafe or overlapping destination')
    props = reference['properties']
    require(props.get('state') == 'Stopped', 'Stopped full target preimage required')
    refs = props['connectionReferences']
    require(set(refs) == {'shared_sharepointonline'} and refs['shared_sharepointonline'].get('source') == 'Embedded',
            'Preserve existing qualified SharePoint-only references')
    def lit(v):
        return "'" + v.replace("'", "''") + "'"
    file_uri = "_api/web/GetFileById(" + lit(source['UniqueId']) + ')'
    http = {'type': 'OpenApiConnection', 'runAfter': {}, 'inputs': {
        'host': {'apiId': '/providers/Microsoft.PowerApps/apis/shared_sharepointonline',
                 'connectionName': 'shared_sharepointonline', 'operationId': 'HttpRequest'},
        'parameters': {'dataset': site, 'parameters/method': 'POST',
                       'parameters/uri': file_uri + '/copyTo(strNewUrl=' + lit(target_path) + ',bOverWrite=false)',
                       'parameters/headers': {'Accept': 'application/json;odata=minimalmetadata'}},
        'retryPolicy': {'type': 'none'}}}
    return {'kind': 'local-body-free-copy-fragment-v1', 'deployable': False, 'qualificationOnly': True,
            'targetPreimageDefinitionSHA256': digest(props['definition']),
            'connectionReferences': copy.deepcopy(refs), 'source': source, 'targetPath': target_path,
            'action': http, 'requiredPreconditions': [
                'Reviewed same-execution current prepared/readiness/complete purpose chain with actual final authorisation',
                'Fresh same-case/source/baseline/template/receipt/history frame; unresolved adverse/open state holds',
                'Complete exact-name target enumeration is empty; an existing target must be reconciled, never copied over'],
            'requiredAfterconditions': [
                'Pin source metadata before and after copy; read actual target UID/ETag/version/length',
                'Independently download source and target and compare exact bytes and SHA256',
                'On copy failure/timeout retain outcome unknown; no automatic retry or publication event',
                'Recheck the full owner frame immediately before publication event; preserve all originals']}


def verify_downloads(scope, source_before, source_after, target_before, target_after, source_bytes, target_bytes):
    """Verify measured bytes, not a trusted hash string or successful copy response."""
    require(all(text(scope.get(k)) for k in SCOPE), 'Exact reviewed prepared scope required')
    src = metadata(source_before); dst = metadata(target_before)
    require(src == metadata(source_after), 'Prepared source changed during binary proof')
    require(dst == metadata(target_after), 'Issued output changed during binary proof')
    require(src['UniqueId'] != dst['UniqueId'] and src['DocumentReference'] != dst['DocumentReference'],
            'Issued output must be a separate physical object')
    require(scope['DocumentReference'] == src['DocumentReference'], 'Prepared scope/source mismatch')
    require(scope['ReviewedVersionRef'] == 'sharepoint:' + src['UniqueId'] + ':' + src['ETag'], 'Prepared version mismatch')
    require(isinstance(source_bytes, bytes) and isinstance(target_bytes, bytes), 'Actual downloaded bytes required')
    require(len(source_bytes) == src['Length'] and len(target_bytes) == dst['Length'], 'Downloaded byte length mismatch')
    require(source_bytes == target_bytes, 'Independent binary byte parity failed')
    sha = hashlib.sha256(source_bytes).hexdigest()
    require(sha == scope['DocumentSHA256'], 'Downloaded prepared SHA256 differs from reviewed scope')
    return {'kind': 'local-downloaded-binary-parity-v1', 'scope': dict(scope), 'source': src,
            'issued': {**dst, 'SHA256': sha}, 'independentByteParity': True,
            'publicationEventCreated': False, 'nativeBinaryTransportQualified': False,
            'limit': 'Byte proof only; native copy provenance, full final-purpose/frame checks and event readback remain required'}


def event_plan(scope, authorisation, purpose_chain, assurance_history, proof, publication, retained_publications):
    """Offline append intent only; never authorises native execution from local data."""
    require(isinstance(publication, dict) and set(publication) <= PUBLICATION_INPUT_FIELDS,
            'Only explicit publication inputs allowed; corrections and native identity fields are unsupported')
    require(proof.get('kind') == 'local-downloaded-binary-parity-v1' and proof.get('scope') == scope
            and proof.get('independentByteParity') is True, 'Actual binary proof required before event preparation')
    measured_source = metadata(proof.get('source')); measured_issued = metadata(proof.get('issued'))
    require(measured_source['DocumentReference'] == scope['DocumentReference']
            and measured_source['UniqueId'] != measured_issued['UniqueId']
            and measured_source['Length'] == measured_issued['Length']
            and proof['issued'].get('SHA256') == scope['DocumentSHA256'], 'Binary proof relation mismatch')
    rows = complete(assurance_history); retained = complete(retained_publications)
    require(len(purpose_chain) == 4 and len(set(purpose_chain)) == 4, 'All four explicit retained purposes required')
    selected = []
    for index, uid in enumerate(purpose_chain):
        matches = [r for r in rows if r.get('EventUID') == uid]
        require(len(matches) == 1, 'Missing or ambiguous retained purpose')
        row = matches[0]
        require(all(row.get(k) == scope[k] for k in SCOPE), 'Purpose scope differs from exact prepared revision')
        require(row.get('Stage') == 'Decision' and row.get('RecordState') == 'Recorded'
                and row.get('FictionalTest') is True and row.get('ConditionsState') in ('None recorded', 'Resolved')
                and row.get('DecisionOutcome') == ('Approved (recorded)' if index == 3 else 'Endorsed (recorded)'),
                'Unresolved or non-authorising purpose')
        require(row.get('ParentEventUID') == (purpose_chain[index-1] if index else None)
                and not row.get('SupersedesEventUID'), 'Broken or superseded purpose chain')
        require(token(row.get('odata.etag')) and isinstance(row.get('Id'), int) and row['Id'] > 0
                and all(text(row.get(k)) for k in ('GUID', 'DecisionReference', 'ReadinessEventUID', 'EvidenceReference', 'OccurredOn')),
                'Actual retained purpose identity/evidence required')
        if selected:
            require(row['ReadinessEventUID'] == selected[0]['ReadinessEventUID'], 'Mixed readiness chain')
        selected.append(row)
    require(authorisation == selected[-1], 'Selected final authorisation must match the complete retained row')
    for row in rows:
        require(row.get('SupersedesEventUID') not in purpose_chain, 'Retained purpose superseder requires resolution')
        if all(row.get(k) == scope[k] for k in SCOPE):
            require(row.get('ConditionsState') in ('None recorded', 'Resolved')
                    and row.get('DecisionOutcome') not in ('Deferred', 'Rejected', 'Return for changes'),
                    'Retained adverse/open exact-scope history holds publication')
            require(row.get('Stage') != 'Decision' or row.get('EventUID') in purpose_chain,
                    'Unselected competing decision requires reconciliation')
    require(publication.get('FictionalTest') is True and text(publication.get('EventUID'))
            and publication['EventUID'].startswith('LC04-PUBLICATION-') and text(publication.get('OccurredOn')),
            'Explicit reserved fictional publication identity and supplied occurrence required')
    issued = proof['issued']
    payload = {**scope, **publication, 'ParentEventUID': authorisation['EventUID'], 'Stage': 'Publication',
               'RecordState': 'Recorded', 'ConditionsState': 'None recorded',
               'PublicationURL': issued['DocumentReference'],
               'PublishedVersionRef': 'sharepoint:' + issued['UniqueId'] + ':' + issued['ETag']}
    require(all(payload[k] == scope[k] for k in SCOPE), 'Publication input cannot override reviewed scope')
    existing = [r for r in retained if r.get('EventUID') == payload['EventUID']]
    require(len(existing) <= 1, 'Duplicate publication identity')
    if existing:
        require(all(existing[0].get(k) == v for k, v in payload.items() if k != 'OccurredOn'),
                'Changed publication payload; preserve output and prior event')
        payload['OccurredOn'] = existing[0].get('OccurredOn')
        require(text(payload['OccurredOn']), 'Missing retained publication occurrence')
    return {'kind': 'local-binary-publication-event-intent-v1', 'deployable': False,
            'payload': payload, 'createIntentCount': 0 if existing else 1, 'retryPolicy': {'type': 'none'},
            'nativeWrites': 0, 'requiredBeforeNativeAppend': [
                'Owner-qualified same-execution complete readiness and consultation coverage',
                'Complete purpose/history identities, profile, chronology and immutable payload checks',
                'Fresh frame, authorisation row token, output/source byte-proof pins and full histories',
                'Unique EventUID native constraint; re-read immediately before append; after-readback reconciliation'],
            'limit': 'Local intent is not runtime authorisation, native copy qualification or actual controlled publication'}

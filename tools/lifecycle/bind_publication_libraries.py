"""Bind existing publication readers to reviewed same-library destinations.

Offline only. This adds no writer, connection, permission or decision and performs
no native mutation.
The byte guards remain mandatory: SharePoint can rewrite DOCX package metadata
when copying between libraries, even while preserving every Word content part.
"""
import copy
import re
from urllib.parse import urlsplit

from build_multisource_case_context import digest
from build_operator_entry import _flatten, _literal, action_references
from build_selected_event_routes import audit_actions
from build_native_closure_entry import _check_expression_lengths


NAMESPACE = "outputs('Native_prepared_revision')?['publicationNamespace']"


def namespace_values(site, libraries, document_expression):
    parsed = urlsplit(site)
    if (parsed.scheme != 'https' or not parsed.netloc or parsed.query or parsed.fragment
            or not isinstance(libraries, list) or len(libraries) != 2):
        raise ValueError('Exactly two reviewed existing same-site libraries required')
    origin = parsed.scheme + '://' + parsed.netloc
    roots, folders, ids = [], [], []
    for row in libraries:
        if not isinstance(row, dict) or set(row) != {'libraryRoot', 'qualificationFolder', 'libraryId', 'evidenceSHA256'}:
            raise ValueError('Exact native library/folder evidence binding required')
        root, folder = row['libraryRoot'], row['qualificationFolder']
        for path in (root, folder):
            if (not isinstance(path, str) or not path.startswith(parsed.path + '/')
                    or path.endswith('/') or '//' in path
                    or any(x in path for x in ('..', '%', '\\', '?', '#', "'", '\n', '\r'))):
                raise ValueError('Canonical reviewed same-site folder required')
        if not folder.startswith(root + '/'):
            raise ValueError('Destination must remain inside its reviewed library')
        if (not isinstance(row['libraryId'], str) or not isinstance(row['evidenceSHA256'], str)
                or not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', row['libraryId'])
                or not re.fullmatch(r'[0-9a-f]{64}', row['evidenceSHA256'])):
            raise ValueError('Actual library identity and retained evidence hash required')
        roots.append(root); folders.append(folder); ids.append(row['libraryId'].lower())
    if (len(set(ids)) != 2 or len({p.casefold() for p in roots}) != 2
            or any(a.casefold().startswith(b.casefold() + '/') for a in roots for b in roots if a != b)):
        raise ValueError('Distinct nonoverlapping library roots required')
    if (not isinstance(document_expression, str) or not document_expression
            or any(x in document_expression for x in ('triggerBody(', 'triggerOutputs(', '@{'))):
        raise ValueError('Use the resolved preparation file, never a caller-supplied path')
    # Follow the actual resolved preparation output, including closure's retained
    # historical branch. A later human case-pointer edit cannot redirect history.
    document = "string(coalesce(" + document_expression + ",''))"
    matches = ['startsWith(' + document + ',' + _literal(origin + root + '/') + ')' for root in roots]
    canonical = ['not(contains(' + document + ',' + _literal(x) + '))' for x in ('..', '%', '\\', '?', '#')]
    return {'eligible': '@and(or(' + ','.join(matches) + '),' + ','.join(canonical) + ')',
            'folder': '@if(' + matches[0] + ',' + _literal(folders[0]) + ',if('
                      + matches[1] + ',' + _literal(folders[1]) + ",''))"}


def _namespace_operand(values):
    return ("setProperty(setProperty(json('{}'),'eligible'," + values['eligible'][1:]
            + "),'folder'," + values['folder'][1:] + ')')


def _document_operand(prepared):
    def operand(value):
        if not isinstance(value, str) or not value or value.startswith('@@') or '@{' in value:
            raise ValueError('Reviewed preparation expression required')
        return value[1:] if value.startswith('@') else _literal(value)
    if isinstance(prepared, str) and prepared.startswith('@'):
        return operand(prepared) + "?['preparedRevision']?['file']?['DocumentReference']"
    if not isinstance(prepared, dict) or 'preparedRevision' not in prepared:
        raise ValueError('Reviewed preparation revision required')
    revision = prepared['preparedRevision']
    if isinstance(revision, str) and revision.startswith('@'):
        return operand(revision) + "?['file']?['DocumentReference']"
    if not isinstance(revision, dict) or 'file' not in revision:
        raise ValueError('Reviewed prepared file required')
    file = revision['file']
    if isinstance(file, str) and file.startswith('@'):
        return operand(file) + "?['DocumentReference']"
    if isinstance(file, dict) and 'DocumentReference' in file:
        return operand(file['DocumentReference'])
    raise ValueError('Reviewed prepared file reference required')


def build(flow, binding):
    if set(binding) != {'approvedDefinitionSHA256', 'libraries', 'stage'}:
        raise ValueError('Exact reviewed namespace repair binding required')
    if binding['approvedDefinitionSHA256'] != digest(flow['properties']['definition']):
        raise ValueError('Reviewed retained definition changed')
    if binding['stage'] not in ('publication', 'implementation', 'verification', 'closure'):
        raise ValueError('Only the existing publication recording chain is supported')
    out = copy.deepcopy(flow)
    definition = out['properties']['definition']; nodes = _flatten(definition['actions'])
    reader = nodes['Read_selected_case']['inputs']['parameters']
    if reader.get('parameters/method') != 'GET':
        raise ValueError('Retain the existing native case reader')
    prepared = nodes['Native_prepared_revision']['inputs']
    site = reader['dataset']; values = namespace_values(site, binding['libraries'], _document_operand(prepared))
    if isinstance(prepared, dict):
        if 'publicationNamespace' in prepared:
            raise ValueError('Namespace already bound; reconcile instead of rebinding')
        prepared['publicationNamespace'] = values
    elif isinstance(prepared, str) and prepared.startswith('@') and not prepared.startswith('@@'):
        nodes['Native_prepared_revision']['inputs'] = (
            '@setProperty(' + prepared[1:] + ",'publicationNamespace'," + _namespace_operand(values) + ')')
    else:
        raise ValueError('Reviewed object-valued preparation interface required')
    eligible = 'equals(' + NAMESPACE + "?['eligible'],true)"
    folder = NAMESPACE + "?['folder']"
    if binding['stage'] == 'closure':
        initial = nodes['ClosureEntry_initial']['expression']
        origin = urlsplit(site).scheme + '://' + urlsplit(site).netloc
        # Retain journal/recovery/date namespaces exactly. Only the publication
        # evidence prefix in the existing initial guard follows the binary file.
        prefix = "startsWith(string(first(body('Closure_selected_publication'))?['EvidenceReference']),"
        pattern = re.escape(prefix) + r"'([^']+/)'\)"
        matches = list(re.finditer(pattern, initial))
        if len(matches) != 1 or not matches[0].group(1).startswith(origin + urlsplit(site).path + '/'):
            raise ValueError('Exact original publication-evidence prefix guard required')
        replacement = prefix + "concat(" + _literal(origin) + ',' + folder + ",'/'))"
        initial = initial[:matches[0].start()] + replacement + initial[matches[0].end():]
        nodes['ClosureEntry_initial']['expression'] = '@and(' + initial[1:] + ',' + eligible + ')'
    else:
        path = nodes['Issued_path']['inputs']
        match = re.fullmatch(r"@concat\('([^']+)/FICTIONAL-issued-',toLower\(outputs\('Native_prepared_revision'\)\?\['preparedRevision'\]\?\['file'\]\?\['UniqueId'\]\),'-v',outputs\('Native_prepared_revision'\)\?\['preparedRevision'\]\?\['file'\]\?\['nativeVersion'\],'.docx'\)", path)
        if not match:
            raise ValueError('Exact retained issued-file naming contract required')
        old = match.group(1)
        expected_find = ("@concat('_api/web/GetFolderByServerRelativePath(decodedurl=''" + old
            + "'')/Files?$filter=Name eq ''',last(split(outputs('Issued_path'),'/')),'''&$select=Name,UniqueId,ETag,UIVersionLabel,Length,ServerRelativeUrl')")
        expected_proof = ("@concat('" + old + "/PPG-binary-proof-',toLower(body('Read_issued')?['UniqueId']),'-v',body('Read_issued')?['UIVersionLabel'],'.json')")
        if (nodes['Find_issued']['inputs']['parameters']['parameters/uri'] != expected_find
                or nodes['Binary_proof_path']['inputs'] != expected_proof):
            raise ValueError('Retain the complete destination lookup and proof naming contract')
        nodes['Issued_path']['inputs'] = '@concat(' + folder + ",'/FICTIONAL-issued-'" + path.split("/FICTIONAL-issued-'", 1)[1]
        nodes['Find_issued']['inputs']['parameters']['parameters/uri'] = (
            "@concat('_api/web/GetFolderByServerRelativePath(decodedurl='''," + folder
            + ",''')/Files?$filter=Name eq ''',last(split(outputs('Issued_path'),'/')),'''&$select=Name,UniqueId,ETag,UIVersionLabel,Length,ServerRelativeUrl')")
        nodes['Binary_proof_path']['inputs'] = '@concat(' + folder + ",'/PPG-binary-proof-'" + expected_proof.split("/PPG-binary-proof-'", 1)[1]
        gate = nodes['Verify_all_retained_purposes']
        if gate.get('type') != 'If' or not gate['expression'].startswith('@and('):
            raise ValueError('Retain the complete pre-destination purpose gate')
        gate['expression'] = '@and(' + gate['expression'][1:] + ',' + eligible + ')'
    out['properties']['state'] = 'Stopped'
    before = audit_actions(flow['properties']['definition']); after = audit_actions(definition)
    if before != after or after['actionCount'] > 500 or after['maximumActionDepth'] > 8:
        raise ValueError('Retain native action topology and geometry')
    _check_expression_lengths(definition)
    if action_references(definition['actions']) - nodes.keys():
        raise ValueError('Unresolved namespace prerequisite')
    return out

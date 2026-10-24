"""Prepare a fixed selected-source Power Automate reader; no network or writes.

Bindings and generated definitions contain private deployment details and stay
outside source control. This prepares a stopped cloud-flow definition, not a
deployment or a qualified conversational assistant. Original native bytes and
the existing CLI extraction/hash route remain authoritative at their own scope.
"""

import copy
from datetime import datetime
from pathlib import PurePosixPath
from urllib.parse import urlsplit
from uuid import UUID


PIN_FIELDS = (
    'UniqueId', 'Name', 'Length', 'ETag', 'MajorVersion', 'MinorVersion',
    'TimeLastModified', 'ServerRelativeUrl',
)
MAX_BYTES = 2_000_000
LABELS = {'captured-reference-unconfirmed', 'draft-unapproved',
          'authority-recorded-not-independently-verified'}


def workflow_literal(value):
    """Escape expression-looking source metadata as Workflow Definition literals."""
    if isinstance(value, str):
        return '@' + value if value.startswith('@') else value
    if isinstance(value, dict):
        return {key: workflow_literal(item) for key, item in value.items()}
    return value


def checked_binding(binding):
    """Reject ambiguous paths, unsupported formats and incomplete native pins."""
    value = copy.deepcopy(binding)
    site = value.get('siteUrl', '')
    if not isinstance(site, str):
        raise ValueError('invalid_site_binding')
    parsed = urlsplit(site)
    pieces = parsed.path.split('/')
    if (parsed.scheme != 'https' or not parsed.hostname
            or not parsed.hostname.endswith('.sharepoint.com')
            or parsed.netloc != parsed.hostname or parsed.query or parsed.fragment
            or len(pieces) != 3 or pieces[1] not in {'sites', 'teams'}
            or not pieces[2] or any(c in site for c in "'\"%\\\r\n\t")
            or any(ord(c) < 32 for c in site)):
        raise ValueError('invalid_site_binding')
    folder = value.get('folder')
    if (not isinstance(folder, str) or not folder.startswith(parsed.path + '/')
            or any(c in folder for c in "'\"%?#\\")
            or any(ord(c) < 32 for c in folder)
            or any(p in {'', '.', '..'} for p in folder.split('/')[1:])):
        raise ValueError('invalid_folder_binding')
    source_id = value.get('sourceId')
    if (not isinstance(source_id, str) or not source_id.strip()
            or len(source_id) > 120 or any(ord(c) < 32 for c in source_id)):
        raise ValueError('invalid_source_identity')
    if value.get('authorityLabel') not in LABELS:
        raise ValueError('invalid_authority_label')
    pin = value.get('pin')
    if not isinstance(pin, dict) or any(k not in pin for k in PIN_FIELDS):
        raise ValueError('incomplete_native_pin')
    try:
        identity = UUID(pin['UniqueId'])
        if identity.int == 0:
            raise ValueError()
        length = pin['Length']
        if type(length) is str and length.isascii() and length.isdecimal():
            length = int(length)
        if type(length) is not int or not 0 <= length <= MAX_BYTES:
            raise ValueError()
        for field in ('MajorVersion', 'MinorVersion'):
            if type(pin[field]) is not int or pin[field] < 0:
                raise ValueError()
        for field in ('Name', 'ETag', 'TimeLastModified', 'ServerRelativeUrl'):
            if not isinstance(pin[field], str) or not pin[field].strip():
                raise ValueError()
        if datetime.fromisoformat(pin['TimeLastModified'].replace('Z', '+00:00')).utcoffset() is None:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise ValueError('invalid_native_pin') from None
    path = pin['ServerRelativeUrl']
    if (not path.startswith(folder + '/') or any(c in path for c in "'\"%?#\\")
            or any(ord(c) < 32 for c in path)
            or any(p in {'', '.', '..'} for p in path.split('/')[1:])
            or PurePosixPath(path).name != pin['Name']):
        raise ValueError('source_outside_selected_folder')
    if PurePosixPath(path).suffix.lower() not in {'.txt', '.md'}:
        raise ValueError('source_format_requires_separate_extraction')
    pin['UniqueId'] = str(identity)
    pin['Length'] = str(length)
    value['pin'] = {key: str(pin[key]) for key in PIN_FIELDS}
    value['connectorPath'] = path[len(parsed.path):]
    return value


def build_flow(existing, binding):
    """Reuse only the selected SharePoint reference; never copy old actions/plan."""
    selected = checked_binding(binding)
    reference = copy.deepcopy(existing['properties']['connectionReferences']['shared_sharepointonline'])
    if not isinstance(reference, dict) or not reference:
        raise ValueError('existing_sharepoint_reference_required')
    pin = selected['pin']

    def after(action):
        return {} if action is None else {action: ['Succeeded']}

    def connector(operation, parameters, previous=None):
        return {'type': 'OpenApiConnection', 'runAfter': after(previous), 'inputs': {
            'host': {'apiId': '/providers/Microsoft.PowerApps/apis/shared_sharepointonline',
                     'connectionName': 'shared_sharepointonline', 'operationId': operation},
            'parameters': {'dataset': selected['siteUrl'], **parameters},
            'authentication': "@parameters('$authentication')", 'retryPolicy': {'type': 'none'},
        }}

    uri = "_api/web/GetFileById('" + pin['UniqueId'] + "')?$select=" + ','.join(PIN_FIELDS)

    def metadata(previous=None):
        return connector('HttpRequest', {'parameters/method': 'GET', 'parameters/uri': uri,
                         'parameters/headers': {'Accept': 'application/json;odata=nometadata'}}, previous)

    def guard(action, previous, code):
        comparisons = []
        for field, expected in pin.items():
            actual = "@string(body('" + action + "')?['" + field + "'])"
            if field == 'UniqueId':
                actual = "@toLower(string(body('" + action + "')?['" + field + "']))"
            comparisons.append({'equals': [actual, workflow_literal(expected)]})
        return {'type': 'If', 'runAfter': after(previous), 'expression': {'and': comparisons},
                'actions': {}, 'else': {'actions': {'Refuse_' + code: {
                    'type': 'Terminate', 'runAfter': {}, 'inputs': {'runStatus': 'Failed',
                    'runError': {'code': code, 'message': 'Selected source pin changed or is incomplete; no accepted result.'}},
                }}}}

    actions = {
        'Metadata_before': metadata(),
        'Require_expected_source': guard('Metadata_before', 'Metadata_before', 'SOURCE_PIN'),
        'Read_content': connector('GetFileContentByPath', {
            'path': selected['connectorPath'], 'inferContentType': False,
        }, 'Require_expected_source'),
        'Metadata_after': metadata('Read_content'),
        'Require_unchanged_source': guard('Metadata_after', 'Metadata_after', 'SOURCE_CHANGED'),
        'Selected_source_result': {'type': 'Compose', 'runAfter': after('Require_unchanged_source'), 'inputs': {
            'schemaVersion': 1, 'sourceId': workflow_literal(selected['sourceId']),
            'canonicalUrl': 'https://' + urlsplit(selected['siteUrl']).netloc + pin['ServerRelativeUrl'],
            'nativeUniqueId': pin['UniqueId'], 'nativeVersionRef': pin['MajorVersion'] + '.' + pin['MinorVersion'],
            'nativePin': workflow_literal(pin), 'authorityLabel': selected['authorityLabel'], 'retrievedAtUtc': '@utcNow()',
            'content': "@body('Read_content')", 'contentBoundary': 'Opaque native connector content; no extracted-text or citation-locator claim.',
            'sha256': None, 'binarySHA256': None, 'textExtractionQualified': False,
            'nativeAssistantRuntimeQualified': False, 'status': 'selected-source-read',
        }},
    }
    definition = {
        '$schema': 'https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#',
        'contentVersion': '1.0.0.0',
        'parameters': {'$authentication': {'defaultValue': {}, 'type': 'SecureObject'},
                       '$connections': {'defaultValue': {}, 'type': 'Object'}},
        'triggers': {'manual': {'type': 'Request', 'kind': 'Button', 'inputs': {
            'schema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
            'runtimeConfiguration': {'concurrency': {'runs': 1}}}},
        'actions': actions, 'outputs': {},
    }
    return {'properties': {'displayName': 'PPG | Cited evidence | Selected-source reader',
            'state': 'Stopped', 'definition': definition,
            'connectionReferences': {'shared_sharepointonline': reference}}}

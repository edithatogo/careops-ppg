"""Inspect SharePoint property-bound covers without filling or modifying them.

SharePoint property demotion is not evidence of refreshed visible Word text.
Only a fully rendered, exact-value cover can pass the package admission check.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile
from xml.etree import ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
DS = '{http://schemas.openxmlformats.org/officeDocument/2006/customXml}'
REL = '{http://schemas.openxmlformats.org/package/2006/relationships}'
FIELDS = ('PPGCoverTitle', 'PPGCoverCaseUID', 'PPGDocumentUID', 'PPGPolicyEdition',
          'PPGCoverRecordedOwner', 'PPGCoverReviewDate', 'PPGCoverOutputRevision')


def accepted_values(values):
    if set(values) != set(FIELDS):
        raise ValueError('cover_fields_mismatch')
    if any(not isinstance(v, str) or not v.strip() or len(v) > 255 for v in values.values()):
        raise ValueError('cover_values_require_explicit_text_max255')
    # Missing operational facts must be explicitly represented as Unresolved.
    date = values['PPGCoverReviewDate']
    if date != 'Unresolved':
        from datetime import date as Date
        Date.fromisoformat(date)
    return values


def inspect_cover(raw, values):
    accepted_values(values)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if len(set(z.namelist())) != len(z.namelist()) or sum(i.file_size for i in z.infolist()) > 10_000_000:
            raise ValueError('unsafe_cover_archive')
        if z.testzip() is not None:
            raise ValueError('corrupt_cover')
        stores = {}
        for name in z.namelist():
            if not re.fullmatch(r'customXml/item[0-9]+\.xml', name):
                continue
            base = name.rsplit('/', 1)[-1]
            rel_name = 'customXml/_rels/' + base + '.rels'
            if rel_name not in z.namelist():
                continue
            for rel in ET.fromstring(z.read(rel_name)):
                if not rel.get('Type', '').endswith('/customXmlProps'):
                    continue
                target = rel.get('Target', '')
                if '/' in target or '\\' in target or not re.fullmatch(r'itemProps[0-9]+\.xml', target):
                    raise ValueError('unsafe_property_relationship')
                prop = ET.fromstring(z.read('customXml/' + target))
                store = prop.get(DS + 'itemID', '').upper()
                if store in stores:
                    raise ValueError('ambiguous_property_store')
                stores[store] = ET.fromstring(z.read(name))
        document = ET.fromstring(z.read('word/document.xml'))
        checks = {}
        for sdt in document.iter(W + 'sdt'):
            tag = sdt.find(W + 'sdtPr/' + W + 'tag')
            name = tag.get(W + 'val') if tag is not None else None
            if name not in FIELDS:
                continue
            if name in checks:
                raise ValueError('duplicate_cover_control')
            binding = sdt.find(W + 'sdtPr/' + W + 'dataBinding')
            if binding is None:
                raise ValueError('missing_property_binding')
            store = stores.get(binding.get(W + 'storeItemID', '').upper())
            ns = dict(re.findall(r"xmlns:(\w+)=[\"']([^\"']+)[\"']", binding.get(W + 'prefixMappings', '')))
            xpath = binding.get(W + 'xpath', '')
            expected_path = '/p:properties[1]/documentManagement[1]/f:' + name + '[1]'
            if xpath != expected_path or ns.get('p') != 'http://schemas.microsoft.com/office/2006/metadata/properties' or not ns.get('f'):
                raise ValueError('unexpected_property_binding')
            nodes = [] if store is None else store.findall('documentManagement/{' + ns['f'] + '}' + name)
            prop_value = nodes[0].text or '' if len(nodes) == 1 else None
            content = sdt.find(W + 'sdtContent')
            displayed = '' if content is None else ''.join(x.text or '' for x in content.iter(W + 't'))
            checks[name] = {'propertyEmpty': prop_value == '', 'propertyMatches': prop_value == values[name],
                            'renderedTextMatches': displayed == values[name]}
        if set(checks) != set(FIELDS):
            raise ValueError('missing_cover_controls')
        all_properties = all(c['propertyMatches'] for c in checks.values())
        all_rendered = all(c['renderedTextMatches'] for c in checks.values())
        return {'route': 'sharepoint-library-properties', 'sha256': hashlib.sha256(raw).hexdigest(),
                'fieldChecks': checks, 'propertiesVerified': all_properties,
                'savedTextVerified': all_rendered, 'packageEligible': all_properties and all_rendered,
                'visualLayoutVerified': False}


def admit_cover(raw, values, expected_sha256):
    """Return an existing-kernel member only for the exact inspected revision."""
    report = inspect_cover(raw, values)
    if report['sha256'] != expected_sha256:
        raise ValueError('cover_changed_requires_new_revision')
    if not report['packageEligible']:
        raise ValueError('cover_requires_native_refresh')
    import base64
    return {'path': 'attachments/ppg-cover-DRAFT.docx', 'base64': base64.b64encode(raw).decode()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('document', type=Path)
    p.add_argument('accepted_values', type=Path)
    p.add_argument('--require-rendered', action='store_true')
    args = p.parse_args()
    result = inspect_cover(args.document.read_bytes(), json.loads(args.accepted_values.read_text()))
    print(json.dumps(result, indent=2))
    if args.require_rendered and not result['packageEligible']:
        raise SystemExit(2)



def build_qualification_flow(existing_flow, site, library_id, template, output_path, values):
    """Prepare an isolated copy/property probe. No API calls or package acceptance.

    CopyFileAsync preserves the ordinary template's filename in a fresh folder.
    Existing destinations fail closed. Metadata writes require the actual item
    response ETag and exact value readback; none of this refreshes Word body text.
    """
    import copy
    from urllib.parse import urlsplit
    accepted_values(values)
    from uuid import UUID
    library_id = str(UUID(library_id))
    origin = urlsplit(site)
    if origin.scheme != 'https' or not origin.hostname or origin.query or origin.fragment or origin.username:
        raise ValueError('invalid_site')
    source_path = template['ServerRelativeUrl']
    for path in (source_path, output_path):
        if not path.startswith(origin.path + '/') or any(x in path for x in ("'", '?', '#', '..')):
            raise ValueError('invalid_cover_path')
    if source_path == output_path:
        raise ValueError('preserve_template')
    if '/forms/' in source_path.lower():
        raise ValueError('ordinary_execution_template_required')
    if not source_path.lower().endswith('.docx') or source_path.rsplit('/', 1)[-1] != output_path.rsplit('/', 1)[-1]:
        raise ValueError('copy_requires_same_docx_filename')
    template_uid = str(UUID(template['UniqueId']))
    if not isinstance(template['ETag'], str) or not template['ETag'].strip() or any(c in template['ETag'] for c in '\r\n'):
        raise ValueError('template_etag_required')
    props = existing_flow['properties']
    refs = props['connectionReferences']
    sp = refs.get('shared_sharepointonline', {})
    sharepoint_api = '/providers/Microsoft.PowerApps/apis/shared_sharepointonline'
    if sp.get('tier') != 'Standard' or sp.get('id') != sharepoint_api:
        raise ValueError('standard_sharepoint_binding_required')
    definition = copy.deepcopy(props['definition'])
    primitives = [x for x in definition['actions'].values()
                  if x.get('type') == 'OpenApiConnection'
                  and isinstance(x.get('inputs'), dict)
                  and isinstance(x['inputs'].get('host'), dict)
                  and x['inputs']['host'].get('apiId') == sharepoint_api
                  and x['inputs']['host'].get('operationId') == 'HttpRequest'
                  and x['inputs']['host'].get('connectionName') == 'shared_sharepointonline']
    if not primitives:
        raise ValueError('qualified_sharepoint_primitive_required')
    def action(method, uri, after=None, body=None):
        # Native readbacks include API-injected authentication. Reuse the exact
        # connector host/reference, not that transport annotation or old action
        # settings. The supported Flow API supplies authentication on save.
        result = {'type': 'OpenApiConnection', 'inputs': {
            'host': copy.deepcopy(primitives[0]['inputs']['host'])},
            'runAfter': {} if after is None else {after: ['Succeeded']}}
        params = {'dataset': site, 'parameters/method': method, 'parameters/uri': uri,
                  'parameters/headers': {'Accept': 'application/json;odata=nometadata',
                                         'Content-Type': 'application/json;odata=nometadata'}}
        if body is not None:
            params['parameters/body'] = json.dumps(body, ensure_ascii=False)
        result['inputs']['parameters'] = params
        result['inputs']['retryPolicy'] = {'type': 'none'}
        return result
    target = "_api/web/GetFileByServerRelativePath(decodedurl='" + output_path + "')"
    source = "_api/web/GetFileByServerRelativePath(decodedurl='" + source_path + "')"
    actions = {'Read_template': action('GET', source + '?$select=UniqueId,ETag,Length')}
    actions['Require_pinned_template'] = {
        'type': 'If', 'runAfter': {'Read_template': ['Succeeded']},
        'expression': {'and': [{'equals': ["@body('Read_template')?['UniqueId']", template_uid]},
                               {'equals': ["@body('Read_template')?['ETag']", template['ETag']]}]},
        'actions': {}, 'else': {'actions': {'Refuse_template_drift': {
            'type': 'Terminate', 'runAfter': {}, 'inputs': {'runStatus': 'Failed',
            'runError': {'code': 'TEMPLATE_CHANGED', 'message': 'Refresh the frozen template selection.'}}}}}}
    def connector_action(operation, parameters, after):
        result = action('GET', '', after)
        result['inputs']['host']['operationId'] = operation
        result['inputs']['parameters'] = parameters
        return result
    actions['Read_template_metadata'] = connector_action('GetFileMetadataByPath',
        {'dataset': site, 'path': source_path[len(origin.path):]}, 'Require_pinned_template')
    actions['Copy_cover'] = connector_action('CopyFileAsync', {
        'dataset': site,
        'parameters/sourceFileId': "@body('Read_template_metadata')?['Id']",
        'parameters/destinationDataset': site,
        'parameters/destinationFolderPath': output_path[len(origin.path):].rsplit('/', 1)[0],
        'parameters/nameConflictBehavior': 0}, 'Read_template_metadata')
    actions['Read_template_after_copy'] = action('GET', source + '?$select=UniqueId,ETag,Length', 'Copy_cover')
    actions['Require_same_template_revision'] = copy.deepcopy(actions['Require_pinned_template'])
    again = actions['Require_same_template_revision']
    again['runAfter'] = {'Read_template_after_copy': ['Succeeded']}
    for condition in again['expression']['and']:
        condition['equals'][0] = condition['equals'][0].replace("body('Read_template')", "body('Read_template_after_copy')")
    again['else']['actions']['Refuse_template_drift_after_copy'] = again['else']['actions'].pop('Refuse_template_drift')
    actions['Read_cover_item'] = action('GET', target + '/ListItemAllFields', 'Require_same_template_revision')
    def refuse(code, message):
        return {'type': 'Terminate', 'runAfter': {}, 'inputs': {'runStatus': 'Failed',
                'runError': {'code': code, 'message': message}}}
    actions['Require_cover_item_etag'] = {
        'type': 'If', 'runAfter': {'Read_cover_item': ['Succeeded']},
        'expression': {'and': [{'not': {'equals': [
            "@coalesce(outputs('Read_cover_item')?['headers']?['ETag'],'')", '']}}]},
        'actions': {}, 'else': {'actions': {'Refuse_missing_etag': refuse(
            'READ_ETAG_MISSING', 'No metadata write without the actual response ETag.')}}}
    actions['Populate_cover_properties'] = action('POST',
        "@concat('_api/web/lists(guid''" + library_id + "'')/items(',string(body('Read_cover_item')?['Id']),')')",
        'Require_cover_item_etag', values)
    actions['Populate_cover_properties']['inputs']['parameters']['parameters/headers'].update({
        'IF-MATCH': "@outputs('Read_cover_item')?['headers']?['ETag']", 'X-HTTP-Method': 'MERGE'})
    actions['Read_saved_properties'] = action('GET', target + '/ListItemAllFields', 'Populate_cover_properties')
    actions['Require_saved_values'] = {
        'type': 'If', 'runAfter': {'Read_saved_properties': ['Succeeded']},
        'expression': {'and': [{'equals': ["@body('Read_saved_properties')?['" + name + "']", values[name]]}
                               for name in FIELDS]},
        'actions': {}, 'else': {'actions': {'Refuse_metadata_mismatch': refuse(
            'METADATA_MISMATCH', 'Readback must match the accepted values.')}}}
    definition['actions'] = actions
    # This is a manually invoked qualification graph, never an automatic schedule.
    definition['triggers'] = {'manual': {'type': 'Request', 'kind': 'Button',
        'inputs': {'schema': {'type': 'object', 'properties': {}, 'required': []}}}}
    return {'properties': {'definition': definition, 'connectionReferences': {'shared_sharepointonline': copy.deepcopy(sp)},
                           'displayName': props['displayName'], 'state': 'Stopped'}}


if __name__ == "__main__":
    main()

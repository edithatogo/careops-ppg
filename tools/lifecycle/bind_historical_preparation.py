"""Repair closure's historical preparation folder bindings without new readers.

Offline only. Reuse the exact reviewed primary preparation folder contract for
its retained HP_ branch. All writers, case/history checks and recovery stay intact.
"""
import copy
import re

from build_multisource_case_context import (
    digest, _preparation_folder_fragments, _check_preparation_folders,
)
from build_operator_entry import _flatten, action_references
from build_selected_event_routes import audit_actions
from build_native_closure_entry import _check_expression_lengths


def _unprefix(value):
    return re.sub(r"((?:outputs|body|actions)\(')HP_([^']+)('\))", r'\1\2\3', value)


def build(flow, binding):
    if (set(binding) != {'approvedDefinitionSHA256'}
            or binding['approvedDefinitionSHA256'] != digest(flow['properties']['definition'])):
        raise ValueError('Exact reviewed retained closure definition required')
    out = copy.deepcopy(flow)
    nodes = _flatten(out['properties']['definition']['actions'])
    limits = nodes['Selected_case_context']['inputs']['limits']
    uid = limits['additionalPreparationContextSource']
    profiles = nodes['SourceProfiles_configured']['inputs']
    if (len(profiles) != 2 or uid not in {p['UniqueId'] for p in profiles}
            or not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', uid)):
        raise ValueError('Retain the two reviewed source identities')
    folders = limits['additionalPreparationArtifactFolders']
    site = nodes['Read_selected_case']['inputs']['parameters']['dataset']
    fragments = _preparation_folder_fragments(site, uid, folders)
    # The resolved primary interface may now be a historical/initial selector.
    # Its original primary receipt remains in the existing initial compose.
    primary = dict(nodes)
    primary['Native_prepared_revision'] = nodes['ClosureEntry_initial_prepared']
    _check_preparation_folders(primary, site, uid, folders)
    guard = nodes['HP_Verify_prepared_selection']
    lookup = nodes['HP_Find_prepared_receipt']['inputs']['parameters']
    receipt = nodes['HP_Native_prepared_revision']['inputs']['preparedRevision']['qualificationReceipt']
    if lookup.get('parameters/method') != 'GET' or lookup.get('dataset') != site:
        raise ValueError('Retain the existing read-only historical receipt lookup')
    leaves = [(guard, 'expression', 'selectionGuardSHA256', fragments[0]),
              (lookup, 'parameters/uri', 'receiptLookupSHA256', fragments[1]),
              (receipt, 'DocumentReference', 'receiptReferenceSHA256', fragments[0])]
    for obj, field, key, (old, new) in leaves:
        value = obj[field]
        if (not isinstance(value, str) or value.count(old) != 1 or new in value
                or digest(_unprefix(value)) != folders[key]):
            raise ValueError('Exact original historical folder guard/lookup/receipt required')
        obj[field] = value.replace(old, new)
    shadow = {
        'Verify_prepared_selection': {'expression': _unprefix(guard['expression'])},
        'Find_prepared_receipt': {'inputs': {'parameters': {'parameters/uri': _unprefix(lookup['parameters/uri'])}}},
        'Native_prepared_revision': {'inputs': {'preparedRevision': {'qualificationReceipt': {
            'DocumentReference': _unprefix(receipt['DocumentReference'])}}}},
    }
    _check_preparation_folders(shadow, site, uid, folders)
    definition = out['properties']['definition']
    if audit_actions(definition) != audit_actions(flow['properties']['definition']):
        raise ValueError('Retain every historical reader, writer and action boundary')
    geometry = audit_actions(definition)
    if geometry['actionCount'] > 500 or geometry['maximumActionDepth'] > 8:
        raise ValueError('Retain native action limits')
    _check_expression_lengths(definition)
    if action_references(definition['actions']) - nodes.keys():
        raise ValueError('Unresolved historical preparation reference')
    out['properties']['state'] = 'Stopped'
    return out

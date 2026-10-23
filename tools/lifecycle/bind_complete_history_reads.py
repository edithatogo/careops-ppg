"""Bound inspected List history reads explicitly; retain continuation refusal.

Pure composition only. SharePoint's implicit 100-row page is not a complete
history. Request up to 5000 rows on the exact reviewed collection readers and
retain every existing continuation, preservation, writer and recovery guard.
Histories beyond this bound must still hold; this is not pagination support.
"""
import copy
import re
from urllib.parse import urlsplit

from build_multisource_case_context import digest
from build_operator_entry import (
    _flatten, action_references, rebind_case_work_handoff, case_work_identity_digest,
)
from build_selected_event_routes import audit_actions
from build_native_closure_entry import _check_expression_lengths


COLLECTION = re.compile(
    r"_api/web/lists(?:\(guid'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}'\)"
    r"|/getbytitle\('[^'\r\n]+'\))/items\Z"
)


def bind_closure_contract_reads(flow, approved_definition_sha256):
    """Pair closure's dynamic committer reads with its bounded initial reads.

    The committer consumes URI values from a Compose contract rather than a
    literal HTTP action. Keep the complete wrapper comparison and every writer
    unchanged; only repair these three reviewed URI values.
    """
    if approved_definition_sha256 != digest(flow['properties']['definition']):
        raise ValueError('Exact reviewed closure definition required')
    out = copy.deepcopy(flow)
    nodes = _flatten(out['properties']['definition']['actions'])
    contract = nodes.get('ClosureEntry_binding_result', {})
    if contract.get('type') != 'Compose':
        raise ValueError('Canonical closure binding Compose required')
    reads = contract.get('inputs', {}).get('evidenceReads', {})
    uris = []
    for kind in ('assurance', 'readiness', 'consultation'):
        entry = reads.get(kind, {})
        uri = entry.get('uri')
        initial = nodes.get('ClosureEntry_check_' + kind, {})
        params = initial.get('inputs', {}).get('parameters', {})
        current = nodes.get('Cycle_current_' + kind, {})
        dynamic = "@outputs('ClosureEntry_write_contract')?['evidenceReads']?['" + kind + "']?['uri']"
        if (set(entry) != {'uri', 'collection'} or entry['collection'] is not True
                or not isinstance(uri, str) or not COLLECTION.fullmatch(uri)
                or initial.get('type') != 'OpenApiConnection'
                or params.get('parameters/method') != 'GET'
                or params.get('parameters/uri') != uri + '?$top=5000'
                or current.get('type') != 'OpenApiConnection'
                or current.get('inputs', {}).get('parameters', {}).get('parameters/uri') != dynamic):
            raise ValueError('Exact paired bounded closure history reader required')
        uris.append(uri)
        entry['uri'] = uri + '?$top=5000'
    if len(set(uris)) != 3:
        raise ValueError('Three distinct history collections required')
    shadow = copy.deepcopy(out)
    original_reads = _flatten(shadow['properties']['definition']['actions'])['ClosureEntry_binding_result']['inputs']['evidenceReads']
    for kind, uri in zip(('assurance', 'readiness', 'consultation'), uris):
        original_reads[kind]['uri'] = uri
    if shadow != flow:
        raise ValueError('Only three contract URI values may change')
    _check_expression_lengths(out['properties']['definition'])
    out['properties']['state'] = 'Stopped'
    return out


def build(flow, binding):
    if (set(binding) != {'approvedDefinitionSHA256', 'site', 'readers', 'pageSize'}
            or binding['approvedDefinitionSHA256'] != digest(flow['properties']['definition'])):
        raise ValueError('Exact reviewed retained definition and binding required')
    site = urlsplit(binding['site'])
    readers = binding['readers']
    if (site.scheme != 'https' or not site.netloc or site.username or site.password
            or site.query or site.fragment or binding['pageSize'] != 5000
            or not isinstance(readers, dict) or not readers):
        raise ValueError('Exact site, nonempty reviewed readers and 5000-row bound required')
    out = copy.deepcopy(flow)
    nodes = _flatten(out['properties']['definition']['actions'])
    for name, uri in readers.items():
        if not isinstance(uri, str) or not COLLECTION.fullmatch(uri) or name not in nodes:
            raise ValueError('Reviewed literal List collection reader required')
        action = nodes[name]
        parameters = action.get('inputs', {}).get('parameters', {})
        if (action.get('type') != 'OpenApiConnection'
                or parameters.get('parameters/method') != 'GET'
                or parameters.get('dataset') != binding['site']
                or parameters.get('parameters/uri') != uri):
            raise ValueError('Retain exact same-site GET history reader')
        parameters['parameters/uri'] = uri + '?$top=5000'
    # Prove these URI leaves are the entire change, including forms/connections.
    shadow = copy.deepcopy(out)
    for name, uri in readers.items():
        _flatten(shadow['properties']['definition']['actions'])[name]['inputs']['parameters']['parameters/uri'] = uri
    if shadow != flow:
        raise ValueError('Only reviewed history URI leaves may change')
    definition = out['properties']['definition']
    geometry = audit_actions(definition)
    if (geometry != audit_actions(flow['properties']['definition'])
            or geometry['actionCount'] > 500 or geometry['maximumActionDepth'] > 8
            or action_references(definition['actions']) - nodes.keys()):
        raise ValueError('Retain native geometry and resolved action references')
    _check_expression_lengths(definition)
    out['properties']['state'] = 'Stopped'
    return out


def rebind_consumer_locator(producer, previous, current, consumer_binding,
                            approved_producer_definition_sha256):
    """Refresh the locator for exactly this reviewed consumer overlay.

    Legacy consumer checks deliberately fingerprint its original coverage graph.
    Validate that original contract, then prove the new consumer is *only* the
    bounded-read overlay before updating the locator. Do not rewrite historical
    coverage provenance or relax any runtime eligibility/preservation predicate.
    """
    if current != build(previous, consumer_binding):
        raise ValueError('Consumer must be exactly the reviewed history-read overlay')
    out = rebind_case_work_handoff(producer, previous, previous,
                                  approved_producer_definition_sha256)
    if out['properties']['definition'] != producer['properties']['definition']:
        raise ValueError('Original consumer locator contract changed')
    node = _flatten(out['properties']['definition']['actions'])['Operator_case_work_handoff']
    if node['inputs']['entrypointSHA256'] != case_work_identity_digest(previous):
        raise ValueError('Original consumer fingerprint changed')
    node['inputs']['entrypointSHA256'] = case_work_identity_digest(current)
    return out

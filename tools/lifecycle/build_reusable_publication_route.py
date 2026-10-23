"""Select both reviewed sources and verify actual draft/issued byte parity.

Pure local composition. The retained proof receipt is still read and bracketed;
its assertions cannot substitute for the two native content reads. Native binary
envelope behavior and first/replay qualification must be proved before promotion.
"""
import copy
from urllib.parse import urlsplit

from build_reusable_purpose_route import build as context_build
from build_multisource_case_context import digest
from build_operator_entry import _flatten, _literal, action_references
from build_selected_event_routes import audit_actions
from build_native_closure_entry import _check_expression_lengths


def metadata_checks(site):
    proof = "outputs('Parse_binary_proof')"
    revision = "outputs('Native_prepared_revision')?['preparedRevision']"
    scope, file, issued = revision + "?['scope']", revision + "?['file']", "body('Read_issued')"
    parsed = urlsplit(site); origin = parsed.scheme + '://' + parsed.netloc
    eq = lambda a, b: 'equals(' + a + ',' + b + ')'
    checks = [eq(proof + "?['kind']", "'local-downloaded-binary-parity-v1'"),
              eq(proof + "?['independentByteParity']", 'true'),
              eq(proof + "?['publicationEventCreated']", 'false')]
    checks += [eq(proof + "?['scope']?['" + key + "']", scope + "?['" + key + "']")
               for key in ('CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256')]
    checks += [eq(proof + "?['source']?['" + key + "']", file + "?['" + key + "']")
               for key in ('UniqueId', 'ETag', 'nativeVersion', 'Length', 'DocumentReference')]
    checks += [eq(proof + "?['issued']?['" + key + "']", issued + "?['" + native + "']")
               for key, native in [('UniqueId', 'UniqueId'), ('ETag', 'ETag'), ('nativeVersion', 'UIVersionLabel')]]
    checks += [eq('string(' + proof + "?['issued']?['Length'])", 'string(' + issued + "?['Length'])"),
               eq(proof + "?['issued']?['DocumentReference']", 'concat(' + _literal(origin) + ",outputs('Issued_path'))"),
               eq(proof + "?['issued']?['SHA256']", scope + "?['DocumentSHA256']")]
    return checks


def parity_checks():
    left = "string(coalesce(body('NativeParity_read_draft')?['$content'],''))"
    right = "string(coalesce(body('NativeParity_read_issued')?['$content'],''))"
    checks = ['not(empty(' + left + '))', 'not(empty(' + right + '))', 'equals(' + left + ',' + right + ')']
    for content, length in ((left, "outputs('Native_prepared_revision')?['preparedRevision']?['file']?['Length']"),
                            (right, "body('Read_issued')?['Length']")):
        # Native binary envelope is required. Equal truncated bodies cannot pass
        # unless their decoded lengths also match the separately read metadata.
        decoded_length = ('sub(mul(div(length(' + content + '),4),3),if(endsWith(' + content
                          + ",'=='),2,if(endsWith(" + content + ",'='),1,0)))")
        checks += ['equals(mod(length(' + content + '),4),0)',
                   'equals(' + decoded_length + ',int(' + length + '))']
    return checks


def download_witness_checks():
    witness = []
    proof = "outputs('Parse_binary_proof')"
    for label in ('source', 'issued'):
        record = proof + "?['" + label + "']"
        downloaded = proof + "?['downloadEvidence']?['" + label + "']"
        expected_hash = (proof + "?['scope']?['DocumentSHA256']" if label == 'source'
                         else record + "?['SHA256']")
        witness += ['equals(' + downloaded + "?['SHA256']," + expected_hash + ')',
                    'equals(string(' + downloaded + "?['Length']),string(" + record + "?['Length']))"]
        for frame in ('metadataBefore', 'metadataAfter'):
            for key in ('UniqueId', 'ETag', 'nativeVersion', 'Length', 'DocumentReference'):
                witness.append('equals(' + downloaded + "?['" + frame + "']?['" + key + "'],"
                               + record + "?['" + key + "'])")
    return witness


def build(original, additional, profiles, binding):
    if set(binding) != {'approvedOriginalDefinitionSHA256', 'approvedAdditionalDefinitionSHA256'}:
        raise ValueError('Exact reviewed reusable-publication binding required')
    # Require both historical graphs to contain the same complete dynamic proof
    # relationships before replacing only their compile-time receipt trust pins.
    site = _flatten(original['properties']['definition']['actions'])['Read_selected_case']['inputs']['parameters']['dataset']
    checks = metadata_checks(site)
    for flow in (original, additional):
        nodes = _flatten(flow['properties']['definition']['actions'])
        if not nodes['Verify_binary_proof_relations_check_0']['inputs'].startswith('@and(' + ','.join(checks) + ','):
            raise ValueError('Complete original dynamic proof relationship checks required')
        if nodes['Verify_record_producer_trust']['expression'] != '@and(true)':
            raise ValueError('Both input profiles must be previously reviewed record-capable graphs')
    out = context_build(original, additional, profiles, {**binding, 'stage': 'publication'})
    definition = out['properties']['definition']; n = _flatten(definition['actions'])
    names = ('NativeParity_read_draft', 'NativeParity_read_issued')
    if any(name in n for name in names):
        raise ValueError('Native binary-parity action collision')
    template = n['Read_source_content']
    params = template['inputs']['parameters']
    if params.get('parameters/method') != 'GET' or params.get('dataset') != site:
        raise ValueError('Retain the qualified same-site binary GET provider')
    identities = ("outputs('Native_prepared_revision')?['preparedRevision']?['file']?['UniqueId']",
                  "body('Read_issued')?['UniqueId']")
    reads = {}
    for name, uid, previous in zip(names, identities, ('Parse_binary_proof', names[0])):
        node = copy.deepcopy(template)
        node['inputs']['parameters']['parameters/uri'] = (
            "@concat('_api/web/GetFileById(',decodeUriComponent('%27')," + uid + ",decodeUriComponent('%27'),')/$value')")
        node['inputs']['retryPolicy'] = {'type': 'none'}
        node['runAfter'] = {previous: ['Succeeded']}
        reads[name] = node
    # Downstream maintained compilers retain actions through the publication
    # replay boundary in insertion order. Keep these prerequisites before it.
    ordered = {}
    for name, node in definition['actions'].items():
        if name == 'Verify_binary_proof_relations_check_0':
            ordered.update(reads)
        ordered[name] = node
    definition['actions'] = ordered
    n['Verify_binary_proof_relations_check_0']['inputs'] = '@and(' + ','.join(checks) + ')'
    n['Verify_binary_proof_relations_check_0']['runAfter'] = {names[1]: ['Succeeded']}
    # This replaces a fixed, historical JSON/pin match with direct native bytes
    # plus all dynamic scope/version relationships and retained download brackets.
    n['Verify_binary_proof_relations_check_1']['inputs'] = '@and(' + ','.join(parity_checks() + download_witness_checks()) + ')'
    n['Selected_case_context']['inputs']['limits'].update(
        nativeDraftIssuedByteParityRequired=True, fixedHistoricalProofReceiptRequired=False, runtimeQualified=False)
    all_nodes = _flatten(definition['actions'])
    geometry = audit_actions(definition)
    if geometry['actionCount'] > 500 or geometry['maximumActionDepth'] > 8:
        raise ValueError('Reusable publication exceeds native geometry limits')
    if action_references(definition['actions']) - all_nodes.keys():
        raise ValueError('Unresolved native binary-parity reference')
    _check_expression_lengths(definition)
    return out

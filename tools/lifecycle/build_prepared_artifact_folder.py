"""Prepare one additional existing artifact folder for fixed-source recorders.

Pure local composition. Selection stays server-resolved and exact-version bound;
the original folder remains usable. Event writers and source/role rules are not
adapted. Native save, first/replay and preservation checks remain separate.
"""
import copy
import re
from urllib.parse import urlsplit
from uuid import UUID

from build_operator_entry import _flatten
from build_multisource_case_context import digest, _preparation_folder_fragments, _check_preparation_folders, _bind_preparation_receipt_reference


def build(profile, additional_folder, approved_definition_sha256):
    definition=profile['properties']['definition']
    if digest(definition)!=approved_definition_sha256:
        raise ValueError('Exact reviewed recorder definition required')
    nodes=_flatten(definition['actions']);context=nodes['Selected_case_context']['inputs']
    if ('SourceProfiles_configured' in nodes or context.get('contextOrigin')!='manual_case_reference_lookup'
            or 'additionalPreparedArtifactFolders' in context.get('limits',{})):
        raise ValueError('Unmodified fixed-source server-resolved recorder required')
    source_uid=str(UUID(context['sourcePins']['UniqueId']))
    site=nodes['Read_selected_case']['inputs']['parameters']['dataset']
    for name in ('Read_prepared_case','Read_prepared_file_before','Find_prepared_receipt','Read_prepared_source_final'):
        action=nodes[name];params=action.get('inputs',{}).get('parameters',{});host=action.get('inputs',{}).get('host',{})
        if (action.get('type')!='OpenApiConnection' or params.get('dataset')!=site
                or params.get('parameters/method')!='GET' or 'parameters/body' in params
                or host.get('operationId')!='HttpRequest' or host.get('connectionName')!='shared_sharepointonline'
                or host.get('apiId')!='/providers/Microsoft.PowerApps/apis/shared_sharepointonline'
                or any(k.lower() in ('x-http-method','x-http-method-override') for k in params.get('parameters/headers',{}))):
            raise ValueError('Existing same-site GET-only prepared readers required')
    if nodes['Read_prepared_source_final']['inputs']['parameters']['parameters/uri']!="_api/web/GetFileById('"+source_uid+"')?$select=UniqueId,ETag,Length":
        raise ValueError('Prepared reader must retain its exact fixed source')
    selection=nodes['Verify_prepared_selection']['expression']
    lookup=nodes['Find_prepared_receipt']['inputs']['parameters']['parameters/uri']
    matches=re.findall(r"startsWith\(outputs\('Prepared_document_reference'\),('(?:[^']|'')*')\)",selection)
    if len(matches)!=1:raise ValueError('Original literal prepared-folder guard required')
    prefix=matches[0][1:-1].replace("''", "'");parsed=urlsplit(site);origin=parsed.scheme+'://'+parsed.netloc
    if not prefix.startswith(origin) or not prefix.endswith('/'):
        raise ValueError('Original same-site folder required')
    folders={'originalFolder':prefix[len(origin):-1],'additionalFolder':additional_folder,
             'selectionGuardSHA256':digest(selection),'receiptLookupSHA256':digest(lookup)}
    fragments=_preparation_folder_fragments(site,None,folders,by_document_reference=True)
    if any(value.count(old)!=1 for value,(old,new) in zip((selection,lookup),fragments)):
        raise ValueError('Exact paired original folder selection/lookup required')
    out=copy.deepcopy(profile);out['properties']['state']='Stopped';updated=_flatten(out['properties']['definition']['actions'])
    updated['Verify_prepared_selection']['expression']=selection.replace(*fragments[0])
    updated['Find_prepared_receipt']['inputs']['parameters']['parameters/uri']=lookup.replace(*fragments[1])
    _bind_preparation_receipt_reference(updated,folders,fragments)
    updated['Selected_case_context']['inputs'].setdefault('limits',{})['additionalPreparedArtifactFolders']=folders
    _check_preparation_folders(updated,site,None,folders,by_document_reference=True)
    return out

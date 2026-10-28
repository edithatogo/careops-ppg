"""Bind the existing fictional publication route to an immutable relationship view.

Offline assembly. Same standard SharePoint connection, GET-only added actions;
the original publication/copy writers and their authority boundaries remain.
"""
import copy
import json
import re

from scripts.ppg_relationship_versions import recover, head, journal_from_native_records
from build_prepared_decision_outcome import digest
from build_selected_event_routes import audit_actions
from build_operator_entry import _flatten


def _bounded_literals(value, actions):
    """Reconstruct complete expected data without oversized executable scalars."""
    if isinstance(value, str) and (len(value) > 2000 or value.startswith('@')):
        names = []
        for offset in range(0, len(value), 2000):
            name = 'RV_literal_' + str(len(actions))
            chunk = value[offset:offset + 2000].replace("'", "''")
            actions[name] = {'type':'Compose', 'inputs':"@concat('"+chunk+"')", 'runAfter':{}}
            names.append("outputs('"+name+"')")
        return '@concat('+','.join(names)+')'
    if isinstance(value, dict):
        return {k:_bounded_literals(v, actions) for k,v in value.items()}
    if isinstance(value, list):
        return [_bounded_literals(v, actions) for v in value]
    return value


def build(profile, binding):
    props = profile['properties']; definition = props['definition']
    if binding.get('qualificationOnly') is not True or digest(definition) != binding.get('approvedDefinitionSHA256'):
        raise ValueError('Exact reviewed fictional publication definition required')
    if set(props['connectionReferences']) != {'shared_sharepointonline'}:
        raise ValueError('Existing SharePoint-only connection required')
    if any(name.startswith('RV_') for name in _flatten(definition['actions'])):
        raise ValueError('Relationship context already bound; rebuild from the reviewed base')
    snapshot = binding['snapshot']; journal = recover(snapshot)
    rows = binding['graphRows']
    journal_from_native_records(rows, head(journal), snapshot)
    if (not rows or len(rows) > 5000 or len({r['Id'] for r in rows}) != len(rows)
            or any(type(r['Id']) is not int or r['Id'] < 1
                or not isinstance(r.get('GUID'), str) or not r['GUID'].strip()
                or not isinstance(r.get('odata.etag'), str) or r['odata.etag'].strip() in ('', '*') for r in rows)):
        raise ValueError('Complete bounded graph with native identity/tokens required')
    uri = binding['graphCollectionUri']
    if not re.fullmatch(r"_api/web/lists\(guid'[0-9a-fA-F-]{36}'\)/items", uri):
        raise ValueError('Exact whole graph collection required')
    checkpoint = binding['checkpoint']
    if (not re.fullmatch(r'[0-9a-fA-F-]{36}', checkpoint['UniqueId'])
            or not checkpoint.get('ETag') or checkpoint['ETag'].strip() == '*'
            or not str(checkpoint.get('Length', '')).isdigit() or int(checkpoint['Length']) < 1
            or not checkpoint.get('UIVersionLabel')):
        raise ValueError('Exact retained native checkpoint pins required')
    original = binding['originalSourceScope']; source = binding['sourceBinding']['source']
    if (not original['CaseUID'].startswith('LC-FICTIONAL-OP-')
            or original['DocumentSHA256'] != source['sha256']
            or original['ReviewedVersionRef'] != 'sharepoint:'+source['UniqueId']+':'+source['ETag']
            or original['DocumentReference'] != source['DocumentReference']
            or binding['sourceBinding']['journalPin'] not in [e['body'] for e in journal['events'] if e['operation'] == 'add-policy']
            or binding['sourceBinding']['journalPin']['sha256'] != source['sha256']
            or binding['sourceBinding']['journalPin']['policyEdition'] != source['policyEdition']):
        raise ValueError('Exact fictional source edition binding required')
    out = copy.deepcopy(profile); out['properties']['state'] = 'Stopped'
    a = out['properties']['definition']['actions']
    template = a['Resolve_context']['actions']['Read_selected_case']
    if (template['type'] != 'OpenApiConnection' or template['inputs']['parameters']['parameters/method'] != 'GET'
            or template['inputs']['host'].get('apiId') != '/providers/Microsoft.PowerApps/apis/shared_sharepointonline'
            or template['inputs']['host'].get('operationId') != 'HttpRequest'):
        raise ValueError('Qualified standard SharePoint GET reader required')
    expected_rows = [{**r, 'odata.id':None} for r in sorted(rows, key=lambda r:r['Id'])]
    literals = {}
    expected_rows = _bounded_literals(expected_rows, literals)
    expected_checkpoint = _bounded_literals(copy.deepcopy(snapshot), literals)
    a.update(literals)
    a['RV_expected_rows'] = {'type':'Compose', 'inputs':expected_rows,
        'runAfter':{name:['Succeeded'] for name in literals}}
    a['RV_expected_checkpoint'] = {'type':'Compose', 'inputs':expected_checkpoint, 'runAfter':{'RV_expected_rows':['Succeeded']}}
    if a['Validate_publication_input'].get('runAfter') != {}:
        raise ValueError('Reviewed initial publication input guard required')
    a['Validate_publication_input']['runAfter'] = {'RV_expected_checkpoint':['Succeeded']}
    def http(path, previous):
        result = copy.deepcopy(template); params = result['inputs']['parameters']
        params.update({'parameters/method':'GET', 'parameters/uri':path,
            'parameters/headers':{'Accept':'application/json;odata=minimalmetadata'}})
        params.pop('parameters/body', None)
        result['runAfter'] = {previous:['Succeeded']}
        return result
    def gate(group, target, label, effect_may_exist):
        prior = group[target]['runAfter']
        if len(prior) != 1 or next(iter(prior.values())) != ['Succeeded']:
            raise ValueError('Reviewed single-success dependency required: '+target)
        graph='RV_'+label+'_graph'; clean='RV_'+label+'_clean'; meta='RV_'+label+'_meta'
        content='RV_'+label+'_content'; parsed='RV_'+label+'_parsed'; guard='RV_'+label+'_guard'
        group[graph]=http(uri+'?$top=5000&$orderby=Id', next(iter(prior)))
        group[clean]={'type':'Select','inputs':{'from':"@body('"+graph+"')?['value']",
            'select':"@union(item(),json('{\"odata.id\":null}'))"},'runAfter':{graph:['Succeeded']}}
        file="_api/web/GetFileById('"+checkpoint['UniqueId']+"')"
        group[meta]=http(file+'?$select=UniqueId,ETag,Length,UIVersionLabel',clean)
        group[content]=http(file+'/$value',meta)
        group[parsed]={'type':'Compose','inputs':"@if(contains(body('"+content+"'),'$content'),json(base64ToString(body('"+content+"')?['$content'])),json(string(body('"+content+"'))))",'runAfter':{content:['Succeeded']}}
        checks=["equals(body('"+clean+"'),outputs('RV_expected_rows'))",
            "equals(outputs('"+parsed+"'),outputs('RV_expected_checkpoint'))",
            "equals(outputs('Native_prepared_revision')?['preparedRevision']?['originalSourceScope'],json('"+json.dumps(original,separators=(',',':')).replace("'","''")+"'))"]
        for key in ('UniqueId','ETag','DocumentUID'):
            checks.append("equals(outputs('Selected_case_context')?['sourcePins']?['"+key+"'],'"+source[key].replace("'","''")+"')")
        checks += ["empty(body('"+graph+"')?['"+key+"'])" for key in ('nextLink','@nextLink','odata.nextLink','@odata.nextLink')]
        for key in ('UniqueId','ETag','Length','UIVersionLabel'):
            value=str(checkpoint[key]).replace("'","''")
            checks.append("equals(string(body('"+meta+"')?['"+key+"']),'"+value+"')")
        expression='@and('+','.join(checks)+')'
        if len(expression)>8192:
            raise ValueError('Native guard expression limit exceeded')
        group[guard]={'type':'If','expression':expression,'runAfter':{parsed:['Succeeded']},
            'actions':{},'else':{'actions':{'RV_'+label+'_held':{'type':'Terminate','runAfter':{},
                'inputs':{'runStatus':'Failed','runError':{'code':'RelationshipContextChanged',
                    'message':'Frozen relationship/source context changed; reconcile retained effects before any retry. effectMayExist='+str(effect_may_exist).lower()}}}}}}
        group[target]['runAfter']={guard:['Succeeded']}
    gate(a,'Copy_if_absent','before_copy',False)
    gate(a['Observe_copy_phase']['actions'],'Native_binary_copy_observation','after_copy',True)
    gate(a,'Ensure_publication','before_event',False)
    gate(a,'Native_binary_publication_receipt','after_event',True)
    for group,name in [(a['Observe_copy_phase']['actions'],'Native_binary_copy_observation'),(a,'Native_binary_publication_receipt')]:
        group[name]['inputs'].update(relationshipJournalHead=head(journal),
            relationshipCheckpoint=copy.deepcopy(checkpoint), generalRelationshipWriterQualified=False)
    audit_actions(out['properties']['definition'])
    return out

"""Build a stopped, PAC-packable source-collection solution from explicit bindings.

No authentication, deployment, record transfer or activation occurs here.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
from uuid import UUID, uuid5
import xml.etree.ElementTree as ET
from ppg_source_update_flows import build as lead_flow
from ppg_public_dataset_flows import build as capture_flow
from ppg_dataset_refresh import extend
from ppg_source_environment import parameterise
from check_email_safety import email_actions

VERSION = '1.1.0.0'
NAMESPACE = UUID('946a7858-5e95-5d88-a5dd-8de1ce81b059')
ROOT = Path(__file__).resolve().parents[1]


def schemas(suffix=""):
    if suffix and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 -]{0,50}", suffix):
        raise ValueError("Simple isolated list suffix required")
    leads = json.loads((ROOT/'config/source-update-leads.json').read_text())
    captures = {'title':'PPG Hospital Dataset Captures', 'fields':[
        {'name':n,'type':t} for n,t in [('SourceKey','Text'),('ObservedAt','DateTime'),
        ('CapturePath','Note'),('RecordCount','Number'),('SourceLink','Note'),('ProcessingState','Text')]]}
    result = {'leads':leads, 'captures':captures}
    common = [{'name':n,'type':t} for n,t in [('SourceKey','Text'),('SourcePresent','Boolean'),
        ('CapturePath','Note'),('SourceLink','Note'),('ObservedAt','DateTime'),
        ('Attribution','Text'),('Notes','Note')]]
    common[0].update(indexed=True, unique=True)
    for c in json.loads((ROOT/'config/hospital-datasets.json').read_text()):
        result[c['key']] = {'title':c['title'], 'keyFields':c['keyFields'],
                            'fields':deepcopy(c['fields'])+deepcopy(common)}
    for key, s in result.items():
        fields = [f['name'] for f in s['fields']]
        visible = (['Title','ChannelKey','ObservedAt','ProcessingState','SourceLink'] if key=='leads'
                   else ['Title','ObservedAt','RecordCount','ProcessingState','CapturePath'] if key=='captures'
                   else ['FacilityCode']+[n for n in fields if n not in ('SourceRecordId','FacilityCode')][:5]+['SourcePresent'])
        query = '<OrderBy><FieldRef Name="ID" Ascending="FALSE" /></OrderBy>'
        if key.startswith('qh-'):
            query = '<OrderBy><FieldRef Name="FacilityCode" /></OrderBy>'
        if key.endswith('busyness'):
            query = '<Where><Eq><FieldRef Name="DayOfWeekNo" /><Value Type="Number">1</Value></Eq></Where>'+query
        s['views']=[{'title':'PPG source records','fields':visible,'query':query,'rowLimit':100}]
        if suffix: s['title'] += ' - ' + suffix
        s.update(schemaVersion=1, baseTemplate=100, enableVersioning=True, enableAttachments=False)
    return result


def private_json(path, value):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
        json.dump(value, f, indent=2)
        f.write("\n")


def write_xml(path, root, *, declaration=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(root)
    ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=declaration)


def text(parent, name, value):
    ET.SubElement(parent, name).text = str(value)


def build(settings, output):
    if output.exists() or output.is_symlink() or '.local' not in output.resolve().parts:
        raise ValueError('Use a new private output under .local')
    for suffix in ('-deployment-settings.json','-manifest.json'):
        if output.with_name(output.name+suffix).exists():
            raise ValueError('Existing private output retained')
    name = settings['solutionName']
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{2,60}', name):
        raise ValueError('Simple explicit solutionName required')
    prefix = settings.get('publisherPrefix','ppg')
    if not re.fullmatch(r'[a-z][a-z0-9]{1,7}', prefix):
        raise ValueError('Invalid publisher prefix')
    if settings.get('schemaVersion') != 1 or not settings.get('collectors'):
        raise ValueError('Explicit nonempty collectors required')
    definitions = []; keys = set(); writers = set(); allvars = {}; refs = {}
    bindings = settings['bindings']; site = bindings['site']
    lists = bindings['lists']; contracts = json.loads((ROOT/'config/hospital-datasets.json').read_text())
    for c in settings['collectors']:
        key = c['key']
        if not re.fullmatch(r'[a-z][a-z0-9-]{1,80}',key) or key in keys:
            raise ValueError('Unique stable collector key required')
        keys.add(key)
        if c['type']=='hospital':
            namespaces=[('rows', site.lower().rstrip('/'), lists[x['key']].lower()) for x in contracts]
        else:
            source_key=c['source']['key']
            namespace='rss' if c['type']=='rss' and source_key=='acsqhc-rss' else c['type']+':'+source_key
            namespaces=[('leads', site.lower().rstrip('/'), lists['leads'].lower(), namespace)]
        if any(namespace in writers for namespace in namespaces):
            raise ValueError('Multiple writers for the same destination source namespace')
        writers.update(namespaces)
        if any(k in c.get('binding',{}) for k in ('site','listId','sharepoint','rss','outlook','onedrive')):
            raise ValueError('Destination and connections belong in installation bindings')
        b = {**bindings.get('connections',{}), 'site':site, 'listId':lists['leads'], **c.get('binding',{})}
        variables = {prefix+'_LeadSite':site, prefix+'_LeadList':lists['leads']}
        if c['type']=='hospital':
            b.update(listId=lists['captures'], rowLists={x['key']:lists[x['key']] for x in contracts},
                     attribution=c['attribution'])
            if {s['key'] for s in c['sources']} != {x['key'] for x in contracts}:
                raise ValueError('Hospital sources must match versioned contracts')
            f = extend(capture_flow(b,c['sources']),b,contracts)
            variables.pop(prefix+'_LeadList')
            variables[prefix+'_Captures'] = lists['captures']
            variables.update({prefix+'_Rows_'+x['key'].replace('-','_'):lists[x['key']] for x in contracts})
        else:
            f = lead_flow(c['type'], b, source=c['source'])
            for field in ('folderId','sourceSite','sourceListId'):
                if b.get(field): variables[prefix+'_'+key.replace('-','_')+'_'+field] = b[field]
        f, _ = parameterise(f,variables)
        for schema, value in variables.items():
            if schema in allvars and allvars[schema]!=value: raise ValueError('Binding collision')
            if schema in f['properties']['definition']['parameters']: allvars[schema]=value
        for alias, ref in f['properties']['connectionReferences'].items():
            logical=prefix+'_'+alias
            refs[logical]={'connectorId':ref['id'], 'connectionId':ref['connectionName']}
            f['properties']['connectionReferences'][alias]={'runtimeSource':'embedded',
                'connection':{'connectionReferenceLogicalName':logical},
                'api':{'name':alias}}
        if email_actions(f): raise ValueError('Communication action refused')
        f['schemaVersion']='1.0.0.0'
        f['properties']['state']='Stopped'; f['properties']['flowFailureAlertSubscribed']=False
        f['properties']['definition']['contentVersion']=VERSION
        display_name=f['properties']['displayName']
        # Dataverse clientdata uses the exported solution envelope, not the Flow API body.
        f={'schemaVersion':'1.0.0.0','properties':{k:f['properties'][k] for k in ('connectionReferences','definition')}}
        f['properties']['templateName']=None
        definitions.append((key,display_name,f))
    return write_package(name,prefix,definitions,allvars,refs,output,schemas(settings.get('listSuffix','')))

def write_package(name,prefix,definitions,allvars,refs,output,datasets=None,version=VERSION):
    output.mkdir(parents=True, mode=0o700)
    solution=ET.Element('ImportExportXml',{'version':'9.2','SolutionPackageVersion':'9.2','languagecode':'1033','generatedBy':'CrmLive'})
    manifest=ET.SubElement(solution,'SolutionManifest')
    text(manifest,'UniqueName',name)
    ET.SubElement(ET.SubElement(manifest,'LocalizedNames'),'LocalizedName',{'description':name,'languagecode':'1033'})
    text(manifest,'Version',version); text(manifest,'Managed',0)
    publisher=ET.SubElement(manifest,'Publisher'); text(publisher,'UniqueName',prefix+'Publisher')
    ET.SubElement(ET.SubElement(publisher,'LocalizedNames'),'LocalizedName',{'description':'PPG source collection','languagecode':'1033'})
    text(publisher,'CustomizationPrefix',prefix); text(publisher,'CustomizationOptionValuePrefix',10000)
    roots=ET.SubElement(manifest,'RootComponents'); ET.SubElement(manifest,'MissingDependencies')
    custom=ET.Element('ImportExportXml')
    for tag in ('Entities','Roles','Workflows','FieldSecurityProfiles','Templates','EntityMaps','EntityRelationships','OrganizationSettings','optionsets','CustomControls','EntityDataProviders'):
        ET.SubElement(custom,tag)
    cr=ET.SubElement(custom,'connectionreferences')
    for logical, ref in sorted(refs.items()):
        el=ET.SubElement(cr,'connectionreference',{'connectionreferencelogicalname':logical})
        for k,v in {'connectionreferencedisplayname':logical,'connectorid':ref['connectorId'],
                    'iscustomizable':1,'promptingbehavior':0,'statecode':0,'statuscode':1}.items():text(el,k,v)
    text(ET.SubElement(custom,'Languages'),'Language',1033)
    for schema,value in sorted(allvars.items()):
        el=ET.Element('environmentvariabledefinition',{'schemaname':schema})
        text(el,'defaultvalue',value)
        ET.SubElement(ET.SubElement(el,'displayname'),'label',{'description':schema,'languagecode':'1033'})
        text(el,'type',100000000); text(el,'iscustomizable',1)
        write_xml(output/'environmentvariabledefinitions'/schema/'environmentvariabledefinition.xml',el,declaration=False)
    flows=[]
    for key,display_name,flow in definitions:
        wid=str(uuid5(NAMESPACE,name+':'+key)); filename=key+'-'+wid+'.json'
        target=output/'Workflows'/filename; target.parent.mkdir(exist_ok=True)
        target.write_text(json.dumps(flow,indent=2)+'\n')
        meta=ET.Element('Workflow',{'WorkflowId':'{'+wid+'}', 'Name':display_name})
        for k,v in {'JsonFileName':'/Workflows/'+filename,'Type':1,'Subprocess':0,'Category':5,
                    'Mode':0,'Scope':4,'OnDemand':0,'TriggerOnCreate':0,'TriggerOnDelete':0,
                    'AsyncAutodelete':0,'SyncWorkflowLogOnFailure':0,'StateCode':0,'StatusCode':1,
                    'RunAs':1,'IsTransacted':1,'IntroducedVersion':version,'IsCustomizable':1,
                    'BusinessProcessType':0,'IsCustomProcessingStepAllowedForOtherPublishers':1,
                    'ModernFlowType':0,'PrimaryEntity':'none'}.items():text(meta,k,v)
        ET.SubElement(ET.SubElement(meta,'LocalizedNames'),'LocalizedName',{'description':display_name,'languagecode':'1033'})
        write_xml(target.with_name(filename+'.data.xml'),meta)
        ET.SubElement(roots,'RootComponent',{'type':'29','id':'{'+wid+'}','behavior':'0'})
        flows.append({'key':key,'workflowId':wid,'state':'Stopped'})
    write_xml(output/'Other/Solution.xml',solution); write_xml(output/'Other/Customizations.xml',custom)
    settings_out={'EnvironmentVariables':[{'SchemaName':k,'Value':v} for k,v in sorted(allvars.items())],
                  'ConnectionReferences':[{'LogicalName':k,'ConnectionId':v['connectionId'],'ConnectorId':v['connectorId']} for k,v in sorted(refs.items())]}
    private_json(output.parent/(output.name+'-deployment-settings.json'), settings_out)
    receipt={'version':version,'solutionName':name,'flows':flows,'datasets':datasets or {},
             'nativeWrites':0,'crossTenantRecovery':'deferred','activation':'separate qualification required',
             'files':{p.relative_to(output).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.rglob('*')) if p.is_file()}}
    private_json(output.parent/(output.name+'-manifest.json'), receipt)
    return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--settings',type=Path)
    p.add_argument('--list-suffix',default=''); p.add_argument('--output',type=Path); p.add_argument('--schemas',action='store_true'); a=p.parse_args()
    if a.schemas: print(json.dumps(schemas(a.list_suffix),indent=2)); return
    if not a.settings or not a.output or '.local' not in a.settings.resolve().parts: p.error('Private --settings and --output required')
    r=build(json.loads(a.settings.read_text()),a.output)
    print(json.dumps({'version':r['version'],'flows':len(r['flows']),'datasets':len(r['datasets']),'nativeWrites':0}))

if __name__=='__main__': main()

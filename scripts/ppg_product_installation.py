"""Compose the source module and maintained PPG workflows into one stopped solution."""
from __future__ import annotations
import argparse,hashlib,json,re
from urllib.parse import urlsplit
from copy import deepcopy
from pathlib import Path
from ppg_source_installation import build as build_sources,write_package,private_json
from check_email_safety import email_actions
from ppg_office_bindings import bind as bind_office
from ppg_installation_paths import bind_paths,bind_checkpoint,bind_catalogue_inputs
ROOT=Path(__file__).resolve().parents[1]
TOKEN=re.compile(r'__PPG_INSTALL_\d{5}__')

def bind_document_generation(flow,binding,settings):
 from ppg_native_package_flow import build_flow
 objects=settings['objects']
 if binding.get('savedBodyFinalisation') is not True:raise ValueError('Saved-body finalisation required for commissioned generation')
 if binding['site']!=settings['site'] or binding['folder']!=objects['review-evidence']['path'] or binding['libraryId']!=objects['review-evidence']['id']:raise ValueError('Document destination must belong to this installation')
 if binding['caseIntake']['reviewQueueListId']!=objects['review-queue']['id'] or binding['caseIntake']['catalogueListId']!=objects['catalogue']['id']:raise ValueError('Document inputs must belong to this installation')
 return build_flow(flow,binding)

def build(settings,output):
 if output.exists() or '.local' not in output.resolve().parts:raise ValueError('New private output required')
 schema=json.loads((ROOT/'config/whole-product-installation.json').read_text());manifest=json.loads((ROOT/'config/product-workflows.json').read_text())
 objects=settings['objects'];required={s['key']for s in schema['objects']}
 if set(objects)!=required:raise ValueError('Complete provisioned object bindings required')
 values={}
 for token,meta in manifest['bindings'].items():
  kind=meta['kind']
  if kind=='site':value=settings['site']
  elif kind=='sitePath':value=urlsplit(settings['site']).path
  elif kind.startswith('office-script:'):value=settings.get('officeScripts',{}).get(kind.split(':',1)[1],{}).get('scriptId') or settings.get('runtimeBindings',{}).get(token)
  elif kind=='workingPath':value=objects['review-evidence']['path']+'/Working'
  elif kind.startswith('list:'):value=objects[kind.split(':',1)[1]]['id']
  elif kind.startswith('path:'):value=objects[kind.split(':',1)[1]]['path']
  else:value=settings.get('runtimeBindings',{}).get(token)
  if not isinstance(value,str)or not value:raise ValueError('Explicit runtime binding required: '+token+' ('+kind+')')
  values[token]=value
 sources=deepcopy(settings['sources']);sources.update(solutionName=settings['solutionName'],publisherPrefix=settings['publisherPrefix']);sources['bindings']['site']=settings['site']
 source_map={'leads':'source-update-leads','captures':'hospital-dataset-captures','qh-hospital-facilities':'hospital-facilities','qh-hospital-metrics':'hospital-current-metrics','qh-hospital-busyness':'hospital-busyness-trends'}
 sources['bindings']['lists']={k:objects[v]['id'] for k,v in source_map.items()}
 source_dir=output.parent/(output.name+'-sources');source=build_sources(sources,source_dir)
 ds=json.loads((source_dir.parent/(source_dir.name+'-deployment-settings.json')).read_text());allvars={v['SchemaName']:v['Value']for v in ds['EnvironmentVariables']};refs={r['LogicalName']:{'connectorId':r['ConnectorId'],'connectionId':r['ConnectionId']}for r in ds['ConnectionReferences']};defs=[]
 for f in source['flows']:
  path=next((source_dir/'Workflows').glob(f['key']+'-*.json'));flow=json.loads(path.read_text());defs.append((f['key'],'PPG | Sources | '+f['key'],flow))
 for entry in manifest['flows']:
  path=ROOT/entry['file'];raw=path.read_text()
  if hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:raise ValueError('Workflow source changed: '+entry['key'])
  raw=TOKEN.sub(lambda m:json.dumps(values[m.group()],ensure_ascii=False)[1:-1],raw);
  if TOKEN.search(raw):raise ValueError('Unresolved installation binding')
  flow=json.loads(raw)
  flow['properties']['definition']=bind_paths(flow['properties']['definition'],settings['site'],objects,schema)
  if settings.get('baselineCheckpointFile'):
   flow['properties']['definition']=bind_checkpoint(flow['properties']['definition'],settings['baselineCheckpointFile'])
  if entry['key']=='qw3source-onlyreconciliation':
   flow['properties']['definition']=bind_catalogue_inputs(flow['properties']['definition'],settings.get('identityApplicationFile'),settings.get('catalogueFixtureDocumentUIDs',[]))
   from ppg_catalogue_flow_batches import build as bind_catalogue_batches
   flow=bind_catalogue_batches(flow)
  if settings.get('officeScripts'):
   flow['properties']['definition'],_=bind_office(flow['properties']['definition'],settings['officeScripts'])
  if settings.get('documentGeneration') and entry['key']=='generatecoverandexistingpack':
   flow=bind_document_generation(flow,settings['documentGeneration'],settings)
  for alias in entry['connectors']:
   logical=settings['publisherPrefix']+'_'+alias;connection=settings['connections'][alias]
   refs[logical]={'connectorId':'/providers/Microsoft.PowerApps/apis/'+alias,'connectionId':connection}
   flow['properties']['connectionReferences'][alias]={'runtimeSource':'embedded','connection':{'connectionReferenceLogicalName':logical},'api':{'name':alias}}
  if email_actions(flow):raise ValueError('Communication-capable workflow refused')
  flow['properties']['definition']['contentVersion']='1.0.4.0';flow['schemaVersion']='1.0.0.0'
  defs.append((entry['key'],entry['name'],flow))
 receipt=write_package(settings['solutionName'],settings['publisherPrefix'],defs,allvars,refs,output,schema,version='1.0.4.0')
 receipt['activation']='Stopped; configure source baselines, script hosts and operator requests before activation'
 receipt['externalDependencies']=schema['externalDependencies'];receipt['deferred']=schema['deferred']
 private_json(output.parent/(output.name+'-product.json'),receipt)
 return receipt

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--settings',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if '.local' not in a.settings.resolve().parts:p.error('Private settings required')
 r=build(json.loads(a.settings.read_text()),a.output);print(json.dumps({'flows':len(r['flows']),'version':r['version'],'nativeWrites':0}))

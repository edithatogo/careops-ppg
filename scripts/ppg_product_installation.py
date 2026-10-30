"""Compose the source module and maintained PPG workflows into one stopped solution."""
from __future__ import annotations
import argparse,hashlib,json,re
from urllib.parse import urlsplit
from copy import deepcopy
from pathlib import Path
from ppg_source_installation import build as build_sources,write_package,private_json
from check_email_safety import email_actions
ROOT=Path(__file__).resolve().parents[1]
TOKEN=re.compile(r'__PPG_INSTALL_\d{5}__')

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
  for alias in entry['connectors']:
   logical=settings['publisherPrefix']+'_'+alias;connection=settings['connections'][alias]
   refs[logical]={'connectorId':'/providers/Microsoft.PowerApps/apis/'+alias,'connectionId':connection}
   flow['properties']['connectionReferences'][alias]={'runtimeSource':'embedded','connection':{'connectionReferenceLogicalName':logical},'api':{'name':alias}}
  if email_actions(flow):raise ValueError('Communication-capable workflow refused')
  flow['properties']['definition']['contentVersion']='1.0.0.0';flow['schemaVersion']='1.0.0.0'
  defs.append((entry['key'],entry['name'],flow))
 receipt=write_package(settings['solutionName'],settings['publisherPrefix'],defs,allvars,refs,output,schema,version='1.0.0.0')
 receipt['activation']='Stopped; configure source baselines, script hosts and operator requests before activation'
 receipt['externalDependencies']=schema['externalDependencies'];receipt['deferred']=schema['deferred']
 private_json(output.parent/(output.name+'-product.json'),receipt)
 return receipt

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--settings',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if '.local' not in a.settings.resolve().parts:p.error('Private settings required')
 r=build(json.loads(a.settings.read_text()),a.output);print(json.dumps({'flows':len(r['flows']),'version':r['version'],'nativeWrites':0}))

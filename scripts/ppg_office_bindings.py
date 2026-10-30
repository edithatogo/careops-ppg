"""Bind named Office Script profiles without changing script inputs or flow identity."""
from copy import deepcopy
import json
from pathlib import Path
PARAMETERS=('source','drive','file','scriptSource','scriptDrive','scriptId')
def bind(definition,bindings):
    result=deepcopy(definition);profiles=json.loads((Path(__file__).resolve().parents[1]/'config/product-office-scripts.json').read_text())['profiles'];actions={a:p for p in profiles for a in p['actions']};used=set()
    def walk(node):
        if not isinstance(node,dict):return
        for name,action in node.items():
            if not isinstance(action,dict):continue
            if isinstance(action.get('inputs'),dict) and action['inputs'].get('host',{}).get('operationId')=='RunScriptProdV2':
                if name not in actions:raise ValueError('Unqualified Office Script action: '+name)
                profile=actions[name];b=bindings[profile['key']]
                required=set(PARAMETERS)-({'file'} if profile['host']=='isolated-source-copy' else set())
                if not required.issubset(b) or any(not isinstance(b[k],str) or not b[k] for k in required):raise ValueError('Incomplete Office Script binding')
                parameters=action['inputs']['parameters'];parameters.update({k:b[k] for k in required});used.add(profile['key'])
                if profile['host']=='isolated-source-copy' and 'file' in b:parameters['file']=b['file']
                action['inputs']['retryPolicy']={'type':'none'}
            walk(action)
    walk(result.get('actions',{}));return result,sorted(used)

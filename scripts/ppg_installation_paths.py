"""Rebind site-relative library paths left inside connector parameters."""
import json,re
from urllib.parse import urlsplit

def bind_paths(definition,site,objects,contract):
    # Only complete path components; an already isolated name must not be rewritten.
    pairs=[];site_path=urlsplit(site).path.rstrip('/')
    for o in contract['objects']:
        if o['baseTemplate']!=101:continue
        old='/'+o['title'];new=objects[o['key']]['path']
        if not new.startswith(site_path+'/'):raise ValueError('Library outside destination site')
        relative=new[len(site_path):]
        pairs.extend([(site.rstrip('/')+old,urlsplit(site).scheme+'://'+urlsplit(site).netloc+new),(site_path+old,new),(old,relative)])
    def walk(x):
        if isinstance(x,dict):return{k:walk(v)for k,v in x.items()}
        if isinstance(x,list):return[walk(v)for v in x]
        if isinstance(x,str):
            for old,new in pairs:
                # Full URLs are processed first; matching a suffix of the result is excluded.
                x=re.sub(r'(?<![A-Za-z0-9/])'+re.escape(old)+r'(?=[/\'"?)#]|$)',lambda _:new,x)
        return x
    return walk(definition)

def bind_checkpoint(definition, filename):
    """Select a separate commissioned checkpoint without replacing an existing fixture."""
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,100}\.json', filename):
        raise ValueError('Safe checkpoint filename required')
    def walk(x):
        if isinstance(x, dict): return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list): return [walk(v) for v in x]
        if isinstance(x, str):
            return re.sub(r'(?<![\w.-])qw3-last-successful\.json(?![\w.-])', lambda _: filename, x)
        return x
    return walk(definition)

def bind_catalogue_inputs(definition, application_file=None, fixture_uids=()):
    """Select reviewed decisions and exclude explicitly retained installation fixtures.

    No source identities are inferred. The caller must qualify each fixture before
    supplying its UUID; all other unexpected catalogue identities still fail closed.
    """
    from uuid import UUID
    if application_file and not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,100}\.json', application_file):
        raise ValueError('Safe identity application filename required')
    uids=[str(UUID(uid)) for uid in fixture_uids]
    if len(uids)!=len(set(uids)):raise ValueError('Duplicate fixture UUID')
    def walk(x):
        if isinstance(x,list):return [walk(v) for v in x]
        if not isinstance(x,dict):return x
        result={k:walk(v) for k,v in x.items()}
        for name in ('Read_current','Read_current_after'):
            action=result.get(name)
            if uids and isinstance(action,dict) and 'inputs' in action:
                params=action['inputs']['parameters'];uri=params['parameters/uri']
                if '$filter=' in uri:raise ValueError('Existing catalogue filter requires review')
                params['parameters/uri']=uri+'&$filter='+ ' and '.join("DocumentUID ne '"+uid+"'" for uid in uids)
        action=result.get('Read_identity_application')
        if application_file and isinstance(action,dict) and 'inputs' in action:
            params=action['inputs']['parameters'];params['parameters/uri']=params['parameters/uri'].replace('/identity-application.json', '/'+application_file)
        return result
    return walk(definition)

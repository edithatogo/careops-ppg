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

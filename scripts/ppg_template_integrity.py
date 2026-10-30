"""Verify Word content while accounting for SharePoint property stamping."""
import base64,hashlib,io,json,re,sys,zipfile
import xml.etree.ElementTree as E

def verify(source,native):
 with zipfile.ZipFile(io.BytesIO(source))as a,zipfile.ZipFile(io.BytesIO(native))as b:
  aa=set(a.namelist());bb=set(b.namelist())
  if len(aa)!=len(a.namelist())or len(bb)!=len(b.namelist())or not aa<=bb:raise ValueError('Template members removed or duplicated')
  mutable={'_rels/.rels','word/_rels/document.xml.rels','[Content_Types].xml'}
  for n in aa-mutable:
   if a.read(n)!=b.read(n):raise ValueError('Template content changed: '+n)
  for n in bb-aa:
   if not re.fullmatch(r'(?:docProps/custom.xml|customXml/(?:item(?:Props)?\d+\.xml|_rels/item\d+\.xml.rels)|\[trash\]/\d+\.dat)',n):raise ValueError('Unexpected template member')
  for n in mutable:
   old=E.fromstring(a.read(n));new=E.fromstring(b.read(n));canonical=lambda e:(e.tag,tuple(sorted(e.attrib.items())))
   before={canonical(e)for e in old};after={canonical(e)for e in new}
   if not before<=after:raise ValueError('Template relationships changed')
   for e in new:
    if canonical(e)in before:continue
    if n.endswith('.rels'):
     if e.get('TargetMode')=='External'or e.get('Type')not in ['http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXml','http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties']:raise ValueError('Unexpected template relationship')
    elif e.get('ContentType')not in ['application/vnd.openxmlformats-officedocument.custom-properties+xml','application/vnd.openxmlformats-officedocument.customXmlProperties+xml','application/octet-stream','application/xml']:raise ValueError('Unexpected content type')
 return {'contentPreserved':True,'sourceSHA256':hashlib.sha256(source).hexdigest(),'nativeSHA256':hashlib.sha256(native).hexdigest(),'sharePointPropertyStamping':source!=native}
if __name__=='__main__':
 if sys.version_info[:3]!=(3,15,1):raise SystemExit('Qualified Python 3.15.1 required')
 x=json.load(sys.stdin);print(json.dumps(verify(base64.b64decode(x['source']),base64.b64decode(x['native']))))

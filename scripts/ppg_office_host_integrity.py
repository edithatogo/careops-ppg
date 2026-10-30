"""Allow service metadata on a deliberately empty detached Excel host only."""
import base64,hashlib,io,json,re,sys,zipfile
import xml.etree.ElementTree as E
N={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
def verify(source,native):
 for data in (source,native):
  with zipfile.ZipFile(io.BytesIO(data)) as z:
   names=z.namelist()
   if len(names)!=len(set(names)) or len(names)>100 or sum(i.file_size for i in z.infolist())>20000000:raise ValueError('Unexpected workbook archive')
   for name in names:
    if name not in {'[Content_Types].xml','_rels/.rels','xl/workbook.xml','xl/_rels/workbook.xml.rels','xl/worksheets/sheet1.xml','xl/styles.xml','xl/theme/theme1.xml','xl/calcChain.xml','docProps/core.xml','docProps/app.xml','docProps/custom.xml'} and not re.fullmatch(r'(customXml/(item\d+\.xml|itemProps\d+\.xml|_rels/item\d+\.xml.rels)|\[trash\]/\d+\.dat)',name):raise ValueError('Unexpected workbook part: '+name)
    if name.endswith('.rels'):
     for r in E.fromstring(z.read(name)):
      if r.get('TargetMode')=='External':raise ValueError('External workbook relationship')
   w=E.fromstring(z.read('xl/workbook.xml'));sheets=w.findall('s:sheets/s:sheet',N)
   if len(sheets)!=1 or sheets[0].get('name')!='Runtime' or sheets[0].get('state','visible')!='visible':raise ValueError('Host sheet changed')
   if w.findall('s:definedNames/*',N) or w.findall('s:externalReferences/*',N):raise ValueError('Host gained workbook content')
   sheet=E.fromstring(z.read('xl/worksheets/sheet1.xml'))
   if sheet.findall('.//s:c',N) or sheet.findall('.//s:f',N):raise ValueError('Host gained cells or formulas')
   if 'xl/calcChain.xml' in names and len(E.fromstring(z.read('xl/calcChain.xml'))):raise ValueError('Host gained calculations')
 return {'emptyHostPreserved':True,'sourceSHA256':hashlib.sha256(source).hexdigest(),'nativeSHA256':hashlib.sha256(native).hexdigest()}
if __name__=='__main__':
 assert sys.version_info[:3]==(3,15,1)
 j=json.load(sys.stdin);print(json.dumps(verify(base64.b64decode(j['source']),base64.b64decode(j['native']))))

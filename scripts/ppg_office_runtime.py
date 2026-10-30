"""Build immutable Office Script assets and detached scratch workbooks."""
import argparse,hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def blank_workbook(path):
    ns='http://schemas.openxmlformats.org/'
    parts={
      '[Content_Types].xml':f'<Types xmlns="{ns}package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
      '_rels/.rels':f'<Relationships xmlns="{ns}package/2006/relationships"><Relationship Id="rId1" Type="{ns}officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
      'xl/workbook.xml':f'<workbook xmlns="{ns}spreadsheetml/2006/main" xmlns:r="{ns}officeDocument/2006/relationships"><sheets><sheet name="Runtime" sheetId="1" r:id="rId1"/></sheets></workbook>',
      'xl/_rels/workbook.xml.rels':f'<Relationships xmlns="{ns}package/2006/relationships"><Relationship Id="rId1" Type="{ns}officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
      'xl/worksheets/sheet1.xml':f'<worksheet xmlns="{ns}spreadsheetml/2006/main"><sheetData/></worksheet>'}
    with zipfile.ZipFile(path,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for name,data in parts.items():z.writestr(zipfile.ZipInfo(name,(2026,1,1,0,0,0)),data)
def build(output,source_system='example-ppg-register'):
    if output.exists() or '.local' not in output.resolve().parts:raise ValueError('New private output required')
    if not source_system or any(ord(c)<32 for c in source_system):raise ValueError('Explicit source identity required')
    output.mkdir(parents=True);manifest=json.loads((ROOT/'config/product-office-scripts.json').read_text());assets=[]
    for profile in manifest['profiles']:
        body=(ROOT/profile['source']).read_text()
        if hashlib.sha256(body.encode()).hexdigest()!=profile['sourceSHA256']:raise ValueError('Script source changed: '+profile['key'])
        if profile['key']=='catalogue':body=body.replace('"example-ppg-register"',json.dumps(source_system))
        package=json.loads((ROOT/profile['metadata']).read_text());package['body']=body
        name='ppg-'+profile['key']+'.osts';(output/name).write_text(json.dumps(package))
        row={**profile,'script':name,'bodySHA256':hashlib.sha256(body.encode()).hexdigest()}
        names=[name]
        if profile['host']=='blank-workbook':
            row['workbook']='ppg-'+profile['key']+'-host.xlsx';blank_workbook(output/row['workbook']);names.append(row['workbook'])
        for name in names:assets.append({'name':name,'sha256':hashlib.sha256((output/name).read_bytes()).hexdigest()})
        profile.update(row)
    manifest['assets']=assets;(output/'runtime.json').write_text(json.dumps(manifest,indent=2));return manifest
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--source-system',default='example-ppg-register');a=p.parse_args();print(json.dumps({'profiles':len(build(a.output,a.source_system)['profiles'])}))

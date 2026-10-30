"""Materialise maintained template assets and an editable Word template locally."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def build(output,dotnet):
 if output.exists()or'.local'not in output.resolve().parts:raise ValueError('New private asset directory required')
 m=json.loads((ROOT/'config/product-template-assets.json').read_text());output.mkdir(parents=True)
 for a in m['assets']:
  p=ROOT/a['source'];data=p.read_bytes()
  if hashlib.sha256(data).hexdigest()!=a['sha256']:raise ValueError('Template source changed')
  (output/a['name']).write_bytes(data)
 source=ROOT/'templates/review-package.md';dll=ROOT/'tools/native-document-template/bin/Debug/net10.0/TemplateBuilder.dll';target=output/'review-package.docx'
 subprocess.run([str(dotnet.resolve()),'exec',str(dll),str(source),hashlib.sha256(source.read_bytes()).hexdigest(),str(target)],check=True)
 m['assets'].append({'source':'tools/native-document-template','name':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'bytes':target.stat().st_size})
 (output/'assets.json').write_text(json.dumps(m,indent=2));return m
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--dotnet',type=Path,required=True);a=p.parse_args();print(json.dumps({'assets':len(build(a.output,a.dotnet)['assets'])}))

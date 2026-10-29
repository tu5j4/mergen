"""Build a fixed, hashed model payload from explicitly supplied local exports."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from installer.catalog import OCR_NAMES
from app.storage import VERSION


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def prepare(output, installed, context, downloads):
    output=Path(output).resolve()
    if output.exists():raise ValueError('choose a new payload folder')
    installed,context,downloads=map(Path,(installed,context,downloads))
    mappings={
        '600m':[(installed/(name:='nllb-200-distilled-600M'+suffix),'models/'+name)
                for suffix in ('-hf','-ct2')],
        '1300m':[(context/'base-bf16','models/nllb-1.3b-baglam-v3/base-bf16'),
                 (context/'adapter-masked','models/nllb-1.3b-baglam-v3/adapter-masked')],
        'ocr-paddle':[(installed/'ocr/paddle'/name,'models/ocr/paddle/'+name) for name in list(OCR_NAMES.values())[:3]],
        'korean-paddle':[(downloads/'korean','models/ocr/paddle/'+OCR_NAMES['korean'])],
        'manga':[(downloads/'manga','models/manga')],
    }
    components={};original_weights=[]
    for key,trees in mappings.items():
        rows=[]
        for source,relative in trees:
            if not source.is_dir():raise ValueError('missing source: '+str(source))
            for path in sorted(source.rglob('*')):
                if not path.is_file() or any(p in ('.cache','__pycache__','.git') for p in path.parts):continue
                if path.name.startswith('.') or path.name=='mergen-ready.json' or path.suffix=='.pyc':continue
                target=output/relative/path.relative_to(source)
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(path,target)
                if path.suffix=='.json':
                    text=target.read_text(encoding='utf-8')
                    if 'Users' in text:
                        data=json.loads(text)
                        def sanitize(value):
                            if isinstance(value,dict):return {k:sanitize(v) for k,v in value.items()}
                            if isinstance(value,list):return [sanitize(v) for v in value]
                            if isinstance(value,str) and (':/Users/' in value.replace('\\','/') or ':\\Users\\' in value):return ''
                            return value
                        data=sanitize(data)
                        if path.name=='adapter_config.json':data['base_model_name_or_path']='base-bf16'
                        target.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
                hashed=digest(target)
                rows.append(dict(path=target.relative_to(output).as_posix(),bytes=target.stat().st_size,sha256=hashed))
                if path.suffix in ('.bin','.safetensors','.pdiparams'):
                    original=digest(path)
                    if original!=hashed:raise ValueError('weights changed while copying')
                    original_weights.append(dict(component=key,path=target.relative_to(output).as_posix(),sha256=original))
        components[key]=rows
    manifest=dict(schema=1,release=VERSION,translation_versions={'600m':'original-standard','1300m':'mergen-context-v1'},
        ocr_sources=json.loads((downloads/'sources.json').read_text(encoding='utf-8')),components=components)
    (ROOT/'assets/bundled-models.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for key,trees in mappings.items():
        parents={output/relative for _,relative in trees}
        if key=='1300m':parents={output/'models/nllb-1.3b-baglam-v3'}
        for parent in parents:(parent/'mergen-ready.json').write_text(json.dumps(dict(complete=True,release=VERSION,component=key)),encoding='utf-8')
    (output/'original-weights.json').write_text(json.dumps(original_weights,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(files=sum(map(len,components.values())),bytes=sum(r['bytes'] for rows in components.values() for r in rows))))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('output','installed','context','downloads'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();prepare(a.output,a.installed,a.context,a.downloads)

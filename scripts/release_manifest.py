"""Sign an installer manifest. The private key must never be shipped."""
import argparse,base64,hashlib,json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from cryptography.hazmat.primitives.serialization import load_pem_private_key

def main():
    p=argparse.ArgumentParser();p.add_argument('--installer',type=Path,required=True)
    p.add_argument('--key',type=Path,required=True);p.add_argument('--version',required=True)
    p.add_argument('--tag',required=True);p.add_argument('--notes',default='');p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    from app.updates import version,trusted_url
    version(a.version)
    payload={'version':a.version,'url':trusted_url('https://github.com/tu5j4/mergen/releases/download/'+a.tag+'/'+a.installer.name),
        'bytes':a.installer.stat().st_size,'sha256':hashlib.sha256(a.installer.read_bytes()).hexdigest(),'notes':a.notes}
    key=load_pem_private_key(a.key.read_bytes(),password=None)
    signature=key.sign(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8'))
    a.output.write_text(json.dumps({'payload':payload,'signature':base64.b64encode(signature).decode()},ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()

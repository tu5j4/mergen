import sys
from pathlib import Path
sys.path.append(str(Path(sys.base_prefix)/'Lib/site-packages'))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,PublicFormat,NoEncryption
root=Path(__file__).resolve().parent.parent
private_path=Path(sys.argv[1])
if private_path.exists():raise FileExistsError('Existing signing key must not be overwritten')
private_path.parent.mkdir(parents=True,exist_ok=True)
key=Ed25519PrivateKey.generate()
private_path.write_bytes(key.private_bytes(Encoding.PEM,PrivateFormat.PKCS8,NoEncryption()))
(root/'assets/update-public-key.pem').write_bytes(key.public_key().public_bytes(Encoding.PEM,PublicFormat.SubjectPublicKeyInfo))
print('Public key generated. Private signing key retained outside the distribution.')

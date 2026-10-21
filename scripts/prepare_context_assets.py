"""Download the official Qwen 0.6B Q8 model and an official CPU llama build.

Stdlib only. Resolved versions and hashes are recorded for reproducibility.
"""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

MODEL_URL = 'https://huggingface.co/Qwen/Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B-Q8_0.gguf'
MODEL_SHA = '9465e63a22add5354d9bb4b99e90117043c7124007664907259bd16d043bb031'


def fetch(url, path, sha):
    if path.is_file():
        with path.open('rb') as existing:
            if hashlib.file_digest(existing, 'sha256').hexdigest() == sha:
                return
    partial = path.with_name(path.name + '.part')
    print('indiriliyor: ' + path.name, flush=True)
    req = urllib.request.Request(url, headers={'User-Agent': 'mergen-context-test'})
    with urllib.request.urlopen(req, timeout=90) as src, partial.open('wb') as dst:
        digest = hashlib.sha256()
        total = 0
        reported = 0
        while block := src.read(1024*1024):
            dst.write(block)
            digest.update(block)
            total += len(block)
            if total-reported >= 64*1024*1024:
                print(f'{path.name}: {total//1024//1024} mb', flush=True)
                reported = total
    if digest.hexdigest() != sha:
        raise ValueError('download hash mismatch: ' + path.name)
    partial.replace(path)


def prepare(root):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / 'assets.json'
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    else:
        req = urllib.request.Request('https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=10',
            headers={'User-Agent': 'mergen-context-test', 'Accept': 'application/vnd.github+json'})
        with urllib.request.urlopen(req, timeout=30) as response:
            releases = json.load(response)
        selected = None
        for release in releases:
            if release.get('draft'):
                continue
            for asset in release.get('assets', []):
                if asset['name'].endswith('-bin-win-cpu-x64.zip') and asset.get('digest', '').startswith('sha256:'):
                    selected = (release['tag_name'], asset)
                    break
            if selected:
                break
        if not selected:
            raise RuntimeError('official Windows CPU asset with sha256 digest not found')
        version, asset = selected
        url = asset['browser_download_url']
        if not url.startswith('https://github.com/ggml-org/llama.cpp/releases/download/'):
            raise ValueError('unexpected binary repository')
        manifest = dict(llama_version=version, binary_url=url,
            binary_sha256=asset['digest'].split(':', 1)[1], model_url=MODEL_URL, model_sha256=MODEL_SHA)
    if not manifest['binary_url'].startswith('https://github.com/ggml-org/llama.cpp/releases/download/'):
        raise ValueError('unexpected binary repository')
    archive = root / 'llama-cpu.zip'
    fetch(manifest['binary_url'], archive, manifest['binary_sha256'])
    binary_root = root / 'llama'
    binary_root.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        for entry in bundle.infolist():
            target = (binary_root / entry.filename).resolve()
            if not target.is_relative_to(binary_root) or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('unsafe zip member')
        bundle.extractall(binary_root)
    executables = list(binary_root.rglob('llama-server.exe'))
    if len(executables) != 1:
        raise RuntimeError('llama-server.exe missing or ambiguous')
    model = root / 'qwen3-0.6b-q8.gguf'
    fetch(MODEL_URL, model, MODEL_SHA)
    manifest.update(executable=str(executables[0]), model=str(model))
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('qwen 0.6b ve cpu calisma zamani dogrulandi.', flush=True)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    prepare(parser.parse_args().root)

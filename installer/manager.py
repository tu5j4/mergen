"""Consent-based dependency manager. Bootstrap runs this outside either venv.

No pip, download, settings write or removal happens in --mode scan / --plan.
Removal accepts catalog keys, never arbitrary paths or package names.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from installer.hardware import detect

COMPONENTS = {
    'core': 'temel uygulama paketleri (zorunlu; cpu torch dahil)',
    'paddle-cpu': 'paddleocr cpu + ortak mobil ocr modelleri',
    'paddle-gpu': 'paddleocr nvidia cuda + ortak mobil ocr modelleri',
    'korean': 'korece mobil ocr modeli',
    'server': 'paddle sunucu modelleri (isteğe bağlı, daha büyük)',
    'manga-cpu': 'manga-ocr cpu + japonca modeli',
    'manga-gpu': 'manga-ocr izole nvidia gpu ortamı + japonca modeli',
    '600m': 'standart çeviri modeli — nllb 600m',
    '1300m': 'kaliteli çeviri modeli — nllb 1.3b',
}
CORE_PACKAGES = ['PySide6', 'mss', 'numpy', 'opencv-contrib-python', 'Pillow',
                 'ctranslate2', 'transformers', 'sentencepiece', 'psutil',
                 'pynput', 'paddleocr', 'paddlex', 'torch', 'torchvision']
MODEL_DIRS = {'600m': 'nllb-200-distilled-600M-ct2', '1300m': 'nllb-200-distilled-1.3B-ct2'}
PADDLE_MODELS = {
    'common': ['PP-OCRv5_mobile_det', 'PP-OCRv5_mobile_rec', 'PP-LCNet_x1_0_textline_ori'],
    'korean': ['korean_PP-OCRv5_mobile_rec'],
    'server': ['PP-OCRv5_server_det', 'PP-OCRv5_server_rec'],
}


def confirm(message):
    return input(message + ' [e/h]: ').strip().lower() in ('e', 'evet')


def owned_path(root, relative):
    """Reject root, traversal and reparse points before any destructive action."""
    root = Path(root).resolve()
    relative = Path(relative)
    if relative.is_absolute() or '..' in relative.parts or not relative.parts:
        raise ValueError('güvensiz hedef yolu')
    target = root / relative
    resolved = target.resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise ValueError('hedef uygulama klasörünün dışında')
    for path in (target, *target.parents):
        if path == root:
            break
        reparse = path.exists() and bool(getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)
        if path.is_symlink() or reparse:
            raise ValueError('bağlantı/junction üzerinde işlem yapılmaz')
    return target


def package_versions(python):
    if not python.is_file():
        return {}
    code = ("import importlib.metadata as m,json; "
            "print(json.dumps({d.metadata['Name'].lower():d.version for d in m.distributions()}))")
    try:
        output = subprocess.check_output([str(python), '-c', code], text=True,
            timeout=30, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return json.loads(output)
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}


class Manager:
    def __init__(self, root=ROOT, hardware=None):
        self.root = Path(root).resolve()
        self.hardware = hardware if hardware is not None else detect()
        self.python = self.root / '.venv' / 'Scripts' / 'python.exe'
        self.helper = self.root / '.manga-venv' / 'Scripts' / 'python.exe'
        self.state_path = self.root / '.install-state.json'
        self.env = dict(os.environ, PYTHONUTF8='1')
        self.env.pop('PYTHONPATH', None)
        self.env.pop('PYTHONHOME', None)
        if (self.root / '.mergen-managed').is_file() or not self.python.is_file():
            self.local_cache_environment()

    def local_cache_environment(self):
        self.env['HF_HOME'] = str(self.root / '.cache' / 'huggingface')
        self.env['HF_HUB_CACHE'] = str(self.root / '.cache' / 'huggingface' / 'hub')
        self.env['PADDLE_PDX_CACHE_HOME'] = str(self.root / '.cache' / 'paddlex')

    def scan(self):
        versions = package_versions(self.python)
        helper_versions = package_versions(self.helper)
        managed = (self.root / '.mergen-managed').is_file() or not self.python.is_file()
        paddle_cache = self.root / '.cache' / 'paddlex' if managed else Path.home() / '.paddlex'
        hf_cache = self.root / '.cache' / 'huggingface' / 'hub' if managed else Path(os.environ.get('HF_HUB_CACHE', Path.home() / '.cache' / 'huggingface' / 'hub'))
        def paddle_ready(key):
            return all((paddle_cache / 'official_models' / name / 'inference.json').is_file()
                       and (paddle_cache / 'official_models' / name / 'inference.pdiparams').is_file()
                       for name in PADDLE_MODELS[key])
        manga_ready = any((config.parent / 'model.safetensors').is_file() or
                          (config.parent / 'pytorch_model.bin').is_file()
                          for config in (hf_cache / 'models--kha-white--manga-ocr-base' / 'snapshots').glob('*/config.json'))
        ready = {
            'core': all(name.lower() in versions for name in CORE_PACKAGES),
            'paddle-cpu': 'paddlepaddle' in versions and paddle_ready('common'),
            'paddle-gpu': 'paddlepaddle-gpu' in versions and paddle_ready('common'),
            'korean': paddle_ready('korean'), 'server': paddle_ready('server'),
            'manga-cpu': 'manga-ocr' in versions and manga_ready,
            'manga-gpu': 'manga-ocr' in helper_versions and '+cu' in helper_versions.get('torch', '') and manga_ready,
        }
        for key, folder in MODEL_DIRS.items():
            ready[key] = (self.root / 'models' / folder / 'model.bin').is_file() and (self.root / 'models' / folder / 'tokenizer' / 'tokenizer_config.json').is_file()
        return {'versions': versions, 'helper_versions': helper_versions, 'ready': ready}

    def show(self):
        report = self.scan()
        print('\nmergen · donanım ve bağımlılıklar')
        print(f"{self.hardware['os']} / {self.hardware['machine']} / python {self.hardware['python']}")
        for adapter in self.hardware['adapters']:
            print(f"ekran kartı: {adapter['name']} ({adapter['vendor']})")
        for gpu in self.hardware['nvidia']:
            print(f"nvidia {gpu['index']}: sürücü {gpu['driver']}, {gpu['memory_mib']} mib, cuda yeteneği {gpu['compute_capability']}")
        print('cuda ön kontrolü: ' + ('uygun aday; kurulumdan sonra gerçek işlem testi yapılır' if self.hardware['cuda_candidate'] else 'bu paket için uygun değil / doğrulanamadı; cpu kullanın'))
        print('amd/intel ekran kartlarında bu dağıtım cpu kullanır.')
        print(f"boş alan: {self.hardware['free_gib']} gib")
        for i, (key, label) in enumerate(COMPONENTS.items(), 1):
            print(f" {i} · [{'mevcut' if report['ready'][key] else 'eksik / tamamlanmamış'}] {label}")
        if 'paddlepaddle' in report['versions'] and 'paddlepaddle-gpu' in report['versions']:
            print('uyarı: iki paddle altyapısı birlikte kurulu; birini yeniden kurarak onarın.')
        print('mevcut bilgisi dosya/paket kontrolüdür; çalışabilirlik için sağlık kontrolünü kullanın.')
        return report

    def plan(self, requested, inventory=None):
        unknown = set(requested) - COMPONENTS.keys()
        if unknown:
            raise ValueError(f'bilinmeyen bileşen: {unknown}')
        if {'paddle-cpu', 'paddle-gpu'} <= set(requested):
            raise ValueError('paddle cpu ve gpu birlikte kurulamaz; birini seçin')
        if any(k in requested for k in ('paddle-gpu', 'manga-gpu')) and not self.hardware['cuda_candidate']:
            raise ValueError('cuda donanım/sürücü ön kontrolü geçmedi; cpu seçin')
        state = inventory if inventory is not None else self.scan()
        result = set(requested)
        if requested and not state['ready']['core']:
            result.add('core')
        if any(k in result for k in ('korean', 'server')) and not (
                {'paddle-cpu', 'paddle-gpu'} & result or state['ready']['paddle-cpu'] or state['ready']['paddle-gpu']):
            result.add('paddle-cpu')
        return [key for key in COMPONENTS if key in result]

    def run(self, args):
        print('>', subprocess.list2cmdline([str(a) for a in args]), flush=True)
        subprocess.run([str(a) for a in args], cwd=self.root, env=self.env, check=True)

    def pip(self, *args):
        if not (self.root / '.venv' / 'pyvenv.cfg').is_file():
            raise RuntimeError('uygulamanın sanal ortamı bulunamadı')
        owned_path(self.root, '.venv')
        self.run([self.python, '-m', 'pip', *args])

    def install_packages(self, *args):
        self.pip('install', '--constraint', self.root / 'installer' / 'constraints.txt', *args)

    def write_settings(self, **changes):
        path = self.root / 'settings.json'
        settings = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
        settings.update(changes)
        path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding='utf-8')

    def record(self, key, status):
        state = json.loads(self.state_path.read_text(encoding='utf-8')) if self.state_path.exists() else {}
        state[key] = {'status': status, 'time': time.strftime('%Y-%m-%d %H:%M:%S')}
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')

    def download(self, component, cpu=False):
        self.run([self.python, self.root / 'installer' / 'models.py', component, *(['--cpu'] if cpu else [])])

    def install_one(self, key):
        if key == 'core':
            if not self.python.exists():
                owned_path(self.root, '.venv')
                self.run([sys.executable, '-m', 'venv', self.root / '.venv'])
                (self.root / '.mergen-managed').write_text('1\n', encoding='ascii')
                self.local_cache_environment()
            self.pip('install', '--upgrade', 'pip', 'setuptools', 'wheel')
            self.install_packages('torch==2.11.0', 'torchvision==0.26.0', '--index-url', 'https://download.pytorch.org/whl/cpu')
            self.install_packages('-r', self.root / 'installer' / 'requirements-base.txt')
            self.pip('check')
            self.run([self.python, '-c', "import torch,cv2,ctranslate2,PySide6; assert torch.version.cuda is None; print((torch.ones(2,2)@torch.ones(2,2)).sum().item())"])
        elif key in ('paddle-cpu', 'paddle-gpu'):
            # They share the 'paddle' import directory: uninstall BOTH before
            # reinstalling the selected implementation, never leave a collision.
            self.pip('uninstall', '-y', 'paddlepaddle', 'paddlepaddle-gpu')
            gpu = key == 'paddle-gpu'
            if gpu:
                self.install_packages('paddlepaddle-gpu==3.2.2', '--index-url', 'https://www.paddlepaddle.org.cn/packages/stable/cu129/')
                self.install_packages('nvidia-nvjitlink-cu12==12.9.86')
            else:
                self.install_packages('paddlepaddle==3.3.1')
            self.run([self.python, '-c',
                "from app.gpu_env import setup_cuda_dll_paths; setup_cuda_dll_paths(); import paddle; "
                + ("assert paddle.is_compiled_with_cuda(); paddle.set_device('gpu:0'); " if gpu else "paddle.set_device('cpu'); ")
                + "print(paddle.matmul(paddle.ones([4,4]),paddle.ones([4,4])).numpy())"])
            self.download('paddle', cpu=not gpu)
            self.write_settings(use_gpu='auto' if gpu else 'no')
        elif key in ('korean', 'server'):
            self.download(key, cpu='paddlepaddle-gpu' not in package_versions(self.python))
        elif key == 'manga-cpu':
            self.install_packages('manga-ocr==0.1.16')
            self.download('manga')
            self.run([self.python, '-c', "from app.core.manga_client import MangaClient; m=MangaClient('cpu'); assert m.device=='cpu'; m.close()"])
            self.write_settings(use_manga_ocr=True, manga_device='cpu')
        elif key == 'manga-gpu':
            owned_path(self.root, '.manga-venv')
            self.run([sys.executable, self.root / 'scripts' / 'setup_manga_gpu.py'])
            self.run([self.python, '-c', "from app.core.manga_client import MangaClient; m=MangaClient('cuda'); assert m.device=='cuda'; m.close()"])
            self.write_settings(use_manga_ocr=True, manga_device='auto', use_gpu='auto')
        elif key in MODEL_DIRS:
            self.download(key)
        else:
            raise ValueError(key)

    def install(self, requested):
        if not self.hardware['supported_os'] or not self.hardware['supported_python'] or not self.hardware['avx']:
            raise RuntimeError('bu kurulum windows 10 2004+/11 x64, python 3.11 x64 ve avx destekli işlemci ister')
        plan = self.plan(requested)
        if not plan:
            return
        print('\nkurulum planı (bağımlı bileşenler dahil):')
        for key in plan:
            print(' · ' + COMPONENTS[key])
        if {'paddle-cpu', 'paddle-gpu'} & set(plan):
            print('paddle cpu/gpu seçimi mevcut paddle altyapısının yerini alır.')
        if set(MODEL_DIRS) & set(plan):
            print('nllb: meta / cc-by-nc-4.0; modeller ticari olmayan kullanım içindir. ayrıntı: THIRD_PARTY_NOTICES.md')
        required = 5 + (8 if 'paddle-gpu' in plan else 0) + (8 if 'manga-gpu' in plan else 0) + (6 if '1300m' in plan else 3 if '600m' in plan else 0)
        print(f'tahmini geçici boş alan bütçesi: {required} gib; internetten büyük indirmeler yapılacak.')
        if self.hardware['free_gib'] < required:
            raise RuntimeError('yeterli boş alan yok; kurulum başlamadı')
        if not confirm('bu planı ve gerekli alt bağımlılıkları kurmayı onaylıyor musunuz?'):
            print('kurulum iptal edildi; paket kurulmadı.')
            return
        if not self.hardware['vc_runtime']:
            if not confirm('microsoft vc++ x64 çalışma zamanı eksik. resmi microsoft paketini sisteminize kurmaya izin veriyor musunuz?'):
                print('gerekli çalışma zamanı kurulmadığı için kurulum durdu.')
                return
            self.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', self.root / 'installer' / 'install_runtime.ps1'])
        if not confirm('mergen penceresini kapattınız mı?'):
            print('uygulamayı kapatıp yeniden deneyin.')
            return
        for key in plan:
            self.record(key, 'installing')
            try:
                self.install_one(key)
            except Exception:
                self.record(key, 'failed')
                print(f'{key} tamamlanamadı. önceki başarılı bileşenler korundu; menüden yeniden deneyebilirsiniz.')
                raise
            self.record(key, 'installed')
        print('\nseçilen işlemler tamamlandı. sağlık kontrolü yapılıyor...')
        self.health()

    def remove_paths(self, relatives):
        # Resolve every target before removing any. Nothing outside this copy,
        # including global model caches, can be selected through the menu.
        targets = [owned_path(self.root, relative) for relative in relatives]
        for target in targets:
            if target.is_dir():
                shutil.rmtree(target)
                print('silindi:', target)
            elif target.is_file():
                target.unlink()
                print('silindi:', target)

    def remove(self, requested):
        if not requested or set(requested) - COMPONENTS.keys():
            raise ValueError('geçerli bileşen seçilmedi')
        print('\nkaldırılacak bileşenler:')
        for key in requested:
            print(' · ' + COMPONENTS[key])
        print('bu bileşenlere bağlı özellikler çalışmayabilir. dosyalar kalıcı silinir; yeniden indirilebilir.')
        print('ortak/sistem önbellekleri, python ve ekran kartı sürücüleri kaldırılmaz.')
        if not confirm('uygulamayı kapattınız mı; seçilen bileşenler kaldırılsın mı?'):
            return
        running_env = Path(sys.prefix).resolve()
        if ('core' in requested and running_env == (self.root / '.venv').resolve()) or ('manga-gpu' in requested and running_env == (self.root / '.manga-venv').resolve()):
            raise RuntimeError('çalışan ortam silinemez; bagliliklar.bat dosyasından açın')
        # Optional package removal must precede removal of the shared environment.
        for key in sorted(set(requested), key=lambda k: k == 'core'):
            if key == 'core':
                self.remove_paths(['.venv'])
            elif key == 'manga-gpu':
                self.remove_paths(['.manga-venv'])
                self.write_settings(manga_device='cpu')
            elif key == 'manga-cpu':
                if self.python.exists():
                    self.pip('uninstall', '-y', 'manga-ocr')
                # The Japanese model is shared by CPU/GPU recognizers; keep it.
                self.write_settings(use_manga_ocr=self.helper.exists())
            elif key in ('paddle-cpu', 'paddle-gpu'):
                if self.python.exists():
                    self.pip('uninstall', '-y', 'paddlepaddle' if key == 'paddle-cpu' else 'paddlepaddle-gpu')
                if key == 'paddle-gpu':
                    self.write_settings(use_gpu='no')
            elif key in ('korean', 'server'):
                if not (self.root / '.mergen-managed').exists():
                    raise RuntimeError('bu eski kurulum ortak model önbelleğini kullanıyor; ortak dosyalar silinmedi')
                self.remove_paths(['.cache/paddlex/official_models/' + name for name in PADDLE_MODELS[key]])
                if key == 'server':
                    self.write_settings(paddle_mobile=True)
                else:
                    self.write_settings(source_lang='en')
            elif key in MODEL_DIRS:
                self.remove_paths(['models/' + MODEL_DIRS[key]])
                if (self.root / '.mergen-managed').is_file():
                    self.remove_paths(['.cache/huggingface/hub/models--facebook--' + MODEL_DIRS[key].removesuffix('-ct2')])
                other = '1300m' if key == '600m' else '600m'
                if (self.root / 'models' / MODEL_DIRS[other] / 'model.bin').exists():
                    self.write_settings(translation_model=MODEL_DIRS[other])
            self.record(key, 'removed')
        if {'manga-cpu', 'manga-gpu'} & set(requested) and (self.root / '.mergen-managed').is_file():
            if not self.helper.exists() and 'manga-ocr' not in package_versions(self.python):
                self.remove_paths(['.cache/huggingface/hub/models--kha-white--manga-ocr-base'])
        print('seçilen kaldırma işlemleri tamamlandı. ortak alt paketler diğer özellikler için korunur.')

    def health(self):
        inventory = self.scan()
        if not inventory['ready']['core']:
            print('temel paketler eksik; önce core kurulmalı. uygulama henüz hazır değil.')
            return False
        self.pip('check')
        versions = inventory['versions']
        if 'paddlepaddle' in versions and 'paddlepaddle-gpu' in versions:
            raise RuntimeError('cpu ve gpu paddle paketleri çakışıyor; tek altyapı seçip onarın')
        gpu = 'paddlepaddle-gpu' in versions
        if not ('paddlepaddle' in versions or gpu):
            print('paddle altyapısı eksik; uygulama henüz hazır değil.')
            return False
        if not (inventory['ready']['paddle-cpu'] or inventory['ready']['paddle-gpu']):
            print('ortak ocr modelleri eksik; paddle bileşenini onarın. uygulama henüz hazır değil.')
            return False
        self.run([self.python, '-c', "from app.gpu_env import setup_cuda_dll_paths; setup_cuda_dll_paths(); import paddle; "
                  + ("paddle.set_device('gpu:0'); " if gpu else "paddle.set_device('cpu'); ")
                  + "print(paddle.matmul(paddle.ones([2,2]),paddle.ones([2,2])).numpy())"])
        if not any(inventory['ready'][k] for k in MODEL_DIRS):
            print('çeviri modeli eksik; uygulama henüz hazır değil.')
            return False
        self.run([self.python, '-c', "from app.gpu_env import setup_cuda_dll_paths; setup_cuda_dll_paths(); "
            "from app.config import Settings; from app.core.translator import Translator; s=Settings.load(); "
            "t=Translator(s.model_path,device='cpu' if s.use_gpu=='no' else 'auto'); "
            "print('ceviri cihazi:',t.device,t.compute_type); print(t.translate(['Hello.'],'eng_Latn')); "
            + ("assert s.use_gpu=='no' or t.device=='cuda', 'ceviri cuda testi basarisiz'" if gpu else "print('cpu profili kontrol edildi')")])
        print('sağlık kontrolü geçti. baslat.bat ile açabilirsiniz.')
        return True


def choose_numbers():
    keys = list(COMPONENTS)
    raw = input('bileşen numaraları (örnek 1,2,8; iptal için boş): ').strip()
    if not raw:
        return []
    try:
        indexes = [int(n.strip()) for n in raw.replace(' ', ',').split(',') if n.strip()]
        if any(n < 1 or n > len(keys) for n in indexes):
            raise ValueError
        return list(dict.fromkeys(keys[n-1] for n in indexes))
    except ValueError:
        raise ValueError('yalnızca listede gösterilen numaraları girin') from None


def wizard(manager):
    selected = ['core']
    if manager.hardware['cuda_candidate']:
        mode = input('paddle altyapısı: 1 nvidia gpu / 2 cpu [varsayılan 1]: ').strip() or '1'
        if mode not in ('1', '2'):
            raise ValueError('1 veya 2 seçin')
        selected.append('paddle-gpu' if mode == '1' else 'paddle-cpu')
    else:
        selected.append('paddle-cpu')
    if confirm('korece ocr modeli de indirilsin mi?'):
        selected.append('korean')
    manga = input('japonca manga-ocr: 0 atla / 1 cpu' + (' / 2 izole gpu' if manager.hardware['cuda_candidate'] else '') + ' [varsayılan 0]: ').strip() or '0'
    if manga not in ('0', '1', '2') or (manga == '2' and not manager.hardware['cuda_candidate']):
        raise ValueError('geçersiz manga-ocr seçimi')
    if manga != '0':
        selected.append('manga-cpu' if manga == '1' else 'manga-gpu')
    model = input('çeviri: 1 standart 600m / 2 kaliteli 1.3b / 3 ikisi / 0 sonra [varsayılan 1]: ').strip() or '1'
    if model not in ('0', '1', '2', '3'):
        raise ValueError('geçersiz çeviri modeli seçimi')
    if model in ('1', '3'):
        selected.append('600m')
    if model in ('2', '3'):
        selected.append('1300m')
    manager.install(selected)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['install', 'menu', 'scan'], default='menu')
    parser.add_argument('--plan', nargs='+', choices=list(COMPONENTS), help='yalnız planı yazdır; kurulum yapma')
    parser.add_argument('--install', nargs='+', choices=list(COMPONENTS), help='açık bileşen listesiyle kurulum')
    parser.add_argument('--yes', action='store_true', help='yalnız --install ile: listelenen plan ve sistem önkoşullarını açıkça onayla')
    args = parser.parse_args()
    if args.yes and not args.install:
        parser.error('--yes yalnız --install ile kullanılabilir')
    manager = Manager()
    if args.plan:
        print(json.dumps(manager.plan(args.plan), ensure_ascii=False))
        return
    manager.show()
    if args.install:
        if args.yes:
            global confirm
            def confirm(message):
                print(message + ' [komut satırında açık onay verildi]')
                return True
        manager.install(args.install)
        return
    if args.mode == 'scan':
        return
    if args.mode == 'install':
        wizard(manager)
        return
    while True:
        choice = input('\n1 tara / 2 kur veya onar / 3 kaldır / 4 sağlık kontrolü / 0 çıkış: ').strip()
        if choice == '0':
            return
        try:
            if choice == '1':
                manager.hardware = detect()
                manager.show()
            elif choice in ('2', '3'):
                manager.show()
                selected = choose_numbers()
                if selected:
                    manager.install(selected) if choice == '2' else manager.remove(selected)
            elif choice == '4':
                manager.health()
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            print('işlem tamamlanamadı:', error)


if __name__ == '__main__':
    try:
        main()
    except (EOFError, KeyboardInterrupt):
        print('\nişlem iptal edildi.')
        sys.exit(1)
    except Exception as error:
        print('kurulum tamamlanamadı:', error)
        sys.exit(1)

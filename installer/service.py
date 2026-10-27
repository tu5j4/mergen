"""GUI component operations run in a background thread and only touch DATA_ROOT."""
import json
import os
import shutil
import subprocess
import sys
import uuid
import queue
import threading
from pathlib import Path
from .catalog import COMPONENTS, COMMON, TORCH, AMD_PACKAGES
from .manager import owned_path
from app.child_process import popen_external
from app.operations import check_cancelled, Cancelled, kill_tree
from app.storage import DATA_ROOT, APP_ROOT, WORKER_ROOT, cache_environment


def python312():
    candidates=[DATA_ROOT/'python/python.exe']
    if sys.version_info[:2]==(3,12) and not getattr(sys,'frozen',False): candidates.append(Path(sys.executable))
    if os.name=='nt':
        launcher=shutil.which('py')
        if launcher:
            try:
                candidates.append(Path(subprocess.check_output([launcher,'-3.12','-c','import sys;print(sys.executable)'],
                    text=True,timeout=10,creationflags=0x08000000).strip()))
            except (OSError,subprocess.SubprocessError): pass
    for path in candidates:
        if path.is_file(): return path
    raise RuntimeError('python 3.12 bulunamadı. kaynak sürümde kurulum.bat dosyasını çalıştırın; kurulu uygulamada python çalışma zamanını kurulum programıyla ekleyin.')


def model_paths(key):
    item=COMPONENTS[key]
    if item['kind']=='environment': return [DATA_ROOT/'envs'/key]
    if item.get('context'): return [DATA_ROOT/'models'/item['folder']]
    if item['kind']=='translation': return [DATA_ROOT/'models'/(item['folder']+suffix) for suffix in ('-hf','-ct2')]
    if item['kind']=='manga': return [DATA_ROOT/'models/manga']
    return [DATA_ROOT/'models/ocr'/item['family']/name for name in item['names']]


def inventory():
    state={}
    for key,item in COMPONENTS.items():
        paths=model_paths(key)
        ready=all((p/'mergen-ready.json').is_file() for p in paths)
        if ready and item['kind']=='environment':
            try:ready=all(json.loads((p/'mergen-ready.json').read_text(encoding='utf-8')).get('runtime_schema')==2 for p in paths)
            except (OSError,ValueError):ready=False
        if item.get('bundled'):
            from .bundled import check_component
            ready=check_component(key, DATA_ROOT)
        partial=item['kind']!='environment' and (DATA_ROOT/'cache/model-downloads'/key).is_dir()
        state[key]={'ready':ready,'present':any(p.exists() for p in paths) or partial,'title':item['title'],'detail':item['detail'],'kind':item['kind'],'bundled':item.get('bundled',False)}
    return state


def run(args, emit):
    env=cache_environment();env['MERGEN_DATA_DIR']=str(DATA_ROOT)
    env.pop('PYTHONHOME',None);env.pop('PYTHONPATH',None)
    emit(' '.join(str(a) for a in args[:4]))
    process=popen_external([str(a) for a in args],cwd=WORKER_ROOT,env=env,stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    log=DATA_ROOT/'logs/components.log';log.parent.mkdir(parents=True,exist_ok=True)
    tail=[]
    lines=queue.Queue()
    def read_output():
        try:
            for line in process.stdout: lines.put(line)
        finally: lines.put(None)
    reader=threading.Thread(target=read_output,daemon=True);reader.start()
    try:
      with log.open('a',encoding='utf-8') as stream:
        while True:
            check_cancelled()
            try:line=lines.get(timeout=.1)
            except queue.Empty:continue
            if line is None:break
            if 'Installing collected packages:' in line:
                event(emit,phase='kütüphaneler diske kuruluyor · indirme tamamlandı',progress=-1)
            elif line.startswith(('Downloading ','Collecting ')):
                event(emit,phase='kütüphaneler indiriliyor ve bağımlılıklar hazırlanıyor',progress=-1)
            stream.write(line);stream.flush();tail=(tail+[line.rstrip()])[-8:];emit(line.rstrip())
      while process.poll() is None:
        check_cancelled()
        threading.Event().wait(.1)
      check_cancelled()
      if process.returncode!=0: raise RuntimeError('işlem tamamlanamadı. '+(' · '.join(tail[-3:]) or 'ayrıntılar işlem günlüğünde.'))
    finally:
      kill_tree(process)
      reader.join(timeout=5)
      process.stdout.close()


def install(key, emit=print):
    check_cancelled()
    if key not in COMPONENTS: raise ValueError('Bilinmeyen bileşen')
    item=COMPONENTS[key]
    if item.get('bundled'):
        from .bundled import verify_component
        verify_component(key, DATA_ROOT, lambda text:event(emit,phase=text,progress=-1))
        return
    if shutil.disk_usage(DATA_ROOT).free < (12 if key=='amd' else 7)*1024**3:
        raise RuntimeError('Kurulum için en az 7 GB; AMD ortamı için 12 GB boş alan gerekiyor.')
    if item['kind']=='environment':
        from .hardware import detect
        from .profiles import eligible
        if not eligible(key,detect()):
            raise RuntimeError('Bu donanım/Windows sürümü seçili çalışma ortamının destek listesinde değil. CPU ortamını kullanın; NVIDIA için sürücüyü kontrol edin.')
        path=owned_path(DATA_ROOT,'envs/'+key)
        (path/'mergen-ready.json').unlink(missing_ok=True)
        base=python312()
        run([base,'-m','venv',path],emit)
        python=path/'Scripts/python.exe'
        if getattr(sys,'frozen',False):
            for pattern in ('MSVCP140*.dll','VCRUNTIME140*.dll','vcomp140.dll'):
                for dll in APP_ROOT.glob(pattern):shutil.copy2(dll,path/'Scripts'/dll.name)
        pip=[python,'-m','pip','install']
        run(pip+['--upgrade','pip','setuptools','wheel'],emit)
        if key=='amd': run(pip+AMD_PACKAGES,emit)
        elif key=='nvidia-paddle': run(pip+TORCH['cpu'],emit)
        else: run(pip+TORCH[key],emit)
        run(pip+COMMON+['ctranslate2==4.8.2'],emit)
        if key in ('cpu','nvidia-paddle'):
            if key=='cpu': run(pip+['paddlepaddle==3.3.1'],emit)
            else:
                run(pip+['paddlepaddle-gpu==3.2.2','--index-url','https://www.paddlepaddle.org.cn/packages/stable/cu129/'],emit)
                run(pip+['nvidia-nvjitlink-cu12==12.9.86'],emit)
        run([python,'-m','pip','check'],emit)
        if key=='nvidia-paddle':
            check="from app.gpu_env import setup_cuda_dll_paths;setup_cuda_dll_paths();import paddle;paddle.set_device('gpu:0');assert paddle.is_compiled_with_cuda();print(paddle.matmul(paddle.ones([4,4]),paddle.ones([4,4])).numpy())"
        else:
            dev='xpu:0' if key=='intel' else 'cuda:0' if key in ('amd','nvidia') else 'cpu'
            vendor_check="assert torch.version.hip, 'ROCm PyTorch gerekli';" if key=='amd' else "assert torch.version.cuda, 'CUDA PyTorch gerekli';" if key=='nvidia' else ''
            check=f"import torch;{vendor_check}x=torch.ones((4,4),device='{dev}');assert float((x@x).sum().cpu())==64;print('GPU/CPU işlem testi geçti')"
            if key=='cpu':
                check+=";import paddle;paddle.set_device('cpu');assert float(paddle.matmul(paddle.ones([4,4]),paddle.ones([4,4])).sum().numpy())==64;print('Paddle CPU işlem testi geçti')"
        run([python,'-c',check],emit)
        check_cancelled()
        (path/'mergen-ready.json').write_text(json.dumps({'runtime':key,'tensor_test':True,'runtime_schema':2}),encoding='utf-8')
        return
    state=inventory()
    runtime='cpu'
    if not state[runtime]['ready']:
        runtime=next((k for k in ('nvidia','amd','intel') if state[k]['ready']),None)
    if runtime is None: raise RuntimeError('Önce bir çalışma ortamı kurun.')
    run([DATA_ROOT/'envs'/runtime/'Scripts/python.exe', WORKER_ROOT/'scripts/component_models.py',key],emit)


def remove(key, emit=print):
    if key not in COMPONENTS: raise ValueError('Bilinmeyen bileşen')
    # Validate all paths and reparse points before removing any directory.
    targets=[owned_path(DATA_ROOT,p.relative_to(DATA_ROOT)) for p in model_paths(key)]
    if COMPONENTS[key]['kind']!='environment':
        targets.append(owned_path(DATA_ROOT,Path('cache/model-downloads')/key))
    for path in targets:
        check_cancelled()
        if path.is_dir(): shutil.rmtree(path)
        emit('Kaldırıldı: '+path.name)
    # Shared download cache remains reusable; removal never touches global caches.


def event(emit, **data):
    check_cancelled()
    emit('@mergen:'+json.dumps(data,ensure_ascii=True))

def task_components(settings,task):
    from app.core.runtime_client import environment_key
    if task=='translate':
        return [settings.translation_backend,'1300m' if settings.translation_model=='nllb-1.3b-baglam-v3' or '1.3B' in settings.translation_model else '600m']
    if task=='manga':return [settings.manga_backend,'manga']
    family='torch' if settings.ocr_backend in ('amd','intel') else 'paddle'
    keys=[environment_key(settings.ocr_backend,'ocr'),'ocr-'+family]
    if settings.source_lang=='ko':keys.append('korean-'+family)
    return keys

def component_ready(settings,task,key,state):
    if task=='translate' and key in ('600m','1300m'):
        if key=='1300m':return state[key]['ready'] and settings.translation_model==COMPONENTS[key]['folder']
        folder=DATA_ROOT/'models'/settings.translation_model
        if settings.translation_backend in ('cpu','nvidia'):
            return (folder/'model.bin').is_file() and (folder/'tokenizer').is_dir()
        folder=folder.with_name(folder.name.replace('-ct2','-hf'))
        return (folder/'config.json').is_file() and bool(list(folder.glob('*.safetensors')) or list(folder.glob('pytorch_model*.bin')))
    return state[key]['ready']

def validate(settings, emit=print):
    from app.core.runtime_client import RuntimeClient
    from app.config import LANGS
    from PIL import Image,ImageDraw,ImageFont
    import re
    checks=[('translate',settings.translation_backend,'çeviri'),('ocr',settings.ocr_backend,'paddleocr')]
    if settings.source_lang=='ja' and settings.use_manga_ocr: checks.append(('manga',settings.manga_backend,'manga-ocr'))
    rows=[]
    for index,(task,backend,title) in enumerate(checks):
        client=None
        row={'task':task,'title':title,'status':'running','message':'kontrol ediliyor…'}
        event(emit,kind='validation',row=row,phase=title+' kontrol ediliyor…',progress=index*100//len(checks))
        try:
            state=inventory()
            missing=[COMPONENTS[k]['title'] for k in task_components(settings,task) if not component_ready(settings,task,k,state)]
            if missing:
                row.update(status='missing',message='eksik: '+', '.join(missing))
            else:
                # Japanese/Chinese share the same general recognition weights.
                # Korean must exercise its own recognizer rather than switching to English.
                language=settings.source_lang if task!='ocr' or settings.source_lang=='ko' else 'en'
                client=RuntimeClient(task,backend,language=language,model=str(settings.model_path),
                    progress=lambda phase:event(emit,phase=title+' · '+phase,progress=-1))
                if task=='translate':
                    samples={'en':'Hello, how are you?','ja':'こんにちは。元気ですか？','ko':'안녕하세요. 잘 지내세요?',
                             'zh':'你好，你好吗？','zh_tw':'您好，您好嗎？'}
                    output=client.request(op='translate',texts=[samples[settings.source_lang]],
                        source=LANGS[settings.source_lang]['nllb'],target='tur_Latn',beam=2)
                    if len(output)!=1 or not output[0].strip():raise RuntimeError('çeviri modeli boş sonuç döndürdü')
                    if output[0].strip()==samples[settings.source_lang] or not re.search('[A-Za-zÇĞİÖŞÜçğıöşü]',output[0]):raise RuntimeError('çeviri örneği türkçe bir sonuç üretmedi')
                    row['result']=output[0][:120]
                elif task=='ocr':
                    korean=settings.source_lang=='ko'
                    image=Image.new('RGB',(700,160),'white')
                    font=ImageFont.truetype('C:/Windows/Fonts/'+('malgun.ttf' if korean else 'arial.ttf'),48)
                    sample='안녕하세요' if korean else 'HELLO WORLD'
                    ImageDraw.Draw(image).text((40,40),sample,font=font,fill='black')
                    output=next(client.predict(__import__('numpy').array(image)))
                    text=''.join(output.get('rec_texts',[])).replace(' ','').upper()
                    if sample.replace(' ','') not in text:raise RuntimeError('ocr örnek metni doğru okuyamadı: '+text)
                    row['result']=' '.join(output['rec_texts'])[:120]
                else:
                    with Image.open(APP_ROOT/'assets/manga-test.png') as sample:
                        output=client.recognize([sample])
                    if not output or not re.search('[\u3040-\u30ff\u4e00-\u9fff]',output[0]):
                        raise RuntimeError('manga-ocr japonca örneği okuyamadı')
                    row['result']=output[0][:120]
                row.update(status='passed',message='model testi geçti · '+client.device,device=client.device)
        except Cancelled:
            raise
        except Exception as exc:
            row.update(status='failed',message=str(exc))
        finally:
            if client:
                try:client.close()
                except Exception as exc:row.update(status='failed',message='model kapatılamadı: '+str(exc))
        rows.append(row)
        event(emit,kind='validation',row=row,phase=title+' · '+row['message'],progress=(index+1)*100//len(checks))
    report={'ok':all(row['status']=='passed' for row in rows),'rows':rows,'language':settings.source_lang,
            'translation':settings.translation_backend,'ocr':settings.ocr_backend,'manga':settings.manga_backend}
    check_cancelled()
    (DATA_ROOT/'last-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


def install_plan(profile, emit=print):
    # Recompute eligibility immediately before any download.
    from .hardware import detect
    from .profiles import eligible
    backend=profile['translation']
    if not eligible(backend,detect()): raise RuntimeError('Donanım seçili kurulum için uygun değil.')
    allowed=['cpu']+([] if backend=='cpu' else [backend])+['600m','ocr-paddle']
    if profile['components']!=allowed: raise ValueError('Geçersiz kurulum planı')
    for index,key in enumerate(allowed):
        event(emit,kind='component',key=key,phase=f"{index+1}/{len(allowed)} · "+COMPONENTS[key]['title'],progress=-1)
        if not inventory()[key]['ready']: install(key,emit)
        event(emit,kind='component',key=key,phase=COMPONENTS[key]['title']+' hazır',progress=(index+1)*100//len(allowed))
    emit('önerilen bileşenler kuruldu; model testi başlıyor.')



def missing_components(settings):
    tasks=['translate','ocr']
    if settings.source_lang=='ja' and settings.use_manga_ocr:tasks.append('manga')
    state=inventory()
    missing=[]
    for task in tasks:
        for key in task_components(settings,task):
            if not component_ready(settings,task,key,state) and key not in missing:missing.append(key)
    return [COMPONENTS[key]['title'] for key in missing]


def automatic_setup(settings, emit=print):
    """Detect again, install only needed runtimes, and commit only tested devices."""
    from dataclasses import replace
    from .hardware import detect
    from .profiles import recommended,eligible
    report=detect()
    if not eligible('cpu',report):raise RuntimeError('bu cihaz windows x64 ve avx gereksinimlerini karşılamıyor')
    backend=recommended(report)['translation']
    requested=backend
    fallback=''
    def ensure(key):
        check_cancelled()
        event(emit,kind='component',key=key,phase=COMPONENTS[key]['title']+' kontrol ediliyor',progress=-1)
        if not inventory()[key]['ready']:install(key,emit)
    ensure('cpu')
    if backend!='cpu':
        try:ensure(backend)
        except Cancelled:raise
        except Exception as exc:
            fallback=str(exc);backend='cpu'
            event(emit,phase='ekran kartı ortamı kurulamadı · cpu ortamıyla devam ediliyor',progress=-1)
    trial=replace(settings,translation_backend=backend,ocr_backend='cpu',
        manga_backend='nvidia' if backend=='nvidia' else 'cpu')
    for key in dict.fromkeys(k for task in ('translate','ocr','manga')
            if task!='manga' or trial.source_lang=='ja' and trial.use_manga_ocr
            for k in task_components(trial,task) if COMPONENTS[k]['kind']!='environment'):
        ensure(key)
    first=validate(trial,emit)
    gpu_tasks=['translate']+(['manga'] if trial.manga_backend==backend and backend!='cpu' else [])
    gpu_failed=backend!='cpu' and any(row['task'] in gpu_tasks and row['status']!='passed' for row in first['rows'])
    result=first
    if gpu_failed:
        fallback='ekran kartında gerçek model testi geçmedi'
        event(emit,phase='ekran kartı model testi geçmedi · cpu modelleri doğrulanıyor',progress=-1)
        trial=replace(trial,translation_backend='cpu',manga_backend='cpu')
        result=validate(trial,emit)
    result=dict(result,automatic=True,requested_backend=requested,fallback_reason=fallback,
        initial_gpu_test=first if gpu_failed else None,
        selected_settings={key:getattr(trial,key) for key in ('translation_backend','ocr_backend','manga_backend')})
    check_cancelled()
    (DATA_ROOT/'automatic-setup.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

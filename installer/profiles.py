"""Conservative install recommendations for the pinned Windows runtime versions."""
import re

AMD_RADEON=('RX 9070 XT','RX 9070','AI PRO R9700','RX 9060 XT','RX 7900 XTX',
            'PRO W7900 DUAL SLOT','PRO W7900','RX 7700')

AMD_RYZEN=('MAX+ 395','MAX 390','MAX 385','9 HX 375','9 HX 370','9 365','9 HX 475','9 HX 470','9 465')

def eligible(key, report):
    if not report.get('supported_os') or report.get('avx') is False: return False
    if key=='cpu': return True
    if key in ('nvidia','nvidia-paddle'): return bool(report.get('cuda_candidate'))
    if report.get('windows_build',0)<22000: return False
    names=[a['name'].upper().replace('™','').replace('®','') for a in report.get('adapters',[])]
    if key=='intel': return any('INTEL' in n and 'ARC' in n for n in names)
    if key=='amd':
        # Exact model endings prevent e.g. RX 7700 XT being approved as RX 7700.
        ryzen=any('AMD RYZEN AI ' in cpu.upper() and any(re.search(r'RYZEN AI '+re.escape(model)+r'(?=\s|$)',cpu.upper()) for model in AMD_RYZEN) for cpu in report.get('processors',[]))
        if ryzen and any('AMD' in n and 'RADEON' in n for n in names):return True
        return any(any(re.search(r'(?<![A-Z0-9])'+re.escape(model)+r'(?: GRAPHICS)?$',n)
                       for model in AMD_RADEON) for n in names)
    return False

def recommended(report):
    backend=next((k for k in ('nvidia','amd','intel') if eligible(k,report)),'cpu')
    components=['cpu']
    if backend!='cpu': components.append(backend)
    components+=['600m','ocr-paddle']
    message={'cpu':'Başlangıç için CPU öneriliyor.',
             'nvidia':'NVIDIA CUDA çeviri öneriliyor. OCR başlangıçta CPU kullanır.',
             'amd':'AMD ROCm çeviri denenebilir. Bu uygulamadaki AMD desteği deneyseldir; OCR başlangıçta CPU kullanır.',
             'intel':'Intel XPU çeviri denenebilir. Bu uygulamadaki Intel desteği deneyseldir; OCR başlangıçta CPU kullanır.'}[backend]
    if not eligible('cpu',report): message='Windows 10/11 x64 ve AVX destekli işlemci gerekiyor.'
    return {'translation':backend,'components':components,'message':message}

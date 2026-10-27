"""Explicit installation allowlist; no arbitrary package names from the UI."""
OCR_NAMES={'detection':'PP-OCRv5_mobile_det','recognition':'PP-OCRv5_mobile_rec',
           'orientation':'PP-LCNet_x1_0_textline_ori','korean':'korean_PP-OCRv5_mobile_rec'}
COMPONENTS={
 'cpu': {'title':'CPU çalışma ortamı','kind':'environment','backend':'cpu','detail':'ekran kartından bağımsız cpu çeviri ve ocr ortamı.'},
 'nvidia': {'title':'NVIDIA çeviri ve manga-ocr','kind':'environment','backend':'nvidia','detail':'CUDA · ekran kartı ve gerçek model testi gerekir.'},
 'nvidia-paddle': {'title':'NVIDIA PaddleOCR','kind':'environment','backend':'nvidia','detail':'Paddle CUDA ayrı ortamda çalışır.'},
 'amd': {'title':'AMD ROCm çalışma ortamı','kind':'environment','backend':'amd','detail':'Deneysel · Windows 11, Python 3.12 ve desteklenen Radeon sürücüsü gerekir.'},
 'intel': {'title':'Intel XPU çalışma ortamı','kind':'environment','backend':'intel','detail':'Deneysel · Windows 11, desteklenen Arc/Core Ultra GPU ve sürücü gerekir.'},
 '600m': {'title':'nllb 600m · standart','kind':'translation','bundled':True,'folder':'nllb-200-distilled-600M','detail':'kurulum paketinde · mevcut standart model · cpu int8 ve nvidia desteği.'},
 '1300m': {'title':'nllb 1.3b · mergen bağlam v3','kind':'translation','bundled':True,'context':True,'folder':'nllb-1.3b-baglam-v3','detail':'kurulum paketinde · geliştirdiğimiz lora ve son üç replikle bağlam · uyarlama eğitimi ingilizce–türkçe için yapıldı.'},
 'ocr-paddle': {'title':'PaddleOCR mobil modelleri','kind':'ocr','family':'paddle','names':list(OCR_NAMES.values())[:3],'detail':'CPU / NVIDIA için tespit, tanıma ve yön modelleri.'},
 'ocr-torch': {'title':'PaddleOCR Transformers modelleri','kind':'ocr','family':'transformers','names':list(OCR_NAMES.values())[:3],'detail':'AMD / Intel için deneysel OCR yolu.'},
 'korean-paddle': {'title':'Korece · Paddle modeli','kind':'ocr','family':'paddle','names':[OCR_NAMES['korean']],'detail':'CPU / NVIDIA için Korece tanıma modeli.'},
 'korean-torch': {'title':'Korece · Transformers modeli','kind':'ocr','family':'transformers','names':[OCR_NAMES['korean']],'detail':'Deneysel · model paketi mevcut değilse kurulum tamamlanmaz.'},
 'manga': {'title':'Japonca manga-ocr modeli','kind':'manga','repo':'kha-white/manga-ocr-base','detail':'Japonca konuşma balonları için.'},
}
COMMON=['transformers==5.19.0','sentencepiece==0.2.2','Pillow==12.3.0','numpy==2.3.5',
        'peft==0.21.2','pandas==3.0.6','huggingface_hub','manga-ocr==0.1.16','paddleocr==3.7.0','paddlex==3.7.2']
TORCH={'cpu':['torch==2.11.0','torchvision==0.26.0','--index-url','https://download.pytorch.org/whl/cpu'],
       'nvidia':['torch==2.11.0','torchvision==0.26.0','--index-url','https://download.pytorch.org/whl/cu128'],
       'intel':['torch==2.11.0','torchvision==0.26.0','--index-url','https://download.pytorch.org/whl/xpu']}
AMD_BASE='https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/'
AMD_PACKAGES=[AMD_BASE+n for n in ('rocm_sdk_core-7.2.1-py3-none-win_amd64.whl',
 'rocm_sdk_devel-7.2.1-py3-none-win_amd64.whl','rocm_sdk_libraries_custom-7.2.1-py3-none-win_amd64.whl',
 'rocm-7.2.1.tar.gz','torch-2.9.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl',
 'torchvision-0.24.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl')]

for _key in ('ocr-paddle','korean-paddle','manga'):
    COMPONENTS[_key]['bundled']=True
    COMPONENTS[_key]['detail']='kurulum paketinde · '+COMPONENTS[_key]['detail'].lower()
for _item in COMPONENTS.values():
    _item['title']=_item['title'].lower()

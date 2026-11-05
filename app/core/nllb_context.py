"""Mergen 1.3b v3 serving, preserving the trained cross-attention boundary."""
from contextlib import nullcontext
from pathlib import Path
import os
from .nllb_current_mask import generate, generate_batch


def cpu_inference_config(logical_cores=None, available_bytes=None):
    """Leave half the logical CPUs free and bound short-passage batch memory."""
    if logical_cores is None:
        logical_cores=os.cpu_count() or 2
        try:
            import psutil
            logical_cores=min(logical_cores,len(psutil.Process().cpu_affinity()))
        except Exception:  # Optional telemetry must not prevent model startup.
            pass
    logical_cores=max(1,int(logical_cores))
    if available_bytes is None:
        try:
            import psutil
            available_bytes=psutil.virtual_memory().available
        except Exception:  # Optional telemetry must not prevent model startup.
            available_bytes=0
    threads=max(1,min(8,logical_cores//2))
    batch=2 if logical_cores>=12 and available_bytes>=8*1024**3 else 1
    return threads,batch


class ContextModel:
    def __init__(self, directory, device):
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        from peft import PeftModel
        self.device=device
        self.autocast=device.startswith('cuda') and torch.cuda.is_bf16_supported()
        threads,cpu_batch=cpu_inference_config()
        torch.set_num_threads(threads)
        directory=Path(directory)
        base=AutoModelForSeq2SeqLM.from_pretrained(directory/'base-bf16',local_files_only=True,
            dtype=torch.bfloat16 if self.autocast else torch.float32,attn_implementation='sdpa')
        self.model=PeftModel.from_pretrained(base,directory/'adapter-masked',local_files_only=True).to(device).eval()
        self.batch_size=3 if device.startswith('cuda') else cpu_batch if device=='cpu' else 1
        if device.startswith('cuda'):
            # Serving-only merge: no save_pretrained and no model-file writes.
            self.model=self.model.merge_and_unload(safe_merge=True).eval()
        self.model.config.use_cache=True
        self.tokenizer=AutoTokenizer.from_pretrained(directory/'base-bf16',local_files_only=True,
            src_lang='eng_Latn',tgt_lang='tur_Latn')

    def infer(self,payload):
        import torch
        texts=payload['texts']
        histories=payload.get('histories',[[] for _ in texts])
        if not isinstance(texts,list) or len(texts)>16 or len(histories)!=len(texts):
            raise ValueError('geçersiz çeviri listesi')
        if payload['target']!='tur_Latn':raise ValueError('bu model türkçe çeviri içindir')
        self.tokenizer.src_lang=payload['source']
        rows=[]
        for text,history in zip(texts,histories):
            if not isinstance(text,str) or not text.strip() or len(text)>8000:
                raise ValueError('geçersiz replik')
            if not isinstance(history,list) or len(history)>3 or any(not isinstance(s,str) or len(s)>8000 for s in history):
                raise ValueError('geçersiz replik geçmişi')
            rows.append(dict(source=text,previous_sources=history))
        results=[]
        precision=torch.autocast('cuda',dtype=torch.bfloat16) if self.autocast else nullcontext()
        with torch.inference_mode(),precision:
            for start in range(0,len(rows),self.batch_size):
                group=rows[start:start+self.batch_size]
                generated=(generate_batch(self.model,self.tokenizer,group,self.device) if self.batch_size>1 else
                           [generate(self.model,self.tokenizer,group[0],self.device,True)])
                if len(generated)!=len(group):raise RuntimeError('bağlamlı model tüm replikleri döndürmedi')
                for result in generated:
                    if result['limit_reached'] or not result['translation']:
                        raise RuntimeError('bağlamlı model repliği tamamlayamadı; metni daha küçük bir alanda tekrar deneyin')
                    results.append(result['translation'])
        return results

"""
Yerel çeviri motoru: Meta NLLB-200 (CTranslate2 ile int8 nicemlenmiş).
İnternet gerektirmez (model bir kez indirildikten sonra).
"""
from __future__ import annotations

import os
import re
import time
from collections import OrderedDict
from pathlib import Path

from ..config import TARGET_NLLB
from .glossary import missing_terms
from .session_context import SessionContext, TranslationPlan


class Translator:
    def __init__(self, model_dir: Path, beam_size: int = 4, cache_size: int = 2000,
                 device: str = 'auto', backend: str = 'local') -> None:
        if backend != 'local':
            from .runtime_client import RuntimeClient
            self._runtime = RuntimeClient('translate', backend, model=str(model_dir))
            self.device = self._runtime.device
            self.compute_type = 'float32' if backend in ('amd','intel') else 'auto'
            self.beam_size, self.cache_size = beam_size, cache_size
            self._cache = OrderedDict()
            self.last_glossary_ms = self.last_retry_count = self.last_context_ms = 0
            return
        import ctranslate2
        from transformers import AutoTokenizer

        model_dir = Path(model_dir)
        tok_dir = model_dir / "tokenizer"
        if not (model_dir / "model.bin").exists() or not tok_dir.exists():
            raise FileNotFoundError(
                f"Çeviri modeli bulunamadı: {model_dir}\n"
                f"Önce şu komutu çalıştırın:  python scripts/download_models.py"
            )

        threads = max(1, (os.cpu_count() or 4) // 2)
        self.tok = AutoTokenizer.from_pretrained(str(tok_dir))

        if device not in ('auto', 'cuda', 'cpu'):
            raise ValueError('Çeviri cihazı auto, cuda veya cpu olmalı.')
        cuda = device != 'cpu' and ctranslate2.get_cuda_device_count() > 0
        self.model = None
        if cuda:
            # RTX 50 (Blackwell, sm_120): int8 GEMM bazı CTranslate2 sürümlerinde
            # CUBLAS_STATUS_NOT_SUPPORTED verir -> önce float16 dene.
            # Paddle GPU ile uyumluluk için PyTorch CPU kurulmuş olabilir.
            # GPU hassasiyetini PyTorch'a bağlamak FP16 tercihinin kaybolmasına
            # ve kısa diyaloglarda belirgin anlam hatalarına yol açıyordu.
            types = ["float16", "int8_float16"]
            for ct in types:
                try:
                    m = ctranslate2.Translator(str(model_dir), device="cuda",
                                               compute_type=ct, inter_threads=1)
                    self.tok.src_lang = "eng_Latn"
                    warm = self.tok.convert_ids_to_tokens(
                        self.tok.encode("Hello, how are you doing today? This is a test."))
                    m.translate_batch([warm, warm], target_prefix=[[TARGET_NLLB]] * 2,
                                      beam_size=2, max_decoding_length=32)
                    self.model = m
                    self.device = "cuda"
                    self.compute_type = ct
                    print(f"[çeviri] GPU hazır ({ct})")
                    break
                except Exception as e:
                    print(f"[çeviri] GPU {ct} çalışmadı: {e}")
        if self.model is None:
            self.device = "cpu"
            self.compute_type = "int8"
            self.model = ctranslate2.Translator(
                str(model_dir), device="cpu", compute_type="int8",
                inter_threads=1, intra_threads=threads,
            )
        self.beam_size = beam_size
        self.cache_size = cache_size
        self._cache: OrderedDict[tuple, str] = OrderedDict()
        self.last_glossary_ms = 0.0
        self.last_retry_count = 0
        self.last_context_ms = 0.0

    # ------------------------------------------------------------------
    def close(self) -> None:
        if getattr(self, "_runtime", None) is not None:
            self._runtime.close()

    def clear_cache(self) -> None:
        self._cache.clear()

    def _cache_get(self, key):
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def _cache_put(self, key, value):
        self._cache[key] = value
        self._cache.move_to_end(key)
        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)

    @staticmethod
    def _natural_turkish(text: str) -> str:
        """NLLB çıktısındaki tipografik pürüzleri, anlamı değiştirmeden düzeltir."""
        text = re.sub(r"\s+([,.!?;:…])", r"\1", text.strip())
        text = re.sub(r"([?!]){2,}", r"\1", text)
        text = re.sub(r"\.{3,}", "…", text)
        text = re.sub(r"\b(ben|sen|o|biz|siz) de\b", r"\1 de", text, flags=re.I)
        # Türkçede soru eki ayrı yazılır; modelin sık yaptığı bitişik yazımı toparla.
        text = re.sub(r"\b([\wçğıöşü]+)(mı|mi|mu|mü)([?!])", r"\1 \2\3", text, flags=re.I)
        text = re.sub(r"\s{2,}", " ", text)
        if text and text[0].isalpha():
            text = text[0].upper() + text[1:]
        return text

    # ------------------------------------------------------------------
    def _translate_texts(self, texts: list[str], src_code: str,
                         target_code: str, beam: int) -> list[str]:
        if getattr(self, "_runtime", None) is not None:
            return self._runtime.request(op="translate", texts=texts, source=src_code, target=target_code, beam=beam)
        self.tok.src_lang = src_code
        batch = [self.tok.convert_ids_to_tokens(
            self.tok.encode(t, truncation=True, max_length=400)) for t in texts]
        results = self.model.translate_batch(
            batch, target_prefix=[[target_code]] * len(batch), beam_size=beam,
            max_batch_size=16, max_decoding_length=256,
            repetition_penalty=1.15, no_repeat_ngram_size=4,
        )
        out = []
        for result in results:
            tokens = result.hypotheses[0]
            if tokens and tokens[0] == target_code:
                tokens = tokens[1:]
            out.append(self.tok.decode(self.tok.convert_tokens_to_ids(tokens),
                                       skip_special_tokens=True).strip())
        return out

    def translate(self, texts: list[str], src_code: str, beam_size: int | None = None,
                  via_english: bool = False, context: SessionContext | None = None) -> list[str]:
        self.last_glossary_ms = 0.0
        self.last_retry_count = 0
        self.last_context_ms = 0.0
        if not texts:
            return []
        beam = max(1, int(beam_size or self.beam_size))
        pivot = via_english and src_code in ("zho_Hans", "zho_Hant")
        context_start = time.perf_counter()
        plans = context.prepare(texts, src_code) if context is not None else [TranslationPlan(t, t) for t in texts]
        keys = [(src_code, t, beam, pivot, plan.signature) if plan.terms else (src_code, t, beam, pivot)
                for t, plan in zip(texts, plans)]
        self.last_context_ms += (time.perf_counter() - context_start) * 1000

        def checked(result, index, target="tur_Latn"):
            return missing_terms(texts[index], result, src_code, target) | plans[index].missing(result)

        def canonical(result, index):
            return plans[index].canonicalize(result)
        out: list[str | None] = [self._cache_get(key) for key in keys]
        todo_idx = [i for i, v in enumerate(out) if v is None]
        if todo_idx:
            pending = [plans[i].prepared for i in todo_idx]
            if pivot:
                pending = self._translate_texts(pending, src_code, "eng_Latn", beam)
                results = self._translate_texts(pending, "eng_Latn", TARGET_NLLB, beam)
            else:
                results = self._translate_texts(pending, src_code, TARGET_NLLB, beam)
            results = [canonical(result, index) for index, result in zip(todo_idx, results)]
            check_start = time.perf_counter()
            suspicious = [i for i, (index, result) in enumerate(zip(todo_idx, results))
                          if checked(result, index)]
            self.last_glossary_ms += (time.perf_counter() - check_start) * 1000
            # Sadece şüpheli balonlar yeniden çevrilir; diğer sonuçlar korunur.
            # Ek işi sınırlamak için bir parçada en fazla iki balon denenir.
            retry_indices = suspicious[:2]
            if retry_indices:
                self.last_retry_count = len(retry_indices)
                originals = [plans[todo_idx[i]].prepared for i in retry_indices]
                retry_beam = max(1, beam - 1) if src_code == "eng_Latn" else max(2, min(4, beam + 1))
                if src_code != "eng_Latn":
                    english = self._translate_texts(originals, src_code, "eng_Latn", retry_beam)
                    check_start = time.perf_counter()
                    english = [canonical(result, todo_idx[retry_indices[i]]) for i, result in enumerate(english)]
                    valid = [i for i, result in enumerate(english)
                             if not checked(result, todo_idx[retry_indices[i]], "eng_Latn")]
                    self.last_glossary_ms += (time.perf_counter() - check_start) * 1000
                    candidates = self._translate_texts([english[i] for i in valid], "eng_Latn", TARGET_NLLB, retry_beam) if valid else []
                else:
                    valid = list(range(len(originals)))
                    candidates = self._translate_texts(originals, src_code, TARGET_NLLB, retry_beam)
                for local_index, candidate in zip(valid, candidates):
                    result_index = retry_indices[local_index]
                    check_start = time.perf_counter()
                    index = todo_idx[result_index]
                    candidate = canonical(candidate, index)
                    accepted = not checked(candidate, index)
                    self.last_glossary_ms += (time.perf_counter() - check_start) * 1000
                    if accepted:
                        results[result_index] = candidate
                for result_index in suspicious:
                    check_start = time.perf_counter()
                    unresolved = checked(results[result_index], todo_idx[result_index])
                    self.last_glossary_ms += (time.perf_counter() - check_start) * 1000
                    if unresolved:
                        # Körlemesine kelime değiştirmek yerine belirsizliği göster.
                        results[result_index] = "[?] " + results[result_index]
            for i, text in zip(todo_idx, results):
                text = self._natural_turkish(text)
                out[i] = text
                self._cache_put(keys[i], text)
        return [t or "" for t in out]

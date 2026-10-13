"""Küçük yerel anlam kontrolü; GPU/model ve kelime değiştirme kullanmaz."""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _rules():
    path = Path(__file__).resolve().parent.parent / "data" / "translation_glossary.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {key: ({lang: re.compile(pattern, re.I) for lang, pattern in rule["sources"].items()},
                  re.compile(rule["turkish"], re.I)) for key, rule in raw.items()}


def missing_terms(source: str, translation: str, source_lang: str,
                  target_lang: str = "tur_Latn") -> set[str]:
    """Sadece açıkça belirtilen anlam öğelerinin kaybolduğunu saptar.

    Eşanlamlılar/çekimler kapsanmamışsa yanlış alarm olabilir. Bu nedenle
    sonuç otomatik bul-değiştir için kullanılmaz.
    """
    source = unicodedata.normalize("NFKC", source)
    translation = unicodedata.normalize("NFKC", translation)
    missing = set()
    rules = _rules()
    matches = [(key, match.start(), match.end())
               for key, (sources, _) in rules.items() if source_lang in sources
               for match in sources[source_lang].finditer(source)]
    # Örn. Korece 할아버지 (dede), 아버지 (baba) sözcüğünü içerir.
    # Daha uzun eşleşmenin içindeki kısa terimi ayrı bir anlam sayma.
    active = {key for key, start, end in matches
              if not any(other_start <= start and end <= other_end and other_end - other_start > end - start
                         for _, other_start, other_end in matches)}
    for key in active:
        sources, turkish = rules[key]
        pattern = sources.get(source_lang)
        target = turkish if target_lang == "tur_Latn" else sources.get(target_lang)
        if pattern and pattern.search(source) and target and not target.search(translation):
            missing.add(key)
    # Sadece yazıyla değil, rakamla verilen sayıları denetler.
    source_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", source))
    target_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", translation))
    missing.update("number:" + n for n in source_numbers - target_numbers)
    return missing

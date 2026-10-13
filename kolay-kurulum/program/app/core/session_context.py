"""Bounded, RAM-only dialogue/term memory; no model and no guessed CJK names."""
from __future__ import annotations

import json
import hashlib
import re
import unicodedata
from collections import OrderedDict, deque
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .glossary import missing_terms


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


def _pattern(alias: str):
    escaped = re.escape(alias).replace(r"\ ", r"\s+")
    # Latin names need word boundaries; Japanese/Chinese/Korean particles do not.
    if re.fullmatch(r"[A-Za-zÀ-ž0-9 .'-]+", alias):
        escaped = r"(?<![A-Za-zÀ-ž0-9])" + escaped + r"(?![A-Za-zÀ-ž0-9])"
    return re.compile(escaped, re.I)


@lru_cache(maxsize=1)
def term_rules():
    path = Path(__file__).resolve().parent.parent / 'data' / 'session_terms.json'
    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
        rules = []
        for key, rule in raw.items():
            target = normalized(rule['target'])
            if not target or len(target) > 80:
                continue
            aliases = {lang: tuple(normalized(a) for a in values if a and len(a) <= 80)
                       for lang, values in rule['sources'].items()}
            short = {lang: tuple(normalized(a) for a in values if a and len(a) <= 80)
                     for lang, values in rule.get('contextual_sources', {}).items()}
            rules.append((key, target, aliases, short))
        return tuple(rules)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        # A missing/invalid optional term file must not prevent translation.
        return ()


@dataclass(frozen=True)
class Term:
    key: str
    source: str
    target: str


@dataclass(frozen=True)
class TranslationPlan:
    original: str
    prepared: str
    terms: tuple[Term, ...] = ()

    @property
    def signature(self):
        return tuple((t.source, t.target) for t in self.terms)

    def canonicalize(self, text: str) -> str:
        for term in sorted(self.terms, key=lambda t: -len(t.source)):
            # Only explicit spellings are changed, never guessed Turkish words.
            text = _pattern(term.source).sub(lambda _: term.target, text)
            text = _pattern(term.target).sub(lambda _: term.target, text)
        return text

    def missing(self, text: str) -> set[str]:
        return {'name:' + t.key for t in self.terms if not _pattern(t.target).search(text)}


@dataclass(frozen=True)
class Dialogue:
    language: str
    source: str
    translation: str
    panel: int | None
    event_id: tuple | None


class SessionContext:
    def __init__(self, history_limit=24, term_limit=128):
        self.history_limit = max(1, history_limit)
        self.term_limit = max(1, term_limit)
        self.history: deque[Dialogue] = deque(maxlen=self.history_limit)
        self.terms: OrderedDict[tuple[str, str], Term] = OrderedDict()
        self._seen: OrderedDict[tuple, None] = OrderedDict()

    def clear(self):
        self.history.clear()
        self.terms.clear()
        self._seen.clear()

    def fork(self):
        clone = SessionContext(self.history_limit, self.term_limit)
        clone.history.extend(self.history)
        clone.terms.update(self.terms)
        clone._seen.update(self._seen)
        return clone

    @staticmethod
    def _explicit_latin_names(source: str, language: str):
        # Mixed-script acronyms (TBS, SASUKE) are explicit spellings, not NER.
        mixed = bool(re.search(r'[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]', source))
        if mixed:
            for match in re.finditer(r'(?<![A-Za-z0-9])[A-Z][A-Z0-9]{1,19}(?![A-Za-z0-9])', source):
                yield match.group()
        if language == 'eng_Latn':
            # Do not interpret arbitrary Title Case / ALL CAPS dialogue as names.
            for match in re.finditer(r"\b(?i:my name is|mr\.|mrs\.|ms\.|dr\.)\s+([A-Za-z][A-Za-z]{1,24}(?:[ -][A-Z][A-Za-z]{1,24})?)", source):
                name = match.group(1)
                if name.split()[0].lower() not in {'fine','sorry','happy','ready','here','back','sure','okay','ok','not','a','the'}:
                    yield name.title() if name.islower() or name.isupper() else name

    def prepare(self, texts: list[str], language: str) -> list[TranslationPlan]:
        sources = [normalized(text) for text in texts]
        rules = term_rules()
        active = {term.key for (lang, _), term in self.terms.items() if lang == language}
        # A full verified name in the same batch can identify its short spelling.
        for key, _, aliases, _ in rules:
            if any(_pattern(alias).search(source) for alias in aliases.get(language, ()) for source in sources):
                active.add(key)
        plans = []
        for original, source in zip(texts, sources):
            candidates = []
            for key, target, aliases, short in rules:
                for alias in aliases.get(language, ()) + (short.get(language, ()) if key in active else ()):
                    candidates.append(Term(key, alias, target))
            candidates.extend(term for (lang, _), term in self.terms.items() if lang == language)
            for name in self._explicit_latin_names(source, language):
                previous = self.terms.get((language, name.casefold()))
                candidates.append(previous or Term('latin:' + name.casefold(), name, name))
            spans = []
            for term in sorted(candidates, key=lambda t: -len(t.source)):
                for match in _pattern(term.source).finditer(source):
                    if not any(match.start() < end and match.end() > start for start, end, _ in spans):
                        spans.append((match.start(), match.end(), term))
            spans.sort(key=lambda span: span[0])
            prepared, cursor = [], 0
            for start, end, term in spans:
                prepared.extend((source[cursor:start], term.target))
                cursor = end
            prepared.append(source[cursor:])
            # Preserve the original input byte-for-byte when there are no terms.
            plans.append(TranslationPlan(original, ''.join(prepared) if spans else original,
                                         tuple(term for _, _, term in spans)))
        return plans

    def remember(self, source: str, translation: str, language: str,
                 panel: int | None = None, event_id: tuple | None = None):
        if not source.strip() or not translation.strip() or translation.startswith('[?]'):
            return False
        if missing_terms(source, translation, language):
            return False
        plan = self.prepare([source], language)[0]
        if plan.missing(translation):
            return False
        # Rescans/cache hits must not fill the history with the same dialogue.
        text_key = (language, normalized(source), normalized(translation))
        digest = hashlib.blake2b(repr(text_key).encode('utf-8'), digest_size=16).digest()
        key = ('event', hashlib.blake2b(repr(event_id).encode('utf-8'), digest_size=16).digest()) if event_id is not None else ('text', digest)
        if key in self._seen or any((d.language, normalized(d.source), normalized(d.translation)) == text_key for d in self.history):
            return False
        self._seen[key] = None
        while len(self._seen) > self.history_limit * 8:
            self._seen.popitem(last=False)
        self.history.append(Dialogue(language, source[:600], translation[:600], panel, event_id))
        for term in plan.terms:
            term_key = (language, term.source.casefold())
            self.terms[term_key] = term
            self.terms.move_to_end(term_key)
        while len(self.terms) > self.term_limit:
            self.terms.popitem(last=False)
        return True

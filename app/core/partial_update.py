"""Conservative source-preserving replacement decisions for OCR rereads."""
import re
import unicodedata
from difflib import SequenceMatcher


def _tokens(text, language):
    text = unicodedata.normalize('NFKC', text).casefold()
    if language in ('ja', 'zh', 'zh_tw'):
        return [c for c in text if c.isalnum()]
    return re.findall(r"[^\W_]+", text, flags=re.UNICODE)


def more_complete(new, old):
    language = new.get('source_lang')
    if not language or language != old.get('source_lang') or new.get('panel') != old.get('panel'):
        return False
    old_area, new_area = old['w'] * old['h'], new['w'] * new['h']
    edge_recovery = bool(old.get('edge_partial')) and new.get('edge_partial') is False
    strong_expansion = edge_recovery and (new.get('confidence') or 0) >= .85
    area_limit = 16 if strong_expansion else 3
    intersection = max(0,min(new['x']+new['w'],old['x']+old['w'])-max(new['x'],old['x'])) * max(0,min(new['y']+new['h'],old['y']+old['h'])-max(new['y'],old['y']))
    if old_area <= 0 or intersection < old_area * .85 or not old_area * .9 <= new_area <= old_area * area_limit:
        return False
    # A newly revealed passage is measured over a different crop. Small score
    # variation must not freeze a known edge fragment, but weak replacements
    # and ordinary non-edge rereads retain the strict confidence rule.
    before_conf, after_conf = old.get('confidence'), new.get('confidence')
    if before_conf is not None:
        if after_conf is None:
            return False
        if after_conf < before_conf and not (edge_recovery and after_conf >= .85 and before_conf-after_conf <= .0300001):
            return False
    before, after = _tokens(old.get('src',''),language), _tokens(new.get('src',''),language)
    minimum = 1 if edge_recovery and len(''.join(before)) >= 3 else 2
    gain = 1 if edge_recovery else 2
    if len(before) < minimum or len(after) < len(before)+gain:
        return False
    matches = sum(b.size for b in SequenceMatcher(None,before,after,autojunk=False).get_matching_blocks())
    return matches == len(before)


def balloon_replaces_fragments(new, overlaps):
    """Allow a verified complete balloon to replace cached line fragments inside it.

    Unverified broad OCR boxes remain strictly blocked from collapsing multiple
    existing entries.
    """
    if not new.get('balloon') or new.get('edge_partial') or len(overlaps) < 2:
        return False
    language = new.get('source_lang')
    if not language:
        return False
    new_area = new['w'] * new['h']
    after_conf = new.get('confidence')
    if new_area <= 0 or (after_conf is not None and after_conf < 0.85):
        return False
    combined_before = []
    ordered = sorted(overlaps, key=lambda b: (b['y'], b['x']))
    for old in ordered:
        if old.get('source_lang') != language:
            return False
        if (old.get('panel') is not None and new.get('panel') is not None
                and old.get('panel') != new.get('panel')):
            return False
        old_area = old['w'] * old['h']
        intersection = (max(0, min(new['x'] + new['w'], old['x'] + old['w']) - max(new['x'], old['x'])) *
                        max(0, min(new['y'] + new['h'], old['y'] + old['h']) - max(new['y'], old['y'])))
        if old_area <= 0 or intersection < old_area * 0.85 or new_area > old_area * 16:
            return False
        before_conf = old.get('confidence')
        if before_conf is not None:
            if after_conf is None or after_conf + 0.0300001 < before_conf:
                return False
        tokens = _tokens(old.get('src', ''), language)
        if not tokens:
            return False
        combined_before.extend(tokens)
    after = _tokens(new.get('src', ''), language)
    if len(after) < len(combined_before):
        return False
    matches = sum(b.size for b in SequenceMatcher(None, combined_before, after, autojunk=False).get_matching_blocks())
    return matches == len(combined_before)


def replacement_index(new, existing):
    """Return one safe match. Any multi-overlap remains observation-only."""
    overlaps=[]
    for index,old in enumerate(existing):
        area=max(1,min(new['w']*new['h'],old['w']*old['h']))
        intersection=max(0,min(new['x']+new['w'],old['x']+old['w'])-max(new['x'],old['x'])) * max(0,min(new['y']+new['h'],old['y']+old['h'])-max(new['y'],old['y']))
        if intersection/area > .5:
            overlaps.append(index)
    if len(overlaps)==1 and more_complete(new,existing[overlaps[0]]):
        return overlaps[0]
    return None

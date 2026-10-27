"""Preserve initial disfluency without guessing or replacing translated words."""
import re

# Single initials and English digraphs; avoid lexical hyphens such as Al-Alamein.
SOURCE=re.compile(r'''^(?P<lead>[\s"'“‘(\[]*)(?P<prefix>(?:(?:[A-Za-z]|[TtWwSsCc][Hh])-){1,4})(?P<stem>[A-Za-z]+)\b''')
TARGET=re.compile(r'''^(?P<lead>[\s"'“‘(\[]*)(?P<prefix>(?:[^\W\d_]{1,3}-){1,4})(?P<stem>[^\W\d_]+)\b''',re.UNICODE)
FIRST=re.compile(r'''^(?P<lead>[\s"'“‘(\[]*)(?P<stem>[^\W\d_]+)\b''',re.UNICODE)

def preserve_initial_stutter(source,translation):
 match=SOURCE.match(source)
 if not match:return translation
 units=match['prefix'].rstrip('-').split('-');stem=match['stem'].casefold()
 if any(not stem.startswith(u.casefold()) or len(u)>=len(stem) and stem!='i' for u in units):return translation
 original=translation;existing=TARGET.match(translation)
 if existing:
  prefixes=existing['prefix'].rstrip('-').split('-');word=existing['stem'].casefold()
  if all(word.startswith(p.casefold()) for p in prefixes):return translation
  # Strip only a leaked English stammer, not arbitrary target compounds.
  if not all(p.casefold() in {u.casefold() for u in units} for p in prefixes):return translation
  translation=existing['lead']+translation[existing.start('stem'):]
 first=FIRST.match(translation)
 if not first:return original
 initial=first['stem'][0]
 return translation[:first.start('stem')]+(initial+'-')*len(units)+translation[first.start('stem'):]

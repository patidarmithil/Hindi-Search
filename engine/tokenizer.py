"""Hindi text normalization and tokenization.

The exact same functions run at index time and at query time, so a query
token always matches the token stored in the inverted index.
"""
import re
import unicodedata

NUKTA = "़"
ZERO_WIDTH = "​‌‍﻿"  # ZWSP, ZWNJ, ZWJ, BOM

# Remove nukta and zero-width characters in one pass.
_STRIP_TABLE = {ord(ch): None for ch in NUKTA + ZERO_WIDTH}

# A token is one of:
#   - a run of Devanagari letters/marks (U+0900-U+0963, U+0971-U+097F);
#     this excludes danda "।" (U+0964), double danda "॥" (U+0965)
#     and Devanagari digits (U+0966-U+096F)
#   - a run of Latin letters
#   - a run of ASCII or Devanagari digits
_TOKEN_RE = re.compile(
    r"[ऀ-ॣॱ-ॿ]+"
    r"|[a-z]+"
    r"|[0-9०-९]+"
)

# Devanagari combining marks (matras, signs, virama). A token must not start
# with one; this happens only when stray punctuation splits a word.
_COMBINING_START = re.compile(r"^[ऀ-ःऺ-ॏ॑-ॗॢॣ]+")

# Common Hindi function words. NOT removed from the index (users may still
# search them); only used to keep suggestions meaningful.
STOPWORDS = frozenset("""
    है हैं था थे थी थीं हो होता होती होते होगा होगी होंगे हुआ हुई हुए रहा रही रहे
    के का की को में से पर ने और या एवं तथा भी तो ही न नहीं ना
    यह ये वह वे इस इन उस उन इसे उसे इसके उसके इसकी उसकी इनके उनके इनकी उनकी
    इसमें उसमें जो जिस जिन जिसे जिसके जिसकी कि कर करने करते करता करती किया किए
    गया गई गए लिए लिये साथ बाद तक एक दो कुछ सभी सब अपने अपनी अपना आप हम मैं
    जा जाता जाती जाते जाएगा जाएगी सकता सकती सकते रूप बात वाले वाली वाला अब जब तब
    कहा कहना बताया द्वारा अनुसार बीच दौरान होने ऐसे ऐसा कोई किसी कई पहले
    """.split())


def normalize(text: str) -> str:
    """NFC-normalize, fold nukta letters (ज़ -> ज), drop zero-width chars, lowercase Latin."""
    # NFC decomposes precomposed nukta letters (U+0958-U+095F) into base + nukta,
    # so removing U+093C afterwards folds both spellings to the same form.
    text = unicodedata.normalize("NFC", text)
    text = text.translate(_STRIP_TABLE)
    return text.lower()


def tokenize(text: str) -> list[str]:
    """Normalize text and split it into searchable tokens."""
    tokens = []
    for tok in _TOKEN_RE.findall(normalize(text)):
        tok = _COMBINING_START.sub("", tok)
        if tok:
            tokens.append(tok)
    return tokens


def is_stopword(token: str) -> bool:
    return token in STOPWORDS

"""Build the inverted index (posting lists) from the Data/ corpus.

Usage:  python -m engine.indexer

Output (in index/):
    postings.bin      pickle: {term: (doc_ids: array('i'), tfs: array('i'))}
                      doc_ids are sorted ascending (enables linear merge)
    docs.json         [{"id", "file", "title", "len"}] indexed by doc_id
    stats.json        corpus / build statistics
    suggestions.json  suggested words and sample queries for the UI
"""
import json
import pickle
import re
import sys
import time
from array import array
from collections import Counter
from multiprocessing import Pool, cpu_count
from pathlib import Path

from engine.config import (
    DATA_DIR,
    DOCS_FILE,
    FILE_ENCODING,
    INDEX_DIR,
    POSTINGS_FILE,
    STATS_FILE,
    SUGGESTIONS_FILE,
)
from engine.tokenizer import is_stopword, tokenize

# Footer present in almost every file:
# "यह खबर ‘भाषा’ न्यूज़ एजेंसी से ‘ऑटो-फीड’ द्वारा ली गई है. इसके कंटेंट के लिए दिप्रिंट जिम्मेदार नहीं है."
# Its words stay searchable but are kept out of suggestions.
BOILERPLATE = frozenset(tokenize(
    "यह खबर भाषा न्यूज़ एजेंसी ऑटो फीड ली गई कंटेंट दिप्रिंट जिम्मेदार"
))

# Candidate sample queries; only those that return results are kept.
SAMPLE_QUERIES = [
    "शेयर बाजार",
    "रिजर्व बैंक",
    "सोने की कीमत",
    "पेट्रोल डीजल",
    "जीएसटी",
    "मुद्रास्फीति",
    "विदेशी मुद्रा भंडार",
    "सेंसेक्स निफ्टी",
    "कच्चा तेल",
    "आर्थिक वृद्धि",
    "बजट",
    "किसान",
]

# Curated economy-domain words for suggestion chips. Raw top-frequency terms are
# dominated by verbs, months and editor names, so a curated list reads better.
# Only words present in the index are kept, ordered by document frequency.
SUGGESTED_WORDS = (
    "बाजार सरकार कंपनी शेयर बैंक निवेश विकास डॉलर तेल अर्थव्यवस्था कृषि उद्योग "
    "उत्पादन रिजर्व व्यापार निर्यात रोजगार आयात कर्ज ब्याज ऋण मुद्रास्फीति सेंसेक्स "
    "आरबीआई बिजली जीएसटी निफ्टी सोने किसान महंगाई जीडीपी बीमा बजट"
).split()

TITLE_MAX_CHARS = 120
_NUM_RE = re.compile(r"\((\d+)\)")


def _doc_sort_key(path: Path):
    """Sort 'Economy (10).txt' after 'Economy (9).txt' (numeric, not lexical)."""
    m = _NUM_RE.search(path.name)
    return (path.name[: m.start()] if m else path.name, int(m.group(1)) if m else 0)


def _process_file(args):
    """Worker: tokenize one document and count term frequencies."""
    doc_id, path = args
    text = Path(path).read_text(encoding=FILE_ENCODING, errors="replace")
    tokens = tokenize(text)
    title = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return doc_id, Counter(tokens), len(tokens), title[:TITLE_MAX_CHARS]


def build_index(data_dir: Path = DATA_DIR, workers: int | None = None, verbose: bool = True) -> dict:
    start = time.perf_counter()
    files = sorted(data_dir.glob("*.txt"), key=_doc_sort_key)
    if not files:
        raise FileNotFoundError(f"No .txt files found in {data_dir}")

    workers = workers or max(1, cpu_count() - 1)
    postings: dict[str, tuple[array, array]] = {}
    docs = [None] * len(files)
    total_tokens = 0

    jobs = [(i, str(p)) for i, p in enumerate(files)]
    with Pool(workers) as pool:
        # imap (ordered) yields documents in doc_id order, so every posting
        # list is appended in ascending doc_id order and needs no sorting.
        for n, (doc_id, counts, length, title) in enumerate(pool.imap(_process_file, jobs, chunksize=64), 1):
            docs[doc_id] = {"id": doc_id, "file": files[doc_id].name, "title": title, "len": length}
            total_tokens += length
            for term, tf in counts.items():
                entry = postings.get(term)
                if entry is None:
                    entry = postings[term] = (array("i"), array("i"))
                entry[0].append(doc_id)
                entry[1].append(tf)
            if verbose and n % 2000 == 0:
                print(f"  indexed {n:,}/{len(files):,} documents")

    index_time = time.perf_counter() - start

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    with open(POSTINGS_FILE, "wb") as f:
        pickle.dump(postings, f, protocol=pickle.HIGHEST_PROTOCOL)
    DOCS_FILE.write_text(json.dumps(docs, ensure_ascii=False), encoding="utf-8")

    suggestions = _build_suggestions(postings)
    SUGGESTIONS_FILE.write_text(json.dumps(suggestions, ensure_ascii=False, indent=2), encoding="utf-8")

    total_time = time.perf_counter() - start
    stats = {
        "documents": len(docs),
        "vocabulary": len(postings),
        "total_tokens": total_tokens,
        "postings": sum(len(d) for d, _ in postings.values()),
        "index_time_sec": round(index_time, 2),
        "build_time_sec": round(total_time, 2),
        "index_size_mb": round(POSTINGS_FILE.stat().st_size / 1024 / 1024, 2),
        "workers": workers,
    }
    STATS_FILE.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    return stats


def _build_suggestions(postings: dict) -> dict:
    """Suggested words (by document frequency) + sample queries that have hits."""
    words = [{"term": t, "df": len(postings[t][0])} for t in SUGGESTED_WORDS if t in postings]
    if not words:
        # Generic fallback for other corpora: most frequent content words.
        for term, (doc_ids, _) in sorted(postings.items(), key=lambda kv: len(kv[1][0]), reverse=True):
            if is_stopword(term) or term in BOILERPLATE or term.isdigit() or len(term) < 3:
                continue
            if not all("ऀ" <= ch <= "ॿ" for ch in term):
                continue
            words.append({"term": term, "df": len(doc_ids)})
            if len(words) == 30:
                break
    words.sort(key=lambda w: -w["df"])

    queries = []
    for q in SAMPLE_QUERIES:
        terms = tokenize(q)
        lists = [set(postings[t][0]) for t in terms if t in postings]
        if len(lists) == len(terms) and set.intersection(*lists):
            queries.append(q)

    return {"words": words, "queries": queries}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"Building inverted index from {DATA_DIR} ...")
    stats = build_index()
    print("Done.")
    for k, v in stats.items():
        print(f"  {k:16}: {v:,}" if isinstance(v, int) else f"  {k:16}: {v}")


if __name__ == "__main__":
    main()

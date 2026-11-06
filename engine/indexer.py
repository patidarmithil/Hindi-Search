"""Build the positional inverted index from the Hindi Wikipedia corpus.

Usage:  python -m engine.indexer [--workers N]

Input : corpus/hiwiki_articles.jsonl   (built by engine.wiki_extractor)
Output (index/):
    postings.bin      every posting list, one record per term, on disk
    lexicon.tsv       vocabulary: term, df, cf, byte offset and size of its record
    docs.json         doc_id -> title, wiki page id, token count, byte offset in the corpus
    stats.json        corpus / build statistics
    suggestions.json  suggested words and sample queries for the UI

Record layout of one term in postings.bin (all integers little-endian):

    doc_ids    uint32 x df   ascending document ids
    tfs        uint32 x df   term frequency in each document
    pos_offs   uint32 x df   byte offset of each document's positions in `positions`
    positions  bytes         for every document, tf positions (0-based token
                             index in the document) stored as gaps (first
                             position, then differences) in variable-byte code

df = document frequency (number of documents containing the term)
cf = collection frequency (total occurrences in the whole collection = sum of tfs)

The fixed-width part lets a query read doc_ids and tfs with one disk read and
no decoding; positions are decoded only for phrase queries and index lookups.
"""
import argparse
import json
import sys
import time
from array import array
from multiprocessing import Pool, cpu_count
from pathlib import Path

from engine.config import (
    CORPUS_FILE,
    DOCS_FILE,
    INDEX_DIR,
    LEXICON_FILE,
    POSTINGS_FILE,
    STATS_FILE,
    SUGGESTIONS_FILE,
)
from engine.tokenizer import is_stopword, tokenize

if sys.byteorder != "little":  # the file format is little-endian
    raise SystemExit("engine.indexer expects a little-endian machine")

# Candidate sample queries for the UI; only those that return results are kept.
# Quoted queries are phrase searches answered with term positions.
SAMPLE_QUERIES = [
    '"महात्मा गांधी"',
    "भारत की राजधानी",
    '"भारतीय संविधान"',
    "गंगा नदी",
    '"स्वतंत्रता संग्राम"',
    "ताजमहल",
    '"सौर मंडल"',
    "रामायण",
    '"मुगल साम्राज्य"',
    "क्रिकेट",
    "हिन्दी साहित्य",
    "प्रधानमंत्री",
]

# Curated general-knowledge words for suggestion chips (ordered by df at build time).
SUGGESTED_WORDS = (
    "भारत इतिहास विज्ञान राजनीति भाषा संस्कृति धर्म नदी पर्वत राज्य जिला गाँव "
    "शहर सरकार साहित्य कला संगीत फिल्म खेल क्रिकेट विश्वविद्यालय शिक्षा अर्थव्यवस्था "
    "ग्रह पृथ्वी मंदिर राजा युद्ध स्वतंत्रता संविधान कृषि"
).split()

# Worker processes for tokenizing (see README: no gain beyond 10 on the dev machine).
MAX_WORKERS = 10


def encode_gaps(positions: list[int]) -> bytes:
    """Variable-byte encode ascending integers as gaps (7 bits per byte, high bit = more)."""
    out = bytearray()
    prev = 0
    for p in positions:
        gap = p - prev
        prev = p
        while gap >= 0x80:
            out.append((gap & 0x7F) | 0x80)
            gap >>= 7
        out.append(gap)
    return bytes(out)


def decode_gaps(data: bytes | memoryview, count: int | None = None) -> list[int]:
    """Inverse of encode_gaps: returns the absolute positions."""
    out = []
    value = shift = prev = 0
    for byte in data:
        value |= (byte & 0x7F) << shift
        if byte & 0x80:
            shift += 7
            continue
        prev += value
        out.append(prev)
        value = shift = 0
        if count is not None and len(out) == count:
            break
    return out


def _process_doc(args):
    """Worker: tokenize one article -> (doc_id, length, [(term, tf, encoded positions)])."""
    doc_id, line = args
    article = json.loads(line)
    tokens = tokenize(article["title"] + "\n" + article["text"])
    positions: dict[str, list[int]] = {}
    for pos, tok in enumerate(tokens):
        lst = positions.get(tok)
        if lst is None:
            positions[tok] = [pos]
        else:
            lst.append(pos)
    terms = [(t, len(p), encode_gaps(p)) for t, p in positions.items()]
    return doc_id, len(tokens), article["title"], article["wiki_id"], terms


def _read_corpus(corpus: Path, limit: int | None):
    """Yield (doc_id, json line) and record each line's byte offset for random access."""
    offsets = array("Q")
    with open(corpus, "rb") as f:
        doc_id = 0
        while True:
            off = f.tell()
            line = f.readline()
            if not line:
                break
            if not line.strip():
                continue
            offsets.append(off)
            yield doc_id, line.decode("utf-8"), offsets
            doc_id += 1
            if limit and doc_id >= limit:
                break


class _Posting:
    """In-build posting list for one term (appended in ascending doc_id order)."""
    __slots__ = ("docs", "tfs", "offs", "pos")

    def __init__(self):
        self.docs = array("I")
        self.tfs = array("I")
        self.offs = array("I")
        self.pos = bytearray()


def build_index(corpus: Path = CORPUS_FILE, workers: int | None = None,
                limit: int | None = None, verbose: bool = True) -> dict:
    if not corpus.exists():
        raise FileNotFoundError(f"{corpus} not found. Run: python -m engine.wiki_extractor")
    start = time.perf_counter()
    workers = workers or max(1, min(MAX_WORKERS, cpu_count() - 1))

    postings: dict[str, _Posting] = {}
    titles, wiki_ids, lengths = [], array("I"), array("I")
    total_tokens = 0
    offsets_ref = [array("Q")]

    def jobs():
        for doc_id, line, offs in _read_corpus(corpus, limit):
            offsets_ref[0] = offs
            yield doc_id, line

    with Pool(workers) as pool:
        # imap (ordered) yields documents in doc_id order, so every posting
        # list is appended in ascending doc_id order and never needs sorting.
        for doc_id, length, title, wiki_id, terms in pool.imap(_process_doc, jobs(), chunksize=64):
            titles.append(title)
            wiki_ids.append(wiki_id)
            lengths.append(length)
            total_tokens += length
            for term, tf, pos_bytes in terms:
                p = postings.get(term)
                if p is None:
                    p = postings[term] = _Posting()
                p.docs.append(doc_id)
                p.tfs.append(tf)
                p.offs.append(len(p.pos))
                p.pos += pos_bytes
            if verbose and (doc_id + 1) % 20000 == 0:
                print(f"  indexed {doc_id + 1:,} documents ({time.perf_counter() - start:.0f} s)")
    index_time = time.perf_counter() - start

    # ---- write postings to disk + lexicon (sorted vocabulary)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    vocab = sorted(postings)
    n_postings = 0
    with open(POSTINGS_FILE, "wb") as pf, open(LEXICON_FILE, "w", encoding="utf-8", newline="\n") as lf:
        lf.write("# term\tdf\tcf\toffset\tbytes\n")
        offset = 0
        for term in vocab:
            p = postings[term]
            record = p.docs.tobytes() + p.tfs.tobytes() + p.offs.tobytes() + bytes(p.pos)
            pf.write(record)
            df = len(p.docs)
            cf = sum(p.tfs)
            n_postings += df
            lf.write(f"{term}\t{df}\t{cf}\t{offset}\t{len(record)}\n")
            offset += len(record)

    offsets = offsets_ref[0]
    docs = {
        "titles": titles,
        "wiki_ids": list(wiki_ids),
        "lengths": list(lengths),
        "offsets": list(offsets[: len(titles)]),
    }
    DOCS_FILE.write_text(json.dumps(docs, ensure_ascii=False), encoding="utf-8")

    suggestions = _build_suggestions(postings)
    SUGGESTIONS_FILE.write_text(json.dumps(suggestions, ensure_ascii=False, indent=2), encoding="utf-8")

    stats = {
        "corpus": "Hindi Wikipedia (hiwiki-latest-pages-articles.xml.bz2)",
        "documents": len(titles),
        "vocabulary": len(vocab),
        "total_tokens": total_tokens,
        "postings": n_postings,
        "avg_doc_length": round(total_tokens / max(1, len(titles)), 1),
        "index_time_sec": round(index_time, 2),
        "build_time_sec": round(time.perf_counter() - start, 2),
        "postings_size_mb": round(POSTINGS_FILE.stat().st_size / 1024 / 1024, 1),
        "lexicon_size_mb": round(LEXICON_FILE.stat().st_size / 1024 / 1024, 1),
        "workers": workers,
    }
    STATS_FILE.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


def _phrase_df(postings: dict, terms: list[str]) -> int:
    """Number of documents containing the terms as consecutive words (build-time check)."""
    if len(terms) < 2 or any(t not in postings for t in terms):
        return 0
    lists = [postings[t] for t in terms]
    index_of = [{d: i for i, d in enumerate(p.docs)} for p in lists]
    common = set(index_of[0]).intersection(*index_of[1:])

    def positions(k, doc):
        p, i = lists[k], index_of[k][doc]
        end = p.offs[i + 1] if i + 1 < len(p.offs) else len(p.pos)
        return decode_gaps(memoryview(p.pos)[p.offs[i]:end])

    hits = 0
    for doc in common:
        later = [set(positions(k, doc)) for k in range(1, len(terms))]
        if any(all(s + k in later[k - 1] for k in range(1, len(terms))) for s in positions(0, doc)):
            hits += 1
    return hits


def _build_suggestions(postings: dict) -> dict:
    """Suggested words (by document frequency) + sample queries that have hits."""
    words = [{"term": t, "df": len(postings[t].docs)} for t in SUGGESTED_WORDS if t in postings]
    if len(words) < 10:
        # Generic fallback for other corpora: most frequent content words.
        words = []
        for term, p in sorted(postings.items(), key=lambda kv: len(kv[1].docs), reverse=True):
            if is_stopword(term) or len(term) < 3 or not all("ऀ" <= ch <= "ॿ" for ch in term):
                continue
            words.append({"term": term, "df": len(p.docs)})
            if len(words) == 30:
                break
    words.sort(key=lambda w: -w["df"])

    queries = []
    for q in SAMPLE_QUERIES:
        terms = tokenize(q)
        if q.startswith('"'):
            ok = _phrase_df(postings, terms) > 0
        else:
            ok = bool(terms) and all(t in postings for t in terms) and bool(
                set(postings[terms[0]].docs).intersection(*(set(postings[t].docs) for t in terms[1:])))
        if ok:
            queries.append(q)
    return {"words": words, "queries": queries}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Build the positional inverted index")
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--limit", type=int, default=None, help="index only the first N articles (testing)")
    args = ap.parse_args()
    print(f"Building positional index from {CORPUS_FILE} ...")
    stats = build_index(workers=args.workers, limit=args.limit)
    print("Done.")
    for k, v in stats.items():
        print(f"  {k:16}: {v:,}" if isinstance(v, int) else f"  {k:16}: {v}")


if __name__ == "__main__":
    main()

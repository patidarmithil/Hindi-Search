"""Query-time search over the in-memory inverted index.

The index is loaded once; every query is then pure in-memory work:
    1. tokenize + normalize the query (same rules as indexing)
    2. O(1) hash lookup of each term's posting list
    3. AND: two-pointer merge of doc_id-sorted lists, shortest first
       (falls back to OR / union if no document contains every term)
    4. rank by total occurrence count, slice the requested page
"""
import bisect
import json
import pickle
import re
import time
from functools import lru_cache
from heapq import merge

from engine.config import DATA_DIR, DOCS_FILE, FILE_ENCODING, POSTINGS_FILE, STATS_FILE, SUGGESTIONS_FILE
from engine.tokenizer import tokenize

# Matches word-like runs in RAW text (incl. nukta letters and zero-width joiners)
# so highlight offsets point into the original, un-normalized document.
_RAW_WORD_RE = re.compile(r"[ऀ-ॣॱ-ॿ‌‍]+|[A-Za-z]+|[0-9०-९]+")


def intersect(a_docs, a_tfs, b_docs, b_tfs):
    """Two-pointer merge of two doc_id-sorted posting lists (AND). Sums tfs."""
    out_docs, out_tfs = [], []
    i = j = 0
    na, nb = len(a_docs), len(b_docs)
    while i < na and j < nb:
        da, db = a_docs[i], b_docs[j]
        if da == db:
            out_docs.append(da)
            out_tfs.append(a_tfs[i] + b_tfs[j])
            i += 1
            j += 1
        elif da < db:
            i += 1
        else:
            j += 1
    return out_docs, out_tfs


def union(lists):
    """k-way merge of doc_id-sorted posting lists (OR). Sums tfs per doc."""
    out_docs, out_tfs = [], []
    streams = [zip(docs, tfs) for docs, tfs in lists]
    for doc_id, tf in merge(*streams):
        if out_docs and out_docs[-1] == doc_id:
            out_tfs[-1] += tf
        else:
            out_docs.append(doc_id)
            out_tfs.append(tf)
    return out_docs, out_tfs


class Searcher:
    def __init__(self):
        self.postings: dict = {}
        self.docs: list = []
        self.vocab: list[str] = []
        self.stats: dict = {}
        self.suggestions: dict = {}
        self.load_time_sec = 0.0

    # ------------------------------------------------------------------ load
    def load(self) -> "Searcher":
        start = time.perf_counter()
        # pickle is safe here: postings.bin is generated locally by engine.indexer,
        # never received from users or the network.
        with open(POSTINGS_FILE, "rb") as f:
            self.postings = pickle.load(f)
        self.docs = json.loads(DOCS_FILE.read_text(encoding="utf-8"))
        self.stats = json.loads(STATS_FILE.read_text(encoding="utf-8"))
        self.suggestions = json.loads(SUGGESTIONS_FILE.read_text(encoding="utf-8"))
        self.vocab = sorted(self.postings)  # for prefix autocomplete via bisect
        self._match.cache_clear()
        self.load_time_sec = time.perf_counter() - start
        return self

    @staticmethod
    def index_exists() -> bool:
        return all(p.exists() for p in (POSTINGS_FILE, DOCS_FILE, STATS_FILE, SUGGESTIONS_FILE))

    # ---------------------------------------------------------------- search
    @lru_cache(maxsize=1024)
    def _match(self, terms: tuple[str, ...]):
        """Return (mode, [(doc_id, count), ...] ranked by count desc)."""
        lists = [self.postings[t] for t in terms if t in self.postings]
        if not lists:
            return "none", ()

        if len(lists) == 1:
            docs, tfs = lists[0]
            # several query terms but only one known: effectively an OR result
            mode = "single" if len(terms) == 1 else "or"
        else:
            # AND only makes sense if every query term exists in the vocabulary.
            docs, tfs = [], []
            if len(lists) == len(terms):
                lists_by_len = sorted(lists, key=lambda p: len(p[0]))
                docs, tfs = lists_by_len[0]
                for other_docs, other_tfs in lists_by_len[1:]:
                    docs, tfs = intersect(docs, tfs, other_docs, other_tfs)
                    if not docs:
                        break
                mode = "and"
            if not docs:
                docs, tfs = union(lists)
                mode = "or"

        ranked = sorted(zip(docs, tfs), key=lambda x: (-x[1], x[0]))
        return mode, tuple(ranked)

    def search(self, query: str, offset: int = 0, limit: int | None = 50) -> dict:
        start = time.perf_counter()
        # dict.fromkeys dedupes while keeping query order
        terms = tuple(dict.fromkeys(tokenize(query)))
        mode, ranked = self._match(terms) if terms else ("none", ())

        page = ranked[offset:] if limit is None else ranked[offset: offset + limit]
        results = [
            {
                "rank": offset + i + 1,
                "doc_id": doc_id,
                "file": self.docs[doc_id]["file"],
                "title": self.docs[doc_id]["title"],
                "count": count,
            }
            for i, (doc_id, count) in enumerate(page)
        ]
        elapsed = time.perf_counter() - start
        return {
            "query": query,
            "terms": list(terms),
            "missing_terms": [t for t in terms if t not in self.postings],
            "mode": mode,
            "total_docs": len(ranked),
            "total_occurrences": sum(c for _, c in ranked),
            "docs_searched": len(self.docs),
            "offset": offset,
            "results": results,
            "time_sec": elapsed,
        }

    # -------------------------------------------------------------- document
    def get_document(self, doc_id: int, query: str = "") -> dict:
        if not 0 <= doc_id < len(self.docs):
            raise KeyError(doc_id)
        meta = self.docs[doc_id]
        text = (DATA_DIR / meta["file"]).read_text(encoding=FILE_ENCODING, errors="replace")
        terms = set(tokenize(query))
        return {**meta, "text": text, "highlights": highlight_spans(text, terms)}

    # ----------------------------------------------------------- suggestions
    def autocomplete(self, prefix: str, limit: int = 10) -> list[dict]:
        tokens = tokenize(prefix)
        if not tokens:
            return []
        p = tokens[-1]
        lo = bisect.bisect_left(self.vocab, p)
        hi = bisect.bisect_left(self.vocab, p + "\U0010FFFF")
        matches = self.vocab[lo:hi]
        matches.sort(key=lambda t: -len(self.postings[t][0]))
        return [{"term": t, "df": len(self.postings[t][0])} for t in matches[:limit]]


def highlight_spans(text: str, terms: set[str]) -> list[list[int]]:
    """[start, end) character offsets in the raw text of words matching any query term."""
    if not terms:
        return []
    spans = []
    for m in _RAW_WORD_RE.finditer(text):
        if any(tok in terms for tok in tokenize(m.group())):
            spans.append([m.start(), m.end()])
    return spans

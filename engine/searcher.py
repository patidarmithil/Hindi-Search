"""Query processing over the positional index.

Main memory holds only the vocabulary (lexicon: term -> df, cf, offset, size)
and per-document metadata. Posting lists stay in index/postings.bin on disk;
each query seeks to the records of its own terms and reads only those bytes.

    1. tokenize + normalize the query (same rules as indexing);
       text in double quotes is a phrase: "महात्मा गांधी"
    2. binary search of each term in the in-memory vocabulary
    3. read the posting list(s) from disk (doc_ids + tfs; positions only for phrases)
    4. AND: intersect sorted doc_id arrays, rarest term first
       (falls back to OR if no document contains every term / phrase)
       phrase: keep documents where the terms occur at consecutive positions
    5. rank with BM25, return the requested page
"""
import bisect
import json
import re
import threading
import time
from functools import lru_cache
from urllib.parse import quote

import numpy as np

from engine.config import (
    CORPUS_FILE,
    DOCS_FILE,
    LEXICON_FILE,
    POSTINGS_FILE,
    STATS_FILE,
    SUGGESTIONS_FILE,
)
from engine.indexer import decode_gaps
from engine.tokenizer import tokenize

# BM25 parameters (standard values).
K1 = 1.2
B = 0.75

_PHRASE_RE = re.compile(r'"([^"]*)"')
# Global token positions leave this many empty slots between documents, so a
# phrase (at most MAX_PHRASE terms) can never match across two documents.
MAX_PHRASE = 32
# Word-like runs in RAW text (incl. nukta letters and zero-width joiners), so
# highlight offsets point into the original, un-normalized article text.
_RAW_WORD_RE = re.compile(r"[ऀ-ॣॱ-ॿ‌‍]+|[A-Za-z]+|[0-9०-९]+")

WIKI_URL = "https://hi.wikipedia.org/wiki/"


def wiki_url(title: str) -> str:
    return WIKI_URL + quote(title.replace(" ", "_"))


def parse_query(query: str) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]:
    """Split a query into (single terms, phrases). Each phrase is a tuple of terms."""
    phrases = []
    for chunk in _PHRASE_RE.findall(query):
        toks = tuple(tokenize(chunk))
        if len(toks) == 1:
            continue  # a quoted single word is just a term; handled below
        if toks:
            phrases.append(toks[:MAX_PHRASE])
    rest = _PHRASE_RE.sub(lambda m: m.group(1) if len(tokenize(m.group(1))) == 1 else " ", query)
    terms = tuple(dict.fromkeys(tokenize(rest.replace('"', " "))))  # dedupe, keep order
    return terms, tuple(dict.fromkeys(phrases))


class Searcher:
    def __init__(self):
        self.vocab: list[str] = []
        self.df = self.cf = self.offsets = self.nbytes = None
        self.titles: list[str] = []
        self.doc_len = None
        self.doc_offsets: list[int] = []
        self.wiki_ids: list[int] = []
        self.avgdl = 1.0
        self.stats: dict = {}
        self.suggestions: dict = {}
        self.load_time_sec = 0.0
        self._fh = None
        self._lock = threading.Lock()
        self.disk_reads = 0
        self.disk_bytes = 0

    # ------------------------------------------------------------------ load
    def load(self) -> "Searcher":
        start = time.perf_counter()
        vocab, df, cf, off, nb = [], [], [], [], []
        with open(LEXICON_FILE, encoding="utf-8") as f:
            for line in f:
                if line.startswith("#"):
                    continue
                t, a, b, c, d = line.rstrip("\n").split("\t")
                vocab.append(t)
                df.append(int(a))
                cf.append(int(b))
                off.append(int(c))
                nb.append(int(d))
        self.vocab = vocab  # sorted (written in sorted order by the indexer)
        self.df = np.array(df, dtype=np.int64)
        self.cf = np.array(cf, dtype=np.int64)
        self.offsets = np.array(off, dtype=np.int64)
        self.nbytes = np.array(nb, dtype=np.int64)

        docs = json.loads(DOCS_FILE.read_text(encoding="utf-8"))
        self.titles = docs["titles"]
        self.wiki_ids = docs["wiki_ids"]
        self.doc_offsets = docs["offsets"]
        self.doc_len = np.array(docs["lengths"], dtype=np.float64)
        self.avgdl = float(self.doc_len.mean()) if len(self.doc_len) else 1.0
        # start of every document on one global position axis (for phrase matching)
        ends = np.cumsum(self.doc_len.astype(np.int64) + MAX_PHRASE)
        self.doc_base = np.concatenate(([0], ends[:-1])).astype(np.int64)
        self.span = int(ends[-1]) if len(ends) else 0

        self.stats = json.loads(STATS_FILE.read_text(encoding="utf-8"))
        self.suggestions = json.loads(SUGGESTIONS_FILE.read_text(encoding="utf-8"))
        if self._fh:
            self._fh.close()
        self._fh = open(POSTINGS_FILE, "rb")
        self._match.cache_clear()
        self.load_time_sec = time.perf_counter() - start
        return self

    @staticmethod
    def index_exists() -> bool:
        return all(p.exists() for p in (POSTINGS_FILE, LEXICON_FILE, DOCS_FILE, STATS_FILE, SUGGESTIONS_FILE))

    @property
    def n_docs(self) -> int:
        return len(self.titles)

    # ------------------------------------------------------------ vocabulary
    def term_id(self, term: str) -> int:
        """Position of term in the sorted in-memory vocabulary, or -1."""
        i = bisect.bisect_left(self.vocab, term)
        return i if i < len(self.vocab) and self.vocab[i] == term else -1

    def _read(self, tid: int, positions: bool) -> bytes:
        """Read one term's record (or only its doc_ids + tfs) from postings.bin."""
        df = int(self.df[tid])
        size = int(self.nbytes[tid]) if positions else 8 * df
        with self._lock:  # one shared file handle; FastAPI serves requests from threads
            self._fh.seek(int(self.offsets[tid]))
            data = self._fh.read(size)
        self.disk_reads += 1
        self.disk_bytes += size
        return data

    def read_postings(self, tid: int, positions: bool = False):
        """-> (doc_ids, tfs[, pos_offs, positions_blob]) for term id tid."""
        df = int(self.df[tid])
        data = self._read(tid, positions)
        docs = np.frombuffer(data, dtype="<u4", count=df, offset=0)
        tfs = np.frombuffer(data, dtype="<u4", count=df, offset=4 * df)
        if not positions:
            return docs, tfs
        offs = np.frombuffer(data, dtype="<u4", count=df, offset=8 * df)
        return docs, tfs, offs, memoryview(data)[12 * df:]

    def postings(self, term: str, max_docs: int | None = None) -> dict | None:
        """Positional posting list of one (normalized) term, as stored on disk."""
        toks = tokenize(term)
        if not toks:
            return None
        term = toks[0]
        tid = self.term_id(term)
        if tid < 0:
            return None
        docs, tfs, offs, blob = self.read_postings(tid, positions=True)
        n = len(docs) if max_docs is None else min(max_docs, len(docs))
        rows = []
        for i in range(n):
            end = int(offs[i + 1]) if i + 1 < len(offs) else len(blob)
            rows.append({
                "doc_id": int(docs[i]),
                "title": self.titles[int(docs[i])],
                "tf": int(tfs[i]),
                "positions": decode_gaps(blob[int(offs[i]):end]),
            })
        return {
            "term": term,
            "df": int(self.df[tid]),
            "cf": int(self.cf[tid]),
            "offset": int(self.offsets[tid]),
            "bytes": int(self.nbytes[tid]),
            "shown": n,
            "postings": rows,
        }

    # ---------------------------------------------------------------- search
    def _bm25(self, docs: np.ndarray, tfs: np.ndarray, df: int) -> np.ndarray:
        n = self.n_docs
        idf = np.log(1.0 + (n - df + 0.5) / (df + 0.5))
        tf = tfs.astype(np.float64)
        norm = K1 * (1.0 - B + B * self.doc_len[docs] / self.avgdl)
        return idf * tf * (K1 + 1.0) / (tf + norm)

    def _phrase(self, terms: tuple[str, ...]):
        """Documents where terms occur consecutively -> (doc_ids, phrase counts).

        Every occurrence of term k becomes a global position g (document start +
        position) and is shifted back by k. A phrase starts at g exactly when
        every term has an occurrence at g + k, so the test is a set intersection
        of shifted positions, done with a boolean array over the position axis.
        Only documents that contain every term are decoded.
        """
        tids = [self.term_id(t) for t in terms]
        if any(t < 0 for t in tids):
            return None
        lists = [self.read_postings(t, positions=True) for t in tids]
        cand = lists[0][0]
        for docs, *_ in lists[1:]:
            cand = np.intersect1d(cand, docs, assume_unique=True)
            if not len(cand):
                return np.empty(0, np.uint32), np.empty(0, np.int64)

        common = None
        for k, (docs, tfs, _offs, blob) in enumerate(lists):
            keep = np.isin(docs, cand, assume_unique=True)
            starts = global_positions(docs, tfs, blob, self.doc_base, keep) - k
            if common is None:
                common = starts
            else:
                seen = np.zeros(self.span, dtype=bool)
                seen[common] = True
                starts = starts[starts >= 0]
                common = starts[seen[starts]]
            if not len(common):
                return np.empty(0, np.uint32), np.empty(0, np.int64)
        doc_of = np.searchsorted(self.doc_base, common, side="right") - 1
        out_docs, counts = np.unique(doc_of, return_counts=True)
        return out_docs.astype(np.uint32), counts.astype(np.int64)

    @lru_cache(maxsize=1024)
    def _match(self, terms: tuple[str, ...], phrases: tuple[tuple[str, ...], ...]):
        """-> (mode, ranked doc_ids, counts, scores, missing units)."""
        units, missing = [], []  # unit = (doc_ids, counts, df)
        for t in terms:
            tid = self.term_id(t)
            if tid < 0:
                missing.append(t)
                continue
            docs, tfs = self.read_postings(tid)
            units.append((docs, tfs.astype(np.int64), int(self.df[tid])))
        for ph in phrases:
            res = self._phrase(ph)
            if res is None or not len(res[0]):
                missing.append('"' + " ".join(ph) + '"')
                continue
            units.append((res[0], res[1], len(res[0])))

        empty = np.empty(0, np.int64)
        if not units:
            return "none", empty, empty, np.empty(0), tuple(missing)

        n_units = len(terms) + len(phrases)
        docs = None
        if len(units) == n_units:
            # AND: rarest first keeps the running intersection small
            units.sort(key=lambda u: len(u[0]))
            docs = units[0][0]
            counts = units[0][1].copy()
            scores = self._bm25(units[0][0], units[0][1], units[0][2])
            for u_docs, u_counts, u_df in units[1:]:
                docs, ia, ib = np.intersect1d(docs, u_docs, assume_unique=True, return_indices=True)
                counts = counts[ia] + u_counts[ib]
                scores = scores[ia] + self._bm25(u_docs[ib], u_counts[ib], u_df)
                if not len(docs):
                    break
            if n_units == 1:
                mode = "phrase" if phrases else "single"
            else:
                mode = "phrase" if phrases and not terms else "and"
        if docs is None or not len(docs):
            # OR fallback: union of all known units, scores and counts summed per doc
            all_docs = np.concatenate([u[0] for u in units]).astype(np.int64)
            all_counts = np.concatenate([u[1] for u in units])
            all_scores = np.concatenate([self._bm25(u[0], u[1], u[2]) for u in units])
            docs, inv = np.unique(all_docs, return_inverse=True)
            counts = np.bincount(inv, weights=all_counts).astype(np.int64)
            scores = np.bincount(inv, weights=all_scores)
            mode = "or"

        order = np.lexsort((docs, -scores))  # score desc, ties by doc_id
        return mode, docs[order].astype(np.int64), counts[order], scores[order], tuple(missing)

    def search(self, query: str, offset: int = 0, limit: int | None = 50) -> dict:
        start = time.perf_counter()
        reads0 = self.disk_reads
        terms, phrases = parse_query(query)
        if terms or phrases:
            mode, docs, counts, scores, missing = self._match(terms, phrases)
        else:
            mode, docs, counts, scores, missing = "none", np.empty(0, np.int64), np.empty(0, np.int64), np.empty(0), ()

        end = len(docs) if limit is None else offset + limit
        results = [
            {
                "rank": offset + i + 1,
                "doc_id": int(d),
                "title": self.titles[int(d)],
                "url": wiki_url(self.titles[int(d)]),
                "count": int(c),
                "score": round(float(s), 4),
            }
            for i, (d, c, s) in enumerate(zip(docs[offset:end], counts[offset:end], scores[offset:end]))
        ]
        return {
            "query": query,
            "terms": list(terms),
            "phrases": [" ".join(p) for p in phrases],
            "missing_terms": list(missing),
            "mode": mode,
            "total_docs": int(len(docs)),
            "total_occurrences": int(counts.sum()) if len(counts) else 0,
            "docs_searched": self.n_docs,
            "disk_reads": self.disk_reads - reads0,  # 0 when served from the query cache
            "offset": offset,
            "results": results,
            "time_sec": time.perf_counter() - start,
        }

    # -------------------------------------------------------------- document
    def read_article(self, doc_id: int) -> dict:
        if not 0 <= doc_id < self.n_docs:
            raise KeyError(doc_id)
        with open(CORPUS_FILE, "rb") as f:
            f.seek(self.doc_offsets[doc_id])
            return json.loads(f.readline().decode("utf-8"))

    def get_document(self, doc_id: int, query: str = "") -> dict:
        art = self.read_article(doc_id)
        terms, phrases = parse_query(query)
        text = art["text"]
        return {
            "id": doc_id,
            "title": art["title"],
            "url": art["url"],
            "wiki_id": art["wiki_id"],
            "len": int(self.doc_len[doc_id]),
            "text": text,
            "highlights": highlight_spans(text, set(terms), phrases),
        }

    # ----------------------------------------------------------- suggestions
    def autocomplete(self, prefix: str, limit: int = 10) -> list[dict]:
        tokens = tokenize(prefix)
        if not tokens:
            return []
        p = tokens[-1]
        lo = bisect.bisect_left(self.vocab, p)
        hi = bisect.bisect_left(self.vocab, p + "\U0010FFFF")
        if lo == hi:
            return []
        dfs = self.df[lo:hi]
        k = min(limit, hi - lo)
        top = np.argpartition(-dfs, k - 1)[:k] if hi - lo > k else np.arange(hi - lo)
        top = top[np.lexsort((top, -dfs[top]))]
        return [{"term": self.vocab[lo + int(i)], "df": int(dfs[i])} for i in top]


def decode_gaps_np(blob) -> np.ndarray:
    """Vectorized variable-byte decode of a whole positions blob -> gap values."""
    b = np.frombuffer(blob, dtype=np.uint8)
    if not len(b):
        return np.empty(0, np.int64)
    ends = np.flatnonzero(b < 0x80)  # last byte of every value
    if len(ends) == len(b):  # every value fits in one byte (the common case)
        return b.astype(np.int64)
    starts = np.concatenate(([0], ends[:-1] + 1))
    group = np.repeat(np.arange(len(starts)), ends - starts + 1)
    shift = (np.arange(len(b)) - starts[group]) * 7
    parts = (b & 0x7F).astype(np.int64) << shift
    return np.add.reduceat(parts, starts)


def global_positions(docs, tfs, blob, doc_base, keep=None) -> np.ndarray:
    """All occurrences of a term as ascending global positions doc_base[doc] + position."""
    gaps = decode_gaps_np(blob)
    tfs = tfs.astype(np.int64)
    seg = np.concatenate(([0], np.cumsum(tfs)[:-1]))  # first gap of each document
    cs = np.cumsum(gaps)
    pos = cs - np.repeat(cs[seg] - gaps[seg], tfs)   # gaps -> absolute positions per document
    doc_rep = np.repeat(docs.astype(np.int64), tfs)
    if keep is not None:
        mask = np.repeat(keep, tfs)
        pos, doc_rep = pos[mask], doc_rep[mask]
    return doc_base[doc_rep] + pos


def highlight_spans(text: str, terms: set[str], phrases=()) -> list[list[int]]:
    """[start, end) character offsets in the raw text of matching words and phrases."""
    if not terms and not phrases:
        return []
    words = []  # (normalized token, start, end) in reading order
    for m in _RAW_WORD_RE.finditer(text):
        for tok in tokenize(m.group()):
            words.append((tok, m.start(), m.end()))
    spans = set()
    for i, (tok, s, e) in enumerate(words):
        if tok in terms:
            spans.add((s, e))
        for ph in phrases:
            n = len(ph)
            if tuple(w[0] for w in words[i:i + n]) == ph:
                spans.add((s, words[i + n - 1][2]))
    # merge overlapping spans
    out = []
    for s, e in sorted(spans):
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out

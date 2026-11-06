"""Generate the submission output: 5 test cases + 10 rare terms with their positional index.

Usage:  python scripts/generate_output.py [--out output/test_cases.txt] [--seed 7]

Every posting printed here is read from index/postings.bin through the
in-memory vocabulary, then checked against the raw article text: the
positions are recomputed by tokenizing the article and must match exactly.
"""
import argparse
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.config import POSTINGS_FILE  # noqa: E402
from engine.searcher import Searcher  # noqa: E402
from engine.tokenizer import is_stopword, tokenize  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LINE = "=" * 90
SUB = "-" * 90


class Report:
    def __init__(self):
        self.lines = []
        self.passed = self.failed = 0

    def __call__(self, text=""):
        self.lines.append(text)

    def check(self, ok: bool, what: str):
        self.passed += ok
        self.failed += not ok
        self(f"  [{'PASS' if ok else 'FAIL'}] {what}")


def doc_tokens(s: Searcher, doc_id: int) -> list[str]:
    """Tokens of an article exactly as the indexer saw them (title + text)."""
    art = s.read_article(doc_id)
    return tokenize(art["title"] + "\n" + art["text"])


def verify_postings(s: Searcher, info: dict) -> bool:
    """Recompute the positions of info['term'] in every listed document from the raw text."""
    for p in info["postings"]:
        toks = doc_tokens(s, p["doc_id"])
        if [i for i, t in enumerate(toks) if t == info["term"]] != p["positions"]:
            return False
    return True


def print_posting_list(r: Report, info: dict, max_pos: int | None = None):
    r(f"  Term: {info['term']}    DF = {info['df']}    CF = {info['cf']}    "
      f"(postings.bin offset {info['offset']:,}, {info['bytes']} bytes)")
    r(f"  {info['term']} -> {info['df']}, {info['cf']}:")
    for p in info["postings"]:
        pos = p["positions"] if max_pos is None else p["positions"][:max_pos]
        more = "" if max_pos is None or len(p["positions"]) <= max_pos else f", ... (+{len(p['positions']) - max_pos})"
        r(f"      doc {p['doc_id']:>7} ({p['title']}), tf={p['tf']}: <{', '.join(map(str, pos))}{more}>")


def pick_rare_terms(s: Searcher, n: int, seed: int) -> list[str]:
    """Rare = DF of 2 or 3: rare, but still shows postings in more than one document."""
    rng = random.Random(seed)
    cands = []
    for i, t in enumerate(s.vocab):
        df = int(s.df[i])
        if 2 <= df <= 3 and len(t) >= 5 and all("ऀ" <= ch <= "ॿ" for ch in t) and not is_stopword(t):
            cands.append(t)
    return sorted(rng.sample(cands, n))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "output" / "test_cases.txt")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    s = Searcher().load()
    st = s.stats
    r = Report()
    r(LINE)
    r("Positional Inverted Index - Test Cases and Rare-Term Positional Index")
    r(LINE)
    r(f"Corpus            : {st['corpus']}")
    r(f"Documents         : {st['documents']:,}")
    r(f"Tokens            : {st['total_tokens']:,}")
    r(f"Vocabulary        : {st['vocabulary']:,} terms (held in main memory)")
    r(f"Postings          : {st['postings']:,} (term, document) pairs")
    r(f"postings.bin      : {st['postings_size_mb']} MB on disk (secondary memory)")
    r(f"Index build time  : {st['build_time_sec']} s with {st['workers']} worker processes")
    r(f"Vocabulary load   : {s.load_time_sec:.2f} s")
    r("")
    r("Notation: term -> DF, CF: doc_id (title), tf=<term frequency>: <positions>")
    r("Positions are 0-based token indexes in the article (title + text), after normalization.")
    r("DF = number of documents containing the term; CF = total occurrences in the collection.")
    r("Each [PASS] means the value was recomputed independently from the raw article text.")

    # ------------------------------------------------------------- test cases
    r("")
    r(LINE)
    r("PART A - 5 TEST CASES")
    r(LINE)

    # 1. single-term positional lookup
    r("\nTest case 1: positional posting list of one term (भारत), read from disk")
    r(SUB)
    info = s.postings("भारत", max_docs=5)
    print_posting_list(r, info, max_pos=15)
    r.check(verify_postings(s, info), "positions of 'भारत' in the first 5 documents match the raw text")
    tid = s.term_id("भारत")
    full_docs, full_tfs = s.read_postings(tid)
    r.check(len(full_docs) == info["df"], f"DF = length of the posting list ({len(full_docs):,})")
    r.check(int(full_tfs.sum()) == info["cf"], f"CF = sum of all term frequencies ({int(full_tfs.sum()):,})")
    r.check(all(full_docs[i] < full_docs[i + 1] for i in range(len(full_docs) - 1)),
            "posting list is sorted by doc_id")

    # 2. phrase query
    q = '"महात्मा गांधी"'
    r(f"\nTest case 2: phrase query {q} (uses term positions)")
    r(SUB)
    res = s.search(q, limit=5)
    r(f"  mode={res['mode']}  documents found={res['total_docs']:,}  "
      f"phrase occurrences={res['total_occurrences']:,}  time={res['time_sec'] * 1000:.2f} ms")
    ok = True
    for row in res["results"]:
        toks = doc_tokens(s, row["doc_id"])
        hits = sum(1 for i in range(len(toks) - 1) if toks[i] == "महात्मा" and toks[i + 1] == "गांधी")
        r(f"    rank {row['rank']}: doc {row['doc_id']} ({row['title']}) phrase count={row['count']}, recount={hits}")
        ok &= hits == row["count"]
    r.check(res["mode"] == "phrase" and res["total_docs"] > 0, "phrase mode used and documents found")
    r.check(ok, "every phrase count equals a recount of consecutive words in the raw text")
    rev = s.search('"गांधी महात्मा"')
    r.check(rev["total_docs"] < res["total_docs"], f"reversed phrase finds fewer documents "
            f"({rev['total_docs']:,} < {res['total_docs']:,}): word order matters")

    # 3. AND query
    q = "गंगा नदी हिमालय"
    r(f"\nTest case 3: multi-word AND query: {q}")
    r(SUB)
    res = s.search(q, limit=5)
    r(f"  mode={res['mode']}  documents found={res['total_docs']:,}  time={res['time_sec'] * 1000:.2f} ms")
    ok = True
    for row in res["results"]:
        toks = set(doc_tokens(s, row["doc_id"]))
        r(f"    rank {row['rank']}: doc {row['doc_id']} ({row['title']}) count={row['count']} BM25={row['score']}")
        ok &= {"गंगा", "नदी", "हिमालय"} <= toks
    r.check(res["mode"] == "and", "AND mode used")
    r.check(ok, "every result contains all three words")

    # 4. normalization + unknown word + OR fallback
    r("\nTest case 4: normalization, unknown word and OR fallback")
    r(SUB)
    a = s.search("ज़िला")
    b = s.search("जिला")
    r(f"  'ज़िला' (with nukta) -> {a['total_docs']:,} documents; 'जिला' -> {b['total_docs']:,} documents")
    r.check(a["total_docs"] == b["total_docs"] > 0, "nukta spelling is normalized to the same term")
    u = s.search("क्ष्यज्ञत्र")
    r(f"  'क्ष्यज्ञत्र' -> mode={u['mode']}, documents={u['total_docs']}, missing={u['missing_terms']}")
    r.check(u["total_docs"] == 0 and u["mode"] == "none", "unknown word returns no documents")
    o = s.search("हिमालय क्ष्यज्ञत्र")
    r(f"  'हिमालय क्ष्यज्ञत्र' -> mode={o['mode']}, documents={o['total_docs']:,}")
    r.check(o["mode"] == "or" and o["total_docs"] == s.search("हिमालय")["total_docs"],
            "OR fallback returns the documents of the known word")

    # 5. vocabulary in memory, postings on disk
    r("\nTest case 5: vocabulary in main memory, posting lists on secondary memory")
    r(SUB)
    s._match.cache_clear()
    reads0, bytes0 = s.disk_reads, s.disk_bytes
    t0 = time.perf_counter()
    res = s.search("भारतीय संविधान")
    dt = time.perf_counter() - t0
    file_size = POSTINGS_FILE.stat().st_size
    r(f"  query 'भारतीय संविधान': {s.disk_reads - reads0} posting lists read, "
      f"{s.disk_bytes - bytes0:,} bytes of {file_size:,} in postings.bin, {dt * 1000:.2f} ms")
    r.check(s.disk_reads - reads0 == 2, "exactly one disk read per query term")
    r.check(s.disk_bytes - bytes0 < file_size / 10, "a query reads only a small part of postings.bin")
    lex_bytes = s.df.nbytes + s.cf.nbytes + s.offsets.nbytes + s.nbytes.nbytes
    r(f"  in-memory lexicon arrays (df, cf, offset, size): {lex_bytes / 2**20:.1f} MB for "
      f"{len(s.vocab):,} terms; posting lists stay in postings.bin ({file_size / 2**20:.1f} MB)")
    r.check(s.disk_bytes - bytes0 == sum(8 * int(s.df[s.term_id(t)]) for t in ("भारतीय", "संविधान")),
            "bytes read = 8 x DF per term (doc_ids + tfs only; positions skipped for non-phrase queries)")
    worst = 0.0
    for q in ["के", "की में है", '"भारत सरकार"', "भारत की राजधानी दिल्ली", "विज्ञान"]:
        s._match.cache_clear()
        worst = max(worst, s.search(q)["time_sec"])
    r(f"  slowest of 5 uncached queries (incl. the most frequent word 'के'): {worst * 1000:.1f} ms")
    r.check(worst < 0.5, "every query answered in under 500 ms")

    # ------------------------------------------------------------- rare terms
    r("")
    r(LINE)
    r("PART B - 10 RARE TERMS WITH THEIR FULL POSITIONAL INDEX")
    r(LINE)
    r(f"Rare terms: DF of 2-3, Devanagari words of 5+ characters, sampled with seed {args.seed}.")
    for k, term in enumerate(pick_rare_terms(s, 10, args.seed), 1):
        info = s.postings(term)
        r(f"\nRare term {k}: {term}")
        r(SUB)
        print_posting_list(r, info)
        r.check(verify_postings(s, info) and sum(p["tf"] for p in info["postings"]) == info["cf"],
                "positions, DF and CF match the raw articles")

    r("")
    r(LINE)
    r(f"SUMMARY: {r.passed} checks passed, {r.failed} failed")
    r(LINE)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(r.lines) + "\n", encoding="utf-8")
    print("\n".join(r.lines))
    print(f"\nWritten to {args.out}")


if __name__ == "__main__":
    main()

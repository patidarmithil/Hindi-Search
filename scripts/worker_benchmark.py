"""Compare index build time and search latency for different worker counts.

Builds the index with 1, 5 and 8 to 12 worker processes (each run rebuilds
index/), then loads it and times the same fixed set of queries. Shows that
the worker count changes only how fast the index is built: the index and the
search results are identical, and search latency does not depend on it.

Usage:  python scripts/worker_benchmark.py [--workers 1 5 8 9 10] [--repeat 2]
"""
import argparse
import hashlib
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.indexer import build_index  # noqa: E402
from engine.searcher import Searcher  # noqa: E402

QUERIES = [
    "बाजार", "शेयर बाजार", "रिजर्व बैंक", "सोने की कीमत", "मुद्रास्फीति",
    "के", "में", "सरकार कंपनी निवेश", "विदेशी मुद्रा भंडार", "किसान",
    "जीएसटी", "पेट्रोल डीजल", "आर्थिक वृद्धि", "कच्चा तेल", "बजट",
]


def search_run(searcher: Searcher) -> tuple[list[float], str]:
    """Uncached latency (ms) per query plus a fingerprint of all results."""
    searcher._match.cache_clear()
    digest = hashlib.sha256()
    times = []
    for q in QUERIES:
        t0 = time.perf_counter()
        res = searcher.search(q, limit=None)
        times.append((time.perf_counter() - t0) * 1000)
        digest.update(repr([(r["doc_id"], r["count"]) for r in res["results"]]).encode())
    return times, digest.hexdigest()[:12]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, nargs="+", default=[1, 5, 8, 9, 10, 11, 12])
    ap.add_argument("--repeat", type=int, default=3, help="builds per worker count (best is reported)")
    args = ap.parse_args()

    rows = []
    for w in args.workers:
        builds = [build_index(workers=w, verbose=False) for _ in range(args.repeat)]
        best = min(builds, key=lambda s: s["build_time_sec"])
        searcher = Searcher().load()
        # Best of 5 rounds per query, so background noise does not skew it.
        rounds = [search_run(searcher) for _ in range(5)]
        times = [min(r[0][i] for r in rounds) for i in range(len(QUERIES))]
        fingerprint = rounds[0][1]
        rows.append((w, best, times, fingerprint, len(searcher.postings)))
        print(f"workers={w:2}  tokenize+merge {best['index_time_sec']:6.2f} s  "
              f"total build {best['build_time_sec']:6.2f} s  "
              f"search avg {statistics.mean(times):6.2f} ms  max {max(times):6.2f} ms  "
              f"results {fingerprint}")

    base = rows[0][1]["build_time_sec"]
    print("\n| Workers | Index build | Speed-up vs 1 | Search avg | Search max | Terms | Results |")
    print("|---|---|---|---|---|---|---|")
    for w, s, times, fp, vocab in rows:
        print(f"| {w} | {s['build_time_sec']:.2f} s | {base / s['build_time_sec']:.1f}x | "
              f"{statistics.mean(times):.2f} ms | {max(times):.2f} ms | {vocab:,} | `{fp}` |")
    same = len({r[3] for r in rows}) == 1
    print(f"\nAll runs return identical results: {'yes' if same else 'NO'}")


if __name__ == "__main__":
    main()

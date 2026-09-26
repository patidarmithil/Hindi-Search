"""Latency benchmark for the search engine (target: every query < 500 ms).

Usage:  python scripts/benchmark.py [--n 200] [--seed 42]
"""
import argparse
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.searcher import Searcher  # noqa: E402

TARGET_MS = 500


def run(searcher: Searcher, queries: list[str]) -> list[float]:
    searcher._match.cache_clear()  # measure uncached (cold) latency
    times = []
    for q in queries:
        t0 = time.perf_counter()
        searcher.search(q, limit=50)
        times.append((time.perf_counter() - t0) * 1000)
    return times


def report(name: str, times: list[float]) -> bool:
    times_sorted = sorted(times)
    p95 = times_sorted[int(len(times_sorted) * 0.95) - 1]
    ok = max(times) < TARGET_MS
    print(f"{name:28} n={len(times):4}  avg {statistics.mean(times):7.3f} ms  "
          f"p50 {statistics.median(times):7.3f} ms  p95 {p95:7.3f} ms  "
          f"max {max(times):7.3f} ms  {'PASS' if ok else 'FAIL'}")
    return ok


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    s = Searcher().load()
    print(f"Index loaded in {s.load_time_sec:.2f} s  "
          f"({len(s.docs):,} docs, {len(s.vocab):,} terms)\n")

    by_df = sorted(s.vocab, key=lambda t: len(s.postings[t][0]), reverse=True)
    frequent = by_df[:50]  # longest posting lists = worst case
    rand_terms = rng.sample(s.vocab, args.n)

    suites = {
        "single random term": rand_terms,
        "single most frequent term": [rng.choice(frequent) for _ in range(args.n)],
        "2-word random": [" ".join(rng.sample(s.vocab, 2)) for _ in range(args.n)],
        "3-word frequent (AND)": [" ".join(rng.sample(frequent, 3)) for _ in range(args.n)],
        "5-word frequent (AND)": [" ".join(rng.sample(frequent, 5)) for _ in range(args.n)],
        "unknown word": ["क्ष्यज्ञ" + str(i) for i in range(args.n)],
    }
    all_ok = all(report(name, run(s, qs)) for name, qs in suites.items())

    # cached path: same query repeated
    s.search("शेयर बाजार")
    t0 = time.perf_counter()
    s.search("शेयर बाजार")
    print(f"\ncached repeat query: {(time.perf_counter() - t0) * 1000:.3f} ms")
    print(f"\nOverall: {'ALL PASS' if all_ok else 'SOME FAILED'} (< {TARGET_MS} ms)")


if __name__ == "__main__":
    main()

"""Corpus sanity scan of the extracted Wikipedia JSONL: articles, size, token/vocabulary stats.

Usage:  python scripts/scan_corpus.py [--limit N]
"""
import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.config import CORPUS_FILE  # noqa: E402
from engine.tokenizer import is_stopword, tokenize  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="scan only the first N articles")
    args = ap.parse_args()
    start = time.perf_counter()

    tokens_per_doc = []
    term_freq = Counter()
    with open(CORPUS_FILE, encoding="utf-8") as f:
        for n, line in enumerate(f):
            if args.limit and n >= args.limit:
                break
            art = json.loads(line)
            tokens = tokenize(art["title"] + "\n" + art["text"])
            tokens_per_doc.append(len(tokens))
            term_freq.update(tokens)

    n = len(tokens_per_doc)
    print(f"Articles            : {n:,}")
    print(f"Corpus file size    : {CORPUS_FILE.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"Total tokens        : {sum(tokens_per_doc):,}")
    print(f"Vocabulary size     : {len(term_freq):,}")
    if n:
        print(f"Tokens per article  : min {min(tokens_per_doc)}, "
              f"avg {sum(tokens_per_doc) / n:.0f}, max {max(tokens_per_doc)}")
    print(f"Scan time           : {time.perf_counter() - start:.1f} s")

    print("\nTop 20 terms (all):")
    print("  " + ", ".join(f"{t}({c})" for t, c in term_freq.most_common(20)))
    content = [(t, c) for t, c in term_freq.most_common(500)
               if not is_stopword(t) and not t.isdigit() and len(t) > 1][:20]
    print("\nTop 20 content terms (no stopwords):")
    print("  " + ", ".join(f"{t}({c})" for t, c in content))


if __name__ == "__main__":
    main()

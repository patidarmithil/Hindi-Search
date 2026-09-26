"""Corpus sanity scan: file count, size, encoding errors, token/vocabulary stats.

Usage:  python scripts/scan_corpus.py
"""
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.config import DATA_DIR, FILE_ENCODING  # noqa: E402
from engine.tokenizer import is_stopword, tokenize  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    start = time.perf_counter()

    files = sorted(DATA_DIR.glob("*.txt"))
    total_bytes = 0
    bad_files = []
    empty_files = []
    tokens_per_doc = []
    term_freq = Counter()

    for path in files:
        raw = path.read_bytes()
        total_bytes += len(raw)
        try:
            text = raw.decode(FILE_ENCODING)
        except UnicodeDecodeError:
            bad_files.append(path.name)
            text = raw.decode(FILE_ENCODING, errors="replace")
        tokens = tokenize(text)
        if not tokens:
            empty_files.append(path.name)
        tokens_per_doc.append(len(tokens))
        term_freq.update(tokens)

    elapsed = time.perf_counter() - start
    n = len(files)
    print(f"Files               : {n}")
    print(f"Total size          : {total_bytes / 1024 / 1024:.1f} MB")
    print(f"Encoding errors     : {len(bad_files)} {bad_files[:5]}")
    print(f"Files with no tokens: {len(empty_files)} {empty_files[:5]}")
    print(f"Total tokens        : {sum(tokens_per_doc):,}")
    print(f"Vocabulary size     : {len(term_freq):,}")
    if n:
        print(f"Tokens per doc      : min {min(tokens_per_doc)}, "
              f"avg {sum(tokens_per_doc) / n:.0f}, max {max(tokens_per_doc)}")
    print(f"Scan time           : {elapsed:.1f} s")

    print("\nTop 20 terms (all):")
    print("  " + ", ".join(f"{t}({c})" for t, c in term_freq.most_common(20)))
    content = [(t, c) for t, c in term_freq.most_common(500)
               if not is_stopword(t) and not t.isdigit() and len(t) > 1][:20]
    print("\nTop 20 content terms (no stopwords):")
    print("  " + ", ".join(f"{t}({c})" for t, c in content))


if __name__ == "__main__":
    main()

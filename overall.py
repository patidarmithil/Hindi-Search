"""Run the whole assignment with one command.

Usage:
    python overall.py                 everything: setup, data, tests, output, sample searches
    python overall.py --skip-tests    same, without the unit tests
    python overall.py --from-dump     build the corpus and index from the Wikipedia dump
                                      instead of downloading the prebuilt ones

Steps:
    1. Check Python (3.10+) and install the missing packages from requirements.txt.
    2. Download the prebuilt index and corpus from the GitHub release (data-v1),
       only the parts that are not already on disk.
    3. Run the unit tests.
    4. Generate output/test_cases.txt (5 test cases + 10 rare terms, every
       posting checked against the raw article text).
    5. Run sample searches through cli.py and save them to output/search_results.txt.
    6. Print a summary.

Everything printed to the terminal is also written to output/run_log.txt.
"""
import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"
INDEX_FILES = ["postings.bin", "lexicon.tsv", "docs.json", "stats.json", "suggestions.json"]
CORPUS_FILE = ROOT / "corpus" / "hiwiki_articles.jsonl"
DUMP_NAME = "hiwiki-latest-pages-articles.xml.bz2"
DUMP_URL = "https://dumps.wikimedia.org/hiwiki/latest/" + DUMP_NAME
ENGINE_PACKAGES =["numpy", "orjson"]  # what the engine, cli and scripts import

# (label, cli.py arguments) for step 5
SAMPLE_SEARCHES = [
    ("Single word, ranked by BM25", ["भारत", "--top", "10"]),
    ("AND query: every word must be in the document", ["गंगा नदी हिमालय", "--top", "10"]),
    ("Phrase query: words next to each other, found with positions", ['"महात्मा गांधी"', "--top", "10"]),
    ("Normalization: nukta spelling matches the plain spelling", ["ज़िला", "--top", "5"]),
    ("Unknown word plus a known word: OR fallback", ["हिमालय क्ष्यज्ञत्र", "--top", "5"]),
    ("Positional posting list of one term (DF, CF, positions)", ["--index", "गंगा", "--top", "5"]),
]

LINE = "=" * 90


class Tee:
    """Print to the terminal and keep a copy for output/run_log.txt."""

    def __init__(self):
        self.lines: list[str] = []

    def __call__(self, text: str = "") -> None:
        print(text, flush=True)
        self.lines.append(text)


log = Tee()


def step(n: int, title: str) -> None:
    log("")
    log(LINE)
    log(f"STEP {n}: {title}")
    log(LINE)


def run(args: list[str], capture: list[str] | None = None) -> int:
    """Run a Python command from the project root, streaming its output line by line."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(
        [sys.executable, *args], cwd=ROOT, env=env, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
    )
    for line in proc.stdout:
        line = line.rstrip("\n")
        log(line)
        if capture is not None:
            capture.append(line)
    return proc.wait()


def missing_packages() -> list[str]:
    return [p for p in ENGINE_PACKAGES if importlib.util.find_spec(p) is None]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-tests", action="store_true", help="do not run the unit tests")
    ap.add_argument("--from-dump", action="store_true",
                    help="build corpus and index from the Wikipedia dump instead of downloading them")
    args = ap.parse_args()
    t_start = time.perf_counter()
    results: dict[str, str] = {}

    log(LINE)
    log("Hindi Wikipedia positional index: full run")
    log(LINE)

    # 1 ---------------------------------------------------------------- setup
    step(1, "Python and packages")
    log(f"Python {sys.version.split()[0]} at {sys.executable}")
    if sys.version_info < (3, 10):
        log("Python 3.10 or newer is required.")
        return 1
    missing = missing_packages()
    if missing:
        log(f"Installing missing packages: {', '.join(missing)}")
        if run(["-m", "pip", "install", "-r", "requirements.txt"]) != 0 or missing_packages():
            log("Package installation failed. Run: python -m pip install -r requirements.txt")
            return 1
    log("Packages OK: " + ", ".join(ENGINE_PACKAGES))
    results["Setup"] = "OK"

    # 2 ----------------------------------------------------------------- data
    step(2, "Corpus and positional index")
    need_index = [f for f in INDEX_FILES if not (ROOT / "index" / f).exists()]
    need_corpus = not CORPUS_FILE.exists()
    if args.from_dump:
        if need_corpus:
            dump = ROOT / "wiki_raw" / DUMP_NAME
            if not dump.exists():
                log(f"Downloading the Hindi Wikipedia dump (about 242 MB) from {DUMP_URL}")
                dump.parent.mkdir(exist_ok=True)
                with urllib.request.urlopen(DUMP_URL) as resp, open(dump, "wb") as out:
                    shutil.copyfileobj(resp, out, length=1 << 20)
            log("Extracting articles from the Wikipedia dump ...")
            if run(["-m", "engine.wiki_extractor"]) != 0:
                return 1
        log("Building the positional index ...")
        if run(["-m", "engine.indexer"]) != 0:
            return 1
        results["Data"] = "built from the dump"
    elif not need_index and not need_corpus:
        log("index/ and corpus/ already present, nothing to download.")
        results["Data"] = "already present"
    else:
        if need_index:
            log(f"index/ is missing {', '.join(need_index)}: downloading hiwiki-index.zip (about 162 MB)")
            if run(["scripts/fetch_data.py", "--only", "index"]) != 0:
                log("Download failed. Check the internet connection, or use --from-dump.")
                return 1
        if need_corpus:
            log("corpus/hiwiki_articles.jsonl is missing: downloading hiwiki-corpus.zip (about 147 MB)")
            if run(["scripts/fetch_data.py", "--only", "corpus"]) != 0:
                log("Download failed. Check the internet connection, or use --from-dump.")
                return 1
        results["Data"] = "downloaded from the GitHub release"
    for f in INDEX_FILES:
        p = ROOT / "index" / f
        log(f"  index/{f:<18} {p.stat().st_size / 2**20:9.1f} MB")
    log(f"  corpus/{CORPUS_FILE.name:<17} {CORPUS_FILE.stat().st_size / 2**20:9.1f} MB")

    # 3 ---------------------------------------------------------------- tests
    if args.skip_tests:
        results["Unit tests"] = "skipped"
    else:
        step(3, "Unit tests")
        tests = ["-m", "unittest", "discover", "-s", "tests", "-t", "."]
        if importlib.util.find_spec("fastapi") is None:  # website API tests need the backend packages
            tests = ["-m", "unittest", "tests.test_tokenizer", "tests.test_searcher", "tests.test_cli"]
        rc = run(tests)
        results["Unit tests"] = "passed" if rc == 0 else "FAILED"

    # 4 --------------------------------------------------------------- output
    step(4, "Test cases and rare terms: output/test_cases.txt")
    out_lines: list[str] = []
    rc = run(["scripts/generate_output.py"], capture=out_lines)
    summary = next((l for l in reversed(out_lines) if l.startswith("SUMMARY")), "")
    results["output/test_cases.txt"] = summary.replace("SUMMARY: ", "") if rc == 0 else "FAILED"

    # 5 ------------------------------------------------------------- searches
    step(5, "Sample searches: output/search_results.txt")
    searches: list[str] = []
    ok = True
    for label, cli_args in SAMPLE_SEARCHES:
        header = f"\n--- {label}\n$ python cli.py {' '.join(cli_args)}"
        log(header)
        searches.append(header)
        ok &= run(["cli.py", *cli_args, "--no-color"], capture=searches) == 0
    OUTPUT.mkdir(exist_ok=True)
    (OUTPUT / "search_results.txt").write_text("\n".join(searches).lstrip() + "\n", encoding="utf-8")
    results["output/search_results.txt"] = f"{len(SAMPLE_SEARCHES)} searches" if ok else "FAILED"

    # 6 -------------------------------------------------------------- summary
    step(6, "Summary")
    for k, v in results.items():
        log(f"  {k:<28} {v}")
    log(f"  {'Total time':<28} {time.perf_counter() - t_start:.1f} s")
    log("")
    log("Files written:")
    for name in ("test_cases.txt", "search_results.txt", "run_log.txt"):
        log(f"  output/{name}")
    log("")
    log('Search yourself: python cli.py   (or python cli.py "भारत की राजधानी")')
    (OUTPUT / "run_log.txt").write_text("\n".join(log.lines) + "\n", encoding="utf-8")

    failed = any(v == "FAILED" for v in results.values()) or " 0 failed" not in summary
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

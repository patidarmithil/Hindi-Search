"""Download the prebuilt index and the extracted corpus from the GitHub release.

Usage:  python scripts/fetch_data.py [--only index|corpus] [--base URL]

Downloads and unzips into the project root:
    hiwiki-index.zip   -> index/   (postings.bin, lexicon.tsv, docs.json, ...)
    hiwiki-corpus.zip  -> corpus/  (hiwiki_articles.jsonl)

Used by the deployed server (Render build command) so it does not have to
download the 242 MB Wikipedia dump and rebuild the index itself.
"""
import argparse
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://github.com/patidarmithil/Hindi-Search/releases/download/data-v1/"
FILES = {"index": "hiwiki-index.zip", "corpus": "hiwiki-corpus.zip"}


def fetch(name: str, base: str) -> None:
    url = base + name
    dest = ROOT / name
    print(f"Downloading {url}")
    with urllib.request.urlopen(url) as resp, open(dest, "wb") as out:
        shutil.copyfileobj(resp, out, length=1 << 20)
    print(f"  {dest.stat().st_size / 2**20:.1f} MB, extracting ...")
    with zipfile.ZipFile(dest) as z:
        for member in z.namelist():  # only extract inside the project folders
            if member.startswith(("index/", "corpus/")) and ".." not in member:
                z.extract(member, ROOT)
    dest.unlink()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=list(FILES))
    ap.add_argument("--base", default=BASE, help="release download URL ending in /")
    args = ap.parse_args()
    for key, name in FILES.items():
        if args.only in (None, key):
            fetch(name, args.base)
    print("Done.")


if __name__ == "__main__":
    sys.exit(main())

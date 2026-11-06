"""Shared paths and constants for the search engine."""
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

# Raw input: Hindi Wikipedia dump (one XML file with every article).
# https://dumps.wikimedia.org/hiwiki/latest/hiwiki-latest-pages-articles.xml.bz2
WIKI_DIR = ROOT_DIR / "wiki_raw"
WIKI_DUMP = WIKI_DIR / "hiwiki-latest-pages-articles.xml.bz2"

# Cleaned corpus: one JSON article per line (built by engine.wiki_extractor).
DATA_DIR = ROOT_DIR / "corpus"
CORPUS_FILE = DATA_DIR / "hiwiki_articles.jsonl"

# Positional index (built by engine.indexer).
INDEX_DIR = ROOT_DIR / "index"
POSTINGS_FILE = INDEX_DIR / "postings.bin"    # all posting lists (secondary memory)
LEXICON_FILE = INDEX_DIR / "lexicon.tsv"      # vocabulary: term, df, cf, offset, bytes
DOCS_FILE = INDEX_DIR / "docs.json"           # doc_id -> title, url, length, corpus offset
SUGGESTIONS_FILE = INDEX_DIR / "suggestions.json"
STATS_FILE = INDEX_DIR / "stats.json"

FILE_ENCODING = "utf-8"

"""Shared paths and constants for the search engine."""
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "Data"
INDEX_DIR = ROOT_DIR / "index"

POSTINGS_FILE = INDEX_DIR / "postings.bin"
DOCS_FILE = INDEX_DIR / "docs.json"
SUGGESTIONS_FILE = INDEX_DIR / "suggestions.json"
STATS_FILE = INDEX_DIR / "stats.json"

FILE_ENCODING = "utf-8"

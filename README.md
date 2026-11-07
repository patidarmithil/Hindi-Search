# खोज — Positional Index for Hindi Wikipedia

**Assignment A1: Positional Index (IR, M2026)** · Roll No. **S20240010143**

A positional inverted index over **all of Hindi Wikipedia: 129,601 articles and 50.7 million words**. For every term the index stores its **document frequency (DF)**, its **collection frequency (CF)** and the **position of every occurrence** in every document. The **vocabulary is kept in main memory**; the **posting lists are stored on secondary memory** (`index/postings.bin`, 317 MB on disk). Each query reads only its own terms' posting lists from disk.

| Link | |
|---|---|
| Live website | **https://hindi-search.vercel.app/** |
| Source code | https://github.com/patidarmithil/Hindi-Search |
| Dataset (original download) | https://dumps.wikimedia.org/hiwiki/latest/hiwiki-latest-pages-articles.xml.bz2 |
| Extracted corpus + built index | https://github.com/patidarmithil/Hindi-Search/releases/tag/data-v1 (`hiwiki-corpus.zip`, `hiwiki-index.zip`) |

### Run everything with one command

```bash
python overall.py
```

From the project root (Python 3.10+), this one command does the whole run ([details in section 4](#run-everything-overallpy)):

- It installs missing packages.
- It downloads the corpus and index if they are not already on disk.
- It runs the unit tests.
- It writes `output/test_cases.txt`.
- It runs sample searches and prints a summary.

---

## Contents

1. [Assignment checklist](#1-assignment-checklist)
2. [Dataset](#2-dataset)
3. [The positional index](#3-the-positional-index)
4. [How to run](#4-how-to-run)
5. [Modules](#5-modules)
6. [Output: 5 test cases and 10 rare terms](#6-output-5-test-cases-and-10-rare-terms)
7. [Searching with the index](#7-searching-with-the-index)
8. [Performance](#8-performance)
9. [Website](#9-website)
10. [Project structure](#10-project-structure)

---

## 1. Assignment checklist

| Requirement | Done | Where |
|---|---|---|
| (a) Indian-language dataset: a wiki dump, one XML file with every article | Yes | Hindi Wikipedia dump, 242 MB `.xml.bz2` ([section 2](#2-dataset)) |
| (c) Positional index: term positions in the postings | Yes | `engine/indexer.py`, `index/postings.bin` |
| (c) Collection Frequency and Document Frequency per term | Yes | `index/lexicon.tsv` (`term df cf offset bytes`) |
| (d) Vocabulary in main memory | Yes | `engine/searcher.py` loads `lexicon.tsv` into sorted arrays |
| (d) Entire postings list on secondary memory | Yes | `index/postings.bin`; one seek and read per term per query |
| README: how to run, description of every module | Yes | this file |
| Source code in one zip | Yes | `S20240010143-src.zip` |
| Output: 5 test cases, 10 rare terms with their positional index | Yes | `output/test_cases.txt` (26 checks, all pass) |
| Full data and index as a link, not uploaded | Yes | GitHub release `data-v1` |

Extras: phrase search ("महात्मा गांधी") using positions, BM25 ranking, AND search with OR fallback, Hindi normalization (nukta, zero-width characters), parallel index building, a terminal search tool, 42 unit tests for the engine, and a live website.

---

## 2. Dataset

| | |
|---|---|
| Source | Hindi Wikipedia XML dump from Wikimedia: one XML file containing every article |
| Download | https://dumps.wikimedia.org/hiwiki/latest/hiwiki-latest-pages-articles.xml.bz2 |
| Dump used | dated 1 Nov 2026, 242 MB compressed |
| Pages in the dump | 176,041 main-namespace pages that are not redirects |
| Articles kept | **129,601** (pages with at least 200 characters of text after cleaning) |
| Extracted text | 696 MB (`corpus/hiwiki_articles.jsonl`) |
| Tokens | 50,713,481 (avg 391 per article) |
| Vocabulary | 1,017,007 distinct terms |

**Why Wikipedia and not FIRE:** the FIRE Hindi collections can only be obtained by signing a user agreement with the FIRE organisers, so they cannot be downloaded from a public link. The Hindi Wikipedia dump is public, and it is the "single XML file containing all wiki articles" the assignment names.

`engine/wiki_extractor.py` streams the compressed dump with `bz2` and `xml.etree.iterparse`, so memory stays small. It keeps main-namespace (`ns 0`) pages that are not redirects and converts MediaWiki markup to plain text:

- removes templates and infoboxes `{{...}}`, tables `{| ... |}`, `<ref>` citations, comments, `<math>` and similar tags;
- turns links `[[target|label]]` into `label` and drops file, category and interlanguage links;
- drops external URLs, bold/italic quotes, heading `=` signs and list markers.

Each article is written as one JSON line: `{"id", "wiki_id", "title", "url", "text"}`.

---

## 3. The positional index

### Tokenization (`engine/tokenizer.py`)

The same function is used for documents and queries, so they always agree.

| Step | Why |
|---|---|
| Unicode NFC normalization | the same letter can be stored in different byte forms |
| Remove the nukta (`़`): `ज़िला` → `जिला` | Wikipedia spells many words both ways |
| Remove zero-width characters (ZWJ, ZWNJ, BOM) | invisible characters would split words |
| Lowercase Latin letters | `GDP` = `gdp` |
| Split into Devanagari words, Latin words and numbers | drops `।`, `॥`, punctuation and quotes |

Stopwords are kept, because a positional index must know where every word is (phrase queries such as "भारत की राजधानी" need `की`). A word's **position** is its 0-based index among the article's tokens; the title comes first, so position 0 is the first word of the title.

### What is stored

For every term:

```
term -> DF, CF : doc_1 (tf_1): <p1, p2, ...>,  doc_2 (tf_2): <p1, ...>,  ...
```

- **DF** (document frequency): number of documents that contain the term.
- **CF** (collection frequency): total occurrences in the whole collection, the sum of all tf.
- **tf**: occurrences in one document, the length of its position list.

Example from the real index (`output/test_cases.txt`):

```
इंटीग्रिन -> 2, 4:
    doc   26333 (कोलेजन), tf=1: <1920>
    doc  120836 (मॉर्फोजेनेसिस), tf=3: <1081, 1096, 1131>
```

### Files (`index/`)

| File | Memory | Content |
|---|---|---|
| `postings.bin` (317 MB) | **disk** | every posting list, one binary record per term |
| `lexicon.tsv` (37 MB) | **main memory** | vocabulary: `term  df  cf  offset  bytes`, sorted by term |
| `docs.json` (10 MB) | main memory | per document: title, Wikipedia page id, length, byte offset in the corpus |
| `stats.json` | main memory | corpus and build statistics |
| `suggestions.json` | main memory | suggested words and sample queries for the UI |

### Record layout of one term in `postings.bin`

All integers are little-endian.

```
doc_ids    uint32 x DF   ascending document ids
tfs        uint32 x DF   term frequency in each document
pos_offs   uint32 x DF   where each document's positions start inside `positions`
positions  bytes         per document: tf positions, gap-encoded
                         (first position, then differences), variable-byte code
```

- **Gap + variable-byte encoding** makes the position lists small: most gaps fit in 1 byte instead of 4 (7 bits per byte, the high bit means "more bytes follow").
- **The fixed-width part first.** A normal word query reads only `8 x DF` bytes (doc_ids + tfs) with one disk read, with no decoding. Positions are read only for phrase queries and index lookups.
- **`pos_offs`** lets the lookup tool jump to one document's positions without decoding the others.

### Vocabulary in main memory, postings on disk

At start-up `Searcher.load()` reads `lexicon.tsv` into a sorted Python list of terms plus four NumPy arrays (`df`, `cf`, `offset`, `bytes`): about 31 MB of arrays for 1,017,007 terms. A lookup is a binary search of the sorted vocabulary (`bisect`, O(log V)), which gives the term's byte offset. The searcher then does `seek(offset)` and `read(bytes)` on the open `postings.bin`. No posting list is kept in memory, apart from the last 1,024 query results in an LRU cache. Test case 5 in the output checks this: a query for `भारतीय संविधान` reads 2 records and 278 KB out of the 332 MB file.

### Building the index (`engine/indexer.py`)

1. The corpus is read line by line, and each line's byte offset is recorded so an article can be fetched later with one seek.
2. **10 worker processes** (`multiprocessing.Pool`) tokenize articles in parallel. For each article a worker returns `term -> (tf, gap-encoded positions)`.
3. Results come back in document order (`imap`), so every posting list is appended already sorted by doc_id and never needs sorting.
4. The vocabulary is sorted and every record is written to `postings.bin`, with one `lexicon.tsv` line (term, DF, CF, offset, size) per term.

Build time on the development machine (Intel i5-12500H, 16 threads): **59 s** for 129,601 articles. Extracting the dump takes about 4 minutes.

---

## 4. How to run

Requirements: **Python 3.10+** (tested on 3.13) and the packages in `requirements.txt` (`numpy` for the engine; `fastapi`, `uvicorn`, `orjson` only for the website server). Run every command from the project root.

### Run everything (`overall.py`)

```bash
python overall.py
```

`overall.py` runs these steps one after another and prints everything to the terminal:

| Step | What happens |
|---|---|
| 1. Setup | Checks Python 3.10+ and installs `requirements.txt` if `numpy` or `orjson` is missing. |
| 2. Data | Downloads `hiwiki-index.zip` (162 MB) and `hiwiki-corpus.zip` (147 MB) from the GitHub release and unzips them into `index/` and `corpus/`. It downloads only the parts that are missing, so a second run downloads nothing. |
| 3. Tests | Runs the unit tests (`python -m unittest`). |
| 4. Output | Runs `scripts/generate_output.py`, which writes `output/test_cases.txt` (5 test cases and 10 rare terms, 26 checks). |
| 5. Searches | Runs six sample searches through `cli.py`: a single word, an AND query, a phrase query, normalization, OR fallback and one posting list. Their results go to `output/search_results.txt`. |
| 6. Summary | Prints pass or fail for each step and the total time. The whole terminal output is also saved to `output/run_log.txt`. |

Options: `python overall.py --skip-tests` skips step 3, and `python overall.py --from-dump` downloads the Wikipedia dump and builds the corpus and index locally instead (Option A below). The first run takes about 2 minutes plus the download time; later runs take about 35 seconds. The script exits with code 0 only if every step passes.

The steps can also be run one at a time:

```bash
python -m pip install -r requirements.txt
```

**Option A: build everything from the original dump (about 6 minutes)**

1. Download the dump (242 MB) into `wiki_raw/`:
   ```bash
   curl -L -o wiki_raw/hiwiki-latest-pages-articles.xml.bz2 https://dumps.wikimedia.org/hiwiki/latest/hiwiki-latest-pages-articles.xml.bz2
   ```
2. Extract plain-text articles into `corpus/hiwiki_articles.jsonl`:
   ```bash
   python -m engine.wiki_extractor
   ```
3. Build the positional index into `index/`:
   ```bash
   python -m engine.indexer
   ```

`wiki_extractor` and `indexer` both accept `--limit N` to try the pipeline on the first N articles.

**Option B: download the ready-made corpus and index**

```bash
python scripts/fetch_data.py
```

This downloads `hiwiki-corpus.zip` and `hiwiki-index.zip` from the GitHub release and unzips them into `corpus/` and `index/`.

**Use the index**

| Command | What it does |
|---|---|
| `python cli.py --index गंगा` | positional posting list of a term: DF, CF, positions per document (`--top N` for N documents) |
| `python cli.py "गंगा नदी"` | AND search, ranked by BM25 |
| `python cli.py "\"महात्मा गांधी\""` | phrase search using positions |
| `python cli.py --show 42 --query गंगा` | print article 42 with the matches highlighted |
| `python cli.py` | interactive mode: type queries; `:index <term>`, `:open <rank>`, `:top N`, `:help`, `:q` |
| `python scripts/generate_output.py` | regenerate `output/test_cases.txt` (5 test cases + 10 rare terms) |
| `python -m unittest discover -s tests -t .` | run the tests (42 engine tests; the repository adds 9 website API tests) |
| `python scripts/benchmark.py` | query-latency benchmark |

---

## 5. Modules

| Module | Description |
|---|---|
| `overall.py` | One-command runner: checks packages, downloads only the missing data, runs the tests, writes `output/test_cases.txt` and `output/search_results.txt`, prints a summary and saves the log to `output/run_log.txt`. |
| `engine/config.py` | All paths: dump, corpus, index files. |
| `engine/wiki_extractor.py` | Streams the `.xml.bz2` dump, keeps main-namespace non-redirect pages, removes wiki markup (`clean_wikitext`), writes one JSON article per line. |
| `engine/tokenizer.py` | `normalize()` (NFC, nukta folding, zero-width removal, lowercase) and `tokenize()` (regex split into Devanagari, Latin and number tokens). The stopword list is used only for suggestions. |
| `engine/indexer.py` | Builds the positional index in parallel. `encode_gaps` / `decode_gaps` implement the gap + variable-byte code. Writes `postings.bin`, `lexicon.tsv`, `docs.json`, `stats.json`, `suggestions.json`. |
| `engine/searcher.py` | Loads the vocabulary into memory and reads posting lists from disk (`read_postings`). `postings(term)` returns the full positional list with DF and CF. `search()` handles AND / OR / phrase queries with BM25 ranking; `_phrase()` matches consecutive positions; `get_document()` reads one article and returns highlight offsets; `autocomplete()` finds prefix matches in the sorted vocabulary. |
| `cli.py` | Terminal interface: index lookup (`--index`), search, phrase search, document view with highlights. |
| `scripts/generate_output.py` | Produces `output/test_cases.txt`. Every value printed is checked against the raw article text. |
| `scripts/benchmark.py` | Latency of 700 uncached queries in 7 groups (rare, frequent, AND, phrase, unknown). |
| `scripts/worker_benchmark.py` | Index build time with different numbers of worker processes. |
| `scripts/scan_corpus.py` | Corpus statistics (articles, tokens, vocabulary, top terms). |
| `scripts/fetch_data.py` | Downloads the prebuilt corpus and index from the GitHub release. |
| `scripts/make_submission.py` | Builds the submission zips (`<roll>-src.zip` and `<roll>-A1-PostIndex-IR-M2026.zip`). |
| `tests/` | 42 engine unit tests: codec round trip, query parsing, highlighting, positions / DF / CF checked against raw text, sorted postings, phrase counts, AND / OR, disk reads, latency, CLI. The GitHub repository also has `test_api.py`, 9 tests for the website server. |
| `backend/`, `frontend/` | Website: FastAPI server and React app. Not part of the submission zip; see [section 9](#9-website). |

---

## 6. Output: 5 test cases and 10 rare terms

`output/test_cases.txt` is produced by `python scripts/generate_output.py`. Every posting printed is read from `postings.bin` through the in-memory vocabulary, and then recomputed independently by tokenizing the raw article. **26 of 26 checks pass.**

| # | Test case | What it checks |
|---|---|---|
| 1 | Positional list of `भारत` (DF 53,226, CF 127,753) | positions match the raw text; DF = list length; CF = sum of tf; doc_ids sorted |
| 2 | Phrase `"महात्मा गांधी"` (885 documents) | every phrase count equals a recount in the raw text; the reversed phrase finds only 9 documents |
| 3 | AND query `गंगा नदी हिमालय` (206 documents) | every result contains all three words |
| 4 | `ज़िला` vs `जिला`, an unknown word, OR fallback | nukta normalization; unknown word gives 0 results; OR returns the known word's documents |
| 5 | Vocabulary in memory, postings on disk | one disk read per term; only 8 x DF bytes read for a word query; every query under 500 ms |

**10 rare terms** (DF 2–3, sampled with a fixed seed), each with its full positional index, for example:

```
Rare term 3: उदयराम
  Term: उदयराम    DF = 3    CF = 11    (postings.bin offset 53,963,565, 51 bytes)
  उदयराम -> 3, 11:
      doc   15399 (गुजराती साहित्य), tf=1: <2130>
      doc   26231 (डिंगल), tf=7: <1232, 1237, 1291, 1296, 1354, 1357, 1373>
      doc   29763 (सालासर बालाजी), tf=3: <330, 337, 762>
  [PASS] positions, DF and CF match the raw articles
```

---

## 7. Searching with the index

| Query | Mode | How |
|---|---|---|
| `गंगा` | single | one posting list read from disk |
| `गंगा नदी` | AND | sorted doc_id arrays intersected, rarest term first |
| `"महात्मा गांधी"` | phrase | positions: the phrase starts at p when term k occurs at p + k |
| `गंगा क्ष्यज्ञ` | OR fallback | if no document has every term, or a term is unknown |

- **Phrase matching.** Each occurrence becomes a global position (document start + position) and term k is shifted back by k. The positions shared by all terms are the phrase starts. This is done with NumPy over a boolean array, and only for documents that contain every term.
- **Ranking: BM25** (k1 = 1.2, b = 0.75) with IDF from DF and document lengths from `docs.json`. Each result also shows its count of matching words.
- **Highlighting.** `get_document()` returns character offsets of matches in the raw text. A phrase is highlighted only where its words are consecutive.

---

## 8. Performance

`python scripts/benchmark.py --n 100`: uncached queries, cache cleared before each group.

| Query type | Average | p95 | Max |
|---|---|---|---|
| Single random word | 0.13 ms | 0.37 ms | 2.3 ms |
| Single most frequent word (`के`, `में`: ~100k documents) | 4.2 ms | 18 ms | 39 ms |
| 3 frequent words (AND) | 13.6 ms | 22 ms | 27 ms |
| 5 frequent words (AND) | 14.4 ms | 22 ms | 30 ms |
| 2-word phrase of frequent words (worst case: `"में के"`, 4 million positions) | 85 ms | 175 ms | 375 ms |
| Unknown word | 1.1 ms | 2.5 ms | 5.4 ms |
| Repeated query (LRU cache) | 0.27 ms | | |

Every query is answered in under 500 ms. Loading the vocabulary takes about 1.5 s, and the process then uses about 205 MB of RAM.

---

## 9. Website

**https://hindi-search.vercel.app/** has everything on this page in a browser, so the index can be tried without installing anything:

- search with a Hindi on-screen keyboard and word suggestions (autocomplete from the vocabulary, ranked by DF);
- AND, OR and phrase search over all 129,601 articles, ranked by BM25, with time taken and documents found;
- a **"Positional index of your words"** panel showing DF, CF, byte offset and per-document positions for every query word, read live from `postings.bin`;
- the full article with matches highlighted (previous / next match) and a link to the page on Wikipedia.

The free server sleeps when idle, so the first visit can take up to a minute while it starts and loads the vocabulary. The website code (`backend/`, `frontend/`) is in the GitHub repository and is not part of the submission zip.

Running it locally (after building or fetching the index):

```bash
cd frontend && npm install && npm run build && cd ..
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Then open http://127.0.0.1:8000. Deployment: the API runs on Render (build command `pip install -r requirements.txt && python scripts/fetch_data.py`, start command `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`), and the site runs on Vercel (root `frontend`, `npm run build`, output `dist`).

---

## 10. Project structure

```
Hindi-Search/
├── engine/
│   ├── config.py            paths
│   ├── wiki_extractor.py    XML dump -> plain-text JSONL
│   ├── tokenizer.py         normalization + tokenization
│   ├── indexer.py           builds the positional index (parallel)
│   └── searcher.py          vocabulary in memory, postings from disk, search
├── overall.py               runs everything: data download, tests, output, sample searches
├── cli.py                   terminal interface
├── scripts/                 generate_output, benchmark, worker_benchmark, scan_corpus, fetch_data, make_submission
├── tests/                   unit tests
├── output/                  test_cases.txt (5 test cases + 10 rare terms); overall.py adds search_results.txt, run_log.txt
├── wiki_raw/                downloaded dump (not in git)
├── corpus/                  hiwiki_articles.jsonl (not in git; GitHub release)
├── index/                   postings.bin, lexicon.tsv, ... (not in git; GitHub release)
├── backend/                 FastAPI server for the website
├── frontend/                React website
└── requirements.txt
```

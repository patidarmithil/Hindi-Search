# Hindi Document Search Engine — Implementation Plan

IR assignment: retrieve Hindi words from a corpus of 16,000 Hindi `.txt` documents using an **inverted index (posting lists)**, with results in **under 500 ms**. Two interfaces share one search engine: a **website** (React + FastAPI) and a **terminal CLI**.

## Corpus facts (checked)

- Location: `Data/`
- Count: 16,000 files, named `Economy (1).txt` … `Economy (16000).txt`
- Size: ~80 MB total, average ~5 KB per file (min ~1.5 KB, max ~28 KB), so the full index fits comfortably in RAM
- Encoding: UTF-8, Devanagari Hindi news articles (headline + body), with punctuation such as `।`, `‘ ’`, `( )`, and nukta letters (`ज़`, `फ़`)

## Target project layout

```
IR/
├── Data/                      # 16k raw .txt files (input, never modified)
├── engine/                    # shared search core (used by CLI + API)
│   ├── tokenizer.py           # Unicode normalization + Hindi tokenization
│   ├── indexer.py             # builds inverted index from Data/
│   ├── searcher.py            # loads index, answers queries
│   └── config.py              # paths, constants
├── index/                     # generated artifacts (gitignored)
│   ├── postings.bin           # term -> posting list
│   ├── docs.json              # doc_id -> filename, length
│   └── suggestions.json       # top terms / sample queries
├── backend/
│   └── main.py                # FastAPI app
├── frontend/                  # Vite + React app
├── cli.py                     # terminal interface
├── requirements.txt
├── README.md
├── how_to_run.md
├── Phase.md
└── progress.md
```

## Core design (how <500 ms is reached)

1. **Build once, query many.** Indexing (the slow part: reading 16k files) runs offline once. Queries never touch raw files except to open one document for the popup.
2. **Inverted index in memory.** `dict[term] -> posting list`. Term lookup is an O(1) hash lookup.
3. **Posting list format.** Each posting is `(doc_id, term_frequency)`. Lists are stored **sorted by doc_id** so multi-word AND queries use a linear two-pointer merge, starting from the shortest list.
4. **Integer doc IDs.** Filenames map to compact ints `0..15999`; postings store ints only. Filenames are resolved only for the result page.
5. **Normalization at index and query time is identical.** NFC normalization, nukta folding (`ज़`→`ज`), strip ZWJ/ZWNJ, remove punctuation (`।`, quotes, digits optional), lowercase for any Latin text. Guarantees the query token matches the indexed token.
6. **Fast persistence.** Index serialized with `pickle` (protocol 5) or `msgpack`; loaded once at server/CLI startup (~1–2 s), then every query is pure in-memory work.
7. **Result shaping.** Sort by frequency (tf, or summed tf for multi-word), return total count plus a page (e.g. top 50), so response size stays small.
8. **Query cache.** `functools.lru_cache` on normalized query string for repeated searches.
9. **Timing.** `time.perf_counter()` around the search call; reported in seconds to the UI and CLI.

## Phase 1 — Setup, corpus analysis, tokenizer

**Goal:** project skeleton and a correct Hindi tokenizer.

- Create folders `engine/`, `backend/`, `frontend/`, `index/`; add `requirements.txt` (`fastapi`, `uvicorn`, `orjson`, `msgpack` optional) and `.gitignore` (`index/`, `node_modules/`, `__pycache__/`).
- Corpus scan script: count files, total size, check encoding errors, sample token counts.
- `engine/tokenizer.py`:
  - `normalize(text)`: NFC, nukta folding, remove ZWJ/ZWNJ, lowercase Latin.
  - `tokenize(text)`: regex over Devanagari range `ऀ-ॿ` plus Latin/digits; drop punctuation and `।`.
  - Optional `STOPWORDS` set (है, के, में, की, और, से, को …) used only for suggestions, **not** removed from the index (so users can still search them).
- Unit tests: `ज़्यादा` and `ज्यादा` normalize to the same token; `‘ट्रैवलर्स` yields `ट्रैवलर्स`.

**Done when:** tokenizer passes tests and produces clean tokens on 10 sample files.

## Phase 2 — Inverted index build + search core

**Goal:** posting-list index on disk and a search function under 500 ms.

- `engine/indexer.py`:
  - Walk `Data/`, sort filenames by numeric part, assign `doc_id`.
  - For each doc: tokenize, count tf with `collections.Counter`, append `(doc_id, tf)` to `postings[term]`.
  - Because docs are processed in doc_id order, posting lists are already sorted — no extra sort.
  - Save `postings`, `docs` (filename, token count), and stats (vocab size, total tokens, build time).
  - Optional speed-up: `multiprocessing.Pool` for tokenizing, merge in order.
- `engine/searcher.py`:
  - `Searcher.load()` reads index once.
  - `search(query)`: normalize + tokenize query → fetch posting lists → single term: direct list; multi-term: AND intersection (shortest-first merge) with OR fallback if AND is empty → sort by tf desc → return `{total_docs, results[{doc_id, filename, count}], time_sec}`.
  - `get_document(doc_id)`: read raw file for popup.
  - `suggest(prefix)`: binary search (`bisect`) on sorted vocabulary for autocomplete.
- Generate `suggestions.json`: top ~30 frequent non-stopword terms and ~10 sample queries.
- Benchmark script: 100 random vocabulary terms + multi-word queries, report p50/p95/max latency.

**Done when:** index builds without errors and benchmark p95 < 500 ms (expected: a few ms).

## Phase 3 — Terminal CLI

**Goal:** run search fully from terminal.

- `cli.py`:
  - On start: load index (build it automatically if `index/` missing), print corpus stats (docs indexed, vocab size, load time).
  - Loop: prompt `खोज / Search >` for a query; `:q` or `exit` to quit.
  - Output: query, total documents found, total documents searched (16,000), time taken in seconds, then a table: rank, filename, count.
  - Flags: `--top N` (default all or 20), `--show <doc>` to print a document with the term highlighted (ANSI yellow).
- Ensure UTF-8 console output on Windows (`sys.stdout.reconfigure(encoding="utf-8")`, note about Windows Terminal font).

**Done when:** `python cli.py` runs interactive search and prints the full list with timing.

## Phase 4 — FastAPI backend

**Goal:** HTTP API over the same engine.

- `backend/main.py`:
  - Load `Searcher` once in the FastAPI `lifespan` startup.
  - `GET /api/search?q=&page=&size=` → total docs, results page, time taken.
  - `GET /api/document/{doc_id}` → filename + full text (frontend highlights).
  - `GET /api/suggestions` → suggested words and queries.
  - `GET /api/autocomplete?prefix=` → vocabulary prefix matches.
  - `GET /api/stats` → docs count, vocab size, index build info.
  - CORS for the Vite dev server; `ORJSONResponse` for fast JSON; gzip middleware.
  - Optionally serve the built frontend (`frontend/dist`) as static files for single-command deployment.
- Test with `curl`/Swagger (`/docs`); measure server-side time vs. network time.

**Done when:** all endpoints return correct JSON and `/api/search` responds in < 500 ms end to end locally.

## Phase 5 — React frontend (classic, aesthetic UI)

**Goal:** website built with Vite + React, designed using the `frontend-design` skill.

- Layout: centered title, search bar, suggestion chips, results area, footer with corpus stats.
- **Search bar:** Hindi input, Enter/button to search, debounced autocomplete dropdown.
- **Virtual Hindi keyboard:** opens on search bar focus; rows for स्वर (vowels), व्यंजन (consonants), मात्राएँ (matras), `्` halant, `ं ँ ः`, digits `०-९`, space, backspace, close. Inserts at cursor position. Custom component, no heavy library.
- **Suggestions:** chips below search bar (from `/api/suggestions`), click = fill + search.
- **Results summary:** "N documents found in X.XXX seconds (searched 16,000 documents)".
- **Results table:** rank, document name, occurrence count; paginated or virtualized.
- **Document modal:** click row → fetch `/api/document/{id}` → show text with every occurrence of the query term(s) wrapped in `<mark>` (yellow). Highlight uses the same normalization rule as backend so nukta variants also highlight. Scroll to first match; close with Esc/overlay click.
- Loading, empty, and error states; responsive on mobile.

**Done when:** full flow works in browser: type/keyboard → search → results → popup with yellow highlights.

## Phase 6 — Optimization, testing, documentation, deployment prep

**Goal:** verify performance, write docs, prepare hosting.

- Performance pass: re-run benchmark; check index load time and memory; add LRU query cache if not yet; confirm < 500 ms for common, rare, and multi-word queries.
- Edge cases: empty query, non-Hindi input, unknown word, very frequent word (e.g. `के`), punctuation in query.
- `README.md`:
  1. Architecture (diagram: Data → tokenizer → indexer → index files → searcher → CLI / FastAPI → React).
  2. How search works: normalization, tokenization, inverted index, posting lists, intersection, ranking.
  3. Why it is fast (< 500 ms): offline indexing, in-memory hash lookup, doc_id-sorted postings, int IDs, caching, paging — with measured benchmark numbers.
  4. Tech stack: Python, FastAPI, Uvicorn, React, Vite, CSS.
  5. Live website link (placeholder until the user provides the name/domain).
- `how_to_run.md`: prerequisites, install, build index, run CLI, run backend, run frontend, open `localhost`, production build, and live site link.
- Deployment prep (after the user gives the website name): pick host, configure env/API base URL, deploy, update link in docs.

**Done when:** docs complete, benchmarks recorded, project ready to hand in / deploy.

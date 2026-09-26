# Progress

Tracks completion of each phase in [Phase.md](Phase.md). Updated at the end of every phase.

| Phase | Title | Status |
|-------|-------|--------|
| 0 | Planning | Done |
| 1 | Setup, corpus analysis, tokenizer | Done |
| 2 | Inverted index build + search core | Done |
| 3 | Terminal CLI | Done |
| 4 | FastAPI backend | Done |
| 5 | React frontend | Done |
| 6 | Optimization, testing, docs, deployment prep | Done (live link pending) |

## Phase 0 — Planning (Done, 2026-09-27)

- Checked corpus: 16,000 UTF-8 Hindi files in `Data/`, all named `Economy (N).txt`.
- Wrote 6-phase plan in `Phase.md`.
- Created this progress file.

## Phase 1 — Setup, corpus analysis, tokenizer (Done, 2026-09-27)

**Built**

- Folders: `engine/`, `backend/`, `frontend/`, `index/`, `scripts/`, `tests/`.
- `requirements.txt` (fastapi, uvicorn, orjson) and `.gitignore` (index artifacts, venv, node_modules, dist).
- `engine/config.py`: shared paths (`Data/`, `index/` files) and encoding.
- `engine/tokenizer.py`:
  - `normalize()`: NFC, nukta folding (`ज़`/`ज़` → `ज`), zero-width char removal, Latin lowercase.
  - `tokenize()`: regex tokens for Devanagari words, Latin words, and numbers; drops `।`, `॥`, quotes, brackets, commas, hyphens.
  - `STOPWORDS` set, used only for suggestions (stopwords remain searchable).
- `tests/test_tokenizer.py`: 13 unit tests, all passing (`python -m unittest discover -s tests -t .`).
- `scripts/scan_corpus.py`: corpus statistics scan.

**Corpus scan results**

| Metric | Value |
|---|---|
| Files | 16,000 |
| Total size | 80.1 MB |
| Encoding errors | 0 |
| Empty files | 0 |
| Total tokens | 6,074,611 |
| Vocabulary (unique terms) | 28,469 |
| Tokens per doc | min 107, avg 380, max 2,039 |
| Full scan time (single process) | 23.3 s |

Top content terms: भाषा, रुपये, सरकार, पार्टी, भारत, बाजार, दिल्ली, कंपनी.

**Notes for Phase 2**

- Many docs share a boilerplate footer (terms like दिप्रिंट, एजेंसी, फीड, कंटेंट, जिम्मेदार, न्यूज). These stay in the index but should be excluded from suggestion chips.
- The vocabulary is small (28k terms), so the whole index is small and loads quickly into memory.
- Tokenizing everything takes 23 s, so the index must be built once and saved; `multiprocessing` can cut the build time.

## Phase 2 — Inverted index build + search core (Done, 2026-09-27)

**Built**

- `engine/indexer.py` (`python -m engine.indexer`):
  - Sorts files numerically (`Economy (2)` before `Economy (10)`) and assigns integer `doc_id` 0–15999.
  - Tokenizes documents in parallel with `multiprocessing.Pool` (15 workers); ordered `imap` means posting lists are appended in ascending `doc_id` order and never need sorting.
  - Posting list per term: `(doc_ids: array('i'), tfs: array('i'))`.
  - Writes `index/postings.bin` (pickle), `docs.json` (file, title = first line, token count), `stats.json`, `suggestions.json`.
  - Suggestions: curated economy words (only those present in the index, ordered by document frequency) + sample queries that are verified to return results. Raw top-frequency terms were dominated by verbs, months and editor names, so the curated list reads better.
- `engine/searcher.py`:
  - `Searcher.load()` loads the index once (~0.1–0.2 s).
  - `search(query, offset, limit)`: tokenize → hash lookup → AND via two-pointer merge (shortest list first) → OR fallback (k-way `heapq.merge`) if AND is empty or a term is unknown → rank by total occurrence count → page.
  - Returns total documents found, total occurrences, documents searched, per-result count and title, missing terms, and time in seconds.
  - `lru_cache` (1024 entries) on the normalized term tuple.
  - `get_document(doc_id, query)`: raw text + highlight spans (character offsets in the raw text; nukta variants also match).
  - `autocomplete(prefix)`: `bisect` prefix range on the sorted vocabulary, ranked by document frequency.
- `tests/test_searcher.py`: merge logic, highlighting, counts verified against raw files, ranking, AND/OR, pagination, autocomplete, latency. All 27 tests pass.
- `scripts/benchmark.py`: uncached latency benchmark.

**Index build**

| Metric | Value |
|---|---|
| Build time | ~3.3 s (15 workers; single process scan was 23 s) |
| Vocabulary | 28,469 terms |
| Postings | 2,936,261 |
| Index file size | 24.0 MB |
| Index load time | 0.1–0.2 s |

**Benchmark (200 queries per suite, cache cleared)**

| Suite | avg | p95 | max |
|---|---|---|---|
| Single random term | 0.08 ms | 0.13 ms | 10.1 ms |
| Single most frequent term (longest lists) | 1.5 ms | 5.6 ms | 19.3 ms |
| 2-word random | 0.08 ms | 0.27 ms | 2.0 ms |
| 3-word frequent (AND) | 6.2 ms | 10.0 ms | 11.6 ms |
| 5-word frequent (AND) | 10.7 ms | 21.1 ms | 30.4 ms |
| Unknown word | 0.01 ms | 0.02 ms | 0.08 ms |
| Cached repeat | 0.2 ms | | |

Every query is far below the 500 ms target (worst case ~30 ms).

## Phase 3 — Terminal CLI (Done, 2026-09-27)

**Built**

- `cli.py`:
  - On start: loads the index (builds it automatically if `index/` is missing; `--rebuild` forces a rebuild) and prints documents indexed, vocabulary, postings and load time.
  - Interactive loop with prompt `खोज / Search >`; suggested words and sample queries are listed at start.
  - For every query prints: query, missing terms (if any), AND/OR note, documents found, documents searched (16,000), total occurrences, time taken in seconds, then the full ranked table (rank, doc id, count, file name, title). The summary line is repeated after long lists.
  - Commands: `:open <rank>` (print that result with every match highlighted black-on-yellow), `:top <N|all>`, `:suggest`, `:help`, `:q` / `exit` (Ctrl+C / Ctrl+D also quit).
  - One-shot mode: `python cli.py "शेयर बाजार" [--top N]`.
  - `--show <doc id | file name> --query <words>`: print a document with highlights and exit.
  - Windows: UTF-8 stdout/stdin, ANSI colours turned on through the console API; `--no-color` (or piped output) uses `[[word]]` markers instead.
- `tests/test_cli.py`: document lookup, summary and full list output, highlight markers. All 30 tests pass.

**Sample run**

| Query | Documents found | Search time |
|---|---|---|
| शेयर बाजार (AND) | 1,993 | 0.0027 s |
| मुद्रास्फीति | 686 | 0.0010 s |
| सोने की कीमत (AND) | 325 | 0.0018 s |
| बाजार क्ष्यज्ञ (OR fallback) | 5,275 | 0.0144 s |
| क्ष्यज्ञ (unknown) | 0 | 0.00004 s |

Startup (index load) takes about 0.12–0.15 s.

## Phase 4 — FastAPI backend (Done, 2026-09-27)

**Built**

- `backend/main.py` (`uvicorn backend.main:app --reload`):
  - The index is loaded once in the FastAPI `lifespan` hook (built automatically if missing); requests never touch the disk except to read one document for the popup.
  - `GET /api/search?q=&page=&size=`: ranked page (size 1–100, default 20) with `total_docs`, `total_occurrences`, `docs_searched`, `time_sec`, `mode` (single / and / or), `missing_terms`, `page`, `pages`.
  - `GET /api/document/{doc_id}?q=`: file name, title, full text and highlight spans (character offsets) for the query; 404 for an unknown id.
  - `GET /api/suggestions`, `GET /api/autocomplete?prefix=&limit=`, `GET /api/stats`, `GET /api/health`.
  - Input validation: query 1–200 characters, page ≥ 1, size ≤ 100 (422 otherwise).
  - `ORJSONResponse` (fast JSON), gzip for responses over 1 KB, CORS for the Vite dev server (`CORS_ORIGINS` env var to override), `Server-Timing` header with total server time.
  - Serves `frontend/dist` at `/` when it exists, so one process runs the whole site.
- `tests/test_api.py`: 7 endpoint tests (paging, validation, empty results, document, 404, suggestions, autocomplete, gzip). All 37 tests pass.

**HTTP latency (real uvicorn server, 20 requests per query)**

| Query | Documents | Avg round trip | Max (after first) |
|---|---|---|---|
| के में है की को | 15,421 | 10.6 ms | 74.5 ms (first, uncached) |
| मुद्रास्फीति | 686 | 4.7 ms | 6.7 ms |
| सरकार | 6,107 | 5.5 ms | 14.2 ms |
| सोने की कीमत | 325 | 5.7 ms | 9.1 ms |
| बाजार क्ष्यज्ञ | 5,275 | 6.8 ms | 14.1 ms |

Document popup request: ~7 ms.

**Note:** on Windows, `http://localhost:8000` adds ~2 s to the first request because `localhost` resolves to IPv6 `::1` first and uvicorn listens on IPv4. Use `http://127.0.0.1:8000` (the Vite proxy in Phase 5 will point there).

## Phase 5 — React frontend (Done, 2026-09-27)

**Design:** an Indian account-book (bahi-khata) page. Indigo ink on white paper, blue ruled result rows, a red double margin rule down the left, and a yellow marker for matches. Hindi text in Tiro Devanagari Hindi (classic serif), interface text in Hind. Occurrence counts sit in a right-hand column like ledger amounts. Light and dark themes follow the system setting.

**Built** (`frontend/`, React 19 + Vite 8)

- `src/App.jsx`: page shell, search state, pagination (25 per page), URL sync (`?q=&page=`, so searches can be shared and back/forward work), index stats footer.
- `src/components/SearchBar.jsx`: search line, debounced autocomplete (120 ms, arrow keys + Enter), keyboard toggle button.
- `src/components/HindiKeyboard.jsx`: opens when the search box is clicked; vowels, vowel signs (shown on ◌), consonants incl. क्ष त्र ज्ञ श्र ड़ ढ़, space, backspace, clear, hide, search. Inserts at the caret without taking focus from the input; closes on outside click or Esc.
- `src/components/Suggestions.jsx`: sample-query chips and common-word chips (with document frequency); one click runs the search.
- `src/components/ResultsTable.jsx`: "N documents found in X seconds", documents searched, total occurrences, page round-trip time, missing-word and any-word notices, ranked rows (rank, title, file name, count), pager, empty state.
- `src/components/DocumentModal.jsx`: native `<dialog>` popup with the full document, every match in yellow `<mark>`, the current match outlined, "Match i of n" with previous/next buttons, scroll to first match, Esc / backdrop click / close button to exit.
- `vite.config.js`: dev server on 127.0.0.1:5173 with `/api` proxied to uvicorn on 127.0.0.1:8000.
- `npm run build` output (`frontend/dist`) is served by FastAPI at `/`, so production is a single process.

**Checked in the browser**

- Keyboard typing, autocomplete, suggestion chips, results page for शेयर बाजार (1,993 documents, 0.0044 s search, 22 ms page load), popup with 31 highlighted matches including nukta variants (बाज़ार), Esc closes the popup.
- 375 px mobile width: no horizontal scroll, keyboard wraps, compact header.
- Dark theme, no console errors.
- Production bundle: 234 KB JS (74 KB gzip), 9 KB CSS.

## Phase 6 — Optimization, testing, docs, deployment prep (Done, 2026-09-27; live link pending)

**Performance pass**

- Index rebuilt: 3.6 s total (15 workers), 24.0 MB file, loads in 0.1–0.2 s, uses about 63 MB of RAM.
- Benchmark re-run (1,200 uncached queries): every suite passes; worst case 42.9 ms (5 frequent words, AND), typical search < 1 ms, cached repeat 0.18 ms.
- The LRU query cache from Phase 2 stays; no further optimization was needed given the ~10x margin under 500 ms.

**Edge cases checked** (all handled, all well under 1 ms except `के` at ~18 ms)

| Query | Result |
|---|---|
| empty, spaces only, `!!!` | 0 documents, no error |
| `market`, `GDP` (Latin) | 0 documents (corpus is Hindi) |
| `बाजार,।!`, `‘बाजार’`, `बाज़ार` | same 5,275 documents as `बाजार` |
| `के` (most frequent word) | 16,000 documents |
| `123`, `२०२३` | 0 documents (the source articles contain no digits) |
| `क्ष्यज्ञ` (unknown) | 0 documents |

- `tests/test_searcher.py`: 2 new tests (edge-case queries, most frequent word). All 39 tests pass.

**Documentation**

- `README.md`: features mapped to requirements, architecture diagram (Mermaid), normalization and tokenization, inverted index layout and statistics, query processing (hash lookup, two-pointer AND, heap-merge OR fallback, ranking), highlighting, autocomplete, why it is fast (technique table), measured performance, tech stack, project structure, API reference, testing, corpus notes.
- `how_to_run.md`: prerequisites, install, build index, CLI (interactive, one-shot, `--show`, options), website (single server and dev mode), using the website, API docs, tests and benchmark, Docker deployment, environment variables, troubleshooting.

**Deployment prep**

- `Dockerfile` (two-stage: Node builds `frontend/dist`, Python image builds the index and runs Uvicorn on `$PORT`) and `.dockerignore`.
- Not built locally: the Docker daemon is not running on this machine.
- The live website link is a placeholder in `README.md` and `how_to_run.md` until the website name / host is decided.

## Open items

- Website name / domain for the live link: waiting on user.

## Post-phase fix: keyboard and word list layout

- Problem: with the Hindi keyboard open, the autocomplete list was positioned below the whole keyboard and was pushed off screen.
- Fix: when the keyboard is open, the word list is docked in its own column beside the keys (a "Matching words" panel); on narrow screens (container width < 620 px) it becomes a short scrolling strip above the keys. With the keyboard closed, the list is still a normal dropdown under the search line.
- Keyboard made more compact (group labels above the keys, 2.4 rem keys) so both fit in the 880 px page.
- Verified in the browser at 1280 px and 375 px (no horizontal overflow).
- Removed the Digits group from the Hindi keyboard: the source articles contain no numbers, so digit keys could never find anything.

## Deployment prep (GitHub + Render)

- Removed `Dockerfile` and `.dockerignore`; deployment is now GitHub + Render without Docker.
- Added `.python-version` (3.13.7), `.gitattributes` (keep `Data/` bytes unchanged) and more `.gitignore` entries (`.claude/`, `.env`, logs).
- `how_to_run.md` section 7 lists the GitHub push commands and the exact Render settings for the backend Web Service and the frontend Static Site.

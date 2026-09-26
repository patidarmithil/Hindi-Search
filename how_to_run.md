# How to run

The project can be used from the **terminal (CLI)** or as a **website on localhost**. Both use the same search engine and the same index.

**Live website:** _coming soon (link will be added after deployment)_

---

## 1. Prerequisites

| Tool | Version | Needed for |
|---|---|---|
| Python | 3.10 or newer (tested on 3.13) | search engine, CLI, backend |
| Node.js | 18 or newer (tested on 24) with npm | website frontend only |

The 16,000 documents must be in the `Data/` folder in the project root (`Data/Economy (1).txt` ... `Data/Economy (16000).txt`).

All commands below are run from the **project root** (the folder containing `cli.py`) unless stated otherwise.

---

## 2. Install

```bash
python -m pip install -r requirements.txt
```

This installs FastAPI, Uvicorn and orjson. The CLI itself only needs the Python standard library.

Optional: use a virtual environment first.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux
```

---

## 3. Build the index (once)

```bash
python -m engine.indexer
```

Takes about 4 seconds and writes `index/postings.bin`, `docs.json`, `stats.json` and `suggestions.json`.

Both the CLI and the backend build the index automatically if it is missing, so this step is optional. Run it again if the files in `Data/` change.

---

## 4. Run in the terminal (CLI)

### Interactive mode

```bash
python cli.py
```

Type a Hindi word or phrase at the `खोज / Search >` prompt and press Enter. For every query the CLI prints:

- documents found
- documents searched (16,000)
- total occurrences
- time taken in seconds
- the full ranked list: rank, doc id, number of occurrences, file name, title

Commands at the prompt:

| Command | What it does |
|---|---|
| `:open <rank>` | print that result's document with the search words highlighted |
| `:top <N>` or `:top all` | print only the top N results, or all of them (default: all) |
| `:suggest` | list suggested words and sample searches |
| `:help` | list commands |
| `:q` or `exit` | quit (Ctrl+C also works) |

### One-shot mode

```bash
python cli.py "शेयर बाजार"
```

```bash
python cli.py "मुद्रास्फीति" --top 20
```

### Show one document with highlights

```bash
python cli.py --show "Economy (43)" --query बाजार
```

`--show` accepts a doc id (as printed in the results) or a file name.

### Other options

| Option | Meaning |
|---|---|
| `--top N` | print only the top N results (0 = all, the default) |
| `--rebuild` | rebuild the index before starting |
| `--no-color` | plain output; matches are shown as `[[word]]` |

**Windows tip:** use Windows Terminal (default on Windows 11) so Hindi text renders correctly. The CLI switches the console to UTF-8 by itself. If you pipe the output to a file, it is written as UTF-8.

---

## 5. Run the website on localhost

There are two ways. Option A is the simplest.

### Option A: one server (recommended)

Build the frontend once, then FastAPI serves both the API and the website.

```bash
cd frontend
npm install
npm run build
cd ..
```

```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000** in the browser.

### Option B: development mode (live reload)

Use two terminals.

Terminal 1, backend (from the project root):

```bash
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal 2, frontend:

```bash
cd frontend
npm install
npm run dev
```

Open **http://127.0.0.1:5173**. The Vite dev server forwards `/api` requests to the backend on port 8000. Code changes reload automatically.

### Using the website

1. Click the search bar: the Hindi keyboard opens below it, with the matching words listed in a column beside the keys (above them on phones). Type with the on-screen keys or your own keyboard. The keyboard button next to the search bar shows or hides it.
2. Pick a word from the autocomplete list, or click a suggested search or word below the search bar.
3. Press **Search** or Enter. The summary shows the number of documents found, the time taken in seconds and the number of documents searched; each row shows how many times the words appear in that document.
4. Click a row to read the document with every match highlighted in yellow. Use **Previous match** / **Next match** to move between matches; press Esc to close.

### API only

With the backend running, the interactive API documentation is at **http://127.0.0.1:8000/docs**. Example:

```bash
curl "http://127.0.0.1:8000/api/search?q=%E0%A4%AC%E0%A4%9C%E0%A4%9F&size=5"
```

---

## 6. Tests and benchmark

```bash
python -m unittest discover -s tests -t .
```

```bash
python scripts/benchmark.py
```

The benchmark runs 1,200 uncached queries of different kinds and reports average, p95 and maximum latency against the 500 ms target.

---

## 7. Deployment (GitHub + Render)

The backend (FastAPI) runs as a Render **Web Service** and the React app as a Render **Static Site**. Both deploy from the same GitHub repository and redeploy on every push.

### 7.1 Push to GitHub

Create an empty repository on GitHub (no README, no .gitignore, no licence, since the project already has them), then from the project root:

```bash
git init
git add .
git commit -m "Hindi search engine: inverted index, FastAPI backend, React frontend, CLI"
git branch -M main
git remote add origin https://github.com/<your-username>/<repo-name>.git
git push -u origin main
```

`.gitignore` keeps out `index/` (generated), `node_modules/`, `frontend/dist/`, caches and `.env`. The `Data/` folder (16,000 files, about 84 MB) **is** pushed, because the server builds the index from it.

### 7.2 Backend on Render (Web Service)

Render dashboard: **New > Web Service**, connect the GitHub repository.

| Setting | Value |
|---|---|
| Language | Python 3 |
| Branch | `main` |
| Root Directory | _(empty)_ |
| Build Command | `pip install -r requirements.txt && python -m engine.indexer` |
| Start Command | `uvicorn backend.main:app --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/api/health` |
| Instance type | Free is enough (the index uses about 63 MB of RAM) |

Environment variables:

| Key | Value |
|---|---|
| `PYTHON_VERSION` | `3.13.7` (also set by `.python-version`) |
| `CORS_ORIGINS` | the frontend URL from 7.3, e.g. `https://<frontend-name>.onrender.com` (no trailing slash) |

After deploying, check `https://<backend-name>.onrender.com/api/health` and `/docs`.

### 7.3 Frontend on Render (Static Site)

Render dashboard: **New > Static Site**, same repository.

| Setting | Value |
|---|---|
| Branch | `main` |
| Root Directory | `frontend` |
| Build Command | `npm ci && npm run build` |
| Publish Directory | `dist` |

Environment variable (read at build time):

| Key | Value |
|---|---|
| `VITE_API_BASE` | the backend URL, e.g. `https://<backend-name>.onrender.com` (no trailing slash) |
| `NODE_VERSION` | `22` |

If you change `VITE_API_BASE` later, trigger **Manual Deploy > Clear build cache & deploy** so the app is rebuilt with the new value.

### 7.4 Notes

- On the free plan the backend sleeps after 15 minutes without traffic; the first request after that takes about 30–60 s while it wakes up and loads the index. Later searches are fast again.
- The first build takes a few minutes; the index is rebuilt on every deploy from `Data/`.

Environment variables used by the project:

| Variable | Default | Meaning |
|---|---|---|
| `PORT` | set by Render | port Uvicorn listens on |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | comma-separated origins allowed to call the API |
| `VITE_API_BASE` | empty (same origin) | API URL baked into the frontend at build time |

---

## 8. Troubleshooting

| Problem | Fix |
|---|---|
| First request to `http://localhost:8000` takes ~2 s on Windows | use `http://127.0.0.1:8000`; `localhost` tries IPv6 first while Uvicorn listens on IPv4 |
| Website says "The search server is not responding" | start the backend (`uvicorn backend.main:app`) |
| Opening port 8000 shows `{"detail":"Not Found"}` | the frontend is not built; run `npm run build` in `frontend/` and restart Uvicorn, or use development mode |
| Hindi shows as boxes or `?` in the terminal | use Windows Terminal or another UTF-8 terminal with a Devanagari font |
| `ModuleNotFoundError: engine` | run the commands from the project root, not from a subfolder |
| Search returns nothing for numbers | numbers are not present in the source articles, so they cannot be found |

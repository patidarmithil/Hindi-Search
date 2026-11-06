"""HTTP API over the positional inverted index (vocabulary in memory, postings on disk).

Run (from the project root):
    uvicorn backend.main:app --reload            development
    uvicorn backend.main:app --host 0.0.0.0      production / LAN

Endpoints:
    GET /api/search?q=&page=1&size=20   ranked results page + totals + time taken
    GET /api/document/{doc_id}?q=       full text + highlight spans for q
    GET /api/suggestions                suggested words and sample queries
    GET /api/autocomplete?prefix=       vocabulary words starting with prefix
    GET /api/index/{term}?limit=        positional posting list of one term (df, cf, positions)
    GET /api/stats                      index / corpus statistics
    GET /api/health                     liveness check

If frontend/dist exists (npm run build), it is served at "/" so the whole
site runs from this one process.
"""
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import ORJSONResponse
from fastapi.staticfiles import StaticFiles

from engine.config import ROOT_DIR
from engine.indexer import build_index
from engine.searcher import Searcher

FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"
MAX_QUERY_CHARS = 200
MAX_PAGE_SIZE = 100

# Browsers allowed to call the API: the deployed frontend on Vercel and the
# local Vite dev server. Override with a comma-separated CORS_ORIGINS env var.
CORS_ORIGINS = os.environ.get(
    "CORS_ORIGINS",
    "https://hindi-search.vercel.app,http://localhost:5173,http://127.0.0.1:5173",
).split(",")
# Vercel preview deployments, e.g. https://hindi-search-git-main-<user>.vercel.app
CORS_ORIGIN_REGEX = os.environ.get(
    "CORS_ORIGIN_REGEX", r"https://hindi-search(-[a-z0-9-]+)?\.vercel\.app"
)

searcher = Searcher()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the vocabulary once; each request reads only its terms' postings from disk.
    if not Searcher.index_exists():
        print("Index not found, building it ...")
        build_index(verbose=True)
    searcher.load()
    print(f"Index loaded in {searcher.load_time_sec:.2f} s "
          f"({searcher.n_docs:,} documents, {len(searcher.vocab):,} terms)")
    yield


app = FastAPI(
    title="Hindi Search Engine",
    description="Positional inverted-index search over Hindi Wikipedia.",
    version="2.0.0",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in CORS_ORIGINS if o.strip()],
    allow_origin_regex=CORS_ORIGIN_REGEX or None,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.middleware("http")
async def server_timing(request: Request, call_next):
    """Expose total server-side time so the browser dev tools show it."""
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["Server-Timing"] = f"app;dur={(time.perf_counter() - start) * 1000:.2f}"
    return response


@app.get("/api/health")
def health():
    return {"status": "ok", "documents": searcher.n_docs}


@app.get("/api/search")
def search(
    q: str = Query(..., min_length=1, max_length=MAX_QUERY_CHARS, description="Hindi word(s)"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
):
    res = searcher.search(q, offset=(page - 1) * size, limit=size)
    total = res["total_docs"]
    res["page"] = page
    res["size"] = size
    res["pages"] = (total + size - 1) // size
    return res


@app.get("/api/document/{doc_id}")
def document(doc_id: int, q: str = Query("", max_length=MAX_QUERY_CHARS)):
    try:
        return searcher.get_document(doc_id, q)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")


@app.get("/api/suggestions")
def suggestions():
    return searcher.suggestions


@app.get("/api/autocomplete")
def autocomplete(
    prefix: str = Query(..., min_length=1, max_length=MAX_QUERY_CHARS),
    limit: int = Query(8, ge=1, le=20),
):
    return {"prefix": prefix, "matches": searcher.autocomplete(prefix, limit)}


@app.get("/api/index/{term}")
def positional_index(term: str, limit: int = Query(10, ge=1, le=100)):
    """Positional posting list of one term, read from postings.bin."""
    res = searcher.postings(term, max_docs=limit)
    if res is None:
        raise HTTPException(status_code=404, detail=f"'{term}' is not in the vocabulary")
    return res


@app.get("/api/stats")
def stats():
    return {**searcher.stats, "load_time_sec": round(searcher.load_time_sec, 3)}


# Serve the built React app last so /api/* routes take priority.
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")

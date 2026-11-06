import { useCallback, useEffect, useRef, useState } from "react";
import { api, nf } from "./api.js";
import SearchBar from "./components/SearchBar.jsx";
import Suggestions from "./components/Suggestions.jsx";
import ResultsTable from "./components/ResultsTable.jsx";
import DocumentModal from "./components/DocumentModal.jsx";
import EngineStatus from "./components/EngineStatus.jsx";

const PAGE_SIZE = 25;
const SHOW_ENGINE_AFTER_MS = 800; // a server that is already awake answers well before this
const ENGINE_DOWN_AFTER_MS = 90000;

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

function readUrl() {
  const p = new URLSearchParams(window.location.search);
  return { q: p.get("q") ?? "", page: Math.max(1, Number(p.get("page")) || 1) };
}

export default function App() {
  const initial = useRef(readUrl()).current;
  const [query, setQuery] = useState(initial.q);
  const [data, setData] = useState(null);
  const [roundTripMs, setRoundTripMs] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [slow, setSlow] = useState(false);
  const [suggestions, setSuggestions] = useState(null);
  const [stats, setStats] = useState(null);
  const [openRow, setOpenRow] = useState(null);
  const [engine, setEngine] = useState("waking");
  const [engineStart] = useState(() => Date.now());
  const [showEngine, setShowEngine] = useState(false);
  const ctrlRef = useRef(null);

  // Wait for the backend (it may be asleep), then load suggestions and stats.
  useEffect(() => {
    let stop = false;
    const showTimer = setTimeout(() => setShowEngine(true), SHOW_ENGINE_AFTER_MS);
    (async () => {
      while (!stop) {
        try {
          await api.health(AbortSignal.timeout(30000));
          break;
        } catch {
          if (Date.now() - engineStart > ENGINE_DOWN_AFTER_MS) setEngine("down");
          await wait(2000);
        }
      }
      if (stop) return;
      clearTimeout(showTimer);
      setEngine("ready");
      api.suggestions().then(setSuggestions).catch(() => {});
      api.stats().then(setStats).catch(() => {});
    })();
    return () => {
      stop = true;
      clearTimeout(showTimer);
    };
  }, [engineStart]);

  // Show 100 % briefly, fade the loading screen out, then remove it.
  useEffect(() => {
    if (engine !== "ready" || !showEngine) return;
    const id = setTimeout(() => setShowEngine(false), 1400);
    return () => clearTimeout(id);
  }, [engine, showEngine]);

  const runSearch = useCallback(async (q, page = 1, { push = true } = {}) => {
    q = q.trim();
    if (push) {
      const url = q ? `?q=${encodeURIComponent(q)}${page > 1 ? `&page=${page}` : ""}` : window.location.pathname;
      window.history.pushState(null, "", url);
    }
    ctrlRef.current?.abort();
    if (!q) {
      setData(null);
      setError(null);
      return;
    }
    const ctrl = (ctrlRef.current = new AbortController());
    setLoading(true);
    setError(null);
    const t0 = performance.now();
    // The free backend sleeps when idle; say so if the first answer is slow.
    const slowTimer = setTimeout(() => setSlow(true), 2500);
    try {
      const res = await api.search(q, page, PAGE_SIZE, ctrl.signal);
      setRoundTripMs(performance.now() - t0);
      setData(res);
      if (page > 1) document.querySelector(".results")?.scrollIntoView({ block: "start" });
    } catch (e) {
      if (e.name === "AbortError") return;
      setError(
        e.message === "Failed to fetch"
          ? "The search server is not responding. Try again in a minute. When running locally, start it with: uvicorn backend.main:app"
          : e.message,
      );
    } finally {
      clearTimeout(slowTimer);
      if (ctrlRef.current === ctrl) {
        setLoading(false);
        setSlow(false);
      }
    }
  }, []);

  // Run the search in the URL on load, and follow browser back/forward.
  useEffect(() => {
    if (initial.q) runSearch(initial.q, initial.page, { push: false });
    const onPop = () => {
      const { q, page } = readUrl();
      setQuery(q);
      runSearch(q, page, { push: false });
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, [initial, runSearch]);

  const pick = (q) => {
    setQuery(q);
    runSearch(q);
  };

  const hasResults = data !== null;

  return (
    <div className="page">
      <header className={`masthead${hasResults ? " is-compact" : ""}`}>
        <h1 className="wordmark">
          <a
            href="./"
            onClick={(e) => {
              e.preventDefault();
              setQuery("");
              runSearch("");
            }}
            lang="hi"
          >
            खोज
          </a>
        </h1>
        <p className="tagline">
          Search {stats ? nf.format(stats.documents) : "all"} Hindi Wikipedia articles with a positional index. Put
          words in quotes for a phrase, like <span lang="hi">"महात्मा गांधी"</span>.
        </p>
      </header>

      {showEngine && <EngineStatus state={engine} startedAt={engineStart} onSkip={() => setShowEngine(false)} />}

      <main>
        <SearchBar value={query} onChange={setQuery} onSubmit={(q) => runSearch(q)} autoFocus={!initial.q} />

        {!hasResults && <Suggestions data={suggestions} onPick={pick} />}

        {slow && !error && !showEngine && (
          <p className="notice" role="status">
            Waking up the search server. It sleeps when nobody is using it, so the first search can take up to a
            minute. Searches after that are instant.
          </p>
        )}

        {error && (
          <p className="notice notice-error" role="alert">
            {error}
          </p>
        )}

        {hasResults && (
          <ResultsTable
            data={data}
            roundTripMs={roundTripMs}
            loading={loading}
            onOpen={setOpenRow}
            onPage={(p) => runSearch(data.query, p)}
          />
        )}

        {hasResults && suggestions && (
          <details className="more-suggest">
            <summary>More searches to try</summary>
            <Suggestions data={suggestions} onPick={pick} />
          </details>
        )}
      </main>

      <footer className="foot">
        {stats && (
          <p>
            Positional index of {nf.format(stats.vocabulary)} words and {nf.format(stats.postings)} postings over{" "}
            {nf.format(stats.documents)} Hindi Wikipedia articles, built in {stats.build_time_sec} seconds. Vocabulary
            in memory, posting lists read from disk ({stats.postings_size_mb} MB).
          </p>
        )}
      </footer>

      {openRow && <DocumentModal row={openRow} query={data?.query ?? ""} onClose={() => setOpenRow(null)} />}
    </div>
  );
}

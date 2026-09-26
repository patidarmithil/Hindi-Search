import { useCallback, useEffect, useRef, useState } from "react";
import { api, nf } from "./api.js";
import SearchBar from "./components/SearchBar.jsx";
import Suggestions from "./components/Suggestions.jsx";
import ResultsTable from "./components/ResultsTable.jsx";
import DocumentModal from "./components/DocumentModal.jsx";

const PAGE_SIZE = 25;

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
  const [suggestions, setSuggestions] = useState(null);
  const [stats, setStats] = useState(null);
  const [openRow, setOpenRow] = useState(null);
  const ctrlRef = useRef(null);

  useEffect(() => {
    api.suggestions().then(setSuggestions).catch(() => {});
    api.stats().then(setStats).catch(() => {});
  }, []);

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
    try {
      const res = await api.search(q, page, PAGE_SIZE, ctrl.signal);
      setRoundTripMs(performance.now() - t0);
      setData(res);
      if (page > 1) document.querySelector(".results")?.scrollIntoView({ block: "start" });
    } catch (e) {
      if (e.name === "AbortError") return;
      setError(
        e.message === "Failed to fetch"
          ? "The search server is not responding. Start it with: uvicorn backend.main:app"
          : e.message,
      );
    } finally {
      if (ctrlRef.current === ctrl) setLoading(false);
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
          Search {stats ? nf.format(stats.documents) : "16,000"} Hindi economy news articles. Results show how many
          times your words appear in each document.
        </p>
      </header>

      <main>
        <SearchBar value={query} onChange={setQuery} onSubmit={(q) => runSearch(q)} autoFocus={!initial.q} />

        {!hasResults && <Suggestions data={suggestions} onPick={pick} />}

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
            Inverted index of {nf.format(stats.vocabulary)} words and {nf.format(stats.postings)} postings over{" "}
            {nf.format(stats.documents)} documents, built in {stats.build_time_sec} seconds.
          </p>
        )}
      </footer>

      {openRow && <DocumentModal row={openRow} query={data?.query ?? ""} onClose={() => setOpenRow(null)} />}
    </div>
  );
}

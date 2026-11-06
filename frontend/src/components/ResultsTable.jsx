import { formatSeconds, nf } from "../api.js";
import TermIndex from "./TermIndex.jsx";

export default function ResultsTable({ data, roundTripMs, onOpen, onPage, loading }) {
  const { results, total_docs, docs_searched, total_occurrences, time_sec, mode, missing_terms, page, pages, terms } =
    data;
  const phrases = data.phrases ?? [];
  const quoted = [...terms, ...phrases.map((p) => `"${p}"`)].join(" ");
  const indexTerms = [...new Set([...terms, ...phrases.flatMap((p) => p.split(" "))])];

  return (
    <section className={`results${loading ? " is-loading" : ""}`} aria-live="polite" aria-busy={loading}>
      <div className="summary">
        <p className="summary-main">
          <strong>{nf.format(total_docs)}</strong> {total_docs === 1 ? "document" : "documents"} found in{" "}
          <strong>{formatSeconds(time_sec)}</strong> seconds
        </p>
        <p className="summary-sub">
          Searched all {nf.format(docs_searched)} documents. {nf.format(total_occurrences)} total occurrences.
          {roundTripMs != null && <> Page loaded in {Math.round(roundTripMs)} ms.</>}
        </p>
        {missing_terms.length > 0 && (
          <p className="notice" lang="hi">
            Not found in any document: {missing_terms.join(", ")}
          </p>
        )}
        {mode === "or" && total_docs > 0 && (
          <p className="notice">No document contains every word, so documents with any of them are shown.</p>
        )}
        {phrases.length > 0 && mode !== "or" && total_docs > 0 && (
          <p className="summary-sub" lang="hi">
            Phrase match (words next to each other, found with term positions): {phrases.map((p) => `“${p}”`).join(", ")}
          </p>
        )}
      </div>

      {indexTerms.length > 0 && <TermIndex terms={indexTerms} />}

      {total_docs === 0 ? (
        <p className="empty">
          No document contains <span lang="hi">“{quoted || data.query}”</span>. Check the spelling, try a single word,
          or pick a suggestion above.
        </p>
      ) : (
        <>
          <div className="ledger" role="list">
            <div className="ledger-head" aria-hidden="true">
              <span>Rank</span>
              <span>Wikipedia article</span>
              <span className="num">Count</span>
            </div>
            {results.map((r) => (
              <button
                type="button"
                role="listitem"
                key={r.doc_id}
                className="ledger-row"
                onClick={() => onOpen(r)}
                aria-label={`${r.title}, ${r.count} occurrences. Open document`}
              >
                <span className="rank">{r.rank}</span>
                <span className="doc">
                  <span className="doc-title" lang="hi">
                    {r.title}
                  </span>
                  <span className="doc-file">
                    Doc {r.doc_id}
                    {typeof r.score === "number" && <> · BM25 score {r.score.toFixed(2)}</>}
                  </span>
                </span>
                <span className="num count">{nf.format(r.count)}</span>
              </button>
            ))}
          </div>

          {pages > 1 && (
            <nav className="pager" aria-label="Result pages">
              <button type="button" className="btn-quiet" disabled={page <= 1} onClick={() => onPage(page - 1)}>
                Previous
              </button>
              <span>
                Page {nf.format(page)} of {nf.format(pages)}
              </span>
              <button type="button" className="btn-quiet" disabled={page >= pages} onClick={() => onPage(page + 1)}>
                Next
              </button>
            </nav>
          )}
        </>
      )}
    </section>
  );
}

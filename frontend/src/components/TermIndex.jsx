import { useEffect, useState } from "react";
import { api, nf } from "../api.js";

const DOCS_SHOWN = 5;
const POSITIONS_SHOWN = 12;

/** Positional posting list (df, cf, doc -> positions) of each query word, read from the index on disk. */
export default function TermIndex({ terms }) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);
  const key = terms.join(" ");

  useEffect(() => {
    setRows(null);
    setError(null);
  }, [key]);

  useEffect(() => {
    if (!open || rows) return;
    const ctrl = new AbortController();
    Promise.all(
      terms.map((t) =>
        api.index(t, DOCS_SHOWN, ctrl.signal).catch((e) => (e.name === "AbortError" ? Promise.reject(e) : { term: t, missing: true })),
      ),
    )
      .then(setRows)
      .catch((e) => e.name !== "AbortError" && setError(e.message));
    return () => ctrl.abort();
  }, [open, rows, key]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <details className="term-index" onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>Positional index of your words (DF, CF, positions)</summary>
      {error && <p className="notice">Could not load the index: {error}</p>}
      {open && !rows && !error && <p className="loading-text">Reading posting lists…</p>}
      {rows?.map((r) =>
        r.missing ? (
          <p key={r.term} className="ti-missing" lang="hi">
            {r.term}: not in the vocabulary
          </p>
        ) : (
          <div key={r.term} className="ti-term">
            <p className="ti-head">
              <strong lang="hi">{r.term}</strong>
              <span>DF {nf.format(r.df)}</span>
              <span>CF {nf.format(r.cf)}</span>
              <span className="ti-dim">
                {nf.format(r.bytes)} bytes at offset {nf.format(r.offset)}
              </span>
            </p>
            <ul className="ti-list">
              {r.postings.map((p) => (
                <li key={p.doc_id}>
                  <span className="ti-doc" lang="hi">
                    {p.title}
                  </span>{" "}
                  <span className="ti-dim">
                    (doc {p.doc_id}, tf {p.tf})
                  </span>{" "}
                  <code>
                    [{p.positions.slice(0, POSITIONS_SHOWN).join(", ")}
                    {p.positions.length > POSITIONS_SHOWN ? `, … +${p.positions.length - POSITIONS_SHOWN}` : ""}]
                  </code>
                </li>
              ))}
            </ul>
            {r.shown < r.df && (
              <p className="ti-dim">
                First {r.shown} of {nf.format(r.df)} documents.
              </p>
            )}
          </div>
        ),
      )}
    </details>
  );
}

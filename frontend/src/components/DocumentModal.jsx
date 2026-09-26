import { useEffect, useMemo, useRef, useState } from "react";
import { api, nf } from "../api.js";

/**
 * The API returns highlight offsets in Unicode code points (Python str indices).
 * JS strings index UTF-16 units, which only differ when the text holds characters
 * outside the BMP (e.g. emoji), so convert only in that case.
 */
function toSegments(text, spans) {
  const hasAstral = /[\uD800-\uDFFF]/.test(text);
  const chars = hasAstral ? Array.from(text) : null;
  const slice = (a, b) => (chars ? chars.slice(a, b).join("") : text.slice(a, b));
  const len = chars ? chars.length : text.length;

  const out = [];
  let last = 0;
  spans.forEach(([s, e], i) => {
    if (s > last) out.push({ text: slice(last, s) });
    out.push({ text: slice(s, e), mark: i });
    last = e;
  });
  if (last < len) out.push({ text: slice(last, len) });
  return out;
}

export default function DocumentModal({ row, query, onClose }) {
  const dialogRef = useRef(null);
  const bodyRef = useRef(null);
  const [doc, setDoc] = useState(null);
  const [error, setError] = useState(null);
  const [current, setCurrent] = useState(0);

  useEffect(() => {
    dialogRef.current?.showModal();
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    setDoc(null);
    setError(null);
    setCurrent(0);
    api
      .document(row.doc_id, query, ctrl.signal)
      .then(setDoc)
      .catch((e) => e.name !== "AbortError" && setError(e.message));
    return () => ctrl.abort();
  }, [row.doc_id, query]);

  const segments = useMemo(() => (doc ? toSegments(doc.text, doc.highlights) : []), [doc]);
  const total = doc?.highlights.length ?? 0;

  // Scroll the current match into view (first match when the document loads).
  useEffect(() => {
    if (!total) return;
    const el = bodyRef.current?.querySelector(`[data-mark="${current}"]`);
    el?.scrollIntoView({ block: "center", behavior: current === 0 ? "auto" : "smooth" });
  }, [current, total]);

  const step = (d) => setCurrent((c) => (c + d + total) % total);

  return (
    <dialog
      ref={dialogRef}
      className="modal"
      aria-labelledby="modal-title"
      onClose={onClose}
      onClick={(e) => e.target === dialogRef.current && dialogRef.current.close()}
    >
      <div className="modal-card">
        <header className="modal-head">
          <div className="modal-heading">
            <h2 id="modal-title" lang="hi">
              {row.title || row.file}
            </h2>
            <p className="modal-meta">
              {row.file}, rank {row.rank}. The search words appear {nf.format(row.count)}{" "}
              {row.count === 1 ? "time" : "times"}.
            </p>
          </div>
          <button type="button" className="icon-btn" onClick={() => dialogRef.current.close()} aria-label="Close">
            <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
              <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
          </button>
        </header>

        {total > 0 && (
          <div className="modal-tools">
            <span>
              Match {current + 1} of {total}
            </span>
            <button type="button" className="btn-quiet" onClick={() => step(-1)}>
              Previous match
            </button>
            <button type="button" className="btn-quiet" onClick={() => step(1)}>
              Next match
            </button>
          </div>
        )}

        <div className="modal-body" ref={bodyRef} lang="hi" tabIndex={0}>
          {error && <p className="notice">Could not load the document: {error}</p>}
          {!doc && !error && <p className="loading-text">Loading document…</p>}
          {doc &&
            segments.map((seg, i) =>
              seg.mark === undefined ? (
                seg.text
              ) : (
                <mark key={i} data-mark={seg.mark} className={seg.mark === current ? "is-current" : undefined}>
                  {seg.text}
                </mark>
              ),
            )}
        </div>
      </div>
    </dialog>
  );
}

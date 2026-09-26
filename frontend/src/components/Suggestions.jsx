import { nf } from "../api.js";

export default function Suggestions({ data, onPick }) {
  if (!data) return null;
  return (
    <section className="suggest" aria-label="Suggestions">
      {data.queries?.length > 0 && (
        <div className="suggest-row">
          <h2 className="suggest-title">Try a search</h2>
          <div className="chips">
            {data.queries.map((q) => (
              <button type="button" key={q} className="chip" lang="hi" onClick={() => onPick(q)}>
                {q}
              </button>
            ))}
          </div>
        </div>
      )}
      {data.words?.length > 0 && (
        <div className="suggest-row">
          <h2 className="suggest-title">Common words</h2>
          <div className="chips">
            {data.words.map((w) => (
              <button
                type="button"
                key={w.term}
                className="chip chip-word"
                lang="hi"
                onClick={() => onPick(w.term)}
                title={`Appears in ${nf.format(w.df)} documents`}
              >
                {w.term}
                <span className="chip-df">{nf.format(w.df)}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

import { useEffect, useState } from "react";

// The free backend sleeps when idle. Waking it takes roughly 30-60 s: the
// instance starts, then the vocabulary is loaded into memory. The server
// only answers /api/health after the index is loaded, so the steps below
// advance on elapsed time and all complete when health answers.
// Shown as a full-screen loading screen so the page is not used before the
// engine can answer.
const STEPS = [
  { at: 0, label: "Reaching the search server" },
  { at: 4, label: "Starting the server, it sleeps when nobody is using it" },
  { at: 18, label: "Loading the vocabulary into memory (posting lists stay on disk)" },
];
const EXPECTED_SEC = 45;

export default function EngineStatus({ state, startedAt, onSkip }) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (state === "ready") return;
    const id = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(id);
  }, [state]);

  const elapsed = Math.max(0, (now - startedAt) / 1000);
  const ready = state === "ready";
  const down = state === "down";
  // Eases toward 95 % while waiting; jumps to 100 % once the engine answers.
  const pct = ready ? 100 : Math.min(95, 100 * (1 - Math.exp(-elapsed / (EXPECTED_SEC / 2.2))));
  const current = STEPS.reduce((i, s, k) => (elapsed >= s.at ? k : i), 0);
  const title = ready
    ? "Search engine ready"
    : down
      ? "The search server is not responding yet"
      : "Starting the search engine";

  return (
    <div className={`engine${ready ? " is-ready" : ""}${down ? " is-down" : ""}`} role="status" aria-live="polite">
      <div className="engine-card">
        <p className="engine-mark" lang="hi" aria-hidden="true">
          खोज
        </p>

        <div className="engine-head">
          <span className="engine-pct">{Math.floor(pct)}%</span>
          {!ready && <span className="engine-time">{Math.floor(elapsed)} s</span>}
        </div>
        <p className="engine-title">{title}</p>

        <div
          className="engine-bar"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(pct)}
          aria-label="Search engine start-up"
        >
          <span style={{ width: `${pct}%` }} />
        </div>

        <ol className="engine-steps">
          {STEPS.map((s, k) => {
            const done = ready || k < current;
            const active = !ready && k === current;
            return (
              <li key={s.label} className={done ? "is-done" : active ? "is-active" : ""}>
                {s.label}
              </li>
            );
          })}
          <li className={ready ? "is-done" : ""}>Ready: Hindi Wikipedia searchable</li>
        </ol>

        {!ready && (
          <p className="engine-note">
            {down
              ? "Still trying every few seconds. The page opens as soon as the server answers."
              : "The first start takes up to a minute. After that every search takes milliseconds."}
          </p>
        )}

        {down && (
          <button type="button" className="engine-skip" onClick={onSkip}>
            Open the page anyway
          </button>
        )}
      </div>
    </div>
  );
}

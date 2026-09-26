import { useEffect, useRef, useState } from "react";
import { api, nf } from "../api.js";
import HindiKeyboard from "./HindiKeyboard.jsx";

/** Replace the word the caret is in (or the last word) with `term`. */
function replaceLastWord(value, term) {
  const words = value.replace(/\s+$/, "").split(/\s+/);
  words[words.length - 1] = term;
  return words.join(" ") + " ";
}

export default function SearchBar({ value, onChange, onSubmit, autoFocus }) {
  const inputRef = useRef(null);
  const wrapRef = useRef(null);
  const [kbOpen, setKbOpen] = useState(false);
  const [matches, setMatches] = useState([]);
  const [active, setActive] = useState(-1);
  const [acOpen, setAcOpen] = useState(false);

  // Close keyboard + autocomplete when clicking anywhere outside the search area.
  useEffect(() => {
    const onDown = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) {
        setKbOpen(false);
        setAcOpen(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  useEffect(() => {
    if (autoFocus) inputRef.current?.focus({ preventScroll: true });
  }, [autoFocus]);

  // Debounced autocomplete for the word being typed.
  useEffect(() => {
    const last = value.split(/\s+/).pop();
    if (!last || /\s$/.test(value)) {
      setMatches([]);
      return;
    }
    const ctrl = new AbortController();
    const t = setTimeout(() => {
      api
        .autocomplete(last, ctrl.signal)
        .then((r) => {
          // hide the list when the only match is the word already typed
          const m = r.matches.filter((x) => x.term !== last || r.matches.length > 1);
          setMatches(m);
          setActive(-1);
        })
        .catch(() => {});
    }, 120);
    return () => {
      clearTimeout(t);
      ctrl.abort();
    };
  }, [value]);

  const submit = (q = value) => {
    setAcOpen(false);
    setKbOpen(false);
    onSubmit(q);
  };

  const pick = (term) => {
    onChange(replaceLastWord(value, term));
    setAcOpen(false);
    inputRef.current?.focus();
  };

  // Insert text from the virtual keyboard at the caret.
  const insert = (text) => {
    const el = inputRef.current;
    const start = el?.selectionStart ?? value.length;
    const end = el?.selectionEnd ?? value.length;
    const next = value.slice(0, start) + text + value.slice(end);
    onChange(next);
    setAcOpen(true);
    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(start + text.length, start + text.length);
    });
  };

  const backspace = () => {
    const el = inputRef.current;
    let start = el?.selectionStart ?? value.length;
    const end = el?.selectionEnd ?? value.length;
    if (start === end) {
      if (start === 0) return;
      start -= 1; // one code point: a matra, halant or letter
    }
    onChange(value.slice(0, start) + value.slice(end));
    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(start, start);
    });
  };

  const onKeyDown = (e) => {
    const listShown = acOpen && matches.length > 0;
    if (e.key === "ArrowDown" && listShown) {
      e.preventDefault();
      setActive((a) => (a + 1) % matches.length);
    } else if (e.key === "ArrowUp" && listShown) {
      e.preventDefault();
      setActive((a) => (a <= 0 ? matches.length - 1 : a - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (listShown && active >= 0) pick(matches[active].term);
      else submit();
    } else if (e.key === "Escape") {
      setAcOpen(false);
      setKbOpen(false);
    }
  };

  // With the keyboard open, the word list is docked beside it instead of
  // dropping down over (or under) the keys.
  const showList = (kbOpen || acOpen) && matches.length > 0;
  const lastWord = /\s$/.test(value) ? "" : value.split(/\s+/).pop();

  const wordList = (
    <ul className="ac" id="ac-list" role="listbox" aria-label="Matching words">
      {matches.map((m, i) => (
        <li
          key={m.term}
          id={`ac-${i}`}
          role="option"
          aria-selected={i === active}
          className={i === active ? "is-active" : undefined}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => pick(m.term)}
        >
          <span className="ac-term" lang="hi">{m.term}</span>
          <span className="ac-df">{nf.format(m.df)} documents</span>
        </li>
      ))}
    </ul>
  );

  return (
    <div className="search" ref={wrapRef}>
      <form
        className="search-line"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <label htmlFor="q" className="visually-hidden">
          Search Hindi words
        </label>
        <input
          id="q"
          ref={inputRef}
          className="search-input"
          type="search"
          lang="hi"
          autoComplete="off"
          spellCheck="false"
          placeholder="हिंदी शब्द लिखें, जैसे शेयर बाजार"
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            setAcOpen(true);
          }}
          onFocus={() => setAcOpen(true)}
          onClick={() => setKbOpen(true)}
          onKeyDown={onKeyDown}
          role="combobox"
          aria-expanded={showList}
          aria-controls="ac-list"
          aria-activedescendant={active >= 0 ? `ac-${active}` : undefined}
        />
        <button
          type="button"
          className={`icon-btn${kbOpen ? " is-on" : ""}`}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => {
            setKbOpen((o) => !o);
            inputRef.current?.focus();
          }}
          aria-pressed={kbOpen}
          title={kbOpen ? "Hide Hindi keyboard" : "Show Hindi keyboard"}
        >
          <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
            <rect x="2.5" y="6" width="19" height="12" rx="2" fill="none" stroke="currentColor" strokeWidth="1.6" />
            <path
              d="M6 9.5h1M9 9.5h1M12 9.5h1M15 9.5h1M18 9.5h0M6 12h1M9 12h1M12 12h1M15 12h1M18 12h0M8 15h8"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
            />
          </svg>
          <span className="visually-hidden">Hindi keyboard</span>
        </button>
        <button type="submit" className="btn-primary">
          Search
        </button>
      </form>

      {kbOpen ? (
        <div className="kb-panel">
          <div className="ac-dock">
            <p className="ac-dock-head">Matching words</p>
            {showList ? (
              wordList
            ) : (
              <p className="ac-dock-empty">
                {lastWord
                  ? <>No other word starts with<span lang="hi">{lastWord}</span>.</>
                  : "Type a letter to see words from the documents."}
              </p>
            )}
          </div>
          <HindiKeyboard
            onKey={insert}
            onSpace={() => insert(" ")}
            onBackspace={backspace}
            onClear={() => {
              onChange("");
              inputRef.current?.focus();
            }}
            onEnter={() => submit()}
            onClose={() => setKbOpen(false)}
          />
        </div>
      ) : (
        showList && <div className="ac-drop">{wordList}</div>
      )}
    </div>
  );
}

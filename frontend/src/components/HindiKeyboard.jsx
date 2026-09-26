const GROUPS = [
  {
    name: "Vowels",
    keys: ["अ", "आ", "इ", "ई", "उ", "ऊ", "ऋ", "ए", "ऐ", "ओ", "औ", "ऑ"],
  },
  {
    name: "Vowel signs",
    // shown on a dotted circle so the matra is visible on its own
    keys: ["ा", "ि", "ी", "ु", "ू", "ृ", "े", "ै", "ो", "ौ", "ॉ", "ं", "ँ", "ः", "्", "़"],
    combining: true,
  },
  {
    name: "Consonants",
    keys: [
      "क", "ख", "ग", "घ", "ङ",
      "च", "छ", "ज", "झ", "ञ",
      "ट", "ठ", "ड", "ढ", "ण",
      "त", "थ", "द", "ध", "न",
      "प", "फ", "ब", "भ", "म",
      "य", "र", "ल", "व",
      "श", "ष", "स", "ह",
      "क्ष", "त्र", "ज्ञ", "श्र", "ड़", "ढ़",
    ],
  },
  // No digit keys: the source articles contain no numbers, so they never match.
];

const SIGN_NAMES = {
  "्": "halant",
  "ं": "anusvara",
  "ँ": "chandrabindu",
  "ः": "visarga",
  "़": "nukta",
};

// Keep focus (and the caret) in the search box while keys are pressed.
const keepFocus = (e) => e.preventDefault();

export default function HindiKeyboard({ onKey, onBackspace, onSpace, onClear, onEnter, onClose }) {
  return (
    <div className="kb" role="group" aria-label="Hindi keyboard">
      {GROUPS.map((g) => (
        <div className="kb-group" key={g.name}>
          <span className="kb-label">{g.name}</span>
          <div className="kb-keys">
            {g.keys.map((k) => (
              <button
                type="button"
                key={k}
                className="kb-key"
                onMouseDown={keepFocus}
                onClick={() => onKey(k)}
                aria-label={g.combining ? `sign ${SIGN_NAMES[k] ?? k}` : k}
              >
                {g.combining ? `◌${k}` : k}
              </button>
            ))}
          </div>
        </div>
      ))}
      <div className="kb-actions">
        <button type="button" className="kb-key kb-wide" onMouseDown={keepFocus} onClick={onSpace}>
          Space
        </button>
        <button type="button" className="kb-key" onMouseDown={keepFocus} onClick={onBackspace} aria-label="Backspace">
          ⌫
        </button>
        <button type="button" className="kb-key kb-text" onMouseDown={keepFocus} onClick={onClear}>
          Clear
        </button>
        <span className="kb-spacer" />
        <button type="button" className="kb-key kb-text" onMouseDown={keepFocus} onClick={onClose}>
          Hide keyboard
        </button>
        <button type="button" className="kb-key kb-text kb-enter" onMouseDown={keepFocus} onClick={onEnter}>
          Search
        </button>
      </div>
    </div>
  );
}

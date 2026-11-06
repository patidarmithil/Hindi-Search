"""Extract plain-text articles from a Hindi Wikipedia XML dump.

Usage:
    python -m engine.wiki_extractor                       default paths (engine/config.py)
    python -m engine.wiki_extractor --dump X.xml.bz2 --out Y.jsonl [--limit N]

Input : hiwiki-latest-pages-articles.xml.bz2, one XML file with every article
        https://dumps.wikimedia.org/hiwiki/latest/hiwiki-latest-pages-articles.xml.bz2
Output: one JSON object per line, {"id", "wiki_id", "title", "url", "text"}

The dump is streamed (bz2 + xml.etree.iterparse), so memory use stays small.
Kept: main-namespace (ns 0) pages that are not redirects and still have at
least MIN_CHARS characters of text after the wiki markup is removed.
"""
import argparse
import bz2
import html
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote

from engine.config import CORPUS_FILE, WIKI_DUMP

MIN_CHARS = 200  # shorter pages are bot stubs / disambiguation leftovers

# Link prefixes whose target is not article text (files, categories, interwiki).
_DROP_NS = (
    "file", "image", "media", "category", "चित्र", "फ़ाइल", "फाइल", "श्रेणी",
    "wikipedia", "विकिपीडिया", "template", "साँचा", "सांचा", "help", "सहायता",
    "portal", "प्रवेशद्वार", "user", "सदस्य", "wikt", "wiktionary", "s", "commons",
)

_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_REF_RE = re.compile(r"<ref[^>/]*/>|<ref[^>]*>.*?</ref>", re.S | re.I)
_DROP_TAG_RE = re.compile(
    r"<(math|gallery|timeline|syntaxhighlight|source|score|graph|mapframe|templatedata)[^>]*>.*?</\1>",
    re.S | re.I,
)
_TEMPLATE_RE = re.compile(r"\{\{[^{}]*\}\}")      # innermost {{...}}
_TABLE_RE = re.compile(r"\{\|(?:(?!\{\|).)*?\|\}", re.S)  # innermost {| ... |}
_LINK_RE = re.compile(r"\[\[([^\[\]]*)\]\]")      # innermost [[...]]
_EXT_LINK_RE = re.compile(r"\[(?:https?:)?//[^\s\]]+\s*([^\]]*)\]")
_URL_RE = re.compile(r"https?://\S+")
_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")
_HEADING_RE = re.compile(r"^=+\s*(.*?)\s*=+\s*$", re.M)
_QUOTES_RE = re.compile(r"'{2,}")
_MAGIC_RE = re.compile(r"__[A-Zऀ-ॿ]+__")
_TABLE_LINE_RE = re.compile(r"^\s*[|!].*$", re.M)
_LIST_MARK_RE = re.compile(r"^[*#:;]+\s*", re.M)
_SPACES_RE = re.compile(r"[ \t]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def _replace_link(m: re.Match) -> str:
    inner = m.group(1)
    target, _, label = inner.partition("|")
    prefix = target.split(":", 1)[0].strip().lower() if ":" in target else ""
    if prefix in _DROP_NS or (len(prefix) in (2, 3) and prefix.isascii() and prefix.isalpha()):
        return ""  # file/category/interlanguage link
    text = label.rsplit("|", 1)[-1] if label else target
    return text.split("#", 1)[0] if not label else text


def _sub_until_stable(pattern: re.Pattern, repl, text: str, max_rounds: int = 20) -> str:
    """Apply a substitution repeatedly; removes nested structures innermost-first."""
    for _ in range(max_rounds):
        new = pattern.sub(repl, text)
        if new == text:
            break
        text = new
    return text


def clean_wikitext(text: str) -> str:
    """Convert MediaWiki markup to plain text."""
    text = _COMMENT_RE.sub("", text)
    text = _REF_RE.sub("", text)
    text = _DROP_TAG_RE.sub("", text)
    text = _sub_until_stable(_TEMPLATE_RE, "", text)   # infoboxes, citations, ...
    text = _sub_until_stable(_TABLE_RE, "", text)
    text = _sub_until_stable(_LINK_RE, _replace_link, text)
    text = _EXT_LINK_RE.sub(r"\1", text)
    text = _URL_RE.sub("", text)
    text = html.unescape(text)
    text = _TAG_RE.sub("", text)
    text = _HEADING_RE.sub(r"\1", text)
    text = _QUOTES_RE.sub("", text)
    text = _MAGIC_RE.sub("", text)
    text = _TABLE_LINE_RE.sub("", text)
    text = _LIST_MARK_RE.sub("", text)
    text = text.replace("{{", "").replace("}}", "").replace("[[", "").replace("]]", "")
    text = _SPACES_RE.sub(" ", text)
    lines = [ln.strip() for ln in text.split("\n")]
    return _BLANK_LINES_RE.sub("\n\n", "\n".join(lines)).strip()


def iter_pages(dump_path: Path):
    """Yield (wiki_id, title, wikitext) for main-namespace, non-redirect pages."""
    opener = bz2.open if str(dump_path).endswith(".bz2") else open
    with opener(dump_path, "rb") as f:
        ns_uri = ""
        for event, elem in ET.iterparse(f, events=("start", "end")):
            tag = elem.tag
            if event == "start":
                if not ns_uri and tag.startswith("{"):
                    ns_uri = tag[: tag.index("}") + 1]
                continue
            if tag != ns_uri + "page":
                continue
            ns = elem.findtext(ns_uri + "ns")
            redirect = elem.find(ns_uri + "redirect")
            if ns == "0" and redirect is None:
                title = elem.findtext(ns_uri + "title") or ""
                wiki_id = elem.findtext(ns_uri + "id") or ""
                rev = elem.find(ns_uri + "revision")
                text = rev.findtext(ns_uri + "text") if rev is not None else ""
                if text and not text.lstrip().lower().startswith(("#redirect", "#अनुप्रेषित")):
                    yield wiki_id, title, text
            elem.clear()


def extract(dump_path: Path = WIKI_DUMP, out_path: Path = CORPUS_FILE,
            limit: int | None = None, verbose: bool = True) -> dict:
    if not dump_path.exists():
        raise FileNotFoundError(
            f"{dump_path} not found. Download it from "
            "https://dumps.wikimedia.org/hiwiki/latest/hiwiki-latest-pages-articles.xml.bz2"
        )
    start = time.perf_counter()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    seen = kept = 0
    with open(out_path, "w", encoding="utf-8", newline="\n") as out:
        for wiki_id, title, wikitext in iter_pages(dump_path):
            seen += 1
            text = clean_wikitext(wikitext)
            if len(text) < MIN_CHARS:
                continue
            url = "https://hi.wikipedia.org/wiki/" + quote(title.replace(" ", "_"))
            out.write(json.dumps({"id": kept, "wiki_id": int(wiki_id), "title": title,
                                  "url": url, "text": text}, ensure_ascii=False) + "\n")
            kept += 1
            if verbose and kept % 10000 == 0:
                print(f"  {kept:,} articles kept ({seen:,} pages read, {time.perf_counter() - start:.0f} s)")
            if limit and kept >= limit:
                break
    return {"pages_read": seen, "articles_kept": kept,
            "seconds": round(time.perf_counter() - start, 1),
            "output_mb": round(out_path.stat().st_size / 1024 / 1024, 1)}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Hindi Wikipedia XML dump -> plain-text JSONL corpus")
    ap.add_argument("--dump", type=Path, default=WIKI_DUMP)
    ap.add_argument("--out", type=Path, default=CORPUS_FILE)
    ap.add_argument("--limit", type=int, default=None, help="stop after N articles (testing)")
    args = ap.parse_args()
    print(f"Extracting {args.dump} -> {args.out}")
    stats = extract(args.dump, args.out, args.limit)
    for k, v in stats.items():
        print(f"  {k:14}: {v:,}" if isinstance(v, int) else f"  {k:14}: {v}")


if __name__ == "__main__":
    main()

"""Terminal interface for the Hindi inverted-index search engine.

Usage:
    python cli.py                          interactive search loop
    python cli.py "शेयर बाजार"             one-shot search, then exit
    python cli.py "बाजार" --top 20         print only the top 20 results
    python cli.py --show 42 --query बाजार  print document 42 with matches highlighted
    python cli.py --rebuild                rebuild the index before searching

Interactive commands:
    :open <rank>   show a result of the last search with matches highlighted
    :top <N|all>   change how many results are printed
    :suggest       list suggested words and sample queries
    :help          show commands
    :q / exit      quit
"""
import argparse
import os
import sys
import time

from engine.indexer import build_index
from engine.searcher import Searcher

PROMPT = "\nखोज / Search > "
TITLE_WIDTH = 70

HELP = """Commands:
  <query>        search (several words = documents containing all of them)
  :open <rank>   show a result of the last search with matches highlighted
  :top <N|all>   number of results to print (current: {top})
  :suggest       suggested words and sample queries
  :help          this help
  :q / exit      quit"""


def _enable_windows_ansi() -> bool:
    """Turn on virtual-terminal (ANSI escape) processing for the Windows console."""
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except (AttributeError, OSError):
        return False


class Style:
    """ANSI styling; disabled with --no-color or when output is not a terminal."""

    def __init__(self, enabled: bool):
        if enabled and os.name == "nt":
            enabled = _enable_windows_ansi()
        self.enabled = enabled

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def bold(self, text):
        return self._wrap("1", text)

    def dim(self, text):
        return self._wrap("2", text)

    def green(self, text):
        return self._wrap("32", text)

    def red(self, text):
        return self._wrap("31", text)

    def mark(self, text):
        # black on yellow; without colour fall back to visible brackets
        return self._wrap("30;43", text) if self.enabled else f"[[{text}]]"


def load_searcher(style: Style, rebuild: bool) -> Searcher:
    if rebuild or not Searcher.index_exists():
        print("Index not found, building it now ..." if not rebuild else "Rebuilding index ...")
        stats = build_index(verbose=True)
        print(f"Index built in {stats['build_time_sec']} s")
    s = Searcher().load()
    st = s.stats
    print(style.bold("Hindi Search Engine (inverted index)"))
    print(f"  documents indexed : {st['documents']:,}")
    print(f"  vocabulary        : {st['vocabulary']:,} terms")
    print(f"  postings          : {st['postings']:,}")
    print(f"  index load time   : {s.load_time_sec:.3f} s")
    return s


def print_results(s: Searcher, query: str, top: int | None, style: Style) -> dict:
    res = s.search(query, limit=top)
    print()
    print(f"{style.bold('Query')}              : {query}")
    # only worth printing when normalization changed the query (nukta, punctuation, ...)
    if res["terms"] and " ".join(res["terms"]) != " ".join(query.split()):
        print(f"{style.bold('Terms')}              : {' '.join(res['terms'])}")
    if res["missing_terms"]:
        print(style.red(f"Not in any document : {' '.join(res['missing_terms'])}"))
    if res["mode"] == "or":
        print(style.dim("No document contains every term; showing documents with any term."))

    summary = (
        f"{style.bold('Documents found')}    : {style.green(format(res['total_docs'], ','))}\n"
        f"{style.bold('Documents searched')} : {res['docs_searched']:,}\n"
        f"{style.bold('Total occurrences')}  : {res['total_occurrences']:,}\n"
        f"{style.bold('Time taken')}         : {res['time_sec']:.6f} seconds"
    )
    print(summary)

    if not res["results"]:
        print(style.red("\nNo documents found."))
        return res

    print()
    print(style.bold(f"{'Rank':>6}  {'Doc ID':>6}  {'Count':>5}  {'Document':<22}  Title"))
    print(style.dim("-" * (6 + 2 + 6 + 2 + 5 + 2 + 22 + 2 + TITLE_WIDTH)))
    for r in res["results"]:
        title = r["title"] if len(r["title"]) <= TITLE_WIDTH else r["title"][: TITLE_WIDTH - 1] + "…"
        print(f"{r['rank']:>6}  {r['doc_id']:>6}  {r['count']:>5}  {r['file']:<22}  {style.dim(title)}")

    shown = len(res["results"])
    if shown < res["total_docs"]:
        print(style.dim(f"\nShowing top {shown:,} of {res['total_docs']:,} documents (use :top all or --top 0 for all)."))
    else:
        # repeat the summary so it is visible after a long list
        print(style.dim(f"\n{res['total_docs']:,} documents found in {res['time_sec']:.6f} seconds "
                        f"(searched {res['docs_searched']:,} documents)."))
    return res


def show_document(s: Searcher, doc_id: int, query: str, style: Style) -> None:
    try:
        doc = s.get_document(doc_id, query)
    except KeyError:
        print(style.red(f"No document with id {doc_id} (valid: 0-{len(s.docs) - 1})."))
        return
    text, spans = doc["text"], doc["highlights"]
    parts, last = [], 0
    for start, end in spans:
        parts.append(text[last:start])
        parts.append(style.mark(text[start:end]))
        last = end
    parts.append(text[last:])

    bar = style.dim("=" * 80)
    print(f"\n{bar}\n{style.bold(doc['file'])}  (doc id {doc['id']}, {doc['len']:,} words, "
          f"{len(spans)} highlighted matches)\n{bar}")
    print("".join(parts).rstrip())
    print(bar)


def resolve_doc(s: Searcher, ref: str) -> int | None:
    """Accept a doc id ('42') or a file name ('Economy (43).txt' / 'Economy (43)')."""
    ref = ref.strip()
    if ref.isdigit():
        return int(ref)
    name = ref if ref.endswith(".txt") else ref + ".txt"
    return next((d["id"] for d in s.docs if d["file"] == name), None)


def print_suggestions(s: Searcher, style: Style) -> None:
    words = s.suggestions.get("words", [])
    queries = s.suggestions.get("queries", [])
    print(style.bold("\nSuggested words:"))
    print("  " + "  ".join(w["term"] for w in words))
    print(style.bold("Sample queries:"))
    print("  " + "  |  ".join(queries))


def interactive(s: Searcher, top: int | None, style: Style) -> None:
    print(style.dim("\nType a Hindi word or phrase. :help for commands, :q to quit."))
    print_suggestions(s, style)
    last = None
    while True:
        try:
            line = input(PROMPT).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in (":q", ":quit", "exit", "quit"):
            break
        if line == ":help":
            print(HELP.format(top="all" if top is None else top))
        elif line == ":suggest":
            print_suggestions(s, style)
        elif line.startswith(":top"):
            arg = line[4:].strip()
            if arg == "all" or arg == "0":
                top = None
            elif arg.isdigit():
                top = int(arg)
            else:
                print(style.red("Usage: :top <N|all>"))
                continue
            print(f"Printing {'all' if top is None else top} results.")
        elif line.startswith(":open"):
            arg = line[5:].strip()
            if last is None:
                print(style.red("Search something first."))
            elif not arg.isdigit() or not 1 <= int(arg) <= last["total_docs"]:
                print(style.red(f"Usage: :open <rank>, rank between 1 and {last['total_docs']}"))
            else:
                # rank may be beyond the printed page, so fetch that single row
                row = s.search(last["query"], offset=int(arg) - 1, limit=1)["results"][0]
                show_document(s, row["doc_id"], last["query"], style)
        elif line.startswith(":"):
            print(style.red("Unknown command. :help for commands."))
        else:
            last = print_results(s, line, top, style)
    print("Bye.")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.stdin and hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(description="Search 16,000 Hindi documents with an inverted index.")
    ap.add_argument("query", nargs="?", help="run one search and exit (omit for interactive mode)")
    ap.add_argument("--top", type=int, default=0, help="results to print, 0 = all (default: all)")
    ap.add_argument("--show", metavar="DOC", help="print a document (doc id or file name) and exit")
    ap.add_argument("--query", dest="highlight", default="", help="words to highlight with --show")
    ap.add_argument("--rebuild", action="store_true", help="rebuild the index before starting")
    ap.add_argument("--no-color", action="store_true", help="disable ANSI colours")
    args = ap.parse_args()

    style = Style(enabled=not args.no_color and sys.stdout.isatty())
    top = args.top if args.top > 0 else None

    start = time.perf_counter()
    s = load_searcher(style, args.rebuild)
    if args.show is not None:
        doc_id = resolve_doc(s, args.show)
        if doc_id is None:
            sys.exit(f"Document not found: {args.show}")
        show_document(s, doc_id, args.highlight or args.query or "", style)
    elif args.query:
        print_results(s, args.query, top, style)
    else:
        print(style.dim(f"Ready in {time.perf_counter() - start:.2f} s."))
        interactive(s, top, style)


if __name__ == "__main__":
    main()

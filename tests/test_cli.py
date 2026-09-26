import contextlib
import io
import unittest

import cli
from engine.searcher import Searcher


@unittest.skipUnless(Searcher.index_exists(), "index not built (python -m engine.indexer)")
class CliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = Searcher().load()
        cls.style = cli.Style(enabled=False)

    def _capture(self, fn, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = fn(*args)
        return buf.getvalue(), result

    def test_resolve_doc(self):
        self.assertEqual(cli.resolve_doc(self.s, "0"), 0)
        name = self.s.docs[5]["file"]
        self.assertEqual(cli.resolve_doc(self.s, name), 5)
        self.assertEqual(cli.resolve_doc(self.s, name[:-4]), 5)
        self.assertIsNone(cli.resolve_doc(self.s, "no such file"))

    def test_results_print_summary_and_all_rows(self):
        out, res = self._capture(cli.print_results, self.s, "मुद्रास्फीति", None, self.style)
        self.assertIn(f"Documents found    : {res['total_docs']:,}", out)
        self.assertIn("Documents searched : 16,000", out)
        self.assertIn("Time taken", out)
        self.assertEqual(len(res["results"]), res["total_docs"])
        self.assertIn(res["results"][-1]["file"], out)

    def test_show_document_marks_matches(self):
        doc_id = self.s.search("बाजार", limit=1)["results"][0]["doc_id"]
        out, _ = self._capture(cli.show_document, self.s, doc_id, "बाजार", self.style)
        self.assertIn("[[बाजार]]", out)


if __name__ == "__main__":
    unittest.main()

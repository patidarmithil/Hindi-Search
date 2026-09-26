import unittest
from array import array

from engine.config import DATA_DIR
from engine.searcher import Searcher, highlight_spans, intersect, union
from engine.tokenizer import tokenize


class MergeTests(unittest.TestCase):
    def test_intersect_sums_tf(self):
        docs, tfs = intersect([1, 3, 5, 7], [1, 2, 3, 4], [3, 4, 7], [10, 20, 30])
        self.assertEqual(docs, [3, 7])
        self.assertEqual(tfs, [12, 34])

    def test_intersect_empty(self):
        self.assertEqual(intersect([1, 2], [1, 1], [3, 4], [1, 1]), ([], []))

    def test_union_merges_and_sums(self):
        docs, tfs = union([(array("i", [1, 4]), array("i", [2, 2])),
                           (array("i", [2, 4]), array("i", [5, 1]))])
        self.assertEqual(docs, [1, 2, 4])
        self.assertEqual(tfs, [2, 5, 3])


class HighlightTests(unittest.TestCase):
    def test_nukta_variant_highlighted(self):
        text = "सबसे ज़्यादा गंतव्यों"
        spans = highlight_spans(text, set(tokenize("ज्यादा")))
        self.assertEqual([text[s:e] for s, e in spans], ["ज़्यादा"])

    def test_multiple_occurrences(self):
        text = "बाजार में तेजी, ‘बाजार’ बंद।"
        spans = highlight_spans(text, {"बाजार"})
        self.assertEqual(len(spans), 2)
        self.assertTrue(all(text[s:e] == "बाजार" for s, e in spans))


@unittest.skipUnless(Searcher.index_exists(), "index not built (python -m engine.indexer)")
class SearcherIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = Searcher().load()

    def test_counts_match_raw_documents(self):
        res = self.s.search("मुद्रास्फीति", limit=5)
        self.assertGreater(res["total_docs"], 0)
        for r in res["results"]:
            text = (DATA_DIR / r["file"]).read_text(encoding="utf-8")
            self.assertEqual(tokenize(text).count("मुद्रास्फीति"), r["count"])

    def test_ranked_by_count_desc(self):
        counts = [r["count"] for r in self.s.search("बाजार", limit=100)["results"]]
        self.assertEqual(counts, sorted(counts, reverse=True))

    def test_and_query_docs_contain_all_terms(self):
        res = self.s.search("शेयर बाजार", limit=20)
        self.assertEqual(res["mode"], "and")
        for r in res["results"]:
            toks = set(tokenize((DATA_DIR / r["file"]).read_text(encoding="utf-8")))
            self.assertTrue({"शेयर", "बाजार"} <= toks)

    def test_or_fallback_when_one_term_unknown(self):
        res = self.s.search("बाजार क्ष्यज्ञ")
        self.assertEqual(res["mode"], "or")
        self.assertEqual(res["missing_terms"], ["क्ष्यज्ञ"])
        self.assertGreater(res["total_docs"], 0)

    def test_unknown_and_empty(self):
        self.assertEqual(self.s.search("क्ष्यज्ञ")["total_docs"], 0)
        self.assertEqual(self.s.search("   ")["total_docs"], 0)

    def test_pagination(self):
        full = self.s.search("सरकार", limit=None)["results"]
        page2 = self.s.search("सरकार", offset=10, limit=10)["results"]
        self.assertEqual([r["doc_id"] for r in page2], [r["doc_id"] for r in full[10:20]])

    def test_document_highlights(self):
        doc_id = self.s.search("बाजार", limit=1)["results"][0]["doc_id"]
        doc = self.s.get_document(doc_id, "बाजार")
        self.assertGreater(len(doc["highlights"]), 0)
        s, e = doc["highlights"][0]
        self.assertEqual(tokenize(doc["text"][s:e]), ["बाजार"])

    def test_autocomplete_prefix(self):
        out = self.s.autocomplete("बाज")
        self.assertTrue(out)
        self.assertTrue(all(o["term"].startswith("बाज") for o in out))

    def test_edge_case_queries(self):
        base = self.s.search("बाजार")["total_docs"]
        # punctuation, curly quotes and nukta spelling all reduce to the same term
        for q in ("बाजार,।!", "‘बाजार’", "बाज़ार", "  बाजार  "):
            self.assertEqual(self.s.search(q)["total_docs"], base, q)
        self.assertEqual(self.s.search("!!!")["total_docs"], 0)
        self.assertEqual(self.s.search("market")["mode"], "none")

    def test_very_frequent_word(self):
        self.s._match.cache_clear()
        res = self.s.search("के")
        self.assertGreater(res["total_docs"], 15000)
        self.assertLess(res["time_sec"], 0.5)

    def test_under_500ms(self):
        self.s._match.cache_clear()
        self.assertLess(self.s.search("के में है की को")["time_sec"], 0.5)


if __name__ == "__main__":
    unittest.main()

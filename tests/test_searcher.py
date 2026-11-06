import unittest

from engine.indexer import decode_gaps, encode_gaps
from engine.searcher import Searcher, highlight_spans, parse_query
from engine.tokenizer import tokenize


class CodecTests(unittest.TestCase):
    def test_gap_varint_roundtrip(self):
        positions = [0, 1, 5, 127, 128, 300, 16384, 2_000_000]
        self.assertEqual(decode_gaps(encode_gaps(positions)), positions)

    def test_small_gaps_use_one_byte(self):
        self.assertEqual(len(encode_gaps([3, 10, 20])), 3)

    def test_decode_count(self):
        self.assertEqual(decode_gaps(encode_gaps([4, 9, 30]), count=2), [4, 9])


class QueryParseTests(unittest.TestCase):
    def test_terms_and_phrases(self):
        terms, phrases = parse_query('गंगा "महात्मा गांधी" नदी')
        self.assertEqual(terms, ("गंगा", "नदी"))
        self.assertEqual(phrases, (("महात्मा", "गांधी"),))

    def test_quoted_single_word_is_a_term(self):
        self.assertEqual(parse_query('"गंगा"'), (("गंगा",), ()))

    def test_unclosed_quote_ignored(self):
        self.assertEqual(parse_query('"गंगा नदी'), (("गंगा", "नदी"), ()))


class HighlightTests(unittest.TestCase):
    def test_nukta_variant_highlighted(self):
        text = "सबसे ज़्यादा गंतव्यों"
        spans = highlight_spans(text, set(tokenize("ज्यादा")))
        self.assertEqual([text[s:e] for s, e in spans], ["ज़्यादा"])

    def test_multiple_occurrences(self):
        text = "गंगा में स्नान, ‘गंगा’ नदी।"
        spans = highlight_spans(text, {"गंगा"})
        self.assertEqual(len(spans), 2)
        self.assertTrue(all(text[s:e] == "गंगा" for s, e in spans))

    def test_phrase_highlight_only_consecutive(self):
        text = "महात्मा गांधी और गांधी महात्मा"
        spans = highlight_spans(text, set(), (("महात्मा", "गांधी"),))
        self.assertEqual([text[s:e] for s, e in spans], ["महात्मा गांधी"])


@unittest.skipUnless(Searcher.index_exists(), "index not built (python -m engine.indexer)")
class SearcherIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = Searcher().load()

    def tokens(self, doc_id):
        art = self.s.read_article(doc_id)
        return tokenize(art["title"] + "\n" + art["text"])

    def test_positions_match_raw_documents(self):
        info = self.s.postings("हिमालय", max_docs=5)
        for p in info["postings"]:
            toks = self.tokens(p["doc_id"])
            self.assertEqual([i for i, t in enumerate(toks) if t == "हिमालय"], p["positions"])
            self.assertEqual(p["tf"], len(p["positions"]))

    def test_df_and_cf(self):
        tid = self.s.term_id("हिमालय")
        docs, tfs = self.s.read_postings(tid)
        self.assertEqual(len(docs), int(self.s.df[tid]))
        self.assertEqual(int(tfs.sum()), int(self.s.cf[tid]))
        self.assertTrue((docs[1:] > docs[:-1]).all())  # sorted, unique

    def test_vocabulary_sorted_and_lookup(self):
        self.assertEqual(self.s.vocab[:1000], sorted(self.s.vocab[:1000]))
        self.assertGreaterEqual(self.s.term_id("भारत"), 0)
        self.assertEqual(self.s.term_id("क्ष्यज्ञत्र"), -1)

    def test_counts_match_raw_documents(self):
        res = self.s.search("हिमालय", limit=5)
        self.assertGreater(res["total_docs"], 0)
        for r in res["results"]:
            self.assertEqual(self.tokens(r["doc_id"]).count("हिमालय"), r["count"])

    def test_ranked_by_score_desc(self):
        scores = [r["score"] for r in self.s.search("नदी", limit=100)["results"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_and_query_docs_contain_all_terms(self):
        res = self.s.search("गंगा नदी", limit=20)
        self.assertEqual(res["mode"], "and")
        for r in res["results"]:
            self.assertTrue({"गंगा", "नदी"} <= set(self.tokens(r["doc_id"])))

    def test_phrase_query(self):
        res = self.s.search('"महात्मा गांधी"', limit=10)
        self.assertEqual(res["mode"], "phrase")
        self.assertGreater(res["total_docs"], 0)
        for r in res["results"]:
            toks = self.tokens(r["doc_id"])
            hits = sum(1 for i in range(len(toks) - 1) if toks[i] == "महात्मा" and toks[i + 1] == "गांधी")
            self.assertEqual(hits, r["count"])
        self.assertLess(self.s.search('"गांधी महात्मा"')["total_docs"], res["total_docs"])

    def test_or_fallback_when_one_term_unknown(self):
        res = self.s.search("हिमालय क्ष्यज्ञत्र")
        self.assertEqual(res["mode"], "or")
        self.assertEqual(res["missing_terms"], ["क्ष्यज्ञत्र"])
        self.assertEqual(res["total_docs"], self.s.search("हिमालय")["total_docs"])

    def test_unknown_and_empty(self):
        self.assertEqual(self.s.search("क्ष्यज्ञत्र")["total_docs"], 0)
        self.assertEqual(self.s.search("   ")["total_docs"], 0)

    def test_pagination(self):
        full = self.s.search("नदी", limit=None)["results"]
        page2 = self.s.search("नदी", offset=10, limit=10)["results"]
        self.assertEqual([r["doc_id"] for r in page2], [r["doc_id"] for r in full[10:20]])

    def test_document_highlights(self):
        doc_id = self.s.search("हिमालय", limit=1)["results"][0]["doc_id"]
        doc = self.s.get_document(doc_id, "हिमालय")
        self.assertGreater(len(doc["highlights"]), 0)
        s, e = doc["highlights"][0]
        self.assertEqual(tokenize(doc["text"][s:e]), ["हिमालय"])

    def test_autocomplete_prefix(self):
        out = self.s.autocomplete("हिमा")
        self.assertTrue(out)
        self.assertTrue(all(o["term"].startswith("हिमा") for o in out))
        dfs = [o["df"] for o in out]
        self.assertEqual(dfs, sorted(dfs, reverse=True))

    def test_edge_case_queries(self):
        base = self.s.search("जिला")["total_docs"]
        for q in ("जिला,।!", "‘जिला’", "ज़िला", "  जिला  "):
            self.assertEqual(self.s.search(q)["total_docs"], base, q)
        self.assertEqual(self.s.search("!!!")["total_docs"], 0)

    def test_postings_read_from_disk(self):
        self.s._match.cache_clear()
        before = self.s.disk_reads
        self.s.search("गंगा नदी")
        self.assertEqual(self.s.disk_reads - before, 2)
        before = self.s.disk_reads
        self.s.search("गंगा नदी")  # cached: no disk access
        self.assertEqual(self.s.disk_reads - before, 0)

    def test_very_frequent_word_under_500ms(self):
        self.s._match.cache_clear()
        res = self.s.search("के")
        self.assertGreater(res["total_docs"], self.s.n_docs // 2)
        self.assertLess(res["time_sec"], 0.5)

    def test_many_frequent_words_under_500ms(self):
        self.s._match.cache_clear()
        self.assertLess(self.s.search("के में है की को")["time_sec"], 0.5)


if __name__ == "__main__":
    unittest.main()

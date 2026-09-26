import unittest

from engine.tokenizer import is_stopword, normalize, tokenize


class NormalizeTests(unittest.TestCase):
    def test_nukta_combining_and_plain_match(self):
        # ज़ written as ज + U+093C nukta
        self.assertEqual(normalize("ज़्यादा"), normalize("ज्यादा"))

    def test_precomposed_nukta_matches_plain(self):
        # U+095B is the precomposed ज़
        self.assertEqual(normalize("ज़्यादा"), "ज्यादा")

    def test_zero_width_removed(self):
        self.assertEqual(normalize("क्‍ष"), "क्ष")

    def test_latin_lowercased(self):
        self.assertEqual(normalize("GST"), "gst")


class TokenizeTests(unittest.TestCase):
    def test_curly_quotes_stripped(self):
        self.assertEqual(tokenize("‘ट्रैवलर्स मैप’"), ["ट्रैवलर्स", "मैप"])

    def test_danda_splits_sentences(self):
        self.assertEqual(tokenize("बाजार बढ़ा। निवेश"), ["बाजार", "बढा", "निवेश"])

    def test_brackets_and_commas(self):
        self.assertEqual(
            tokenize("गुरुग्राम (हरियाण), अगस्त (भाषा)"),
            ["गुरुग्राम", "हरियाण", "अगस्त", "भाषा"],
        )

    def test_matras_and_halant_kept(self):
        self.assertEqual(tokenize("स्वतंत्रता दिवस"), ["स्वतंत्रता", "दिवस"])

    def test_digits_are_separate_tokens(self):
        self.assertEqual(tokenize("2023 में ५० करोड़"), ["2023", "में", "५०", "करोड"])

    def test_mixed_latin(self):
        self.assertEqual(tokenize("RBI ने रेपो-रेट"), ["rbi", "ने", "रेपो", "रेट"])

    def test_query_and_document_tokenize_identically(self):
        doc = tokenize("देश के सबसे ज़्यादा लोकप्रिय स्थान")
        self.assertIn(tokenize("ज्यादा")[0], doc)

    def test_empty(self):
        self.assertEqual(tokenize(""), [])
        self.assertEqual(tokenize("।,‘’()"), [])


class StopwordTests(unittest.TestCase):
    def test_stopwords(self):
        self.assertTrue(is_stopword("के"))
        self.assertFalse(is_stopword("बाजार"))


if __name__ == "__main__":
    unittest.main()

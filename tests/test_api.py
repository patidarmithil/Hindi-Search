import unittest

from engine.searcher import Searcher

try:
    from fastapi.testclient import TestClient

    from backend.main import app
except ImportError:  # fastapi / httpx not installed
    app = None


@unittest.skipUnless(app is not None and Searcher.index_exists(), "fastapi or index missing")
class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = TestClient(app)
        cls.client = cls.ctx.__enter__()  # runs lifespan (loads the index)
        from backend.main import searcher
        cls.n_docs = searcher.n_docs

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def test_health(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["documents"], self.n_docs)

    def test_search_page(self):
        r = self.client.get("/api/search", params={"q": "गंगा नदी", "page": 2, "size": 10})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["mode"], "and")
        self.assertEqual(body["docs_searched"], self.n_docs)
        self.assertEqual(len(body["results"]), 10)
        self.assertEqual(body["results"][0]["rank"], 11)
        self.assertEqual(body["pages"], (body["total_docs"] + 9) // 10)
        self.assertLess(body["time_sec"], 0.5)
        self.assertIn("Server-Timing", r.headers)

    def test_search_validation(self):
        self.assertEqual(self.client.get("/api/search").status_code, 422)
        self.assertEqual(self.client.get("/api/search", params={"q": "x", "size": 1000}).status_code, 422)
        self.assertEqual(self.client.get("/api/search", params={"q": "क" * 500}).status_code, 422)

    def test_search_no_results(self):
        body = self.client.get("/api/search", params={"q": "क्ष्यज्ञत्र"}).json()
        self.assertEqual(body["total_docs"], 0)
        self.assertEqual(body["results"], [])
        self.assertEqual(body["pages"], 0)

    def test_document(self):
        doc_id = self.client.get("/api/search", params={"q": "हिमालय"}).json()["results"][0]["doc_id"]
        body = self.client.get(f"/api/document/{doc_id}", params={"q": "हिमालय"}).json()
        self.assertTrue(body["text"])
        self.assertTrue(body["highlights"])
        self.assertTrue(body["url"].startswith("https://hi.wikipedia.org/wiki/"))
        self.assertEqual(self.client.get("/api/document/99999999").status_code, 404)

    def test_phrase_search(self):
        body = self.client.get("/api/search", params={"q": '"महात्मा गांधी"'}).json()
        self.assertEqual(body["mode"], "phrase")
        self.assertEqual(body["phrases"], ["महात्मा गांधी"])
        self.assertGreater(body["total_docs"], 0)

    def test_positional_index(self):
        body = self.client.get("/api/index/हिमालय", params={"limit": 3}).json()
        self.assertGreater(body["df"], 3)
        self.assertGreaterEqual(body["cf"], body["df"])
        self.assertEqual(len(body["postings"]), 3)
        self.assertTrue(all(p["tf"] == len(p["positions"]) for p in body["postings"]))
        self.assertEqual(self.client.get("/api/index/क्ष्यज्ञत्र").status_code, 404)

    def test_suggestions_autocomplete_stats(self):
        self.assertTrue(self.client.get("/api/suggestions").json()["queries"])
        matches = self.client.get("/api/autocomplete", params={"prefix": "हिमा"}).json()["matches"]
        self.assertTrue(all(m["term"].startswith("हिमा") for m in matches))
        self.assertEqual(self.client.get("/api/stats").json()["documents"], self.n_docs)

    def test_gzip(self):
        r = self.client.get("/api/search", params={"q": "नदी", "size": 100},
                            headers={"Accept-Encoding": "gzip"})
        self.assertEqual(r.headers.get("content-encoding"), "gzip")


if __name__ == "__main__":
    unittest.main()

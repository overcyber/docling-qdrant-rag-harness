import unittest

from app.schemas import ProcessingOptions, SearchRequest


class SchemaTests(unittest.TestCase):
    def test_three_chunker_variants(self):
        for kind in ("hybrid", "hierarchical", "line_based"):
            model = ProcessingOptions.model_validate({"chunking": {"type": kind}})
            self.assertEqual(model.chunking.type, kind)

    def test_invalid_page_range(self):
        with self.assertRaises(Exception):
            ProcessingOptions.model_validate({"conversion": {"page_range": [5, 1]}})

    def test_retrieval_modes(self):
        for mode in ("hybrid", "dense", "sparse"):
            self.assertEqual(SearchRequest(query="x", mode=mode).mode, mode)


if __name__ == "__main__":
    unittest.main()

import unittest

from app.schemas import AgentProfileCreate, ChatRequest, GenerationOptions, ProcessingOptions, SearchRequest, TextIngestRequest


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

    def test_corpora_are_trimmed_and_deduplicated(self):
        search = SearchRequest(query="x", corpora=[" thesis ", "thesis", "papers", ""])
        chat = ChatRequest(question="x", corpora=[" thesis ", "thesis", "papers"])
        self.assertEqual(search.corpora, ["thesis", "papers"])
        self.assertEqual(chat.corpora, ["thesis", "papers"])

    def test_four_llm_providers(self):
        for provider in ("openai_compatible", "ollama", "llama_cpp", "vllm"):
            request = ChatRequest(question="x", provider=provider)
            self.assertEqual(request.provider, provider)

    def test_advanced_generation_options(self):
        generation = GenerationOptions.model_validate({"temperature": 0.2, "top_p": 0.9, "max_tokens": 512, "top_k": 40, "min_p": 0.05, "repetition_penalty": 1.1, "mirostat": 2, "mirostat_tau": 5.0, "mirostat_eta": 0.1, "extra_body": {"think": False}})
        self.assertEqual(generation.top_k, 40)
        self.assertEqual(generation.mirostat, 2)
        self.assertFalse(generation.extra_body["think"])

    def test_text_ingest_schema(self):
        request = TextIngestRequest(text="durable text input", title="Knowledge note", corpus_id="knowledge-base", processing_options={"chunking": {"type": "hybrid", "max_tokens": 120}})
        self.assertEqual(request.corpus_id, "knowledge-base")
        self.assertEqual(request.processing_options.chunking.type, "hybrid")

    def test_agent_profile_schema(self):
        profile = AgentProfileCreate(agent_id="researcher", name="Researcher", provider="ollama", model="qwen3:8b", corpora=["thesis", "papers"], retrieval={"mode": "hybrid", "top_k": 8}, generation={"temperature": 0.1, "top_k": 40}, memory={"enabled": True, "max_messages": 12})
        self.assertEqual(profile.provider, "ollama")
        self.assertEqual(profile.generation.top_k, 40)

    def test_auth_compare_digest(self):
        try:
            from app.auth import require_auth
            from app.config import settings
            from fastapi import HTTPException
        except ImportError:
            self.skipTest("pydantic_settings not installed on host")
            return
        orig_key = settings.api_key
        try:
            settings.api_key = "secret123"
            self.assertIsNone(require_auth(authorization="Bearer secret123"))
            self.assertIsNone(require_auth(x_api_key="secret123"))
            with self.assertRaises(HTTPException) as cm:
                require_auth(x_api_key="wrong")
            self.assertEqual(cm.exception.status_code, 401)
        finally:
            settings.api_key = orig_key


if __name__ == "__main__":
    unittest.main()

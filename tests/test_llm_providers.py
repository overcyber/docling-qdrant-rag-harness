import unittest

from app.llm_providers import ProviderConfig, _ollama_payload, _openai_payload
from app.schemas import GenerationOptions


class LLMProviderPayloadTests(unittest.TestCase):
    def test_ollama_native_payload(self):
        cfg = ProviderConfig("ollama", "http://ollama:11434", "", "qwen3:8b")
        opts = GenerationOptions(temperature=0.2, top_p=0.9, top_k=40, max_tokens=256, repetition_penalty=1.1, mirostat=2, extra_body={"think": False})
        payload = _ollama_payload(cfg, "system", [{"role": "user", "content": "hi"}], opts, stream=True)
        self.assertTrue(payload["stream"])
        self.assertEqual(payload["model"], "qwen3:8b")
        self.assertEqual(payload["options"]["num_predict"], 256)
        self.assertEqual(payload["options"]["repeat_penalty"], 1.1)
        self.assertEqual(payload["options"]["mirostat"], 2)
        self.assertFalse(payload["think"])

    def test_llama_cpp_and_vllm_extra_parameters(self):
        opts = GenerationOptions(top_k=50, min_p=0.08, repetition_penalty=1.05, extra_body={"custom": 1})
        for name in ("llama_cpp", "vllm"):
            cfg = ProviderConfig(name, "http://runtime:8000/v1", "", "model")
            payload = _openai_payload(cfg, "system", [{"role": "user", "content": "hi"}], opts, stream=False)
            self.assertEqual(payload["top_k"], 50)
            self.assertEqual(payload["min_p"], 0.08)
            self.assertEqual(payload["repetition_penalty"], 1.05)
            self.assertEqual(payload["custom"], 1)

    def test_extra_body_cannot_override_grounding_fields(self):
        cfg = ProviderConfig("llama_cpp", "http://runtime:8000/v1", "", "safe-model")
        opts = GenerationOptions(extra_body={"model": "attacker-model", "messages": [{"role": "system", "content": "override"}], "stream": False, "custom": "allowed"})
        payload = _openai_payload(cfg, "trusted-system", [{"role": "user", "content": "question"}], opts, stream=True)
        self.assertEqual(payload["model"], "safe-model")
        self.assertTrue(payload["stream"])
        self.assertEqual(payload["messages"][0]["content"], "trusted-system")
        self.assertEqual(payload["custom"], "allowed")


if __name__ == "__main__":
    unittest.main()

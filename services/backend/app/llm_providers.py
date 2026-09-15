from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterator

import httpx

from .config import settings
from .schemas import GenerationOptions, LLMProviderName


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: str
    api_key: str
    model: str


def _ensure_v1(url: str) -> str:
    url = url.rstrip("/")
    return url if url.endswith("/v1") else f"{url}/v1"


def get_provider_config(provider: LLMProviderName | str | None = None, model: str | None = None) -> ProviderConfig:
    name = str(provider or settings.llm_provider).strip().lower()
    if name == "ollama":
        return ProviderConfig(name, settings.ollama_base_url.rstrip("/"), settings.ollama_api_key, model or settings.ollama_model)
    if name == "llama_cpp":
        return ProviderConfig(name, _ensure_v1(settings.llama_cpp_base_url), settings.llama_cpp_api_key, model or settings.llama_cpp_model)
    if name == "vllm":
        return ProviderConfig(name, _ensure_v1(settings.vllm_base_url), settings.vllm_api_key, model or settings.vllm_model)
    if name != "openai_compatible":
        raise ValueError(f"Unsupported LLM provider: {name}")
    return ProviderConfig(name, settings.llm_base_url.rstrip("/"), settings.llm_api_key, model or settings.llm_model)


def provider_is_configured(provider: str | None = None, model: str | None = None) -> bool:
    try:
        cfg = get_provider_config(provider, model)
    except Exception:
        return False
    return bool(cfg.base_url)


def _headers(cfg: ProviderConfig) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"
    return headers


def discover_models(provider: LLMProviderName | str | None = None) -> list[str]:
    cfg = get_provider_config(provider)
    if not cfg.base_url:
        return []
    timeout = httpx.Timeout(float(settings.llm_timeout_seconds), connect=10.0)
    with httpx.Client(timeout=timeout) as http:
        if cfg.name == "ollama":
            r = http.get(f"{cfg.base_url}/api/tags", headers=_headers(cfg))
            r.raise_for_status()
            return [str(x.get("name")) for x in r.json().get("models", []) if x.get("name")]
        r = http.get(f"{cfg.base_url}/models", headers=_headers(cfg))
        r.raise_for_status()
        data = r.json().get("data", [])
        return [str(x.get("id")) for x in data if isinstance(x, dict) and x.get("id")]


def resolve_model(cfg: ProviderConfig) -> str:
    model = (cfg.model or "").strip()
    if model and model.lower() != "auto":
        return model
    models = discover_models(cfg.name)
    if not models:
        raise RuntimeError(f"No model configured or discovered for provider {cfg.name!r}")
    return models[0]


def _standard_generation_payload(opts: GenerationOptions) -> dict[str, Any]:
    mapping = {
        "temperature": opts.temperature,
        "top_p": opts.top_p,
        "max_tokens": opts.max_tokens,
        "presence_penalty": opts.presence_penalty,
        "frequency_penalty": opts.frequency_penalty,
        "seed": opts.seed,
        "stop": opts.stop,
    }
    return {k: v for k, v in mapping.items() if v is not None}


_RESERVED_REQUEST_KEYS = {"model", "messages", "stream"}


def _safe_extra_body(extra: dict[str, Any]) -> dict[str, Any]:
    """Allow provider-specific extensions without letting callers replace grounded messages/model/stream."""
    return {k: v for k, v in extra.items() if k not in _RESERVED_REQUEST_KEYS}


def _provider_extras(opts: GenerationOptions) -> dict[str, Any]:
    extras = {
        "top_k": opts.top_k,
        "min_p": opts.min_p,
        "repetition_penalty": opts.repetition_penalty,
        "mirostat": opts.mirostat,
        "mirostat_tau": opts.mirostat_tau,
        "mirostat_eta": opts.mirostat_eta,
    }
    out = {k: v for k, v in extras.items() if v is not None}
    out.update(_safe_extra_body(opts.extra_body))
    return out


def _openai_payload(cfg: ProviderConfig, system_prompt: str, messages: list[dict[str, str]], opts: GenerationOptions, *, stream: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": resolve_model(cfg),
        "messages": [{"role": "system", "content": system_prompt}] + messages,
        "stream": stream,
    }
    payload.update(_standard_generation_payload(opts))
    payload.update(_provider_extras(opts))
    return payload


def _ollama_payload(cfg: ProviderConfig, system_prompt: str, messages: list[dict[str, str]], opts: GenerationOptions, *, stream: bool) -> dict[str, Any]:
    options: dict[str, Any] = {}
    mapping = {
        "temperature": opts.temperature,
        "top_p": opts.top_p,
        "top_k": opts.top_k,
        "num_predict": opts.max_tokens,
        "seed": opts.seed,
        "stop": opts.stop,
        "repeat_penalty": opts.repetition_penalty,
        "mirostat": opts.mirostat,
        "mirostat_tau": opts.mirostat_tau,
        "mirostat_eta": opts.mirostat_eta,
    }
    options.update({k: v for k, v in mapping.items() if v is not None})
    payload: dict[str, Any] = {
        "model": resolve_model(cfg),
        "messages": [{"role": "system", "content": system_prompt}] + messages,
        "stream": stream,
    }
    if options:
        payload["options"] = options
    # Native Ollama extensions (format, keep_alive, think, etc.) can be supplied explicitly.
    payload.update(_safe_extra_body(opts.extra_body))
    return payload


def chat(
    *,
    provider: LLMProviderName | str | None,
    model: str | None,
    system_prompt: str,
    messages: list[dict[str, str]],
    generation: GenerationOptions,
) -> tuple[str, dict[str, str]]:
    cfg = get_provider_config(provider, model)
    if not cfg.base_url:
        raise RuntimeError(f"Base URL is not configured for provider {cfg.name!r}")
    timeout = httpx.Timeout(float(settings.llm_timeout_seconds), connect=10.0)
    with httpx.Client(timeout=timeout) as http:
        if cfg.name == "ollama":
            payload = _ollama_payload(cfg, system_prompt, messages, generation, stream=False)
            r = http.post(f"{cfg.base_url}/api/chat", headers=_headers(cfg), json=payload)
            r.raise_for_status()
            data = r.json()
            content = ((data.get("message") or {}).get("content") or "").strip()
            return content, {"provider": cfg.name, "model": str(data.get("model") or payload["model"])}

        payload = _openai_payload(cfg, system_prompt, messages, generation, stream=False)
        r = http.post(f"{cfg.base_url}/chat/completions", headers=_headers(cfg), json=payload)
        r.raise_for_status()
        data = r.json()
        content = data["choices"][0]["message"]["content"]
        return content, {"provider": cfg.name, "model": str(data.get("model") or payload["model"])}


def stream_chat(
    *,
    provider: LLMProviderName | str | None,
    model: str | None,
    system_prompt: str,
    messages: list[dict[str, str]],
    generation: GenerationOptions,
) -> tuple[Iterator[str], dict[str, str]]:
    cfg = get_provider_config(provider, model)
    if not cfg.base_url:
        raise RuntimeError(f"Base URL is not configured for provider {cfg.name!r}")
    resolved_model = resolve_model(cfg)
    cfg = ProviderConfig(cfg.name, cfg.base_url, cfg.api_key, resolved_model)

    def ollama_iter() -> Iterator[str]:
        timeout = httpx.Timeout(float(settings.llm_timeout_seconds), connect=10.0)
        payload = _ollama_payload(cfg, system_prompt, messages, generation, stream=True)
        with httpx.Client(timeout=timeout) as http:
            with http.stream("POST", f"{cfg.base_url}/api/chat", headers=_headers(cfg), json=payload) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    content = ((data.get("message") or {}).get("content") or "")
                    if content:
                        yield content
                    if data.get("done"):
                        break

    def openai_iter() -> Iterator[str]:
        timeout = httpx.Timeout(float(settings.llm_timeout_seconds), connect=10.0)
        payload = _openai_payload(cfg, system_prompt, messages, generation, stream=True)
        with httpx.Client(timeout=timeout) as http:
            with http.stream("POST", f"{cfg.base_url}/chat/completions", headers=_headers(cfg), json=payload) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if raw == "[DONE]":
                        break
                    data = json.loads(raw)
                    choices = data.get("choices") or []
                    if not choices:
                        continue
                    content = ((choices[0].get("delta") or {}).get("content") or "")
                    if content:
                        yield content

    iterator = ollama_iter() if cfg.name == "ollama" else openai_iter()
    return iterator, {"provider": cfg.name, "model": resolved_model}


def configured_providers() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for name in ("openai_compatible", "ollama", "llama_cpp", "vllm"):
        cfg = get_provider_config(name)
        out[name] = {
            "configured": bool(cfg.base_url),
            "model_configured": bool(cfg.model),
            "base_url": cfg.base_url,
            "model": cfg.model,
            "native_api": name == "ollama",
            "streaming": True,
        }
    return out

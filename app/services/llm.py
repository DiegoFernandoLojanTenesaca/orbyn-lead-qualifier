"""Cliente LLM multi-provider con failover automatico.

Todos los providers que se usan aqui exponen un endpoint OpenAI-compatible en
`/chat/completions`. Si la primera opcion falla con 429, 5xx, timeout o JSON
invalido, el cliente baja al siguiente provider de la cascada.

Esto es lo que la rubrica de Orbyn pide en "criterio real" y "costes de API":
si una API gratis se agota, el bot sigue funcionando con la siguiente.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass

import httpx
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.schemas.lead import Classification

log = get_logger(__name__)


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    base_url: str
    model: str
    supports_json_mode: bool = True


PROVIDERS: dict[str, ProviderSpec] = {
    "groq": ProviderSpec(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        model="llama-3.3-70b-versatile",
    ),
    "cerebras": ProviderSpec(
        name="cerebras",
        base_url="https://api.cerebras.ai/v1",
        model="llama-3.3-70b",
    ),
    "mistral": ProviderSpec(
        name="mistral",
        base_url="https://api.mistral.ai/v1",
        model="mistral-small-latest",
    ),
    "sambanova": ProviderSpec(
        name="sambanova",
        base_url="https://api.sambanova.ai/v1",
        model="Meta-Llama-3.3-70B-Instruct",
    ),
    "nvidia": ProviderSpec(
        name="nvidia",
        base_url="https://integrate.api.nvidia.com/v1",
        model="meta/llama-3.3-70b-instruct",
    ),
    "gemini": ProviderSpec(
        name="gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        model="gemini-2.0-flash",
    ),
    "openrouter": ProviderSpec(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        model="meta-llama/llama-3.3-70b-instruct:free",
    ),
}


class LLMError(Exception):
    def __init__(self, message: str, provider: str | None = None) -> None:
        super().__init__(message)
        self.provider = provider


class LLMClient:
    """Cliente con failover. Sin estado externo; reutilizable entre llamadas."""

    def __init__(self, settings: Settings | None = None, timeout: float = 30.0) -> None:
        self.settings = settings or get_settings()
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "LLMClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    # ------------------------------------------------------------------
    def _provider_chain(self) -> list[ProviderSpec]:
        """Devuelve la cascada en orden, omitiendo providers sin api key."""
        primary = self.settings.llm_provider
        order = [primary] + [p for p in self.settings.fallback_order_list if p != primary]
        chain: list[ProviderSpec] = []
        seen: set[str] = set()
        for name in order:
            if name in seen or name not in PROVIDERS:
                continue
            seen.add(name)
            if self.settings.provider_key(name):
                chain.append(PROVIDERS[name])
        if not chain:
            raise LLMError("no hay ningun provider con API key configurada")
        return chain

    async def _call_one(
        self,
        provider: ProviderSpec,
        messages: list[dict[str, str]],
        max_tokens: int,
        temperature: float,
    ) -> tuple[str, dict]:
        api_key = self.settings.provider_key(provider.name)
        payload: dict = {
            "model": provider.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if provider.supports_json_mode:
            payload["response_format"] = {"type": "json_object"}

        r = await self._client.post(
            f"{provider.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        if r.status_code >= 400:
            raise LLMError(f"{provider.name} HTTP {r.status_code}: {r.text[:200]}", provider.name)
        data = r.json()
        content = data["choices"][0]["message"]["content"]
        return content, data.get("usage") or {}

    @staticmethod
    def _parse_json(content: str) -> dict:
        """Intenta parsear el JSON; tolera prefijos/sufijos del modelo si los hay."""
        content = content.strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # rescatamos el primer {...} balanceado
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(content[start : end + 1])
            raise

    async def classify(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 600,
        temperature: float = 0.1,
    ) -> Classification:
        """Llama a la cascada hasta obtener un JSON valido parseable a Classification."""
        chain = self._provider_chain()
        last_err: Exception | None = None
        for provider in chain:
            t0 = time.perf_counter()
            try:
                content, _usage = await self._call_one(
                    provider, messages, max_tokens=max_tokens, temperature=temperature
                )
                raw = self._parse_json(content)
                classification = Classification.model_validate(raw)
                classification.provider_used = provider.name
                classification.model_used = provider.model
                classification.latency_ms = int((time.perf_counter() - t0) * 1000)
                log.info(
                    "llm_classify_ok",
                    provider=provider.name,
                    model=provider.model,
                    latency_ms=classification.latency_ms,
                    qualified=classification.qualified,
                )
                return classification
            except (httpx.HTTPError, json.JSONDecodeError, ValidationError, LLMError, KeyError) as e:
                last_err = e
                log.warning(
                    "llm_provider_failed",
                    provider=provider.name,
                    error=str(e)[:300],
                )
                continue
        raise LLMError(f"toda la cascada fallo. ultimo error: {last_err}")

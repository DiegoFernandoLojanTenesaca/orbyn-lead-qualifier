"""Tests del cliente LLM: failover y resistencia a basura del modelo.

Estos tests NO llaman a la red real. Monkeypatch sobre `_call_one`.
"""
from __future__ import annotations

import pytest

from app.core.config import Settings
from app.schemas.lead import Classification
from app.services.llm import LLMClient, LLMError, PROVIDERS


def _settings(**overrides) -> Settings:
    defaults = dict(
        TELEGRAM_TOKEN="dummy",
        LLM_PROVIDER="groq",
        LLM_FALLBACK_ORDER="groq,cerebras,mistral",
        GROQ_API_KEY="g",
        CEREBRAS_API_KEY="c",
        MISTRAL_API_KEY="m",
    )
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


VALID_JSON = (
    '{"qualified": true, "confidence": 0.9,'
    ' "signals": {"company_type":"consultoria","company_type_match":true,'
    '"employees_estimate":"20","size_match":true,'
    '"location":"Madrid","location_match":true,'
    '"needs":["IA"],"needs_match":true},'
    ' "reason": "ok"}'
)


@pytest.mark.asyncio
async def test_uses_primary_when_ok(monkeypatch):
    client = LLMClient(_settings())

    async def fake_call(self, provider, messages, max_tokens, temperature):
        assert provider.name == "groq"
        return VALID_JSON, {}

    monkeypatch.setattr(LLMClient, "_call_one", fake_call)
    res = await client.classify([{"role": "user", "content": "x"}])
    assert isinstance(res, Classification)
    assert res.provider_used == "groq"
    assert res.qualified is True
    await client.aclose()


@pytest.mark.asyncio
async def test_falls_back_when_primary_fails(monkeypatch):
    client = LLMClient(_settings())
    calls: list[str] = []

    async def fake_call(self, provider, messages, max_tokens, temperature):
        calls.append(provider.name)
        if provider.name == "groq":
            raise LLMError("429 rate limited", provider="groq")
        return VALID_JSON, {}

    monkeypatch.setattr(LLMClient, "_call_one", fake_call)
    res = await client.classify([{"role": "user", "content": "x"}])
    assert calls[0] == "groq"
    assert calls[1] == "cerebras"
    assert res.provider_used == "cerebras"
    await client.aclose()


@pytest.mark.asyncio
async def test_raises_when_all_providers_fail(monkeypatch):
    client = LLMClient(_settings())

    async def fake_call(self, provider, messages, max_tokens, temperature):
        raise LLMError("nope", provider=provider.name)

    monkeypatch.setattr(LLMClient, "_call_one", fake_call)
    with pytest.raises(LLMError):
        await client.classify([{"role": "user", "content": "x"}])
    await client.aclose()


@pytest.mark.asyncio
async def test_skips_providers_without_key(monkeypatch):
    # Solo mistral tiene clave
    client = LLMClient(_settings(GROQ_API_KEY="", CEREBRAS_API_KEY=""))
    chain = client._provider_chain()
    assert [p.name for p in chain] == ["mistral"]
    await client.aclose()


@pytest.mark.asyncio
async def test_tolerates_json_with_garbage_prefix(monkeypatch):
    client = LLMClient(_settings())

    async def fake_call(self, provider, messages, max_tokens, temperature):
        return "Aqui tienes el JSON:\n" + VALID_JSON + "\nGracias.", {}

    monkeypatch.setattr(LLMClient, "_call_one", fake_call)
    res = await client.classify([{"role": "user", "content": "x"}])
    assert res.qualified is True
    await client.aclose()

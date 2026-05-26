"""Tests de robustez operacional:

- Idempotencia por update_id (dedup de reentregas de Telegram).
- Pre-filtro sin LLM (mensajes que no son leads se cortan antes de gastar tokens).
- Footer tecnico en la respuesta de Telegram (provider, modelo, latencia, prompt_version).
- Stats agregados sobre SQLite (sustento del comando /stats).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.agent.nodes import _looks_like_lead, _short_circuit_reply, format_reply, validate_input
from app.schemas.lead import Classification, ICPSignals, LeadInput, LeadRecord
from app.services import storage


def _tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


def _make_record(*, qualified: bool = True, ts: datetime | None = None) -> LeadRecord:
    return LeadRecord(
        received_at=ts or datetime.now(),
        chat_id=1,
        user_id=1,
        username="u",
        text="Consultora 15 empleados Madrid IA",
        qualified=qualified,
        reason="test",
        confidence=0.9,
        provider_used="groq",
        model_used="llama-3.3-70b-versatile",
        latency_ms=700,
        prompt_version="v2",
    )


# ----- Idempotencia -------------------------------------------------------


def test_claim_update_is_idempotent(tmp_path):
    db = _tmp_db(tmp_path)
    # primera vez: True (procesar)
    assert storage.claim_update(101, path=db) is True
    # segunda vez con mismo id: False (skip)
    assert storage.claim_update(101, path=db) is False
    # distinto id: True
    assert storage.claim_update(102, path=db) is True


def test_claim_update_does_not_affect_leads_table(tmp_path):
    """La tabla de updates es independiente: claimar updates no crea leads."""
    db = _tmp_db(tmp_path)
    storage.claim_update(1, path=db)
    storage.claim_update(2, path=db)
    # no hay leads
    s = storage.stats_recent(path=db)
    assert s["total"] == 0


# ----- Pre-filtro sin LLM -------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "hola",
        "Hola!",
        "buenos dias",
        "test",
        "?",
        "👋",
        "👋👋👋",
        "hi",
        "  ",
        "aaa",  # menos de MIN_CHARS
    ],
)
def test_prefilter_rejects_non_lead(text):
    ok, why = _looks_like_lead(text)
    assert ok is False
    assert why  # motivo no vacio


@pytest.mark.parametrize(
    "text",
    [
        "Consultora de RRHH, 22 empleados, Valencia, quieren agente IA.",
        "Bufete de abogados en Bogota, 12 socios, asistente RAG.",
        "Fabrica en Brasil 80 empleados vision computador.",
        "Soy autonomo y trabajo solo quiero un chatbot.",  # NO cualifica pero ES lead
    ],
)
def test_prefilter_lets_real_leads_through(text):
    ok, _ = _looks_like_lead(text)
    assert ok is True


def test_validate_input_short_circuits_on_greeting():
    state = {"lead": LeadInput(text="hola", chat_id=1)}
    out = validate_input(state)
    assert "prefilter_reply" in out
    assert "saludo" in out["prefilter_reply"].lower() or "datos" in out["prefilter_reply"].lower()


def test_format_reply_uses_prefilter_response():
    """Si validate_input genera prefilter_reply, format_reply lo devuelve tal cual,
    sin pasar por el LLM ni mostrar mensaje de error."""
    out = format_reply({"prefilter_reply": "x"})
    assert out["reply_text"] == "x"


def test_short_circuit_message_guides_user():
    msg = _short_circuit_reply("parece un saludo, no un lead")
    assert "lead" in msg.lower()
    assert "ejemplo" in msg.lower() or "consultora" in msg.lower()


# ----- Footer tecnico en respuesta ---------------------------------------


def test_telegram_text_includes_provider_model_latency():
    c = Classification(
        qualified=True,
        confidence=0.9,
        signals=ICPSignals(),
        reason="ok",
        provider_used="groq",
        model_used="llama-3.3-70b-versatile",
        latency_ms=812,
    )
    text = c.to_telegram_text(prompt_version="v2")
    assert "groq" in text
    assert "llama-3.3-70b-versatile" in text
    assert "812ms" in text
    assert "v2" in text


def test_telegram_text_footer_optional_prompt_version():
    c = Classification(
        qualified=False,
        confidence=0.5,
        signals=ICPSignals(),
        reason="x",
        provider_used="cerebras",
        model_used="llama-3.3-70b",
        latency_ms=300,
    )
    text = c.to_telegram_text()  # sin prompt_version
    assert "cerebras" in text
    assert "300ms" in text


def test_telegram_text_footer_when_provider_unknown():
    """Si no hay metadata (LLM no ejecutado por short-circuit), el footer
    no rompe: muestra '?' como sentinel."""
    c = Classification(qualified=False, confidence=0.0, signals=ICPSignals(), reason="x")
    text = c.to_telegram_text()
    assert "?" in text  # sentinel del footer


# ----- Stats -------------------------------------------------------------


def test_stats_aggregates_recent(tmp_path):
    db = _tmp_db(tmp_path)
    # 3 cualificados + 2 no
    for q in [True, True, True, False, False]:
        storage.insert_lead(_make_record(qualified=q), path=db)
    s = storage.stats_recent(path=db)
    assert s["total"] == 5
    assert s["qualified"] == 3
    assert s["not_qualified"] == 2
    assert s["qualified_pct"] == pytest.approx(60.0)
    assert s["avg_latency_ms"] == 700
    assert s["avg_confidence"] == pytest.approx(0.9)


def test_stats_ignores_old_records(tmp_path):
    db = _tmp_db(tmp_path)
    old = datetime.now() - timedelta(hours=48)
    storage.insert_lead(_make_record(qualified=True, ts=old), path=db)
    storage.insert_lead(_make_record(qualified=True), path=db)
    s = storage.stats_recent(hours=24, path=db)
    assert s["total"] == 1  # el viejo queda fuera de la ventana


def test_stats_empty_does_not_divide_by_zero(tmp_path):
    db = _tmp_db(tmp_path)
    s = storage.stats_recent(path=db)
    assert s["total"] == 0
    assert s["qualified_pct"] == 0.0
    assert s["avg_latency_ms"] == 0

"""Tests de schemas: validacion estricta y formateo del mensaje a Telegram."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.lead import Classification, ICPSignals, LeadInput


def test_lead_input_strips_whitespace():
    lead = LeadInput(text="  hola  ", chat_id=1)
    assert lead.text == "hola"


def test_lead_input_rejects_empty():
    with pytest.raises(ValidationError):
        LeadInput(text="   ", chat_id=1)


def test_classification_confidence_bounds():
    base = dict(qualified=False, signals=ICPSignals(), reason="x")
    with pytest.raises(ValidationError):
        Classification(confidence=1.5, **base)
    with pytest.raises(ValidationError):
        Classification(confidence=-0.1, **base)


def test_classification_to_telegram_qualified():
    c = Classification(
        qualified=True,
        confidence=0.9,
        signals=ICPSignals(
            company_type="consultoria",
            company_type_match=True,
            employees_estimate="15",
            size_match=True,
            location="Madrid, Espana",
            location_match=True,
            needs=["automatizacion"],
            needs_match=True,
        ),
        reason="Encaja en los 4 criterios del ICP.",
    )
    out = c.to_telegram_text()
    assert "CUALIFICADO" in out and "❌" not in out
    assert "Confianza: 90%" in out
    assert "consultoria" in out and "Madrid" in out


def test_classification_to_telegram_not_qualified():
    c = Classification(
        qualified=False,
        confidence=0.2,
        signals=ICPSignals(),
        reason="Faltan datos.",
    )
    out = c.to_telegram_text()
    assert "NO CUALIFICADO" in out
    assert "Confianza: 20%" in out

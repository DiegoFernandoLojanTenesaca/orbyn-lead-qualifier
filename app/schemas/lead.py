"""Schemas Pydantic para input del usuario y salida del clasificador."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LeadInput(BaseModel):
    """Texto libre recibido en Telegram."""

    text: str = Field(..., min_length=1, max_length=4000)
    chat_id: int
    user_id: int | None = None
    username: str | None = None
    received_at: datetime = Field(default_factory=datetime.now)

    @field_validator("text")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("texto vacio")
        return v


class ICPSignals(BaseModel):
    """Senales que el LLM debe extraer del texto del lead."""

    model_config = ConfigDict(extra="ignore")

    company_type: str = "unknown"
    company_type_match: bool = False

    employees_estimate: str = "unknown"
    size_match: bool = False

    location: str = "unknown"
    location_match: bool = False

    needs: list[str] = Field(default_factory=list)
    needs_match: bool = False


class Classification(BaseModel):
    """Salida final del agente. Debe ser parseable a 1-1 desde el JSON del LLM."""

    model_config = ConfigDict(extra="ignore")

    qualified: bool
    confidence: float = Field(..., ge=0.0, le=1.0)
    signals: ICPSignals
    reason: str = Field(..., min_length=1, max_length=1200)
    # se rellenan despues del LLM
    provider_used: str | None = None
    model_used: str | None = None
    latency_ms: int | None = None

    def verdict_emoji(self) -> str:
        return "✅" if self.qualified else "❌"

    def to_telegram_text(self) -> str:
        head = f"{self.verdict_emoji()} {'CUALIFICADO' if self.qualified else 'NO CUALIFICADO'}"
        conf = f"Confianza: {int(self.confidence * 100)}%"
        bullets = []
        s = self.signals
        bullets.append(f"• Tipo: {s.company_type} {'✓' if s.company_type_match else '✗'}")
        bullets.append(f"• Tamano: {s.employees_estimate} {'✓' if s.size_match else '✗'}")
        bullets.append(f"• Ubicacion: {s.location} {'✓' if s.location_match else '✗'}")
        needs = ", ".join(s.needs) if s.needs else "—"
        bullets.append(f"• Necesidades: {needs} {'✓' if s.needs_match else '✗'}")
        return "\n".join([head, conf, "", *bullets, "", self.reason])


class LeadRecord(BaseModel):
    """Lo que guardamos en SQLite y enviamos a Google Sheets."""

    received_at: datetime
    chat_id: int
    user_id: int | None
    username: str | None
    text: str
    qualified: bool
    reason: str
    confidence: float
    provider_used: str
    model_used: str
    latency_ms: int
    prompt_version: str

    def as_sheet_row(self) -> list[str]:
        return [
            self.received_at.isoformat(timespec="seconds"),
            str(self.chat_id),
            self.username or "",
            self.text,
            "qualified" if self.qualified else "not_qualified",
            self.reason,
            f"{self.confidence:.2f}",
            self.provider_used,
            self.model_used,
            str(self.latency_ms),
            self.prompt_version,
        ]


SHEET_HEADERS: list[str] = [
    "received_at",
    "chat_id",
    "username",
    "text",
    "decision",
    "reason",
    "confidence",
    "provider",
    "model",
    "latency_ms",
    "prompt_version",
]


VerdictName = Literal["qualified", "not_qualified"]

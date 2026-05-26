"""Estado que viaja por el grafo del agente."""
from __future__ import annotations

from typing import TypedDict

from app.schemas.lead import Classification, LeadInput


class AgentState(TypedDict, total=False):
    """State compartido por todos los nodos del grafo.

    El campo `error` corta la ejecucion: si esta presente, los nodos
    posteriores deben ser no-op y `format_reply` lo convierte en mensaje.
    """

    lead: LeadInput
    sanitized_text: str
    classification: Classification
    reply_text: str
    error: str

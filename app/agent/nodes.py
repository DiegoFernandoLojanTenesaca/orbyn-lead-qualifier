"""Nodos del grafo LangGraph del clasificador.

Pipeline:
  validate_input -> classify -> format_reply

`validate_input` se encarga de:
  - cortar el texto a MAX_INPUT_CHARS,
  - aplicar saneados anti prompt-injection (eliminar marcadores que podrian
    confundir al modelo o cerrar el bloque del USER_PROMPT_TEMPLATE).
"""
from __future__ import annotations

import re

from app.agent.state import AgentState
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.prompts import build_messages
from app.schemas.lead import Classification, ICPSignals
from app.services.llm import LLMClient, LLMError

log = get_logger(__name__)

# Borramos cualquier ocurrencia del cierre del bloque del user prompt,
# para que el lead no pueda "salir" del bloque marcador y simular instrucciones
# de sistema.
_FENCE_PATTERN = re.compile(r"LEAD_INPUT", re.IGNORECASE)


def _sanitize(text: str, max_chars: int) -> str:
    text = text.strip()
    text = _FENCE_PATTERN.sub("LEAD-DATA", text)
    if len(text) > max_chars:
        text = text[:max_chars] + " …[truncado]"
    return text


def validate_input(state: AgentState) -> AgentState:
    lead = state.get("lead")
    if lead is None:
        return {**state, "error": "estado sin lead"}
    settings = get_settings()
    sanitized = _sanitize(lead.text, settings.max_input_chars)
    if not sanitized:
        return {**state, "error": "el mensaje esta vacio"}
    log.info(
        "validate_input_ok",
        chat_id=lead.chat_id,
        chars_in=len(lead.text),
        chars_out=len(sanitized),
    )
    return {**state, "sanitized_text": sanitized}


async def classify(state: AgentState, *, llm: LLMClient | None = None) -> AgentState:
    if state.get("error"):
        return state
    text = state.get("sanitized_text") or ""
    messages = build_messages(text)
    client = llm or LLMClient()
    owns_client = llm is None
    try:
        try:
            classification = await client.classify(messages)
        except LLMError as e:
            log.error("classify_failed", error=str(e))
            return {**state, "error": f"clasificador no disponible: {e}"}
    finally:
        if owns_client:
            await client.aclose()
    return {**state, "classification": classification}


def format_reply(state: AgentState) -> AgentState:
    if state.get("error"):
        return {
            **state,
            "reply_text": (
                "No pude procesar tu mensaje ahora mismo. Detalle tecnico:\n"
                f"{state['error']}\n\n"
                "Vuelve a intentarlo en unos segundos."
            ),
        }
    classification = state.get("classification")
    if classification is None:
        # nunca deberia pasar, pero curamos la salida
        classification = Classification(
            qualified=False,
            confidence=0.0,
            signals=ICPSignals(),
            reason="el modelo no devolvio una clasificacion utilizable.",
        )
    return {**state, "reply_text": classification.to_telegram_text()}

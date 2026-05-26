"""Nodos del grafo LangGraph del clasificador.

Pipeline:
  validate_input -> classify -> format_reply

`validate_input` se encarga de:
  - cortar el texto a MAX_INPUT_CHARS,
  - aplicar saneados anti prompt-injection (eliminar marcadores que podrian
    confundir al modelo o cerrar el bloque del USER_PROMPT_TEMPLATE),
  - **pre-filtro sin LLM**: si el mensaje es claramente no-lead (saludo,
    muy corto, solo emojis) cortamos aqui y respondemos directo, sin
    quemar tokens del clasificador.
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

# Mensajes que NO son leads: saludos sueltos, "?", emojis...
# Si despues de quitar emojis/puntuacion no queda nada util, no llamamos al LLM.
_GREETING_PATTERN = re.compile(
    r"^\s*(hola|hi|hello|holaa+|buenas|buenos dias|buenas tardes|buenas noches|test|prueba|hey|que tal|qtal)\W*$",
    re.IGNORECASE,
)
_EMOJI_AND_PUNCT = re.compile(r"[^\w\sÀ-ÿñÑ]", re.UNICODE)
_LETTERS = re.compile(r"[a-zA-ZÀ-ÿñÑ]")

# Heuristica minima: un lead real tiene al menos *unas pocas* palabras y
# una pista de empresa (numero de empleados, sector, ciudad, tecnologia...).
_MIN_CHARS = 15
_MIN_WORDS = 3


def _sanitize(text: str, max_chars: int) -> str:
    text = text.strip()
    text = _FENCE_PATTERN.sub("LEAD-DATA", text)
    if len(text) > max_chars:
        text = text[:max_chars] + " …[truncado]"
    return text


def _looks_like_lead(text: str) -> tuple[bool, str]:
    """Devuelve (es_lead_plausible, motivo_si_no).

    Es un filtro barato y conservador: si hay duda, dejamos pasar al LLM.
    Solo bloqueamos cosas obvias (saludos, mensajes muy cortos, solo
    emojis/puntuacion). Cualquier descripcion minimamente seria, pasa.
    """
    if not text or len(text) < _MIN_CHARS:
        return False, "el mensaje es demasiado corto, necesito mas datos del lead"
    if _GREETING_PATTERN.match(text):
        return False, "parece un saludo, no un lead"
    # texto sin letras (solo emojis/digitos/puntuacion) no es un lead
    if not _LETTERS.search(text):
        return False, "no detecto texto util, manda los datos del lead"
    stripped = _EMOJI_AND_PUNCT.sub(" ", text).strip()
    words = [w for w in stripped.split() if w]
    if len(words) < _MIN_WORDS:
        return False, "el mensaje tiene muy pocas palabras para clasificarlo"
    return True, ""


def _short_circuit_reply(reason: str) -> str:
    return (
        "🤔 No es un lead para mí.\n\n"
        f"{reason.capitalize()}.\n\n"
        "Mándame los datos del lead en texto libre, por ejemplo:\n"
        "_Consultora, 15 empleados, Madrid, quieren automatizar ventas con IA._"
    )


def validate_input(state: AgentState) -> AgentState:
    lead = state.get("lead")
    if lead is None:
        return {**state, "error": "estado sin lead"}
    settings = get_settings()
    sanitized = _sanitize(lead.text, settings.max_input_chars)
    if not sanitized:
        return {**state, "error": "el mensaje esta vacio"}
    ok, why = _looks_like_lead(sanitized)
    if not ok:
        log.info(
            "prefilter_rejected",
            chat_id=lead.chat_id,
            reason=why,
            chars=len(sanitized),
        )
        # short-circuit: marcamos reply directo y dejamos clasificador en None.
        # No gastamos tokens del LLM; la respuesta es educada y guia al usuario.
        return {
            **state,
            "sanitized_text": sanitized,
            "prefilter_reply": _short_circuit_reply(why),
        }
    log.info(
        "validate_input_ok",
        chat_id=lead.chat_id,
        chars_in=len(lead.text),
        chars_out=len(sanitized),
    )
    return {**state, "sanitized_text": sanitized}


async def classify(state: AgentState, *, llm: LLMClient | None = None) -> AgentState:
    if state.get("error") or state.get("prefilter_reply"):
        # short-circuit del pre-filtro: no llamamos al LLM
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
    if state.get("prefilter_reply"):
        return {**state, "reply_text": state["prefilter_reply"]}
    classification = state.get("classification")
    if classification is None:
        # nunca deberia pasar, pero curamos la salida
        classification = Classification(
            qualified=False,
            confidence=0.0,
            signals=ICPSignals(),
            reason="el modelo no devolvio una clasificacion utilizable.",
        )
    from app.core.prompts import PROMPT_VERSION

    return {**state, "reply_text": classification.to_telegram_text(prompt_version=PROMPT_VERSION)}

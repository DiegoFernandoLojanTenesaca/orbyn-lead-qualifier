"""Servicio de Telegram (long-polling con python-telegram-bot v21)."""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import structlog
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.agent.graph import get_graph
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.prompts import PROMPT_VERSION
from app.schemas.lead import LeadInput, LeadRecord
from app.services.sheets import SheetsClient
from app.services.storage import count_recent, insert_lead, mark_synced

log = get_logger(__name__)

HELP_TEXT = (
    "👋 *orbyn-lead-qualifier*\n\n"
    "Soy un bot que cualifica leads contra el ICP de Orbyn.\n"
    "Mandame los datos de un lead en *texto libre* y te dire si encaja.\n\n"
    "*Ejemplo*:\n"
    "Empresa de consultoria, 15 empleados, Madrid, "
    "quieren automatizar su proceso de ventas con IA.\n\n"
    "Comandos:\n"
    "/start, /help — esta ayuda\n"
    "/id — muestra tu chat\\_id"
)


async def cmd_start(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(HELP_TEXT, parse_mode="Markdown")


async def cmd_id(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id if update.effective_chat else "?"
    await update.effective_message.reply_text(f"chat_id: {chat_id}")


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not msg or not chat or not msg.text:
        return

    settings = get_settings()
    allowed = settings.allowed_chat_ids_set
    if allowed and str(chat.id) not in allowed:
        await msg.reply_text(
            "🔒 Bot privado. Para que el dueno te de acceso pasale tu chat_id:\n"
            f"`{chat.id}`",
            parse_mode="Markdown",
        )
        return

    # rate limit blando por chat: cuenta leads en los ultimos 60 s
    recent = count_recent(chat.id, seconds=60)
    if recent >= settings.rate_limit_per_minute:
        await msg.reply_text(
            f"⏸️ Has enviado {recent} leads en el ultimo minuto. "
            "Espera unos segundos antes de mandar otro."
        )
        return

    request_id = uuid4().hex[:8]
    structlog.contextvars.bind_contextvars(
        request_id=request_id, chat_id=chat.id, user_id=user.id if user else None
    )
    log.info("lead_received", chars=len(msg.text))

    try:
        lead = LeadInput(
            text=msg.text,
            chat_id=chat.id,
            user_id=user.id if user else None,
            username=(user.username if user else None),
            received_at=datetime.now(),
        )
    except Exception as e:
        await msg.reply_text(f"❌ No pude leer tu mensaje: {e}")
        structlog.contextvars.clear_contextvars()
        return

    try:
        await ctx.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)
    except Exception:
        pass

    graph = get_graph()
    result = await graph.ainvoke({"lead": lead})

    reply_text = result.get("reply_text") or "❌ No tengo respuesta."
    await msg.reply_text(reply_text)

    # Persistencia + sheet (no bloqueamos al usuario si esto falla)
    classification = result.get("classification")
    if classification is not None:
        record = LeadRecord(
            received_at=lead.received_at,
            chat_id=lead.chat_id,
            user_id=lead.user_id,
            username=lead.username,
            text=lead.text,
            qualified=classification.qualified,
            reason=classification.reason,
            confidence=classification.confidence,
            provider_used=classification.provider_used or "?",
            model_used=classification.model_used or "?",
            latency_ms=classification.latency_ms or 0,
            prompt_version=PROMPT_VERSION,
        )
        try:
            lead_id = insert_lead(record)
            sheets: SheetsClient | None = ctx.application.bot_data.get("sheets")
            if sheets and sheets.enabled and sheets.append_lead(record):
                mark_synced(lead_id)
        except Exception as e:
            log.error("storage_failed", error=str(e))

    structlog.contextvars.clear_contextvars()


def build_application() -> Application:
    settings = get_settings()
    app = Application.builder().token(settings.telegram_token).build()
    app.bot_data["sheets"] = SheetsClient(settings)
    app.add_handler(CommandHandler(["start", "help"], cmd_start))
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    return app

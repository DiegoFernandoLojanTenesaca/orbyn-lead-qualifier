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
from app.services.storage import claim_update, count_recent, insert_lead, mark_synced, stats_recent

log = get_logger(__name__)

HELP_TEXT = (
    "👋 *orbyn-lead-qualifier*\n\n"
    "Cualifico leads contra el ICP de Orbyn: empresas de *servicios* o "
    "*consultoría*, *≥5 empleados*, en *España o LATAM*, con interés en "
    "*automatización / IA / agentes / RAG / chatbots*.\n\n"
    "Mándame los datos del lead en *texto libre* — analizo, decido y "
    "respondo con razonamiento.\n\n"
    "*Ejemplos*\n\n"
    "✅ _Consultora de RRHH, 22 empleados, Valencia, quieren un agente "
    "para responder consultas internas con su Confluence._\n"
    "→ CUALIFICADO\n\n"
    "❌ _Soy autónomo y vendo cursos de yoga online, trabajo solo. Quiero "
    "un chatbot._\n"
    "→ NO CUALIFICADO (autónomo, falla tipo y tamaño)\n\n"
    "*Comandos*\n"
    "/start, /help — esta ayuda\n"
    "/version — info técnica (modelo, prompt, fallbacks)\n"
    "/stats — leads procesados en las últimas 24 h\n"
    "/id — muestra tu chat\\_id"
)


async def cmd_start(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(HELP_TEXT, parse_mode="Markdown")


async def cmd_id(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id if update.effective_chat else "?"
    await update.effective_message.reply_text(f"chat_id: {chat_id}")


async def cmd_version(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    from app import __version__ as app_version
    from app.services.llm import PROVIDERS

    settings = get_settings()
    primary = settings.llm_provider
    chain = [p for p in settings.fallback_order_list if settings.provider_key(p)]
    primary_model = next((p.model for p in PROVIDERS if p.name == primary), "?")
    text = (
        f"🛠 *orbyn-lead-qualifier* v{app_version}\n\n"
        f"• Prompt: `{PROMPT_VERSION}`\n"
        f"• Primary: `{primary}` ({primary_model})\n"
        f"• Fallback: {' → '.join(chain)}\n"
        f"• Sheets: {'on' if settings.sheets_enabled else 'off'}\n"
        f"• Rate limit: {settings.rate_limit_per_minute}/min por chat\n"
        f"• Max input: {settings.max_input_chars} chars"
    )
    await update.effective_message.reply_text(text, parse_mode="Markdown")


async def cmd_stats(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if not chat:
        return
    s24 = stats_recent(chat_id=chat.id, hours=24)
    sall = stats_recent(chat_id=None, hours=24)
    text = (
        f"📊 *Stats últimas 24 h*\n\n"
        f"*Este chat*: {s24['total']} leads · "
        f"{s24['qualified']} ✅ / {s24['not_qualified']} ❌ "
        f"({s24['qualified_pct']:.0f}% cualifica)\n"
        f"latencia media: {s24['avg_latency_ms']} ms · "
        f"confianza media: {s24['avg_confidence']:.2f}\n\n"
        f"*Global*: {sall['total']} leads · "
        f"{sall['qualified']} ✅ / {sall['not_qualified']} ❌"
    )
    await update.effective_message.reply_text(text, parse_mode="Markdown")


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not msg or not chat or not msg.text:
        return

    # Idempotencia: Telegram puede reentregar el mismo update si nuestra
    # respuesta tarda; sin esto el bot procesa 2x el mismo lead.
    if not claim_update(update.update_id):
        log.info("duplicate_update_skipped", update_id=update.update_id, chat_id=chat.id)
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
    app.add_handler(CommandHandler("version", cmd_version))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    return app

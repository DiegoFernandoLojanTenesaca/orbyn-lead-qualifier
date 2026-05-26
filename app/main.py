"""Entrypoint del bot: arranca polling de Telegram."""
from __future__ import annotations

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.services.telegram_bot import build_application


def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    log = get_logger("app.main")
    log.info("startup", provider=settings.llm_provider, sheets=settings.sheets_enabled)

    app = build_application()
    log.info("polling_start")
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    run()

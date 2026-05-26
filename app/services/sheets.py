"""Cliente Google Sheets (opcional).

Si el .env no trae GOOGLE_SERVICE_ACCOUNT_FILE + GOOGLE_SHEET_ID, este servicio
queda inactivo y `append_lead` es un no-op. El bot sigue funcionando 100%; la
Sheet se puede activar mas adelante sin tocar el resto del codigo.
"""
from __future__ import annotations

from pathlib import Path

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.schemas.lead import SHEET_HEADERS, LeadRecord

log = get_logger(__name__)


class SheetsClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._ws = None
        if not self.settings.sheets_enabled:
            log.info("sheets_disabled", reason="GOOGLE_SERVICE_ACCOUNT_FILE / GOOGLE_SHEET_ID vacios")
            return
        self._open_worksheet()

    def _open_worksheet(self) -> None:
        try:
            import gspread
            from google.oauth2.service_account import Credentials
        except ImportError as e:  # pragma: no cover - solo si las deps no estan
            log.warning("sheets_dep_missing", error=str(e))
            return

        creds_path = Path(self.settings.google_service_account_file)
        if not creds_path.is_file():
            log.warning("sheets_creds_not_found", path=str(creds_path))
            return

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file",
        ]
        creds = Credentials.from_service_account_file(str(creds_path), scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(self.settings.google_sheet_id)
        tab = self.settings.google_sheet_tab
        try:
            ws = sh.worksheet(tab)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=tab, rows=1000, cols=len(SHEET_HEADERS))
            ws.append_row(SHEET_HEADERS)
            log.info("sheets_tab_created", tab=tab)
        # asegura headers si la pestania estaba vacia
        first_row = ws.row_values(1)
        if first_row != SHEET_HEADERS:
            if not first_row:
                ws.append_row(SHEET_HEADERS)
            else:
                log.warning("sheets_headers_mismatch", got=first_row[:3], expected=SHEET_HEADERS[:3])
        self._ws = ws
        log.info("sheets_ready", sheet_id=self.settings.google_sheet_id, tab=tab)

    @property
    def enabled(self) -> bool:
        return self._ws is not None

    def append_lead(self, record: LeadRecord) -> bool:
        if not self.enabled:
            return False
        try:
            self._ws.append_row(record.as_sheet_row(), value_input_option="USER_ENTERED")  # type: ignore[union-attr]
            return True
        except Exception as e:  # gspread expone muchas; preferimos no fallar el flujo
            log.error("sheets_append_failed", error=str(e))
            return False

"""Server-side UI internationalisation helpers.

Centralises the translation strings and helper functions that all route
modules need.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from fastapi import Request

_UI_STRINGS = {
    "no": {
        "err_no_config": "Ingen kundekonfigurasjon funnet. Kjør oppsett først.",
        "err_customer_not_found": "Kunde ikke funnet",
        "err_missing_customer_id": "Mangler customer_id",
        "err_audit_running": "Audit kjører allerede",
        "err_no_audit_running": "Ingen audit kjører",
        "err_no_customers": "Ingen kunder registrert",
        "err_invalid_path": "Ugyldig sti",
        "err_invalid_status": "Ugyldig status",
        "err_missing_title": "Mangler tittel",
        "err_file_too_large": "Filen er for stor (maks 5 MB)",
        "err_invalid_file_type": "Ugyldig filtype",
        "err_no_active_customer": "Ingen aktiv kunde",
        "err_setup_running": "Oppsett kjører allerede",
        "err_bulk_running": "Masseaudit kjører allerede",
        "err_missing_sections": "Ingen seksjoner valgt",
        "err_preset_builtin": "Kan ikke overskrive innebygd forhåndsinnstilling",
        "msg_settings_saved": "Innstillinger lagret",
        "msg_audit_cancelled": "Audit avbrutt",
        "msg_customer_deleted": "Kunde slettet",
        "msg_customer_wiped": "Kundedata slettet",
        "msg_credentials_renewed": "Tilganger fornyet",
        "err_no_audit_data": "Ingen audit-data tilgjengelig",
        "err_no_audit_results": "Ingen audit-resultater tilgjengelig",
        "err_no_config_to_register": "Ingen konfigurasjon å registrere",
        "err_no_data_files": "Ingen datafiler funnet i mappen",
        "err_no_recipient": "Ingen mottakeradresse angitt",
        "err_no_webhook_url": "Ingen webhook-URL",
        "err_no_api_key": "Ingen API-nøkkel konfigurert",
        "err_no_orgs_selected": "Ingen organisasjoner valgt",
        "err_no_report_files": "Ingen rapportfiler funnet",
        "err_no_customer_config": "Ingen kundekonfigurasjon",
        "err_no_key_provided": "Ingen nøkkel oppgitt",
        "err_invalid_key": "Ugyldig nøkkel — må være 32 bytes base64url",
        "err_no_file_path": "Ingen filsti oppgitt",
        "err_file_not_found": "Filen finnes ikke",
        "err_file_must_be_zip": "Filen må være en .zip-fil",
        "err_invalid_backup": "Ugyldig backup — manifest.json mangler",
        "err_preset_not_found": "Preset ikke funnet",
        "err_no_logo": "Ingen logo lastet opp",
        "err_cannot_create_dir": "Kan ikke opprette mappe",
        "err_cannot_create_cert_dir": "Kan ikke opprette sertifikatmappe",
        "err_backup_failed": "Backup feilet",
        "err_restore_failed": "Gjenoppretting feilet",
        "err_name_required": "Navn er påkrevd",
        "err_customer_exists": "En kunde med dette navnet finnes allerede",
    },
    "en": {
        "err_no_config": "No customer configuration found. Run setup first.",
        "err_customer_not_found": "Customer not found",
        "err_missing_customer_id": "Missing customer_id",
        "err_audit_running": "Audit is already running",
        "err_no_audit_running": "No audit is running",
        "err_no_customers": "No customers registered",
        "err_invalid_path": "Invalid path",
        "err_invalid_status": "Invalid status",
        "err_missing_title": "Missing title",
        "err_file_too_large": "File too large (max 5 MB)",
        "err_invalid_file_type": "Invalid file type",
        "err_no_active_customer": "No active customer",
        "err_setup_running": "Setup is already running",
        "err_bulk_running": "Bulk audit is already running",
        "err_missing_sections": "No sections selected",
        "err_preset_builtin": "Cannot overwrite built-in preset",
        "msg_settings_saved": "Settings saved",
        "msg_audit_cancelled": "Audit cancelled",
        "msg_customer_deleted": "Customer deleted",
        "msg_customer_wiped": "Customer data wiped",
        "msg_credentials_renewed": "Credentials renewed",
        "err_no_audit_data": "No audit data available",
        "err_no_audit_results": "No audit results available",
        "err_no_config_to_register": "No configuration to register",
        "err_no_data_files": "No data files found in directory",
        "err_no_recipient": "No recipient address specified",
        "err_no_webhook_url": "No webhook URL",
        "err_no_api_key": "No API key configured",
        "err_no_orgs_selected": "No organizations selected",
        "err_no_report_files": "No report files found",
        "err_no_customer_config": "No customer configuration",
        "err_no_key_provided": "No key provided",
        "err_invalid_key": "Invalid key — must be 32 bytes base64url",
        "err_no_file_path": "No file path specified",
        "err_file_not_found": "File not found",
        "err_file_must_be_zip": "File must be a .zip file",
        "err_invalid_backup": "Invalid backup — manifest.json missing",
        "err_preset_not_found": "Preset not found",
        "err_no_logo": "No logo uploaded",
        "err_cannot_create_dir": "Cannot create directory",
        "err_cannot_create_cert_dir": "Cannot create certificate directory",
        "err_backup_failed": "Backup failed",
        "err_restore_failed": "Restore failed",
        "err_name_required": "Name is required",
        "err_customer_exists": "A customer with this name already exists",
    },
}


def get_ui_lang(request: Request = None) -> str:
    """Get UI language from query param, header, or default."""
    if request:
        lang = request.query_params.get("lang", "")
        if lang in ("no", "en"):
            return lang
        accept = request.headers.get("accept-language", "")
        if "en" in accept.lower():
            return "en"
    return "no"


@lru_cache(maxsize=1)
def _web_strings() -> dict[str, dict[str, str]]:
    """The front-end's language file, as a fallback for this module's table.

    There are two translation tables for one application, and they had already
    drifted: eight keys the routes ask for are only in the JSON, so ``ui_t``
    handed back the key name and the activity log on the home view read
    "log_history_deleted" to whoever deleted a run.

    They are not merged here. Six Norwegian and ten English strings say
    different things in the two tables, several with a ``{placeholder}`` on one
    side only, so a wholesale merge would silently reword messages that work
    today. This only covers keys the table below does not define at all.
    """
    path = Path(__file__).parent / "static" / "ui_i18n.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"no": {}, "en": {}}


def ui_t(key: str, request: Request = None) -> str:
    """Translate a UI string."""
    lang = get_ui_lang(request)
    for table in (_UI_STRINGS.get(lang, {}), _UI_STRINGS["no"]):
        if key in table:
            return table[key]
    web = _web_strings()
    for table in (web.get(lang, {}), web.get("no", {})):
        if key in table:
            return table[key]
    return key

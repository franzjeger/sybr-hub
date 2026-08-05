"""App-level configuration and paths."""

from __future__ import annotations

import json
import os
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir, user_documents_dir

from app.core.version import get_version

APP_NAME = "MSPToolkit"
APP_AUTHOR = "MSP"
VERSION = get_version()

# Directories — env-var overrides for container / non-XDG deployments
# (Docker, custom systemd unit with explicit paths). When set, the env var
# wins over platformdirs.
DATA_DIR   = Path(os.environ.get("MSP_DATA_DIR")   or user_data_dir(APP_NAME, APP_AUTHOR))
CONFIG_DIR = Path(os.environ.get("MSP_CONFIG_DIR") or user_config_dir(APP_NAME, APP_AUTHOR))
CERTS_DIR  = DATA_DIR / "certs"

# Ensure base dirs exist before reading settings
for _d in (DATA_DIR, CONFIG_DIR, CERTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

_DEFAULT_AUDIT_DIR = Path(user_documents_dir()) / "MSPToolkit" / "Audits"


def get_audit_dir() -> Path:
    """Return the configured audit output directory, falling back to Documents/MSPToolkit/Audits."""
    settings_path = CONFIG_DIR / "settings.json"
    if settings_path.exists():
        try:
            import json as _json

            from app.core.encryption import encrypted_read_json
            val = encrypted_read_json(settings_path).get("audit_dir", "")
            if val:
                p = Path(val)
                p.mkdir(parents=True, exist_ok=True)
                return p
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug("Could not read audit_dir from settings: %s", e)
    _DEFAULT_AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    return _DEFAULT_AUDIT_DIR


# Module-level reference — resolved once at import, so it goes stale the
# moment an operator changes the audit directory in Settings.
#
# Deprecated: call get_audit_dir() instead. Kept only so an out-of-tree import
# doesn't break; nothing in app/ uses it any more.
AUDIT_DIR = get_audit_dir()

# Graph permissions required for audit. The single source: GraphClient
# validates against this list, and setup_helper.ps1 is handed it on stdin
# rather than carrying its own copy. It was written out three times — here, in
# GraphClient, and in the PowerShell that actually grants the consent — with a
# "keep in sync" comment standing in for a mechanism. They happened to agree,
# which is the state a drift hazard is in right up until it isn't: adding a
# permission to two of the three grants a consent nothing checks, or requires
# one the wizard never asks for.
REQUIRED_GRAPH_PERMISSIONS: list[str] = [
    "AuditLog.Read.All",
    "Application.Read.All",
    "DeviceManagementApps.Read.All",
    "DeviceManagementConfiguration.Read.All",
    "DeviceManagementManagedDevices.Read.All",
    "DeviceManagementServiceConfig.Read.All",
    "Device.Read.All",
    "Directory.Read.All",
    "Group.Read.All",
    "IdentityRiskyUser.Read.All",
    "Organization.Read.All",
    "Policy.Read.All",
    "Reports.Read.All",
    "RoleManagement.Read.Directory",
    "SecurityEvents.Read.All",
    "Sites.Read.All",
    "SharePointTenantSettings.Read.All",
    "User.Read.All",
    "UserAuthenticationMethod.Read.All",
    "AccessReview.Read.All",
    "SecurityAlert.Read.All",
    "SensitivityLabels.Read.All",
]

GRAPH_APP_ID  = "00000003-0000-0000-c000-000000000000"  # Microsoft Graph
EXO_APP_ID    = "00000002-0000-0ff1-ce00-000000000000"  # Exchange Online
EXO_PERMISSION = "Exchange.ManageAsApp"
AUDIT_APP_NAME = "MSP Toolkit Audit"

AZURE_ROLES = ["Reader", "Cost Management Reader"]

# Setup scopes (interactive / delegated — used only during first-run)
SETUP_SCOPES = [
    "https://graph.microsoft.com/Application.ReadWrite.All",
    "https://graph.microsoft.com/AppRoleAssignment.ReadWrite.All",
    "https://graph.microsoft.com/RoleManagement.ReadWrite.Directory",
    "https://graph.microsoft.com/Directory.ReadWrite.All",
    "https://graph.microsoft.com/Organization.Read.All",
]


# Default branding — empty by default so a fresh install doesn't
# accidentally publish reports under the vendor's own name.
# Operators set their company name in Settings → Branding on first run.
DEFAULT_BRANDING = {
    "company_name": "",
    "report_title": "IT-Sikkerhetsrapport",
    "primary_color": "#0f4c81",
    "accent_color": "#1a6fad",
    "contact_email": "",
    "contact_phone": "",
    "website": "",
}


BRANDING_DIR = CONFIG_DIR / "branding"
BRANDING_DIR.mkdir(parents=True, exist_ok=True)

LOGO_PATH = BRANDING_DIR / "logo.png"


def get_logo_path() -> Path | None:
    """Return the custom logo path if it exists, else None."""
    if LOGO_PATH.exists():
        return LOGO_PATH
    return None


def get_branding() -> dict:
    """Return branding settings, merging defaults with user overrides."""
    settings = load_app_settings()
    branding = {**DEFAULT_BRANDING}
    branding.update(settings.get("branding", {}))
    return branding


DEFAULT_SCHEDULER = {
    "enabled": False,
    "interval_hours": 168,  # weekly
    "audit_all_customers": True,  # True = rotate all customers, False = only active
    "webhook_url": "",  # Teams/Slack incoming webhook URL
    "alert_on": {
        "audit_completed": True,
        "risk_score_drop": 5,      # alert if score drops by N+ (False = disabled)
        "new_risky_users": True,
        "expired_credentials": True,
        "secure_score_drop": 5,    # alert if score drops by N+ (False = disabled)
        "new_nsg_warnings": True,
        "mfa_below_threshold": 80, # alert if MFA coverage < N% (False = disabled)
    },
}

def get_scheduler_config() -> dict:
    settings = load_app_settings()
    scheduler = {**DEFAULT_SCHEDULER}
    saved = settings.get("scheduler", {})
    scheduler.update(saved)
    # Deep-merge alert_on so new defaults are preserved
    merged_alert = {**DEFAULT_SCHEDULER["alert_on"]}
    merged_alert.update(saved.get("alert_on", {}))
    scheduler["alert_on"] = merged_alert
    return scheduler


def get_cert_dir() -> Path:
    """Return the configured certificate directory, falling back to DATA_DIR/certs."""
    settings = load_app_settings()
    val = settings.get("cert_dir", "")
    if val:
        p = Path(val)
        p.mkdir(parents=True, exist_ok=True)
        return p
    CERTS_DIR.mkdir(parents=True, exist_ok=True)
    return CERTS_DIR


def load_app_settings() -> dict:
    from app.core.encryption import encrypted_read_json
    path = CONFIG_DIR / "settings.json"
    if path.exists():
        return encrypted_read_json(path)
    return {}


def save_app_settings(settings: dict) -> None:
    from app.core.encryption import encrypted_write_json
    path = CONFIG_DIR / "settings.json"
    encrypted_write_json(path, settings)



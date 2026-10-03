"""Optional parts of the toolkit, which an administrator switches on or off.

The product is a read-mostly aggregator: customers, audits, findings that
become tickets or plan items, reports, network audit and VPN. Everything in
MODULES is useful to some MSPs and noise or risk to others, so each is a
decision. A switched-off module is not only hidden: its routes answer 404 and
its scheduled jobs do not run.

The first start after this setting exists decides the defaults once and
stores them. A module with evidence of use (stored hosts, a configured key,
scan history) starts on, so an existing install keeps what it uses; a new
install has none of that evidence and starts with everything off.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

SETTINGS_KEY = "modules"


@dataclass(frozen=True)
class Module:
    key: str
    # Views the interface hides while the module is off.
    views: tuple[str, ...] = ()
    # Scheduler task ids that belong to the module.
    tasks: tuple[str, ...] = ()


MODULES: tuple[Module, ...] = (
    Module(
        "remote", views=("hosts", "terminal", "rdp", "ssh", "browser"), tasks=("guacamole_cleanup",)
    ),
    Module("tailscale", views=("tailscale",)),
    Module("pentest", views=("pentest",)),
    Module("provisioning", views=("provision",)),
    # ALSO licensing and Uniweb hosting: distributor finance rather than audit.
    Module("billing", views=("billing",), tasks=("uniweb_sync", "also_price_refresh")),
    Module("ai", views=("ai",)),
)

_BY_KEY = {m.key: m for m in MODULES}


class UnknownModule(KeyError):
    """A module name that does not exist; loud, never a silent yes."""


def get(key: str) -> Module:
    if key not in _BY_KEY:
        raise UnknownModule(f"No module {key!r}. Known: {', '.join(_BY_KEY)}")
    return _BY_KEY[key]


def _stored() -> dict | None:
    from app.core.config import load_app_settings

    value = load_app_settings().get(SETTINGS_KEY)
    return value if isinstance(value, dict) else None


def enabled() -> set[str]:
    """Keys of the modules that are on. Before initialize() has run, none."""
    stored = _stored() or {}
    return {m.key for m in MODULES if stored.get(m.key) is True}


def is_enabled(key: str) -> bool:
    get(key)
    return key in enabled()


def task_allowed(task_id: str) -> bool:
    """False for a scheduled job whose module is off; True for core jobs."""
    on = enabled()
    return all(m.key in on for m in MODULES if task_id in m.tasks)


def hidden_views() -> set[str]:
    on = enabled()
    return {v for m in MODULES if m.key not in on for v in m.views}


def set_enabled(changes: dict[str, bool]) -> set[str]:
    """Switch modules on or off. Returns the keys that are on afterwards."""
    from app.core.config import update_app_settings

    for key in changes:
        get(key)

    def mutate(settings: dict) -> None:
        current = settings.get(SETTINGS_KEY)
        current = dict(current) if isinstance(current, dict) else {}
        for key, value in changes.items():
            current[key] = bool(value)
        settings[SETTINGS_KEY] = current

    update_app_settings(mutate)
    return enabled()


async def _evidence_of_use() -> dict[str, bool]:
    """What this install already uses, from data that only use leaves behind."""
    from app.core.config import load_app_settings
    from app.core.database import get_db

    settings = load_app_settings()

    async def has_rows(table: str) -> bool:
        try:
            async with get_db() as db, db.execute(f"SELECT 1 FROM {table} LIMIT 1") as cur:
                return (await cur.fetchone()) is not None
        except Exception:
            # A table that does not exist yet is no evidence of use.
            return False

    existing_install = await has_rows("users")
    return {
        "remote": await has_rows("ssh_hosts") or await has_rows("ssh_keys"),
        "tailscale": bool(settings.get("tailscale_api_key")),
        "pentest": await has_rows("pentest_scans"),
        # Provisioning leaves nothing behind to detect, so an install that
        # already has accounts keeps it rather than losing it unannounced.
        "provisioning": existing_install,
        "billing": bool(
            settings.get("also_username")
            or settings.get("uniweb_email")
            or await has_rows("also_renewals")
        ),
        "ai": bool(settings.get("claude_api_key")) or settings.get("claude_mode") == "cli",
    }


async def initialize() -> None:
    """Decide the defaults once, on the first start that knows about modules."""
    if _stored() is not None:
        return
    evidence = await _evidence_of_use()
    on = set_enabled({m.key: evidence.get(m.key, False) for m in MODULES})
    log.info("Modules initialised from what this install uses: %s", ", ".join(sorted(on)) or "none")

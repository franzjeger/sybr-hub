"""Customer context — loaded from config file and keyring.

Includes CustomerContext (single-customer dataclass) and
CustomerManager (multi-tenant registry).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.core.config import DATA_DIR

_CUSTOMERS_DIR = DATA_DIR / "customers"
_CUSTOMERS_DIR.mkdir(parents=True, exist_ok=True)

# Tags cache: {customer_id: (tags_list, timestamp)}
_tags_cache: dict[str, tuple[list[str], float]] = {}
_TAGS_CACHE_TTL = 60  # seconds


@dataclass
class CustomerContext:
    # Identity
    customer_name:   str = ""
    primary_domain:  str = ""
    initial_domain:  str = ""
    tenant_id:       str = ""

    # App registration
    client_id:       str = ""
    app_object_id:   str = ""

    # Azure
    subscription_id: str = ""

    # Metadata
    setup_date:      str = ""
    secret_expiry:   str = ""
    cert_expiry:     str = ""

    # Auth mode: "legacy" (per-customer app) or "gdap" (partner delegation)
    auth_mode:       str = "legacy"

    # Runtime paths (set after load)
    config_path:     Path = field(default_factory=Path)
    cert_path:       Path = field(default_factory=Path)

    @classmethod
    def from_file(cls, path: Path) -> "CustomerContext":
        from app.core.encryption import encrypted_read_json
        data = encrypted_read_json(path)
        ctx = cls(
            customer_name   = data.get("CustomerName", ""),
            primary_domain  = data.get("PrimaryDomain", ""),
            initial_domain  = data.get("InitialDomain", ""),
            tenant_id       = data.get("TenantId", ""),
            client_id       = data.get("ClientId", ""),
            app_object_id   = data.get("AppObjectId", ""),
            subscription_id = data.get("SubscriptionId", ""),
            setup_date      = data.get("SetupDate", ""),
            secret_expiry   = data.get("SecretExpiry", ""),
            cert_expiry     = data.get("CertExpiry", ""),
            auth_mode       = data.get("AuthMode", "legacy"),
        )
        ctx.config_path = path
        ctx.cert_path   = path.parent / "audit_cert.pfx"
        return ctx

    def to_dict(self) -> dict:
        return {
            "CustomerName":   self.customer_name,
            "PrimaryDomain":  self.primary_domain,
            "InitialDomain":  self.initial_domain,
            "TenantId":       self.tenant_id,
            "ClientId":       self.client_id,
            "AppObjectId":    self.app_object_id,
            "SubscriptionId": self.subscription_id,
            "SetupDate":      self.setup_date,
            "SecretExpiry":   self.secret_expiry,
            "CertExpiry":     self.cert_expiry,
            "AuthMode":       self.auth_mode,
        }

    def save(self) -> None:
        from app.core.encryption import encrypted_write_json
        encrypted_write_json(self.config_path, self.to_dict())

    # ── Expiry helpers ────────────────────────────────────────────────────────

    def _days_until(self, iso: str) -> Optional[int]:
        if not iso:
            return None
        try:
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            return (dt - datetime.now(timezone.utc)).days
        except ValueError:
            return None

    @property
    def secret_days_left(self) -> Optional[int]:
        return self._days_until(self.secret_expiry)

    @property
    def cert_days_left(self) -> Optional[int]:
        return self._days_until(self.cert_expiry)

    @property
    def is_secret_expiring(self) -> bool:
        d = self.secret_days_left
        return d is not None and d < 30

    @property
    def is_cert_expiring(self) -> bool:
        d = self.cert_days_left
        return d is not None and d < 30

    def __bool__(self) -> bool:
        if self.auth_mode == "gdap":
            return bool(self.tenant_id)
        return bool(self.tenant_id and self.client_id)


# ── Multi-tenant customer registry ──────────────────────────────────────────


def _validate_customer_id(customer_id: str) -> None:
    """Raise ValidationError if customer_id contains path traversal or unsafe characters."""
    from app.core.exceptions import ValidationError
    if not customer_id or '..' in customer_id or '/' in customer_id or '\\' in customer_id or '\x00' in customer_id:
        raise ValidationError("Invalid customer ID")


class CustomerManager:
    """Manage multiple customer configurations stored under DATA_DIR/customers/."""

    @staticmethod
    def list_customers() -> list[dict]:
        """List all saved customer configs."""
        customers = []
        for d in sorted(_CUSTOMERS_DIR.iterdir()):
            if d.is_dir():
                cfg_path = d / "config.json"
                if cfg_path.exists():
                    from app.core.encryption import encrypted_read_json
                    cfg = encrypted_read_json(cfg_path)
                    cfg["_dir"] = str(d)
                    cfg["_id"] = d.name
                    customers.append(cfg)
        return customers

    @staticmethod
    def list_gdap_customers() -> list[dict]:
        """List only GDAP-managed customers."""
        return [c for c in CustomerManager.list_customers() if c.get("AuthMode") == "gdap"]

    @staticmethod
    def list_legacy_customers() -> list[dict]:
        """List only legacy per-app customers."""
        return [c for c in CustomerManager.list_customers() if c.get("AuthMode", "legacy") != "gdap"]

    @staticmethod
    def get_customer(customer_id: str) -> Optional[dict]:
        _validate_customer_id(customer_id)
        d = _CUSTOMERS_DIR / customer_id
        cfg_path = d / "config.json"
        if cfg_path.exists():
            from app.core.encryption import encrypted_read_json
            cfg = encrypted_read_json(cfg_path)
            cfg["_dir"] = str(d)
            cfg["_id"] = d.name
            return cfg
        return None

    @staticmethod
    def save_customer(config: dict) -> str:
        """Save customer config. Returns customer_id."""
        from app.core.encryption import encrypted_write_json
        name = config.get("CustomerName", "unknown")
        customer_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        d = _CUSTOMERS_DIR / customer_id
        d.mkdir(parents=True, exist_ok=True)
        cfg_path = d / "config.json"
        encrypted_write_json(cfg_path, config)
        return customer_id

    @staticmethod
    def get_customer_dir(customer_id: str) -> Path:
        if customer_id:  # allow empty for parent-dir lookups
            _validate_customer_id(customer_id)
        return _CUSTOMERS_DIR / customer_id

    @staticmethod
    def get_cert_path(customer_id: str) -> Path:
        _validate_customer_id(customer_id)
        from app.core.config import CERTS_DIR, get_cert_dir
        cert_dir = get_cert_dir()
        # If a custom cert_dir is configured (not the default), store certs there
        if cert_dir != CERTS_DIR:
            cert_dir.mkdir(parents=True, exist_ok=True)
            return cert_dir / f"{customer_id}.pfx"
        # Default: store alongside the customer config
        return _CUSTOMERS_DIR / customer_id / "cert.pfx"

    @staticmethod
    def get_tags(customer_id: str) -> list[str]:
        """Get tags for a customer (cached with 60s TTL)."""
        _validate_customer_id(customer_id)
        now = time.monotonic()
        cached = _tags_cache.get(customer_id)
        if cached and (now - cached[1]) < _TAGS_CACHE_TTL:
            return cached[0]
        d = _CUSTOMERS_DIR / customer_id
        tags_path = d / "tags.json"
        if tags_path.exists():
            from app.core.encryption import encrypted_read_json
            data = encrypted_read_json(tags_path)
            tags = data if isinstance(data, list) else []
        else:
            tags = []
        _tags_cache[customer_id] = (tags, now)
        return tags

    @staticmethod
    def set_tags(customer_id: str, tags: list[str]) -> None:
        """Set tags for a customer (list of strings)."""
        _validate_customer_id(customer_id)
        _tags_cache.pop(customer_id, None)  # Invalidate cache
        from app.core.encryption import encrypted_write_json
        d = _CUSTOMERS_DIR / customer_id
        d.mkdir(parents=True, exist_ok=True)
        tags_path = d / "tags.json"
        # Deduplicate and strip whitespace
        clean = list(dict.fromkeys(t.strip() for t in tags if t.strip()))
        encrypted_write_json(tags_path, clean)

    @staticmethod
    def delete_customer(customer_id: str) -> None:
        _validate_customer_id(customer_id)
        import shutil
        d = _CUSTOMERS_DIR / customer_id
        if d.exists():
            shutil.rmtree(d)

    @staticmethod
    def set_active(customer_id: str) -> None:
        """Set active customer by writing to active.txt."""
        _validate_customer_id(customer_id)
        from app.core.encryption import encrypted_write_text
        encrypted_write_text(_CUSTOMERS_DIR / "active.txt", customer_id)

    @staticmethod
    def get_active_id() -> Optional[str]:
        p = _CUSTOMERS_DIR / "active.txt"
        if p.exists():
            from app.core.encryption import encrypted_read_text
            return encrypted_read_text(p).strip()
        return None

    @staticmethod
    def get_active() -> Optional[dict]:
        active_id = CustomerManager.get_active_id()
        if active_id:
            return CustomerManager.get_customer(active_id)
        return None

    @staticmethod
    def migrate_legacy() -> Optional[str]:
        """Import legacy single-customer config if it exists."""
        from app.core.credentials import cert_path, config_path, load_config
        legacy_cfg = config_path()
        if not legacy_cfg.exists():
            return None
        cfg = load_config()
        if not cfg:
            return None
        # Check if already migrated
        customer_id = "".join(
            c if c.isalnum() or c in "-_" else "_"
            for c in cfg.get("CustomerName", "unknown")
        )
        if (CustomerManager.get_customer_dir(customer_id) / "config.json").exists():
            return customer_id  # already migrated
        # Save to new location
        cid = CustomerManager.save_customer(cfg)
        # Copy cert if exists
        legacy_cert = cert_path()
        if legacy_cert.exists():
            import shutil
            shutil.copy2(str(legacy_cert), str(CustomerManager.get_cert_path(cid)))
        CustomerManager.set_active(cid)
        return cid


# ── Audit-tree naming ────────────────────────────────────────────────────────
# The audit tree is laid out as <audit_dir>/<customer-dir-name>/<timestamp>/…,
# so the first path segment is the customer selector. That transform was
# open-coded in eight places (collector, scheduler, reports, dashboards, also,
# itglue) and UniFi used a different one, which is how a route that serves
# files out of this tree ended up with no way to tell whose data it was
# handing back. One definition, used by writers and by the access check.

def customer_dir_name(customer_name: str) -> str:
    """Canonical directory name for a customer's audit output."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in customer_name or "")


def _legacy_customer_dir_name(customer_name: str) -> str:
    """The variant UniFi used to write (spaces only). Read-compatibility."""
    return (customer_name or "unknown").replace(" ", "_")


def customers_for_dir_name(segment: str) -> list[dict]:
    """Every customer whose audit directory is named *segment*.

    Returns a list, not a single customer, because the transform is lossy:
    "Acme A/S" and "Acme A S" both become "Acme_A_S". Callers must treat more
    than one match as "requires access to all of them" rather than picking the
    first, or the collision becomes a way to read someone else's data.
    """
    if not segment:
        return []
    out = []
    for c in CustomerManager.list_customers():
        name = c.get("CustomerName", "")
        if segment in (customer_dir_name(name), _legacy_customer_dir_name(name)):
            out.append(c)
    return out

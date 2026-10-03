"""Disposable browser fixture. No operator keyring, directories or integrations."""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def run():
    with tempfile.TemporaryDirectory(prefix="sybr-browser-") as directory:
        root = Path(directory)
        os.environ.update(
            {
                "MSP_DATA_DIR": str(root / "data"),
                "MSP_CONFIG_DIR": str(root / "config"),
                "MSP_AUDIT_DIR": str(root / "audits"),
                "SYBR_KEY_WRAP_SECRET": "browser-fixture-independent-wrap-secret",
            }
        )
        import keyring

        keyring.get_password = lambda *args: None
        keyring.set_password = lambda *args: None
        import app.core.encryption as encryption

        encryption._backup_locations = lambda: [root / "key.backup"]

        async def seed():
            from app.core.auth import _get_jwt_secret, create_user
            from app.core.config import update_app_settings
            from app.core.customer import CustomerManager
            from app.core.database import close_pool, init_db
            from app.core.modules import MODULES
            from app.core.rbac import set_can_write
            from app.models.user import Role
            from app.services.scheduler import DEFAULT_TASKS

            await init_db()
            # Workers log in in parallel the moment the server is up. On an
            # empty database each first login would mint its own signing
            # secret and the overwritten one's tokens would answer 401.
            await _get_jwt_secret()
            for username, role in [
                ("browser-admin", Role.admin),
                ("browser-tech", Role.technician),
                # Its own active customer: the switch-race spec moves it while
                # other specs, signed in as browser-admin, read theirs.
                ("browser-switcher", Role.technician),
            ]:
                user = await create_user(
                    username, "Browser-test123!", username, role=role, all_customers=True
                )
                await set_can_write(user.id, True)
            CustomerManager.save_customer(
                {"CustomerName": "Browser Alpha", "TenantId": ""}, create=True
            )
            # An audited customer, so the findings flow has something to show.
            # Delegated (GDAP) access counts as M365 access without a secret.
            from app.core.config import get_audit_dir
            from app.core.customer import customer_dir_name
            from app.core.encryption import encrypted_write_json

            CustomerManager.save_customer(
                {"CustomerName": "Browser Beta", "TenantId": "beta-tenant", "AuthMode": "gdap"},
                create=True,
            )
            run = get_audit_dir() / customer_dir_name("Browser Beta") / "2026-09-30_120000"
            run.mkdir(parents=True)
            encrypted_write_json(
                run / "_audit_metrics.json",
                {
                    "risk_grade": "C",
                    "risk_score": 58,
                    "mfa_coverage_pct": 72,
                    "secure_score_pct": 41,
                    "total_users": 24,
                    "recommendations": [
                        {
                            "rec_id": "fx-low",
                            "title": "Rydd bort gamle gjestekontoer",
                            "detail": "4 gjester uten innlogging på 180 dager",
                            "priority": "low",
                        },
                        {
                            "rec_id": "fx-crit",
                            "title": "Global administrator uten MFA",
                            "detail": "1 konto med full tilgang kan logge inn uten MFA",
                            "priority": "critical",
                        },
                        {
                            "rec_id": "fx-high",
                            "title": "DMARC mangler for beta.example",
                            "detail": "E-post kan forfalskes i domenets navn",
                            "priority": "high",
                        },
                    ],
                },
            )
            # What the checks last saw, stored the way a TLS check and a
            # firmware read store it: a certificate five days from expiry and
            # an end-of-life access point. No alert channel is set up, so
            # Varsler can only show them by reading this state.
            from datetime import UTC, datetime, timedelta

            from app.services import firmware_inventory, tls_inventory

            await tls_inventory.record_results(
                [
                    {
                        "host": "shop.beta.example",
                        "port": 443,
                        "customer_id": "Browser_Beta",
                        "label": "Browser Beta nettbutikk",
                        "source": "manual",
                        "subject": {"commonName": "shop.beta.example"},
                        "issuer": {"organizationName": "Example CA"},
                        "not_after": (datetime.now(UTC) + timedelta(days=5)).isoformat(),
                        "chain_valid": True,
                    }
                ],
                allowed=None,
                may_add=True,
            )
            await firmware_inventory.record(
                "Browser_Beta",
                "unifi",
                [
                    firmware_inventory.unifi_reading(
                        key="02:00:00:00:00:01",
                        name="Browser AP lager",
                        model="UAP-LR",
                        version="4.3.28",
                    )
                ],
            )
            update_app_settings(
                lambda s: s.update(
                    {
                        "task_scheduler": {key: {"enabled": False} for key in DEFAULT_TASKS},
                        "scheduler": {"enabled": False},
                        # Every optional module on, so every view can be tested.
                        "modules": {m.key: True for m in MODULES},
                    }
                )
            )
            await close_pool()

        asyncio.run(seed())
        # All browser workers share one loopback IP and load the full asset
        # bundle per test. Rate-limit behavior has its own isolated unit tests;
        # the production limit must not turn this suite into a one-minute wait.
        import app.web.middleware.rate_limit as rate_limit

        rate_limit.GENERAL_LIMIT = 10000
        rate_limit.SENSITIVE_LIMIT = 10000
        import uvicorn

        uvicorn.run("app.web.server:app", host="127.0.0.1", port=18099, log_level="warning")


if __name__ == "__main__":
    run()

"""Request models on the settings router: what the SPA sends still saves.

Each route below used to read ``await request.json()`` and pick fields with
``body.get``. The cases are the three that matter for that change: the body the
front-end actually sends, a value of the wrong type, and a key nobody declared.
"""

from __future__ import annotations

from tests.request_body_fixtures import (  # autouse fixtures apply to this module
    _init_db,
    _reset_middleware_state,
    admin_client,
    assert_refused,
    tech_client,
)

# ── POST /api/settings ───────────────────────────────────────────────────────

# What app-settings.js saveSettings() sends, field for field.
GENERAL_FORM = {
    "audit_dir": "",
    "cert_dir": "",
    "itglue_api_key": "",
    "itglue_region": "eu",
    "smtp_server": "smtp.example.no",
    "smtp_port": 2525,
    "smtp_user": "mailer",
    "smtp_password": "app-password",
    "smtp_from": "hub@example.no",
    "email_default_recipient": "ops@example.no",
    "email_auto_send": True,
    "branding": {
        "company_name": "Example MSP",
        "contact_email": "post@example.no",
        "website": "https://example.no",
        "primary_color": "#123456",
    },
}


def _stored() -> dict:
    from app.core.config import load_app_settings

    return load_app_settings()


async def test_the_general_settings_form_still_saves(admin_client):
    r = admin_client.post("/api/settings", json=GENERAL_FORM)

    assert r.status_code == 200, r.text
    stored = _stored()
    assert stored["smtp_server"] == "smtp.example.no"
    assert stored["smtp_port"] == 2525
    assert stored["email_auto_send"] is True
    assert stored["branding"]["company_name"] == "Example MSP"


async def test_a_card_that_echoes_the_whole_get_response_still_saves(admin_client):
    """The ALSO and Tailscale cards send GET /api/settings back, changed.

    Every read-only key that response carries arrives with it, so a key added
    to the GET side has to be accepted here too — this is the test that says so.
    """
    current = admin_client.get("/api/settings").json()
    body = {**current, "tailscale_api_key": "tskey-new", "tailscale_tailnet": "example.no"}
    # The echoed directories are the suite's sandbox, which sits outside the
    # home-or-data-dir rule the handler applies. In an install they are under
    # one of the two; blanking them keeps this test about the read-only keys.
    body.update(audit_dir="", cert_dir="")

    r = admin_client.post("/api/settings", json=body)

    assert r.status_code == 200, r.text
    assert _stored()["tailscale_tailnet"] == "example.no"


async def test_the_masked_secret_is_still_not_stored(admin_client):
    admin_client.post("/api/settings", json={"itglue_api_key": "real-key"})
    admin_client.post("/api/settings", json={"itglue_api_key": "••••••"})

    assert _stored()["itglue_api_key"] == "real-key"


async def test_an_absent_smtp_port_leaves_the_stored_one_alone(admin_client):
    admin_client.post("/api/settings", json={"smtp_port": 2525})
    admin_client.post("/api/settings", json={"itglue_region": "us"})

    assert _stored()["smtp_port"] == 2525


async def test_one_card_saving_leaves_another_cards_settings_alone(admin_client):
    """Saving the ALSO card used to clear the SMTP setup and auto-send."""
    admin_client.post("/api/settings", json=GENERAL_FORM | {"email_auto_send": True})
    admin_client.post("/api/settings", json={"also_username": "partner@example.no"})

    stored = _stored()
    assert stored["smtp_server"] == "smtp.example.no"
    assert stored["smtp_user"] == "mailer"
    assert stored["email_auto_send"] is True
    assert stored["also_username"] == "partner@example.no"


async def test_a_field_sent_empty_still_resets(admin_client):
    admin_client.post("/api/settings", json={"smtp_server": "smtp.example.no"})
    admin_client.post("/api/settings", json={"smtp_server": ""})

    assert "smtp_server" not in _stored()


async def test_a_settings_value_of_the_wrong_type_is_refused(admin_client):
    for body in ({"smtp_port": "not-a-port"}, {"audit_dir": 5}, {"branding": "red"}, [1, 2]):
        assert_refused(admin_client.post("/api/settings", json=body), 422)


async def test_a_misspelt_settings_key_is_refused_not_dropped(admin_client):
    """``smtp_sever`` used to be ignored, and the operator's server never saved."""
    body = assert_refused(
        admin_client.post("/api/settings", json={"smtp_sever": "smtp.example.no"}), 422
    )
    assert "smtp_sever" in body["error"]


async def test_a_bad_autotask_picklist_keeps_its_own_message(admin_client):
    """The handler's numeric check names the field; the model leaves it there."""
    body = assert_refused(
        admin_client.post("/api/settings", json={"autotask_default_priority": "high"}), 400
    )
    assert "autotask_default_priority" in body["error"]


async def test_an_empty_autotask_picklist_still_clears_it(admin_client):
    admin_client.post("/api/settings", json={"autotask_default_queue_id": 7})
    assert _stored()["autotask_default_queue_id"] == 7

    r = admin_client.post("/api/settings", json={"autotask_default_queue_id": ""})

    assert r.status_code == 200, r.text
    assert "autotask_default_queue_id" not in _stored()


# ── POST /api/encryption/key-restore ─────────────────────────────────────────


async def test_an_empty_restore_key_keeps_its_translated_message(admin_client):
    body = assert_refused(admin_client.post("/api/encryption/key-restore", json={"key": " "}), 400)
    assert body["error"] != "err_no_key_provided"


async def test_a_restore_key_of_the_wrong_type_is_refused(admin_client):
    assert_refused(admin_client.post("/api/encryption/key-restore", json={"key": 12345}), 422)
    assert_refused(
        admin_client.post("/api/encryption/key-restore", json={"key": "x", "force": True}), 422
    )


# ── POST /api/alerts/config ──────────────────────────────────────────────────

# What app-integrations.js _alertDoSave() sends.
ALERT_FORM = {
    "enabled": True,
    "notify_teams": True,
    "notify_email": False,
    "email_recipient": "ops@example.no",
    "rules": {
        "ssl_expiry": {"enabled": True, "days": 21},
        "domain_expiry": {"enabled": False, "days": 14},
        "fortigate_threats": {"enabled": True, "threshold": 40},
        "firmware_outdated": {"enabled": True},
        "also_license_expiry": {"enabled": True, "days": 14},
        "mfa_coverage": {"enabled": True, "threshold": 90},
    },
}


async def test_the_alert_form_still_saves(admin_client):
    r = admin_client.post("/api/alerts/config", json=ALERT_FORM)

    assert r.status_code == 200, r.text
    cfg = admin_client.get("/api/alerts/config").json()
    assert cfg["enabled"] is True
    assert cfg["rules"]["ssl_expiry"]["days"] == 21
    assert cfg["rules"]["domain_expiry"]["enabled"] is False


async def test_the_rule_switch_changes_only_what_it_sends(admin_client):
    """The notification view sends ``rules`` alone, copied from the GET."""
    admin_client.post("/api/alerts/config", json=ALERT_FORM)
    rules = admin_client.get("/api/alerts/config").json()["rules"]
    rules["mfa_coverage"]["enabled"] = False

    r = admin_client.post("/api/alerts/config", json={"rules": rules})

    assert r.status_code == 200, r.text
    cfg = admin_client.get("/api/alerts/config").json()
    assert cfg["rules"]["mfa_coverage"] == {"enabled": False, "threshold": 90}
    assert cfg["enabled"] is True, "an absent key must keep its stored value"


async def test_an_unknown_rule_name_is_still_skipped(admin_client):
    r = admin_client.post("/api/alerts/config", json={"rules": {"made_up": {"enabled": True}}})

    assert r.status_code == 200, r.text
    assert "made_up" not in admin_client.get("/api/alerts/config").json()["rules"]


async def test_an_alert_value_of_the_wrong_type_is_refused(admin_client):
    for body in (
        {"rules": {"ssl_expiry": {"days": "many"}}},
        {"rules": ["ssl_expiry"]},
        {"enabled": None},
    ):
        assert_refused(admin_client.post("/api/alerts/config", json=body), 422)


async def test_an_unknown_alert_key_is_refused(admin_client):
    assert_refused(admin_client.post("/api/alerts/config", json={"notify_slack": True}), 422)
    assert_refused(
        admin_client.post("/api/alerts/config", json={"rules": {"ssl_expiry": {"dayz": 3}}}),
        422,
    )


# ── POST /api/scheduler/tasks/config ─────────────────────────────────────────


async def test_a_task_value_that_is_not_an_object_is_refused(admin_client):
    """It used to be skipped without a word."""
    assert_refused(
        admin_client.post("/api/scheduler/tasks/config", json={"uniweb_sync": True}), 422
    )


async def test_an_unknown_task_id_is_still_skipped(admin_client):
    r = admin_client.post("/api/scheduler/tasks/config", json={"no_such_task": {"enabled": True}})
    assert r.status_code == 200, r.text


# ── POST /api/scheduler, as the Settings form sends it ───────────────────────


async def test_the_settings_forms_scheduler_block_saves(admin_client):
    """saveSettings() sends backup_after_audit, which the model did not declare.

    With extra="forbid" that made every save of this block a 422, so the
    scheduler could not be configured from the Settings page at all.
    """
    customer = _customer("Acme")
    r = admin_client.post(
        "/api/scheduler",
        json={
            "enabled": True,
            "audit_all_customers": False,
            "customer_id": customer,
            "interval_hours": 24,
            "webhook_url": "",
            "backup_after_audit": True,
            "alert_on": {
                "audit_completed": True,
                "risk_score_drop": 5,
                "new_risky_users": True,
                "expired_credentials": True,
                "secure_score_drop": False,
                "new_nsg_warnings": True,
                "mfa_below_threshold": 80,
            },
        },
    )

    assert r.status_code == 200, r.text
    stored = admin_client.get("/api/scheduler").json()
    assert stored["backup_after_audit"] is True
    assert stored["interval_hours"] == 24
    assert stored["customer_id"] == customer


async def test_saving_the_webhook_card_leaves_the_schedule_on(admin_client):
    """The webhook card sends only its own fields; it used to switch audits off."""
    admin_client.post("/api/scheduler", json={"enabled": True, "interval_hours": 24})
    r = admin_client.post(
        "/api/scheduler",
        json={"webhook_url": "https://hooks.example.no/x", "alert_on": {"audit_completed": True}},
    )
    assert r.status_code == 200
    block = _stored()["scheduler"]
    assert block["enabled"] is True and block["interval_hours"] == 24
    assert block["webhook_url"] == "https://hooks.example.no/x"


# ── POST /api/scheduler: the one customer the one-customer mode audits ───────
# That mode audited the setup staging slot, the customer set up last. It names
# a customer by id now, and the id is checked before it is stored.


def _customer(name: str) -> str:
    from app.core.customer import CustomerManager

    return CustomerManager.save_customer(
        {"CustomerName": name, "TenantId": f"{name.lower()}-tenant"}, create=True
    )


async def test_one_customer_mode_without_a_customer_is_refused(admin_client):
    body = assert_refused(
        admin_client.post("/api/scheduler", json={"audit_all_customers": False}), 400
    )
    assert body["error_key"] == "err_scheduler_customer_required"
    assert "scheduler" not in _stored(), "the refused mode was stored anyway"


async def test_a_customer_that_does_not_exist_is_refused(admin_client):
    body = assert_refused(
        admin_client.post(
            "/api/scheduler", json={"audit_all_customers": False, "customer_id": "Nobody"}
        ),
        400,
    )
    assert body["error_key"] == "err_scheduler_customer_unknown"


async def test_a_customer_the_admin_cannot_reach_is_refused(admin_client, monkeypatch):
    """An admin reaches every customer today; the check is there for the day that changes."""
    customer = _customer("Acme")

    async def no_access(user, customer_id):
        return customer_id != customer

    monkeypatch.setattr("app.core.rbac.check_customer_access", no_access)
    assert_refused(
        admin_client.post(
            "/api/scheduler", json={"audit_all_customers": False, "customer_id": customer}
        ),
        403,
    )
    assert "scheduler" not in _stored()


async def test_choosing_every_customer_forgets_the_one(admin_client):
    customer = _customer("Acme")
    admin_client.post(
        "/api/scheduler", json={"audit_all_customers": False, "customer_id": customer}
    )
    assert _stored()["scheduler"]["customer_id"] == customer

    r = admin_client.post("/api/scheduler", json={"audit_all_customers": True})

    assert r.status_code == 200, r.text
    assert _stored()["scheduler"]["customer_id"] is None


async def test_the_webhook_card_saves_beside_a_mode_that_names_no_customer(admin_client):
    """Settings from before the id: one customer, none named. They stay as
    they are (the scheduler audits nothing and says so) until someone picks a
    customer, and the card that sends neither field still saves."""
    from app.core.config import update_app_settings

    update_app_settings(
        lambda s: s.__setitem__("scheduler", {"enabled": True, "audit_all_customers": False})
    )

    r = admin_client.post("/api/scheduler", json={"webhook_url": "https://hooks.example.no/x"})

    assert r.status_code == 200, r.text
    block = _stored()["scheduler"]
    assert block["audit_all_customers"] is False and block["customer_id"] is None
    assert block["webhook_url"] == "https://hooks.example.no/x"


# ── GET /api/settings: the server's paths are for the admin ──────────────────

_PATH_KEYS = {
    "audit_dir",
    "audit_dir_default",
    "audit_dir_custom",
    "cert_dir",
    "cert_dir_default",
    "cert_dir_custom",
}


async def test_a_technician_is_not_sent_the_servers_paths(tech_client):
    """The interface shows the storage folders to admins only; the server sent them to all.

    A technician's settings screen reads the rest of the response as before:
    language, branding and the integration cards it is shown.
    """
    r = tech_client.get("/api/settings")

    assert r.status_code == 200, r.text
    body = r.json()
    assert not _PATH_KEYS & set(body), sorted(_PATH_KEYS & set(body))
    assert "branding" in body and "itglue_region" in body


async def test_an_admin_is_sent_the_paths_they_choose(admin_client):
    body = admin_client.get("/api/settings").json()

    assert set(body) >= _PATH_KEYS
    assert body["audit_dir"]

"""The screen for the one feature that writes into a customer's tenant.

I shipped the deployment engine with no controls, which is the same mistake as
the baseline that lived only at an endpoint: a technician would have had to
curl it, so in practice it deployed nothing. These assert the screen is
actually reachable — a view nothing dispatches to is dead markup that still
passes every other test in this suite.
"""

from __future__ import annotations

import pathlib
import re

STATIC = pathlib.Path("app/web/static")


def test_the_script_is_served():
    html = (STATIC / "index.html").read_text(encoding="utf-8")

    assert re.search(r'src="/static/app-policy-deploy\.js', html)


def test_the_view_exists_and_something_dispatches_to_it():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    dispatcher = (STATIC / "app-integrations.js").read_text(encoding="utf-8")

    assert 'id="view-policy-deploy"' in html
    assert "policyDeployLoad()" in dispatcher, "the view is markup nothing opens"


def test_the_menu_entry_is_hidden_from_read_only_accounts():
    """It leads only to actions a read-only account cannot take."""
    html = (STATIC / "index.html").read_text(encoding="utf-8")

    entry = next(
        line for line in html.splitlines() if "showView('policy-deploy')" in line
    )
    assert "data-write" in entry


def test_apply_sends_the_reviewed_fingerprint_not_a_fresh_one():
    """Recomputing it at the moment of the click would confirm whatever the
    tenant looks like then — precisely the state nobody reviewed."""
    js = (STATIC / "app-policy-deploy.js").read_text(encoding="utf-8")
    apply_fn = js.split("async function policyDeployApply")[1]

    assert "fingerprint: _pdPlan.fingerprint" in apply_fn


def test_the_break_glass_field_starts_empty_and_gates_the_button():
    """An unfilled exclusion excludes nobody, in a policy that applies to
    everybody. The template refuses it server-side; the form should not offer
    to send it."""
    js = (STATIC / "app-policy-deploy.js").read_text(encoding="utf-8")

    assert "id=\"pd-breakglass\"" in js
    assert 'id="pd-plan-btn" disabled' in js
    assert "_pdValidate" in js


def test_applying_is_behind_a_typed_confirmation():
    js = (STATIC / "app-policy-deploy.js").read_text(encoding="utf-8")

    assert "showTypedConfirm" in js.split("async function policyDeployApply")[1]


def test_the_screen_reads_state_the_application_actually_keeps():
    """_currentCustomer does not exist — I invented it, and the screen would
    have shown "no customer selected" for every session."""
    js = (STATIC / "app-policy-deploy.js").read_text(encoding="utf-8")
    app = (STATIC / "app.js").read_text(encoding="utf-8")

    assert "_currentCustomer" not in js
    for name in ("_customersActiveId", "_allCustomers"):
        assert name in js
        assert f"var {name}" in app, f"{name} is not a variable app.js declares"


def test_the_restore_panel_is_reachable_from_the_same_screen():
    """An engine with no controls deploys nothing, and a rollback nobody can
    reach is worse than none — it is a promise the interface does not keep."""
    js = (STATIC / "app-policy-deploy.js").read_text(encoding="utf-8")

    assert "policyRestoreLoad()" in js.split("function policyDeployLoad")[1].split("}")[0] or \
        "policyRestoreLoad();" in js
    assert 'id="pd-restore"' in js


def test_a_rollback_still_goes_through_a_plan():
    """The one path where somebody writes into production without reading what
    changes would be the one they take when most rushed."""
    js = (STATIC / "app-policy-deploy.js").read_text(encoding="utf-8")

    assert "policy-restore/" in js and "/plan" in js
    apply_fn = js.split("async function policyRestoreApply")[1]
    assert "fingerprint: _pdRestore.fingerprint" in apply_fn
    assert "showTypedConfirm" in apply_fn

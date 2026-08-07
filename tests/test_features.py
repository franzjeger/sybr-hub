"""What an account reaches, in one table the server and the screen both read.

Roles were applied a route at a time — 84 of 331 endpoints carried a
require_role, and the interface hid nothing. A viewer saw the whole menu,
clicked into things, and met a wall; or met no wall, because the route needing
the check was one of the 247 without one.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from app.core.features import FEATURES, UnknownFeature, allows, available_to, get, views_for
from app.models.user import Role


class _User:
    def __init__(self, role, **caps):
        self.role = role
        self.username = "test"
        for k, v in caps.items():
            setattr(self, k, v)

    def __getattr__(self, name):
        return False


# ── The table itself ─────────────────────────────────────────────────────────

def test_a_typo_raises_rather_than_granting_access():
    """The worst failure this table could have is a silent yes."""
    with pytest.raises(UnknownFeature):
        get("integratoins")


def test_every_feature_key_is_unique():
    keys = [f.key for f in FEATURES]

    assert len(keys) == len(set(keys))


def test_no_view_is_owned_by_two_features():
    """Two owners means one of them decides and nobody knows which."""
    seen: dict[str, str] = {}
    for feature in FEATURES:
        for view in feature.views:
            assert view not in seen, f"{view!r} claimed by {seen[view]!r} and {feature.key!r}"
            seen[view] = feature.key


def test_every_view_in_the_markup_belongs_to_a_feature():
    """A view no feature owns is one nothing can hide — which is how the gap
    this table exists to close reopens, one screen at a time.
    """
    html = pathlib.Path("app/web/static/index.html").read_text(encoding="utf-8")
    in_markup = set(re.findall(r'id="view-([a-z-]+)"', html))
    owned = {v for f in FEATURES for v in f.views}

    assert not (in_markup - owned), f"views no feature owns: {sorted(in_markup - owned)}"


# ── Who reaches what ─────────────────────────────────────────────────────────

def test_a_viewer_reaches_reading_and_nothing_else():
    reachable = set(available_to(_User(Role.viewer)))

    assert "dashboard" in reachable and "customers" in reachable
    assert "settings" not in reachable
    assert "vpn" not in reachable
    assert "users" not in reachable


def test_a_technician_reaches_customer_systems_but_not_the_toolkit_settings():
    reachable = set(available_to(_User(Role.technician)))

    assert {"vpn", "remote", "audit", "network"} <= reachable
    assert "settings" not in reachable
    assert "users" not in reachable


def test_an_admin_reaches_the_toolkit_itself():
    reachable = set(available_to(_User(Role.admin)))

    assert {"settings", "users", "logs", "provisioning"} <= reachable


def test_a_capability_gates_on_top_of_the_role():
    """policy_deploy is technician-level and still needs tenant_write — the
    role says which part of the tool, the capability says whether you may reach
    into somebody's production."""
    without = _User(Role.admin)
    with_it = _User(Role.admin, tenant_write=True)

    assert "policy_deploy" not in available_to(without)
    assert "policy_deploy" in available_to(with_it)


def test_views_follow_the_features_that_own_them():
    assert "vpn" not in views_for(_User(Role.viewer))
    assert "vpn" in views_for(_User(Role.technician))
    assert "policy-deploy" not in views_for(_User(Role.admin))
    assert "policy-deploy" in views_for(_User(Role.admin, tenant_write=True))


def test_a_missing_role_reaches_nothing():
    """An object without a role must not fall through to viewer."""

    class _Nobody:
        role = None

    assert available_to(_Nobody()) == []


# ── The screen reads the same list ───────────────────────────────────────────

def test_the_client_holds_no_copy_of_the_rules():
    """It is sent by /auth/me. A copy is the thing that goes stale, and it goes
    stale in the direction of offering what the server refuses."""
    js = pathlib.Path("app/web/static/app.js").read_text(encoding="utf-8")

    assignments = re.findall(r"_features\s*=\s*([^;\n]+)", js)
    assert assignments, "_features is never assigned"
    for value in assignments:
        assert value.strip() in ("[]", "_me.features || []"), (
            f"_features assigned {value.strip()!r} — the list must come from the server"
        )


def test_the_server_sends_what_it_enforces():
    source = pathlib.Path("app/web/routes/auth.py").read_text(encoding="utf-8")

    assert "available_to(user)" in source
    assert "views_for(user)" in source


def test_feature_gating_is_a_separate_attribute_from_write_gating():
    """"May change things" and "may reach this at all" are different questions,
    and conflating them is how one of them stops being asked."""
    js = pathlib.Path("app/web/static/app.js").read_text(encoding="utf-8")

    assert "data-feature" in js
    assert "data-write" in js


def test_every_navigation_control_is_gated_on_the_view_it_opens():
    """A menu entry nothing hides is the gap this table exists to close,
    reopening one screen at a time."""
    html = pathlib.Path("app/web/static/index.html").read_text(encoding="utf-8")

    unmarked = []
    for m in re.finditer(
        r'''<button\b((?:[^>"]|"[^"]*")*?)onclick="showView\('([a-z-]+)'\)"((?:[^>"]|"[^"]*")*?)>''',
        html,
    ):
        attrs = m.group(1) + m.group(3)
        if "data-view-gate" not in attrs:
            unmarked.append((html[: m.start()].count("\n") + 1, m.group(2)))

    assert not unmarked, (
        "navigation that opens a view without gating on it:\n"
        + "\n".join(f"  line {ln}: showView('{v}')" for ln, v in unmarked)
    )


def test_the_gate_names_the_view_the_button_actually_opens():
    """A gate on the wrong view hides the right thing for the wrong reason, and
    shows the wrong thing for no reason."""
    html = pathlib.Path("app/web/static/index.html").read_text(encoding="utf-8")

    for m in re.finditer(
        r'''<button\b[^>]*?data-view-gate="([a-z-]+)"[^>]*?onclick="showView\('([a-z-]+)'\)"''',
        html,
    ):
        assert m.group(1) == m.group(2), (
            f'gated on "{m.group(1)}" but opens "{m.group(2)}"'
        )

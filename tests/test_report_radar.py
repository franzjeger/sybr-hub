"""Regression tests for the risk radar chart.

The radar is the first thing a technician looks at in a customer report, and
it has five axes but no legend for "we couldn't check this". Every axis it
draws is therefore read as a measurement. ``_build_risk_radar`` used to plot a
default on any axis whose source data was missing:

  * Devices fell back to a literal ``50  # unknown``
  * Azure started at ``80  # default ok`` and only ever went down
  * Data Protection started at a ``50`` baseline
  * Email started at ``100`` and only deducted for domains it found
  * Identity averaged MFA/CA/admin-roles, treating a failed fetch as a zero

Two of those (Azure 80, Email 100) are false assurance — a green axis for a
subscription or a domain set nobody looked at. The others are false alarms,
which send a technician to fix something that may already be correct. The
function's own docstring named the failure mode ("fallback values like
Identity=16, Devices=50") but only guarded it behind ``blocking_data_gaps``,
which ``_compute_risk`` raises for missing MFA and nothing else.

The rule these tests lock in: an axis is drawn only when its inputs carry
``has_data``. Absent data means an absent axis.
"""

from __future__ import annotations

import pytest

from app.reports.generator import T, _build_risk_radar, _render_radar_svg


def _labels(lang: str = "no"):
    t = T(lang)
    return {
        "identity": t.radar_identity,
        "devices": t.radar_devices,
        "email": t.radar_email,
        "azure": t.radar_azure,
        "data": t.radar_data,
    }


def _email_controls(*statuses: str) -> list[dict]:
    """CIS email-category controls with the given statuses, as the compliance
    map would emit them. The radar scores its email axis off these, not off the
    raw spf_dmarc tokens, so the axis can never contradict the compliance table."""
    cat = T("no").cis_cat_email
    return [
        {"cis_id": f"5.2.{i + 1}", "category": cat, "status": s}
        for i, s in enumerate(statuses)
    ]


def _full_context() -> dict:
    """A context where every axis has genuine data behind it."""
    return {
        "risk": {"blocking_data_gaps": []},
        "mfa": {"has_data": True, "pct": 90},
        "ca": {"has_data": True, "enabled": 4},
        "admin_roles": {"has_data": True, "global_admin_count": 3},
        "intune": {"has_data": True, "total": 40, "compliance_pct": 85},
        "spf_dmarc": [{"domain": "example.com", "spf": "OK", "dmarc": "OK"}],
        # The email axis reads the CIS email controls the compliance map already
        # graded (see _build_risk_radar), not spf_dmarc directly. A clean tenant
        # passes SPF, DMARC and DKIM, so the axis lands at 100.
        "compliance": _email_controls("pass", "pass", "pass"),
        "azure": {"has_data": True, "orphaned": 0, "advisor_recs": 2},
        "purview": {
            "has_data": True,
            "sensitivity_label_count": 3,
            "dlp_policy_count": 2,
            "retention_policy_count": 1,
        },
    }


def test_full_data_still_produces_all_five_axes():
    """The fix must not cost coverage on a tenant that was audited cleanly."""
    cats = _build_risk_radar(_full_context())
    assert set(cats) == set(_labels().values())
    assert all(isinstance(v, int) and 0 <= v <= 100 for v in cats.values())


def test_empty_context_draws_nothing():
    assert _build_risk_radar({}) == {}


def test_blocking_data_gaps_still_suppress_the_whole_chart():
    ctx = _full_context()
    ctx["risk"] = {"blocking_data_gaps": ["MFA-dekning utilgjengelig"]}
    assert _build_risk_radar(ctx) == {}


# ── False assurance: an unmeasured axis must never render green ───────────────


def test_missing_azure_data_does_not_plot_a_passing_score():
    """Azure used to start at 80 regardless of whether we saw a subscription.

    A tenant with no Azure audit — or no Azure at all — got a comfortably
    green axis, which is the single most misleading thing this chart can do.
    """
    ctx = _full_context()
    ctx["azure"] = {"has_data": False, "orphaned": 0, "advisor_recs": 0}
    cats = _build_risk_radar(ctx)
    assert _labels()["azure"] not in cats


def test_missing_azure_key_entirely_does_not_plot_a_passing_score():
    ctx = _full_context()
    del ctx["azure"]
    assert _labels()["azure"] not in _build_risk_radar(ctx)


def test_no_email_controls_does_not_plot_perfect_email_security():
    """The axis is the pass-rate of the CIS email controls. When the DNS section
    did not run — or every domain in it was a vendor domain the compliance map
    skips — there are no email controls, and a fabricated 100 would be false
    assurance for a domain set nobody actually scored.
    """
    ctx = _full_context()
    ctx["compliance"] = []
    assert _labels()["email"] not in _build_risk_radar(ctx)


def test_email_controls_that_could_not_be_verified_do_not_plot_an_axis():
    """"info" controls are excluded from the axis exactly as they are excluded
    from compliance_pct — all-info means nothing about email was measured."""
    ctx = _full_context()
    ctx["compliance"] = _email_controls("info", "info", "info")
    assert _labels()["email"] not in _build_risk_radar(ctx)


def test_email_axis_is_the_weighted_pass_rate_of_its_controls():
    """pass = full credit, partial = half, fail = none — the mean, times 100."""
    ctx = _full_context()
    ctx["compliance"] = _email_controls("pass", "partial", "fail")
    cats = _build_risk_radar(ctx)
    assert cats[_labels()["email"]] == 50  # (1.0 + 0.5 + 0.0) / 3 * 100


def test_dmarc_quarantine_does_not_score_a_perfect_email_axis():
    """The C3 regression. p=quarantine tokenises as "WARN (p=quarantine)", which
    the old SPF/DMARC ladder matched under neither MISSING nor WEAK, so the axis
    sat at 100 while CIS 5.2.2 graded that very policy only "partial". Scoring the
    axis off the controls makes the two agree: one partial drags it below 100.
    """
    ctx = _full_context()
    ctx["compliance"] = _email_controls("pass", "partial", "pass")  # DMARC quarantine
    email = _build_risk_radar(ctx)[_labels()["email"]]
    assert email < 100
    assert email == round((1.0 + 0.5 + 1.0) / 3 * 100)  # 83


def test_missing_purview_data_does_not_plot_a_baseline():
    ctx = _full_context()
    ctx["purview"] = {
        "has_data": False,
        "sensitivity_label_count": 0,
        "dlp_policy_count": 0,
        "retention_policy_count": 0,
    }
    assert _labels()["data"] not in _build_risk_radar(ctx)


# ── False alarm: an unmeasured axis must never render red either ──────────────


def test_failed_conditional_access_fetch_is_not_scored_as_zero_policies():
    """has_data=False on CA means the fetch failed, not "no policies".

    Averaging a fabricated 0 into Identity cost ~30 points on a tenant whose
    conditional access may be perfectly configured. Dropping the component
    entirely still moves the average — a measured 100 was holding it up — but
    it must land on the mean of what we *did* measure, not on the mean of what
    we measured plus a zero.
    """
    ctx = _full_context()
    ctx["ca"] = {"has_data": False, "enabled": 0}

    scored = _build_risk_radar(ctx)[_labels()["identity"]]

    # MFA 90 and admin-roles 100 are the only measured components.
    assert scored == int((90 + 100) / 2)
    # What the old code produced by folding in a fabricated ca_score of 0.
    assert scored > int((90 + 0 + 100) / 3)


def test_failed_admin_roles_fetch_does_not_invent_a_middling_score():
    """A zero global-admin count from a failed fetch used to score 50."""
    ctx = _full_context()
    ctx["mfa"] = {"has_data": True, "pct": 100}
    ctx["ca"] = {"has_data": True, "enabled": 5}
    ctx["admin_roles"] = {"has_data": False, "global_admin_count": 0}

    cats = _build_risk_radar(ctx)
    # 100 (MFA) and 100 (CA) with the fabricated 50 excluded.
    assert cats[_labels()["identity"]] == 100


def test_identity_axis_disappears_when_no_component_has_data():
    ctx = _full_context()
    ctx["mfa"] = {"has_data": False, "pct": 0}
    ctx["ca"] = {"has_data": False, "enabled": 0}
    ctx["admin_roles"] = {"has_data": False, "global_admin_count": 0}
    assert _labels()["identity"] not in _build_risk_radar(ctx)


@pytest.mark.parametrize(
    "intune",
    [
        {"has_data": False, "total": 0, "compliance_pct": 0},
        {"has_data": False, "total": 12, "compliance_pct": 0},  # parse failed mid-file
        {"has_data": True, "total": 0, "compliance_pct": 0},    # nothing enrolled
    ],
)
def test_devices_axis_is_omitted_unless_devices_were_actually_counted(intune):
    """The old code plotted a hardcoded 50 for every one of these."""
    ctx = _full_context()
    ctx["intune"] = intune
    assert _labels()["devices"] not in _build_risk_radar(ctx)


def test_devices_axis_uses_compliance_when_devices_exist():
    ctx = _full_context()
    ctx["intune"] = {"has_data": True, "total": 25, "compliance_pct": 64}
    assert _build_risk_radar(ctx)[_labels()["devices"]] == 64


# ── Rendering ─────────────────────────────────────────────────────────────────


def test_chart_is_hidden_rather_than_drawn_with_two_axes():
    """A two-spoke "radar" is a triangle-less shape that reads as broken.

    _render_radar_svg already refused fewer than three axes; now that axes can
    genuinely go missing, that path matters.
    """
    ctx = _full_context()
    ctx["azure"] = {"has_data": False}
    ctx["purview"] = {"has_data": False}
    ctx["intune"] = {"has_data": False, "total": 0}

    cats = _build_risk_radar(ctx)
    assert len(cats) == 2
    assert _render_radar_svg(cats) == ""


def test_three_axes_still_render():
    ctx = _full_context()
    ctx["azure"] = {"has_data": False}
    ctx["purview"] = {"has_data": False}

    cats = _build_risk_radar(ctx)
    assert len(cats) == 3
    svg = _render_radar_svg(cats)
    assert svg.startswith("<svg")
    assert svg.count("<polygon") == 1


def test_radar_labels_are_translated_constants_not_customer_data():
    """The SVG interpolates labels and scores raw, and the template renders it
    with ``| safe``. That is only sound while every label comes from T(lang)
    and every score is an int — assert both, so a future axis keyed on a
    customer domain or policy name fails here rather than shipping an
    injection into the customer-facing report.
    """
    cats = _build_risk_radar(_full_context())
    allowed = set(_labels().values())
    for label, score in cats.items():
        assert label in allowed
        assert isinstance(score, int)
    assert "<" not in "".join(cats)

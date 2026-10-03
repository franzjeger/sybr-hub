"""A recommendation is written once and read for months.

Two things follow, and neither was true before.

It must be readable in the reader's language, not the one the audit happened
to run in — otherwise the only way to see an English recommendation is to run
the audit again in English, which is a strange thing to ask of a report about
last month.

And its identity must survive that. Remediation state was keyed on the
rendered title, so an operator who marked something done in Norwegian found it
open again in English — the same finding, under a name the database had never
seen.
"""

from __future__ import annotations

import json

from app.reports.i18n import Localised
from app.reports.recommendations import _build_recommendations


def _recs(lang="no", *, no_mfa=3, domain="kunde-a.example"):
    return _build_recommendations(
        mfa={"has_data": True, "no_mfa": no_mfa, "mfa_registered": 10, "ca_covered": 2},
        spf_dmarc=[{"domain": domain, "dmarc": "MISSING", "spf": "OK"}],
        secure_score={},
        ext_fwd="",
        risky_users="",
        licenses=[],
        file_contents={},
        lang=lang,
    )


def test_every_recommendation_carries_an_id_and_its_own_recipe():
    for rec in _recs():
        assert rec["rec_id"], f"{rec['title']!r} has no stable id"
        assert rec["title_key"], f"{rec['title']!r} cannot be re-rendered"
        assert rec["detail_key"], f"{rec['title']!r} has no detail key"


def test_ids_are_unique_within_a_run():
    ids = [r["rec_id"] for r in _recs()]
    assert len(ids) == len(set(ids)), f"remediation state would merge: {ids}"


def test_the_id_is_the_same_in_both_languages():
    """The whole point. A different id is a different row in the database."""
    assert [r["rec_id"] for r in _recs("no")] == [r["rec_id"] for r in _recs("en")]


def test_the_id_survives_the_count_changing():
    """Marking an item done must not come undone when the number moves.

    "3 users without MFA" and "5 users without MFA" are the same finding at two
    moments. Only params that name *which* thing a recommendation is about may
    enter the id.
    """
    before = {r["rec_id"] for r in _recs(no_mfa=3)}
    after = {r["rec_id"] for r in _recs(no_mfa=5)}

    assert before == after, f"the id moved with the count: {before ^ after}"


def test_a_different_subject_is_a_different_id():
    """The complement — or every domain would share one remediation row."""
    a = {r["rec_id"] for r in _recs(domain="kunde-a.example")}
    b = {r["rec_id"] for r in _recs(domain="kunde-b.example")}

    assert a != b


def test_the_text_differs_between_languages_even_though_the_id_does_not():
    no = {r["rec_id"]: r["title"] for r in _recs("no")}
    en = {r["rec_id"]: r["title"] for r in _recs("en")}

    assert set(no) == set(en)
    assert any(no[k] != en[k] for k in no), "nothing was actually translated"


# ── The carrier ──────────────────────────────────────────────────────────────


def test_a_localised_string_is_a_string_everywhere_it_matters():
    """It has to survive templates, f-strings and json.dumps untouched.

    That is what let this be added without editing the twenty-eight places a
    recommendation is built.
    """
    from app.reports.i18n import T

    value = T("no")("rec_dmarc_title", domain="x.no")

    assert isinstance(value, str)
    assert json.loads(json.dumps({"t": value}))["t"] == str(value)
    assert f"{value}" == str(value)
    assert value.key == "rec_dmarc_title"
    assert value.params == {"domain": "x.no"}


def test_a_plain_lookup_also_remembers_its_key():
    """t.some_key is used as often as t('some_key') and must carry as much."""
    from app.reports.i18n import T

    value = T("no").rec_dmarc_detail

    assert isinstance(value, Localised)
    assert value.key == "rec_dmarc_detail"
    assert value.params == {}


# ── A CA-excluded privileged/attacked account is its own critical finding ─────


def _excluded_recs(**over):
    base = dict(
        mfa={
            "has_data": True,
            "no_mfa": 1,
            "mfa_registered": 5,
            "ca_covered": 0,
            "users": [
                {
                    "name": "sybr_admin",
                    "upn": "sybr_admin@example.no",
                    "ca_excluded": True,
                    "has_mfa": True,
                    "protected": False,
                },
                {
                    "name": "post",
                    "upn": "post@example.no",
                    "ca_excluded": True,
                    "has_mfa": True,
                    "protected": False,
                },
                {
                    "name": "Ola",
                    "upn": "ola@example.no",
                    "ca_excluded": True,
                    "has_mfa": True,
                    "protected": False,
                },
            ],
        },
        spf_dmarc=[],
        secure_score={},
        ext_fwd="",
        risky_users="",
        licenses=[],
        admin_roles={
            "global_admin_users": [
                {
                    "role": "Global Administrator",
                    "user": "sybr_admin",
                    "email": "sybr_admin@example.no",
                }
            ]
        },
        signin_risk={"brute_force_suspects": ["post@example.no"]},
        file_contents={},
    )
    base.update(over)
    return _build_recommendations(**base)


def test_a_ca_excluded_global_admin_or_attacked_account_is_surfaced_as_critical():
    recs = _excluded_recs()
    excluded = [r for r in recs if r.get("finding_id") == "finding-mfa-excluded"]
    assert len(excluded) == 1, "the excluded GA / brute-forced account must be a top finding"
    rec = excluded[0]
    assert rec["priority"] == "critical"
    joined = " ".join(rec["sub_items"])
    assert "sybr_admin@example.no" in joined, "the Global Admin must be named"
    assert "post@example.no" in joined, "the brute-forced account must be named"
    # Ola is CA-excluded but neither privileged nor attacked — not in THIS finding.
    assert "ola@example.no" not in joined


def test_no_excluded_finding_when_no_excluded_account_is_privileged_or_attacked():
    recs = _excluded_recs(
        admin_roles={"global_admin_users": []},
        signin_risk={"brute_force_suspects": []},
    )
    assert not [r for r in recs if r.get("finding_id") == "finding-mfa-excluded"]


def test_a_high_risk_excluded_account_is_not_counted_by_both_criticals():
    """The double-count the review flagged: a CA-excluded Global Admin showed up
    in finding-mfa (as "without MFA") AND finding-mfa-excluded. It must be one."""
    recs = _build_recommendations(
        mfa={
            "has_data": True,
            "no_mfa": 2,
            "mfa_registered": 5,
            "ca_covered": 0,
            "no_mfa_registered": 0,
            "registered_but_excluded": 2,
            "users": [
                {
                    "name": "sybr_admin",
                    "upn": "sybr_admin@example.no",
                    "ca_excluded": True,
                    "has_mfa": True,
                    "protected": False,
                    "unknown": False,
                },
                {
                    "name": "post",
                    "upn": "post@example.no",
                    "ca_excluded": True,
                    "has_mfa": True,
                    "protected": False,
                    "unknown": False,
                },
            ],
        },
        spf_dmarc=[],
        secure_score={},
        ext_fwd="",
        risky_users="",
        licenses=[],
        admin_roles={"global_admin_users": [{"email": "sybr_admin@example.no"}]},
        signin_risk={"brute_force_suspects": ["post@example.no"]},
        file_contents={},
    )
    mfa_ids = [r["finding_id"] for r in recs if r.get("finding_id", "").startswith("finding-mfa")]
    assert mfa_ids == ["finding-mfa-excluded"], f"double-counted: {mfa_ids}"
    joined = " ".join(item for r in recs for item in r.get("sub_items", []))
    assert joined.count("sybr_admin@example.no") == 1, "named in more than one finding"


def test_rec_mfa_detail_does_not_claim_excluded_users_lack_registration():
    from app.reports.i18n import T

    detail = str(
        T("en")(
            "rec_mfa_detail",
            registered=5,
            ca_covered=0,
            no_mfa_registered=0,
            registered_but_excluded=2,
        )
    )
    assert "neither MFA registered nor CA coverage" not in detail
    assert "excluded from enforcement" in detail


def test_finding_mfa_detail_breakdown_sums_to_its_own_title_count():
    """The card's headline and its breakdown must describe the same population.

    finding-mfa's title is adjusted_no_mfa — no_mfa minus the high-risk excluded
    accounts routed to the separate finding-mfa-excluded critical. If the detail
    keeps enumerating the full no_mfa partition, it re-describes (and re-counts)
    those very accounts: the card then says "1 without enforced MFA" over a
    breakdown that sums to 3, and the excluded admin appears in both criticals.
    """
    recs = _build_recommendations(
        mfa={
            "has_data": True,
            "no_mfa": 3,
            "mfa_registered": 10,
            "ca_covered": 2,
            "no_mfa_registered": 1,
            "registered_but_excluded": 2,
            "users": [
                {
                    "name": "GA1",
                    "upn": "ga1@x.no",
                    "ca_excluded": True,
                    "has_mfa": True,
                    "protected": False,
                    "unknown": False,
                },
                {
                    "name": "GA2",
                    "upn": "ga2@x.no",
                    "ca_excluded": True,
                    "has_mfa": True,
                    "protected": False,
                    "unknown": False,
                },
                {
                    "name": "Plain",
                    "upn": "plain@x.no",
                    "ca_excluded": False,
                    "has_mfa": False,
                    "protected": False,
                    "unknown": False,
                },
            ],
        },
        spf_dmarc=[],
        secure_score={},
        ext_fwd="",
        risky_users="",
        licenses=[],
        admin_roles={"global_admin_users": [{"email": "ga1@x.no"}, {"email": "ga2@x.no"}]},
        file_contents={
            "04_mfa_methods.json": json.dumps(
                {
                    "users": [
                        {
                            "display_name": "Plain",
                            "upn": "plain@x.no",
                            "mfa_registered": False,
                            "ca_covered": False,
                            "ca_excluded": False,
                            "methods": [],
                        },
                        {
                            "display_name": "GA1",
                            "upn": "ga1@x.no",
                            "mfa_registered": True,
                            "ca_covered": False,
                            "ca_excluded": True,
                            "methods": ["app"],
                        },
                        {
                            "display_name": "GA2",
                            "upn": "ga2@x.no",
                            "mfa_registered": True,
                            "ca_covered": False,
                            "ca_excluded": True,
                            "methods": ["app"],
                        },
                    ]
                }
            )
        },
    )
    mfa_rec = next(r for r in recs if r.get("finding_id") == "finding-mfa")
    count = mfa_rec["title_params"]["count"]
    dp = mfa_rec["detail_params"]
    assert count == 1, "the two GAs belong to finding-mfa-excluded, not this count"
    assert count == dp["no_mfa_registered"] + dp["registered_but_excluded"], (
        f"card headline says {count} but its breakdown sums to "
        f"{dp['no_mfa_registered'] + dp['registered_but_excluded']}"
    )
    # And each GA is still named by exactly one critical.
    named = " ".join(item for r in recs for item in r.get("sub_items", []))
    assert named.count("ga1@x.no") == 1 and named.count("ga2@x.no") == 1


# ── The lockout map must match the labels the collector actually emits (F5) ───


def test_lockout_map_covers_every_method_label_the_collector_emits():
    """A key that no collector label matches is a silent hole: the lockout check
    treats the method as unrecognised (assumed usable) and never fires."""
    from app.modules.m365_audit.sections.users_mfa import _METHOD_LABELS
    from app.reports.recommendations import _METHOD_LABEL_TO_POLICY

    emitted = set(_METHOD_LABELS.values()) - {"Password"}  # Password is not MFA
    missing = emitted - set(_METHOD_LABEL_TO_POLICY)
    assert not missing, f"lockout check is blind to real method labels: {missing}"


def test_a_tap_only_user_with_tap_disabled_is_flagged():
    # Regression: the map keyed TAP as "Temporary Access Pass" while the collector
    # emits "Temp Access Pass", so a TAP-only account slipped the lockout check.
    policy = (
        "  AUTHENTICATION METHODS POLICY\n"
        "  temporaryAccessPass     disabled\n"
        "  fido2                   enabled\n"
    )
    recs = _build_recommendations(
        mfa={
            "has_data": True,
            "no_mfa": 0,
            "mfa_registered": 1,
            "ca_covered": 0,
            "users": [
                {
                    "name": "Tap",
                    "upn": "tap@x.no",
                    "methods": "Temp Access Pass",
                    "has_mfa": True,
                    "protected": True,
                    "unknown": False,
                }
            ],
        },
        spf_dmarc=[],
        secure_score={},
        ext_fwd="",
        risky_users="",
        licenses=[],
        file_contents={"09b_auth_methods_policy.txt": policy},
    )
    rec = [r for r in recs if r.get("finding_id") == "finding-auth-method-lockout"]
    assert len(rec) == 1, "a TAP-only user with TAP disabled would be locked out"
    assert "tap@x.no" in " ".join(rec[0]["sub_items"])


# ── A critical finding floors the headline grade (F9) ────────────────────────


def test_a_critical_finding_caps_the_grade():
    from app.reports.risk import _apply_critical_floor

    risk = {"score": 65, "grade": "B", "level": "x", "color": "blue"}
    _apply_critical_floor(risk, [{"priority": "critical"}], "no")
    assert risk["grade"] == "C"
    assert risk["capped_by_criticals"] == 1


def test_no_critical_leaves_the_grade_alone():
    from app.reports.risk import _apply_critical_floor

    risk = {"score": 65, "grade": "B", "level": "x", "color": "blue"}
    _apply_critical_floor(risk, [{"priority": "high"}], "no")
    assert risk["grade"] == "B"


def test_the_floor_never_raises_a_worse_grade():
    from app.reports.risk import _apply_critical_floor

    risk = {"score": 15, "grade": "F", "level": "x", "color": "darkred"}
    _apply_critical_floor(risk, [{"priority": "critical"}], "no")
    assert risk["grade"] == "F"


def test_the_floor_skips_an_ungradeable_tenant():
    from app.reports.risk import _apply_critical_floor

    risk = {"score": None, "grade": "?"}
    _apply_critical_floor(risk, [{"priority": "critical"}], "no")
    assert risk["grade"] == "?"


# ── Unmanaged Entra devices are their own finding (F10b) ──────────────────────


def test_unmanaged_entra_devices_are_raised_as_a_finding():
    recs = _build_recommendations(
        mfa={"has_data": True, "no_mfa": 0, "mfa_registered": 5, "ca_covered": 0, "users": []},
        spf_dmarc=[],
        secure_score={},
        ext_fwd="",
        risky_users="",
        licenses=[],
        intune={
            "has_data": True,
            "total": 7,
            "noncompliant": 0,
            "entra_total": 16,
            "entra_unmanaged": 9,
        },
        file_contents={},
    )
    rec = [r for r in recs if r.get("finding_id") == "finding-entra-unmanaged"]
    assert len(rec) == 1
    assert rec[0]["priority"] == "high"  # 9/16 ≥ 50%


def test_no_unmanaged_devices_no_finding():
    recs = _build_recommendations(
        mfa={"has_data": True, "no_mfa": 0, "mfa_registered": 5, "ca_covered": 0, "users": []},
        spf_dmarc=[],
        secure_score={},
        ext_fwd="",
        risky_users="",
        licenses=[],
        intune={
            "has_data": True,
            "total": 16,
            "noncompliant": 0,
            "entra_total": 16,
            "entra_unmanaged": 0,
        },
        file_contents={},
    )
    assert not [r for r in recs if r.get("finding_id") == "finding-entra-unmanaged"]


# ── Auth-method lockout cross-check (F5) ──────────────────────────────────────

_POLICY_AUTH_DISABLED = (
    "  AUTHENTICATION METHODS POLICY\n"
    "  Method                  State\n"
    "  microsoftAuthenticator  disabled\n"
    "  sms                     disabled\n"
    "  voice                   disabled\n"
    "  fido2                   enabled\n"
)


def _lockout_recs(users):
    return _build_recommendations(
        mfa={
            "has_data": True,
            "no_mfa": 0,
            "mfa_registered": len(users),
            "ca_covered": 0,
            "users": users,
        },
        spf_dmarc=[],
        secure_score={},
        ext_fwd="",
        risky_users="",
        licenses=[],
        file_contents={"09b_auth_methods_policy.txt": _POLICY_AUTH_DISABLED},
    )


def test_a_user_whose_only_methods_are_disabled_is_flagged():
    recs = _lockout_recs(
        [
            {
                "name": "Locked",
                "upn": "locked@x.no",
                "methods": "Authenticator App",
                "has_mfa": True,
                "protected": True,
                "unknown": False,
            },
            {
                "name": "Safe",
                "upn": "safe@x.no",
                "methods": "FIDO2 Key",
                "has_mfa": True,
                "protected": True,
                "unknown": False,
            },
        ]
    )
    rec = [r for r in recs if r.get("finding_id") == "finding-auth-method-lockout"]
    assert len(rec) == 1
    joined = " ".join(rec[0]["sub_items"])
    assert "locked@x.no" in joined, "only-Authenticator user (disabled) must be flagged"
    assert "safe@x.no" not in joined, "user with an enabled method (FIDO2) must not be"


def test_no_lockout_finding_when_every_user_has_an_enabled_method():
    recs = _lockout_recs(
        [
            {
                "name": "Safe",
                "upn": "safe@x.no",
                "methods": "FIDO2 Key, Authenticator App",
                "has_mfa": True,
                "protected": True,
                "unknown": False,
            },
        ]
    )
    assert not [r for r in recs if r.get("finding_id") == "finding-auth-method-lockout"]


# ── Re-rendering on the way out ──────────────────────────────────────────────


def test_the_dashboard_rebuilds_recommendations_in_the_readers_language():
    from app.web.routes.dashboard_overview import relocalise_recommendations

    stored = {
        "recommendations": [
            {
                "title_key": "rec_dmarc_title",
                "title_params": {"domain": "x.no"},
                "detail_key": "rec_dmarc_detail",
                "detail_params": {},
                "title": "DMARC mangler eller er svak på x.no",
                "detail": "norsk",
            },
        ]
    }

    out = relocalise_recommendations(stored, "en")["recommendations"][0]

    assert "DMARC" in out["title"]
    assert out["title"] != "DMARC mangler eller er svak på x.no", "still Norwegian"


def test_a_run_from_before_this_keeps_its_stored_text():
    """No recipe means no re-render. Its own words beat a blank line."""
    from app.web.routes.dashboard_overview import relocalise_recommendations

    stored = {"recommendations": [{"title": "Gammel anbefaling", "detail": "detalj"}]}

    out = relocalise_recommendations(stored, "en")["recommendations"][0]

    assert out["title"] == "Gammel anbefaling"


def test_a_stale_param_set_costs_one_line_not_the_dashboard():
    """Templates change; stored params do not follow them."""
    from app.web.routes.dashboard_overview import relocalise_recommendations

    stored = {
        "recommendations": [
            {
                "title": "kept",
                "detail": "kept",
                "title_key": "rec_dmarc_title",
                "title_params": {"wrong": "param"},
            },
        ]
    }

    out = relocalise_recommendations(stored, "en")["recommendations"][0]

    assert out["title"] == "kept"


# ── Turning an id back into words ────────────────────────────────────────────


def test_a_stored_id_is_resolved_back_to_a_sentence(monkeypatch, tmp_path):
    """The panel shows the finding, not the key it is filed under.

    Storing an id is what lets remediation survive a language change; something
    still has to turn it back into words, and the recommendation it came from
    is the only thing that can.
    """
    from app.core.encryption import encrypted_write_json
    from app.web.routes.dashboard_remediation import _recommendation_titles

    root = tmp_path / "audits"
    run = root / "Acme" / "2026-01-01_0000"
    run.mkdir(parents=True)
    encrypted_write_json(
        run / "_audit_metrics.json",
        {
            "recommendations": [
                {
                    "rec_id": "rec_dmarc_title:x.no",
                    "title": "norsk",
                    "title_key": "rec_dmarc_title",
                    "title_params": {"domain": "x.no"},
                },
            ]
        },
    )
    monkeypatch.setattr("app.core.config.get_audit_dir", lambda: root)
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.get_customer",
        staticmethod(lambda cid: {"CustomerName": "Acme"}),
    )

    titles = _recommendation_titles("Acme", "en")

    assert "DMARC" in titles["rec_dmarc_title:x.no"]
    assert titles["rec_dmarc_title:x.no"] != "norsk", "not re-rendered"


def test_an_id_with_no_matching_finding_is_shown_rather_than_hidden(monkeypatch, tmp_path):
    """Something was actioned that this run does not raise.

    Unlovely to show a raw id, and honest — hiding the row would lose the note
    attached to it.
    """
    from app.web.routes.dashboard_remediation import _recommendation_titles

    root = tmp_path / "audits"
    (root / "Acme").mkdir(parents=True)
    monkeypatch.setattr("app.core.config.get_audit_dir", lambda: root)
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.get_customer",
        staticmethod(lambda cid: {"CustomerName": "Acme"}),
    )

    assert _recommendation_titles("Acme", "no") == {}


# ── Azure Advisor: the category, not its translation ─────────────────────────

_ADVICE = [
    {"category": "Security", "impact": "High", "count": 1, "description": "Lukk port 3389"},
    {
        "category": "HighAvailability",
        "impact": "High",
        "count": 2,
        "description": "Sett opp backup",
    },
]


def _advisor_recs(lang: str) -> dict[str, dict]:
    recs = _build_recommendations(
        mfa={},
        spf_dmarc=[],
        secure_score={},
        ext_fwd="",
        risky_users="",
        licenses=[],
        azure={"advisor_summary": _ADVICE},
        file_contents={},
        lang=lang,
    )
    return {r["rec_id"]: r for r in recs if r.get("title_key") == "rec_advisor_title"}


def test_an_advisor_recommendation_has_one_id_in_both_languages():
    """The id was built from the translated category, "Sikkerhet" or "Security".

    Remediation state recorded in one language was then lost in the other, the
    very thing the language-independent id exists to prevent.
    """
    no, en = _advisor_recs("no"), _advisor_recs("en")

    assert (
        set(no)
        == set(en)
        == {
            "rec_advisor_title:Security",
            "rec_advisor_title:HighAvailability",
        }
    )
    assert no["rec_advisor_title:Security"]["title"].startswith("Azure Advisor (Sikkerhet)")
    assert en["rec_advisor_title:Security"]["title"].startswith("Azure Advisor — Security")


def test_a_stored_advisor_recommendation_is_relabelled_for_the_reader():
    """The label was stored in the run's language and re-rendered as it was."""
    from app.reports.recommendations import relocalise_recommendations

    stored = {"recommendations": list(_advisor_recs("no").values())}
    out = relocalise_recommendations(json.loads(json.dumps(stored)), "en")["recommendations"]

    titles = {r["rec_id"]: r["title"] for r in out}
    assert titles["rec_advisor_title:HighAvailability"].startswith(
        "Azure Advisor — High Availability: 1"
    )


def test_a_run_from_before_reads_with_the_new_id():
    """A run recorded before carries the translated label as its id and "category".

    Its recommendation is read under the id the remediation state was moved to,
    so the dashboard does not show the state as lost until the next audit.
    """
    from app.reports.recommendations import relocalise_recommendations

    stored = {
        "recommendations": [
            {
                "rec_id": "rec_advisor_title:Høy tilgjengelighet",
                "title": "Azure Advisor (Høy tilgjengelighet): 2 anbefaling(er)",
                "title_key": "rec_advisor_title",
                "title_params": {"category": "Høy tilgjengelighet", "count": 2},
            },
            {
                "rec_id": "rec_advisor_title:Unknown",
                "title": "Azure Advisor (Unknown): 3 anbefaling(er)",
                "title_key": "rec_advisor_title",
                "title_params": {"category": "Unknown", "count": 3},
            },
        ]
    }

    known, unknown = relocalise_recommendations(stored, "en")["recommendations"]

    assert known["rec_id"] == "rec_advisor_title:HighAvailability"
    assert known["title"] == "Azure Advisor — High Availability: 2 recommendation(s)"
    assert unknown["rec_id"] == "rec_advisor_title:Unknown", "not a label: left as it was"
    assert unknown["title"] == "Azure Advisor — Unknown: 3 recommendation(s)"


def test_the_frozen_labels_are_the_ones_the_report_used():
    """The migration maps the labels as they were; they must be every label there was."""
    from app.reports.i18n import T
    from app.reports.recommendations import _ADVISOR_LABELS, ADVISOR_CATEGORY_BY_LABEL

    current = {
        str(getattr(T(lang), key)): category
        for category, key in _ADVISOR_LABELS.items()
        for lang in ("no", "en")
    }
    assert current == ADVISOR_CATEGORY_BY_LABEL


async def test_the_migration_moves_state_from_both_old_ids(tmp_path, monkeypatch):
    from app.core import database
    from app.core.database import get_db, run_migrations

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "advisor.db")
    await database.close_pool()
    await run_migrations()

    remediation = [
        # (customer, id, status, updated_at)
        ("kunde-a", "rec_advisor_title:Sikkerhet", "done", "2026-09-01T10:00:00"),
        ("kunde-b", "rec_advisor_title:High Availability", "in_progress", "2026-09-02T10:00:00"),
        # Recorded in both languages: the later decision wins the new id.
        ("kunde-c", "rec_advisor_title:Kostnadsoptimalisering", "done", "2026-09-03T10:00:00"),
        ("kunde-c", "rec_advisor_title:Cost Optimisation", "open", "2026-08-03T10:00:00"),
        # The English id was already the new one; the later Norwegian row wins it.
        ("kunde-d", "rec_advisor_title:Sikkerhet", "ignored", "2026-09-04T10:00:00"),
        ("kunde-d", "rec_advisor_title:Security", "open", "2026-08-04T10:00:00"),
        ("kunde-e", "rec_dmarc_title:kunde-e.example", "done", "2026-09-05T10:00:00"),
    ]
    async with get_db() as conn:
        for customer, rec_id, status, updated in remediation:
            await conn.execute(
                "INSERT INTO remediation_items "
                "(customer_id, recommendation_id, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (customer, rec_id, status, updated, updated),
            )
        # A ticket raised in each language for the same finding and system.
        for n, rec_id in enumerate(("rec_advisor_title:Drift", "rec_advisor_title:Operations")):
            await conn.execute(
                "INSERT INTO finding_tickets "
                "(customer_id, rec_id, system, external_id, created_at) "
                "VALUES ('kunde-a', ?, 'autotask', ?, '2026-09-01T10:00:00')",
                (rec_id, f"T{n}"),
            )
            await conn.execute(
                "INSERT INTO finding_operations "
                "(operation_id, customer_id, rec_id, system, status, created_at, created_by) "
                "VALUES (?, 'kunde-a', ?, 'autotask', 'succeeded', '2026-09-01T10:00:00', 'tech')",
                (f"op-{n}", rec_id),
            )
        await conn.execute("UPDATE schema_version SET version = 23")
        await conn.commit()

    await run_migrations()
    await run_migrations()  # a second run changes nothing

    async with get_db() as conn:
        async with conn.execute(
            "SELECT customer_id, recommendation_id, status FROM remediation_items"
        ) as cur:
            rows = {(r[0], r[1]): r[2] for r in await cur.fetchall()}
        tickets = {}
        for table in ("finding_tickets", "finding_operations"):
            async with conn.execute(f"SELECT rec_id FROM {table} ORDER BY rec_id") as cur:
                tickets[table] = [r[0] for r in await cur.fetchall()]
    await database.close_pool()

    assert rows == {
        ("kunde-a", "rec_advisor_title:Security"): "done",
        ("kunde-b", "rec_advisor_title:HighAvailability"): "in_progress",
        ("kunde-c", "rec_advisor_title:Cost"): "done",
        ("kunde-c", "rec_advisor_title:Cost Optimisation"): "open",
        ("kunde-d", "rec_advisor_title:Security"): "ignored",
        ("kunde-d", "rec_advisor_title:Sikkerhet"): "open",
        ("kunde-e", "rec_dmarc_title:kunde-e.example"): "done",
    }
    # One ticket per finding and system: the first moves, the second keeps its id.
    for table in ("finding_tickets", "finding_operations"):
        assert tickets[table] == [
            "rec_advisor_title:OperationalExcellence",
            "rec_advisor_title:Operations",
        ], table

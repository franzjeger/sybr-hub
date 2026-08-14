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

from app.reports.generator import _build_recommendations
from app.reports.i18n import Localised


def _recs(lang="no", *, no_mfa=3, domain="fonnafly.com"):
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
    a = {r["rec_id"] for r in _recs(domain="fonnafly.com")}
    b = {r["rec_id"] for r in _recs(domain="helifly.no")}

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
        mfa={"has_data": True, "no_mfa": 1, "mfa_registered": 5, "ca_covered": 0,
             "users": [
                 {"name": "sybr_admin", "upn": "sybr_admin@example.no",
                  "ca_excluded": True, "has_mfa": True, "protected": False},
                 {"name": "post", "upn": "post@example.no",
                  "ca_excluded": True, "has_mfa": True, "protected": False},
                 {"name": "Ola", "upn": "ola@example.no",
                  "ca_excluded": True, "has_mfa": True, "protected": False},
             ]},
        spf_dmarc=[], secure_score={}, ext_fwd="", risky_users="", licenses=[],
        admin_roles={"global_admin_users": [
            {"role": "Global Administrator", "user": "sybr_admin", "email": "sybr_admin@example.no"}]},
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


# ── Re-rendering on the way out ──────────────────────────────────────────────

def test_the_dashboard_rebuilds_recommendations_in_the_readers_language():
    from app.web.routes.dashboard_overview import relocalise_recommendations

    stored = {"recommendations": [
        {"title_key": "rec_dmarc_title", "title_params": {"domain": "x.no"},
         "detail_key": "rec_dmarc_detail", "detail_params": {},
         "title": "DMARC mangler eller er svak på x.no", "detail": "norsk"},
    ]}

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

    stored = {"recommendations": [
        {"title": "kept", "detail": "kept",
         "title_key": "rec_dmarc_title", "title_params": {"wrong": "param"}},
    ]}

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
    encrypted_write_json(run / "_audit_metrics.json", {"recommendations": [
        {"rec_id": "rec_dmarc_title:x.no", "title": "norsk",
         "title_key": "rec_dmarc_title", "title_params": {"domain": "x.no"}},
    ]})
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

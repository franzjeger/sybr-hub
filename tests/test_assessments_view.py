"""The assessment-library screen is actually reachable.

The engine (app/core/baseline.py) and the endpoints predate any screen, so for
a while a technician could only reach a baseline by curling
/api/baselines/.../evaluate. This is the same lesson the policy-deploy view
test records: a view nothing dispatches to is dead markup that still passes
every other test. These assert the wiring — script served, view present,
dispatcher branch, feature-gated menu entry, and the strings it needs — so the
library cannot silently stop opening.
"""

from __future__ import annotations

import json
import pathlib
import re

STATIC = pathlib.Path("app/web/static")


def test_the_script_is_served():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert re.search(r'src="/static/app-assessments\.js', html)


def test_the_view_exists_and_something_dispatches_to_it():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    dispatcher = (STATIC / "app-integrations.js").read_text(encoding="utf-8")
    assert 'id="view-assessments"' in html
    assert "assessmentsLoad()" in dispatcher, "the view is markup nothing opens"


def test_the_menu_entry_is_gated_on_the_view_it_opens():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    entry = next(
        line for line in html.splitlines() if "showView('assessments')" in line
    )
    assert 'data-view-gate="assessments"' in entry


def test_a_feature_owns_the_view():
    """test_features enforces this globally; naming it here explains why it is
    viewer-level — browsing baselines and reading conformance is a read."""
    from app.core.features import FEATURES, Role

    owners = [f for f in FEATURES if "assessments" in f.views]
    assert len(owners) == 1, "exactly one feature must own the view"
    assert owners[0].role == Role.viewer


def test_the_strings_the_view_renders_exist_in_both_languages():
    d = json.loads((STATIC / "ui_i18n.json").read_text(encoding="utf-8"))
    for key in (
        "nav_assessments", "hdr_assessments", "msg_assessments_intro",
        "lbl_checks", "lbl_house_standard", "btn_run_assessment",
        "msg_baseline_none_assessed",
    ):
        assert key in d["no"] and key in d["en"], f"{key} missing a translation"


def test_the_evaluate_call_matches_the_backend_route_shape():
    """A typo in the URL here is invisible until someone clicks Run.

    test_frontend_api_calls checks this across the whole app; this pins the one
    call this screen depends on, so a rename of the baselines route breaks a
    test named after the screen it breaks.
    """
    js = (STATIC / "app-assessments.js").read_text(encoding="utf-8")
    assert "/api/baselines/" in js and "/evaluate/" in js
    assert "/latest?lang=" in js

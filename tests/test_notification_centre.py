"""Frame 7a — the notification centre.

The Varsler tab used to render three tables stacked down the page, one per
source: credential expiry, licence renewals, Uniweb hosting. Nothing merged
them, so answering "what should I deal with first" meant reading three
sortings in turn and holding the answer in your head. 7a makes it one stream
grouped by urgency, with severity moved into filter chips.

These assertions are structural rather than visual — they pin the claims the
redesign makes, so the tab cannot quietly regress to three tables or start
showing a control that does not do anything.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

STATIC = pathlib.Path("app/web/static")
JS = (STATIC / "app-dashboard.js").read_text()
CSS = (STATIC / "app.css").read_text()


class TestTheStreamIsMerged:
    def test_all_three_sources_land_in_one_list(self):
        """Each source contributes items to _notifCollect rather than getting
        a table of its own."""
        collect = JS[JS.index("function _notifCollect"):JS.index("function _notifRender")]
        for source in ("credential_expiry", "renewals", "uniweb"):
            assert source in collect, f"{source} is not folded into the stream"

    def test_the_old_per_source_tables_are_gone(self):
        """Three <table> blocks under three headings was the thing being
        replaced; a table creeping back means the merge came undone."""
        alerts = JS[JS.index("async function dashLoadAlerts"):JS.index("// ═══", JS.index("async function dashLoadAlerts"))]
        assert "<table" not in alerts, "the alerts tab is rendering a table again"

    def test_read_state_is_keyed_on_identity_not_position(self):
        """An id built from the list index would mark the wrong alert read as
        soon as one expired and the list shifted."""
        collect = JS[JS.index("function _notifCollect"):JS.index("function _notifRender")]
        ids = re.findall(r"id:\s*'([a-z]+):'\s*\+([^,]+),", collect)
        assert len(ids) == 3, f"expected three id builders, found {ids}"
        for prefix, expr in ids:
            assert "customer" in expr or "item_name" in expr, (
                f"the {prefix} id is not built from what identifies the alert: {expr}"
            )
            assert "idx" not in expr and "index" not in expr, (
                f"the {prefix} id depends on list position"
            )


class TestSeverityIsAFilterNotALayout:
    def test_the_chips_count_the_whole_stream(self):
        """A chip that recounted itself against the filtered view could never
        be clicked back — "Kritisk 3" would become "Kritisk 3 of 3" and the
        other chips would read zero."""
        render = JS[JS.index("function _notifRender"):JS.index("function _notifSelect")]
        counts_at = render.index("var counts")
        filter_at = render.index("var shown")
        assert counts_at < filter_at, (
            "the counts are computed after the filter, so the chips describe "
            "the filtered view rather than the stream"
        )

    @pytest.mark.parametrize("sev", ["critical", "warning", "info"])
    def test_every_severity_has_one_vocabulary(self, sev):
        """Colour, dot and badge come from a single table, so a colour cannot
        mean two things on one screen."""
        assert f"{sev}:" in JS[JS.index("var _SEV"):JS.index("function _notifDays")]

    def test_unread_is_not_signalled_by_colour_alone(self):
        """A 5% tint is invisible to plenty of people; the weight change is
        what actually carries it."""
        assert ".notif-row.unread { background:" in CSS
        assert ".notif-row.unread .notif-title { font-weight: 700; }" in CSS


class TestNoControlLiesAboutWhatItDoes:
    def test_the_rule_toggles_read_the_real_config(self):
        """The sidebar in the design is a set of switches. They are wired to
        /api/alerts/config, not to a local array that forgets on reload."""
        assert "/api/alerts/config" in JS
        sidebar = JS[JS.index("function _notifSidebar"):JS.index("async function notifToggleRule")]
        assert "window._notifConfig" in sidebar

    def test_a_non_admin_sees_the_switches_disabled(self):
        """Writing the config is admin-only server-side. Showing a technician
        a live-looking switch that 403s is worse than showing a dead one."""
        sidebar = JS[JS.index("function _notifSidebar"):JS.index("async function notifToggleRule")]
        # Match the conditional itself, not the word "disabled" — msg_alerts_disabled
        # contains it too, so a looser check passed even with the guard removed.
        assert re.search(r"isAdmin\s*\?\s*''\s*:\s*' disabled'", sidebar), (
            "the switches are not disabled for a non-admin"
        )

    def test_a_rejected_toggle_snaps_back(self):
        """Leaving the switch showing a state the server refused would make
        the screen disagree with the system it describes."""
        toggle = JS[JS.index("async function notifToggleRule"):]
        assert "if (!saved)" in toggle and "_notifRender()" in toggle

    def test_the_switch_is_a_real_checkbox(self):
        """So it keeps its keyboard and screen-reader behaviour."""
        assert '<input type="checkbox"' in JS[JS.index("function _notifSidebar"):]
        assert ".switch input:focus-visible ~ .track" in CSS, "no visible focus ring"

    def test_alerts_being_switched_off_is_stated(self):
        """Rules that are on inside a feature that is off send nothing. The
        sidebar says so rather than showing seven enabled switches."""
        assert "msg_alerts_disabled" in JS

    def test_read_state_says_where_it_lives(self):
        """It is per-browser. Two technicians will disagree, and the screen
        admits that instead of implying a shared inbox."""
        assert "msg_read_local" in JS
        assert "localStorage" in JS


class TestTheGroupingMatchesTheData:
    def test_groups_are_urgency_bands_not_calendar_days(self):
        """The design groups by "I dag" / "Tidligere denne uken", which suits
        an event feed. These alerts are forward-looking state whose only
        timestamp is a future expiry date, so a "today" heading would label
        the rows with something that is not true of them.
        """
        render = JS[JS.index("function _notifRender"):JS.index("function _notifSelect")]
        assert "grp_now" in render and "grp_month" in render
        assert "n.days <= 7" in render, "the bands are not derived from days remaining"

    def test_an_item_with_no_deadline_still_appears(self):
        """Three bands whose tests do not cover null would drop those rows off
        the screen entirely rather than showing them last."""
        render = JS[JS.index("function _notifRender"):JS.index("function _notifSelect")]
        assert "grp_other" in render


def test_every_string_is_in_both_languages():
    table = json.loads((STATIC / "ui_i18n.json").read_text())
    # The lookahead keeps `.split('a')` and friends out: only a bare `t(`
    # is the translator, not any identifier that happens to end in one.
    keys = set(re.findall(r"(?<![\w.])t\('([a-z0-9_]+)'", JS))
    assert keys, "no translatable strings found — has the call form changed?"
    missing_no = sorted(k for k in keys if k not in table["no"])
    missing_en = sorted(k for k in keys if k not in table["en"])
    assert not missing_no, f"missing Norwegian: {missing_no}"
    assert not missing_en, f"missing English: {missing_en}"

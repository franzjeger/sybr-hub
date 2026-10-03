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
        collect = JS[JS.index("function _notifCollect") : JS.index("function _notifRender")]
        for source in ("credential_expiry", "renewals", "uniweb"):
            assert source in collect, f"{source} is not folded into the stream"

    def test_the_old_per_source_tables_are_gone(self):
        """Three <table> blocks under three headings was the thing being
        replaced; a table creeping back means the merge came undone."""
        alerts = JS[
            JS.index("async function dashLoadAlerts") : JS.index(
                "// ═══", JS.index("async function dashLoadAlerts")
            )
        ]
        assert "<table" not in alerts, "the alerts tab is rendering a table again"

    def test_read_state_is_keyed_on_identity_not_position(self):
        """An id built from the list index would mark the wrong alert read as
        soon as one expired and the list shifted."""
        collect = JS[JS.index("function _notifCollect") : JS.index("function _notifRender")]
        ids = dict(re.findall(r"id:\s*'([a-z]+):'\s*\+([^,]+),", collect))
        assert set(ids) == {"cred", "renew", "uniweb", "alert", "event"}, (
            f"expected one id builder per source, found {sorted(ids)}"
        )
        for prefix in ("cred", "renew", "uniweb"):
            assert "customer" in ids[prefix] or "item_name" in ids[prefix], (
                f"the {prefix} id is not built from what identifies the alert: {ids[prefix]}"
            )
        # A sent alert is the rule, the customer and the item it was about.
        assert ids["alert"].strip() == "key"
        assert (
            "var key = (h.type || '') + ':' + (h.customer || '') + ':' + (h.item || '')" in collect
        )
        # An event is the moment it happened and what happened.
        assert "e.timestamp" in ids["event"] and "e.action" in ids["event"]
        for prefix, expr in ids.items():
            assert "idx" not in expr and "index" not in expr, (
                f"the {prefix} id depends on list position"
            )

    def test_the_bells_events_and_what_was_sent_are_in_the_stream(self):
        """The bell had its own dropdown of events and the Varsler tab its own
        list of deadlines; the bell now opens the tab, so the tab carries both,
        plus what the automatic alerts actually sent."""
        loader = JS[JS.index("async function dashLoadAlerts") : JS.index("function _notifCollect")]
        assert "/api/alerts/history" in loader and "/api/activity-log" in loader
        chrome = (STATIC / "app-chrome.js").read_text()
        toggle = chrome[chrome.index("function toggleNotifications") :]
        toggle = toggle[: toggle.index("\n}\n")]
        assert "openOverviewTab('dash-alerts')" in toggle


class TestSeverityIsAFilterNotALayout:
    def test_the_chips_count_the_whole_stream(self):
        """A chip that recounted itself against the filtered view could never
        be clicked back — "Kritisk 3" would become "Kritisk 3 of 3" and the
        other chips would read zero."""
        render = JS[JS.index("function _notifRender") : JS.index("function _notifSelect")]
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
        assert f"{sev}:" in JS[JS.index("var _SEV") : JS.index("function _notifDays")]

    def test_unread_is_not_signalled_by_colour_alone(self):
        """A 5% tint is invisible to plenty of people; the weight change is
        what actually carries it."""
        assert ".notif-row.unread { background:" in CSS
        assert ".notif-row.unread .notif-title { font-weight: 700; }" in CSS


class TestNoControlLiesAboutWhatItDoes:
    """The rule switches lived in the Varsler sidebar, where a technician saw
    them disabled. They are settings, so they moved to the Varsler pane
    of Administrasjon, which only an administrator can open."""

    HTML = (STATIC / "index.html").read_text()
    ALERTS_PANE = HTML[HTML.index('id="admin-pane-alerts"') :]
    ALERTS_PANE = ALERTS_PANE[: ALERTS_PANE.index("</section>")]

    def test_the_varsler_sidebar_has_no_switches_left(self):
        sidebar = JS[JS.index("function _notifSidebar") :]
        sidebar = sidebar[: sidebar.index("\n}\n")]
        assert '<input type="checkbox"' not in sidebar
        assert "notifToggleRule" not in JS

    def test_the_rule_toggles_read_the_real_config(self):
        """Wired to /api/alerts/config, not to a local array that forgets on
        reload."""
        integ = (STATIC / "app-integrations.js").read_text()
        load = integ[integ.index("async function alertLoadConfig") :]
        assert load.index("/api/alerts/config") < 200
        assert 'id="rule-ssl-expiry"' in self.ALERTS_PANE

    def test_only_an_administrator_reaches_the_switches(self):
        """Writing the config is admin-only server-side. The page holding the
        switches is admin-only, and the Varsler sidebar offers the way there
        only to an account that can open it."""
        assert '<div class="view" id="view-admin" data-admin-only>' in self.HTML
        sidebar = JS[JS.index("function _notifSidebar") :]
        assert "canOpenView('admin')" in sidebar[: sidebar.index("\n}\n")]

    def test_the_switch_is_a_real_checkbox(self):
        """So it keeps its keyboard and screen-reader behaviour."""
        assert '<input type="checkbox" id="rule-' in self.ALERTS_PANE

    def test_alerts_being_switched_off_is_stated(self):
        """Rules that are on inside a feature that is off send nothing. The
        sidebar says so rather than implying the deadlines are being sent."""
        assert "msg_alerts_disabled" in JS

    def test_read_state_says_where_it_lives(self):
        """It is per-browser. Two technicians will disagree, and the settings
        page admits that instead of implying a shared inbox."""
        assert 'data-i18n="msg_read_local"' in self.ALERTS_PANE
        assert "localStorage" in JS


class TestTheGroupingMatchesTheData:
    def test_groups_are_urgency_bands_not_calendar_days(self):
        """The design groups by "I dag" / "Tidligere denne uken", which suits
        an event feed. These alerts are forward-looking state whose only
        timestamp is a future expiry date, so a "today" heading would label
        the rows with something that is not true of them.
        """
        render = JS[JS.index("function _notifRender") : JS.index("function _notifSelect")]
        assert "grp_now" in render and "grp_month" in render
        assert "n.days <= 7" in render, "the bands are not derived from days remaining"

    def test_an_item_with_no_deadline_still_appears(self):
        """Three bands whose tests do not cover null would drop those rows off
        the screen entirely rather than showing them last."""
        render = JS[JS.index("function _notifRender") : JS.index("function _notifSelect")]
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

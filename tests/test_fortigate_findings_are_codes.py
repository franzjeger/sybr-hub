"""The FortiGate quick audit notes kinds; the report and the interface word them.

It wrote each policy's finding as an English sentence ("Policy 12: allow-all
(src=all, dst=all, svc=ALL)") and its HA mode capitalised ("A-p"), and the
customer report listed both as they stood in a Norwegian report; the risk
score and the recommendations counted the sentences by the words "allow-all"
and "logging" (TODO C15). A run saved before still holds the sentences, so
those are read into the same findings, counted the same way, and worded
where the report knows them.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.reports.i18n import T
from app.reports.parsers.network import (
    FORTIGATE_POLICY_FINDINGS,
    ha_mode_text,
    policy_finding_text,
    policy_findings,
)
from app.reports.recommendations import _build_recommendations
from app.reports.risk import _network_penalty


def _fg(handler):
    from app.modules.fortigate_audit.client import FortiGateClient

    fg = FortiGateClient("192.0.2.1", api_token="t", verify_ssl=False)
    fg._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url=fg.base_url, headers=fg._client.headers
    )
    return fg


_POLICIES = [
    {
        "policyid": 12,
        "name": "any-any",
        "action": "accept",
        "srcaddr": [{"name": "all"}],
        "dstaddr": [{"name": "all"}],
        "service": [{"name": "ALL"}],
        "logtraffic": "all",
    },
    {
        "policyid": 19,
        "name": "",
        "action": "accept",
        "srcaddr": [{"name": "lan"}],
        "dstaddr": [{"name": "wan"}],
        "service": [{"name": "HTTPS"}],
        "logtraffic": "disable",
    },
]


async def test_the_quick_audit_stores_kinds_and_fortioss_own_ha_mode(monkeypatch):
    from app.services.fortigate_api import quick_audit_fortigate

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("system/status"):
            return httpx.Response(200, json={"results": {"hostname": "fw1"}, "version": "v7.4.3"})
        if path.endswith("firewall/policy"):
            return httpx.Response(200, json={"results": _POLICIES})
        if path.endswith("system/ha"):
            return httpx.Response(200, json={"results": {"mode": "a-p"}})
        return httpx.Response(200, json={"results": []})

    monkeypatch.setattr("app.services.fortigate_api._build_client", lambda c, t: _fg(handler))
    result = await quick_audit_fortigate({}, "t")

    assert result["policy_findings"] == [
        {"policy_id": "12", "name": "any-any", "kind": "allow_all"},
        {"policy_id": "19", "name": "", "kind": "no_logging"},
    ]
    assert "policy_warnings" not in result
    assert result["ha_mode"] == "a-p"


@pytest.mark.parametrize(
    ("lang", "allow_all", "no_logging", "ha"),
    [
        (
            "no",
            "Regel 12 (any-any): tillater all trafikk (kilde all, mål all, tjeneste ALL)",
            "Regel 19: logger ikke trafikken",
            "Aktiv-passiv",
        ),
        (
            "en",
            "Policy 12 (any-any): allows all traffic (source all, destination all, service ALL)",
            "Policy 19: does not log its traffic",
            "Active-passive",
        ),
    ],
)
def test_the_report_words_each_finding(lang, allow_all, no_logging, ha):
    t = T(lang)
    findings = [
        {"policy_id": "12", "name": "any-any", "kind": "allow_all"},
        {"policy_id": "19", "name": "", "kind": "no_logging"},
    ]
    assert [policy_finding_text(f, t) for f in findings] == [allow_all, no_logging]
    assert ha_mode_text("a-p", t) == ha


# What the quick audit saved before it stored kinds.
_OLD_FORTIGATE = {
    "hostname": "fw1",
    "ha_mode": "A-p",
    "admins": [],
    "policy_warnings": [
        "Policy 12: allow-all (src=all, dst=all, svc=ALL)",
        "Policy 19: logging disabled",
        "Policy 23 uses a weak profile",
    ],
}
_NEW_FORTIGATE = {
    "hostname": "fw1",
    "ha_mode": "a-p",
    "admins": [],
    "policy_findings": [
        {"policy_id": "12", "name": "", "kind": "allow_all"},
        {"policy_id": "19", "name": "", "kind": "no_logging"},
    ],
}


def test_an_old_runs_sentences_become_the_same_findings():
    old = policy_findings(_OLD_FORTIGATE)

    assert [(f["kind"], f["policy_id"]) for f in old] == [
        ("allow_all", "12"),
        ("no_logging", "19"),
        (None, None),
    ]
    t = T("no")
    assert [policy_finding_text(f, t) for f in old] == [
        "Regel 12: tillater all trafikk (kilde all, mål all, tjeneste ALL)",
        "Regel 19: logger ikke trafikken",
        # Neither kind: not counted, and shown as it was stored.
        "Policy 23 uses a weak profile",
    ]
    assert ha_mode_text("A-p", t) == "Aktiv-passiv"
    assert ha_mode_text("cluster", t) == "cluster", "a mode FortiOS adds later is shown as sent"


def test_an_old_run_scores_and_recommends_as_a_new_one():
    for lang in ("no", "en"):
        recs = {}
        for name, fortigate in (("old", _OLD_FORTIGATE), ("new", _NEW_FORTIGATE)):
            network = {"has_data": True, "fortigate": fortigate}
            assert _network_penalty(network) == 3 + 1, name
            recs[name] = _build_recommendations(
                {"has_data": False},
                [],
                {"has_data": False},
                "",
                "",
                [],
                {"has_data": False},
                {"has_data": False},
                {"has_data": False},
                {"has_data": False},
                {"has_data": False},
                {},
                network=network,
                lang=lang,
            )
        assert recs["old"] == recs["new"], lang


def test_a_warning_naming_both_kinds_is_counted_as_both_as_before():
    both = policy_findings({"policy_warnings": ["Policy 9 ALLOW-ALL without Logging"]})
    assert [(f["kind"], f["policy_id"]) for f in both] == [
        ("allow_all", "9"),
        ("no_logging", "9"),
    ]


def test_every_kind_is_worded_in_both_languages():
    from app.reports.i18n import TRANSLATIONS

    ui = json.loads(Path("app/web/static/ui_i18n.json").read_text(encoding="utf-8"))
    for kind in FORTIGATE_POLICY_FINDINGS:
        for lang in ("no", "en"):
            assert TRANSLATIONS[f"fg_finding_{kind}"][lang].strip()
            assert ui[lang][f"fg_finding_{kind}"].strip()

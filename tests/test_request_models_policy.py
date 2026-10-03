"""Request models on the Conditional Access deploy, adoption and restore routes.

These routes write into a customer's Microsoft tenant. They used to read the
raw body and ``str()`` whatever arrived, so a list as the template, a number
as a break-glass group or a string in place of the ``select`` list reached the
renderer and the planner as text. Every rail the handlers had is still theirs;
these tests pin that a body of the right shape reaches them and one of the
wrong shape does not.
"""

from __future__ import annotations

import pytest

from tests.request_body_fixtures import (  # autouse fixtures apply to this module
    _init_db,
    _reset_middleware_state,
    assert_refused,
    tenant_writer_client,
)

BODY = {"template": "sybr-baseline-ca", "values": {"break_glass_group": "g-1"}}


@pytest.mark.parametrize(
    "method,path,body,key",
    [
        (
            "post",
            "/api/policy-deploy/acme/plan",
            {"template": "", "select": []},
            "err_policy_no_template",
        ),
        ("post", "/api/policy-deploy/acme/apply", BODY, "err_policy_template_fingerprint_required"),
        ("post", "/api/policy-deploy/acme/enable", {"policy_id": " "}, "err_policy_which_policy"),
        (
            "post",
            "/api/policy-deploy/acme/adoption/suggest",
            {"template": ""},
            "err_policy_no_template",
        ),
        (
            "put",
            "/api/policy-deploy/acme/adoption",
            {"template": "", "mapping": {}},
            "err_policy_no_template",
        ),
        (
            "post",
            "/api/policy-restore/acme/plan",
            {"kind": "", "ref": ""},
            "err_policy_restore_source_required",
        ),
        (
            "post",
            "/api/policy-restore/acme/apply",
            {"kind": "deployment", "ref": "x"},
            "err_policy_fingerprint_required",
        ),
    ],
)
async def test_a_body_the_spa_sends_reaches_the_handlers_own_checks(
    tenant_writer_client, method, path, body, key
):
    r = tenant_writer_client.request(method.upper(), path, json=body)

    assert assert_refused(r, 400)["error_key"] == key


async def test_the_handlers_refusal_reads_in_the_readers_language(tenant_writer_client):
    path, body = "/api/policy-deploy/acme/enable", {"policy_id": " "}

    english = tenant_writer_client.post(path, json=body, headers={"Accept-Language": "en"})
    norwegian = tenant_writer_client.post(path, json=body, headers={"Accept-Language": "nb-NO"})

    assert assert_refused(english, 400)["error"] == "Which policy? Name it by id."
    assert assert_refused(norwegian, 400)["error"] == "Hvilken policy? Oppgi den med id."


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("post", "/api/policy-deploy/acme/plan", {**BODY, "template": ["sybr-baseline-ca"]}),
        ("post", "/api/policy-deploy/acme/plan", {**BODY, "values": {"break_glass_group": 5}}),
        ("post", "/api/policy-deploy/acme/plan", {**BODY, "select": "CA001"}),
        ("post", "/api/policy-deploy/acme/plan", {**BODY, "delete": [1]}),
        ("post", "/api/policy-deploy/acme/plan", {**BODY, "templat": "x"}),
        ("post", "/api/policy-deploy/acme/apply", {**BODY, "fingerprint": 123}),
        ("post", "/api/policy-deploy/acme/enable", {"policy_id": ["p1"]}),
        ("post", "/api/policy-deploy/acme/enable", {"id": "p1"}),
        ("post", "/api/policy-deploy/acme/adoption/suggest", {**BODY, "select": []}),
        ("put", "/api/policy-deploy/acme/adoption", {**BODY, "mapping": ["CA001"]}),
        ("post", "/api/policy-restore/acme/plan", {"kind": ["deployment"], "ref": "x"}),
        ("post", "/api/policy-restore/acme/apply", {"kind": "a", "ref": "b", "fingerprint": 1}),
    ],
)
async def test_a_malformed_body_is_a_422_before_anything_reaches_the_tenant(
    tenant_writer_client, monkeypatch, method, path, body
):
    from app.web.routes import policy_deploy

    async def _never(*args, **kwargs):
        raise AssertionError("the tenant was read for a refused request")

    monkeypatch.setattr(policy_deploy, "_live_policies", _never)

    assert_refused(tenant_writer_client.request(method.upper(), path, json=body), 422)

"""A customer nobody could measure is not a customer scoring zero.

The dashboard's health score scales each customer by the categories it has data
for. Two cases slipped past that:

* An audit that ends without a grade ("?", when a blocking part of the evidence
  is missing) scored 0 of 30 with the 30 still counted, so the customer landed
  below one whose audit earned an F.
* A customer with no data in any category got total_score 0 and was averaged in
  as a zero, dragging the fleet average down for every customer not yet set up.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.web.routes import dashboard_health


def _metrics(cid: str, grade: str | None, mfa: float | None) -> SimpleNamespace:
    return SimpleNamespace(
        customer_id=cid,
        risk_grade=grade,
        risk_score=None,
        secure_score_pct=None,
        mfa_coverage_pct=mfa,
        audit_date="2026-11-01",
        total_users=10,
        users_no_mfa=0,
    )


@pytest.fixture
def fleet(monkeypatch):
    customers = [
        {"_id": "ungraded", "CustomerName": "Ungraded"},
        {"_id": "failing", "CustomerName": "Failing"},
        {"_id": "blank", "CustomerName": "Blank"},
    ]
    metrics = {
        "ungraded": _metrics("ungraded", "?", 100.0),
        "failing": _metrics("failing", "F", 100.0),
    }

    async def _allowed(_user):
        return None

    async def _latest():
        return metrics

    monkeypatch.setattr(dashboard_health, "get_accessible_customer_ids", _allowed)
    monkeypatch.setattr(dashboard_health, "filter_customers", lambda cs, _allowed: cs)
    monkeypatch.setattr(dashboard_health, "latest_metrics_per_customer", _latest)
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.list_customers", staticmethod(lambda: customers)
    )


async def _scores() -> tuple[dict[str, dict], dict]:
    out = await dashboard_health.dashboard_health_scores(user={"username": "boss"})
    return {r["customer_id"]: r for r in out["scores"]}, out


async def test_an_audit_without_a_grade_is_not_scored_as_zero(fleet):
    by_id, _ = await _scores()

    ungraded, failing = by_id["ungraded"], by_id["failing"]
    # Only MFA is known for it: 15 of 15.
    assert ungraded["max_possible"] == 15
    assert ungraded["total_score"] == 100
    assert ungraded["breakdown"]["security_audit"]["score"] == 0
    assert "Ingen karakter" in ungraded["breakdown"]["security_audit"]["detail"]
    # An F is a measurement and still counts: 6 + 15 of 45.
    assert failing["max_possible"] == 45
    assert failing["total_score"] == 47


async def test_a_customer_with_no_data_is_left_out_of_the_average(fleet):
    by_id, out = await _scores()

    assert by_id["blank"]["grade"] == "?"
    assert by_id["blank"]["scored"] is False
    assert out["average_score"] == 73.5, "the mean of 100 and 47, not of 100, 47 and 0"


async def test_owning_a_firewall_and_access_points_earns_no_points(fleet, monkeypatch):
    """The score is about how a customer is doing, not what it has bought."""
    customers = [
        {"_id": "failing", "CustomerName": "Only audit"},
        {"_id": "ungraded", "CustomerName": "Both", "FortiGateHost": "10.0.0.1", "UniFiHost": "u"},
    ]
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.list_customers", staticmethod(lambda: customers)
    )

    by_id, _ = await _scores()

    with_products, without = by_id["ungraded"], by_id["failing"]
    assert with_products["breakdown"]["infrastructure"] == {
        "score": None,
        "max": 0,
        "detail": "FortiGate + UniFi",
    }
    assert with_products["max_possible"] == 15, "MFA only, as without the products"
    assert without["max_possible"] == 45

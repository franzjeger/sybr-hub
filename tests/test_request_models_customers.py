"""Request models on the customer router: what the SPA sends still works.

A JSON list or a number where a string was expected used to reach
``.strip()`` or ``CustomerManager`` and come back as a 500. Missing values the
handlers answered with their own message still get that message.
"""

from __future__ import annotations

from tests.request_body_fixtures import (  # autouse fixtures apply to this module
    _init_db,
    _reset_middleware_state,
    admin_client,
    assert_refused,
    tech_client,
)

# What app-customers.js submitManualCustomer() sends.
MANUAL = {
    "name": "Customer A",
    "primary_domain": "customer-a.example",
    "contact_email": "it@customer-a.example",
    "contact_phone": "+47 22 00 00 00",
    "org_number": "999999999",
    "notes": "Added by hand",
}


def _add(client, **overrides) -> str:
    r = client.post("/api/customers/add-manual", json={**MANUAL, **overrides})
    assert r.status_code == 200, r.text
    return r.json()["customer_id"]


async def test_a_manual_customer_is_still_created(tech_client):
    from app.core.customer import CustomerManager

    cid = _add(tech_client)

    stored = CustomerManager.get_customer(cid)
    assert stored["CustomerName"] == "Customer A"
    assert stored["PrimaryDomain"] == "customer-a.example"


async def test_null_fields_still_mean_empty(tech_client):
    """``(body.get(k) or "")`` accepted null; the model keeps that."""
    from app.core.customer import CustomerManager

    cid = _add(tech_client, name="Customer B", primary_domain=None, notes=None)

    assert CustomerManager.get_customer(cid)["PrimaryDomain"] == ""


async def test_a_missing_name_keeps_its_own_message(tech_client):
    body = assert_refused(tech_client.post("/api/customers/add-manual", json={"name": None}), 400)
    assert body["error"] != "err_name_required"


async def test_a_manual_customer_field_of_the_wrong_type_is_refused(tech_client):
    for body in ({"name": 42}, {"name": "C", "notes": ["x"]}, ["Customer C"]):
        assert_refused(tech_client.post("/api/customers/add-manual", json=body), 422)


async def test_an_unknown_manual_customer_key_is_refused(tech_client):
    assert_refused(
        tech_client.post("/api/customers/add-manual", json={"name": "C", "tenant_id": "x"}),
        422,
    )


async def test_there_is_no_customer_switch_any_more(tech_client):
    """Each call names its customer; nothing on the server selects one."""
    cid = _add(tech_client)

    r = tech_client.post("/api/customers/switch", json={"customer_id": cid})
    assert r.status_code in (404, 405), r.text


async def test_archiving_a_customer_still_needs_an_id(admin_client):
    assert_refused(admin_client.post("/api/customers/delete", json={}), 400)
    assert_refused(admin_client.post("/api/customers/delete", json={"customer_id": ["a"]}), 422)

    cid = _add(admin_client)
    r = admin_client.post("/api/customers/delete", json={"customer_id": cid})
    assert r.status_code == 200, r.text
    assert r.json()["archived"] is True


async def test_notes_save_for_the_customer_in_the_path(tech_client):
    cid = _add(tech_client)
    other = tech_client.post("/api/customers/add-manual", json={"name": "Customer Other"}).json()[
        "customer_id"
    ]
    notes = f"/api/customer/{cid}/notes"

    r = tech_client.post(notes, json={"notes": "Gate code 1234"})

    assert r.status_code == 200, r.text
    assert r.json()["customer_id"] == cid
    assert tech_client.get(notes).json()["notes"] == "Gate code 1234"
    assert tech_client.get(f"/api/customer/{other}/notes").json()["notes"] == ""
    assert_refused(tech_client.post(notes, json={"notes": 1234}), 422)
    assert_refused(tech_client.post(notes, json={"note": "typo"}), 422)
    assert_refused(tech_client.post("/api/customer/nobody/notes", json={"notes": "x"}), 404)


async def test_tags_still_save_and_must_be_a_list_of_strings(tech_client):
    cid = _add(tech_client)

    r = tech_client.post(f"/api/customer/{cid}/tags", json={"tags": ["vip", " vip ", "m365"]})

    assert r.status_code == 200, r.text
    assert r.json()["tags"] == ["vip", "m365"]
    for tags in ("vip", [1, 2], {"vip": True}):
        assert_refused(
            tech_client.post(f"/api/customer/{cid}/tags", json={"tags": tags}),
            422,
        )

"""A customer mapped to a non-numeric IT Glue organisation gets a clear refusal.

int() on a hand-edited ITGlueOrgId used to escape as a 502 that quoted the
ValueError. The sync now answers with a keyed error, which the single-customer
route raises as a 400.
"""

from __future__ import annotations

from app.core.customer import CustomerManager
from app.web.routes.itglue import _sync_customer_documentation


async def test_a_non_numeric_org_id_is_a_keyed_error(tmp_path, monkeypatch):
    import app.core.customer as customer_module

    monkeypatch.setattr(customer_module, "_CUSTOMERS_DIR", tmp_path)
    cid = CustomerManager.save_customer({"CustomerName": "Acme", "ITGlueOrgId": "acme-org"})

    result = await _sync_customer_documentation(cid, client=object())

    assert result["error_key"] == "err_itglue_org_id_invalid"
    assert "acme-org" in result["error"]
    assert result["customer_id"] == cid

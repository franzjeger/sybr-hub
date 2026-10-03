"""A renamed customer keeps its audit history.

Run folders are named after the customer, so renaming one used to start an
empty history next to the old runs, which then belonged to nobody.
"""

from __future__ import annotations

import pytest

from app.core.customer import CustomerManager, customer_dir_name
from app.core.exceptions import ConflictError


@pytest.fixture(autouse=True)
def _dirs(tmp_path, monkeypatch):
    import app.core.config as config_module
    import app.core.customer as customer_module

    (tmp_path / "customers").mkdir()
    monkeypatch.setattr(customer_module, "_CUSTOMERS_DIR", tmp_path / "customers")
    monkeypatch.setattr(config_module, "_DEFAULT_AUDIT_DIR", tmp_path / "Audits")
    (tmp_path / "Audits").mkdir()
    return tmp_path / "Audits"


def _run(audits, name, run="2026-09-30_120000"):
    path = audits / customer_dir_name(name) / run
    path.mkdir(parents=True)
    (path / "marker.txt").write_text("run")
    return path


def test_the_runs_follow_the_new_name(_dirs):
    cid = CustomerManager.save_customer({"CustomerName": "Acme AS"}, create=True)
    _run(_dirs, "Acme AS")
    CustomerManager.save_customer({"CustomerId": cid, "CustomerName": "Acme Holding AS"})
    assert (
        _dirs / customer_dir_name("Acme Holding AS") / "2026-09-30_120000" / "marker.txt"
    ).exists()
    assert not (_dirs / customer_dir_name("Acme AS")).exists()


def test_a_rename_onto_another_customers_folder_is_refused_before_anything_changes(_dirs):
    cid = CustomerManager.save_customer({"CustomerName": "Acme AS"}, create=True)
    _run(_dirs, "Acme AS")
    _run(_dirs, "Beta AS")
    with pytest.raises(ConflictError):
        CustomerManager.save_customer({"CustomerId": cid, "CustomerName": "Beta AS"})
    assert CustomerManager.get_customer(cid)["CustomerName"] == "Acme AS"
    assert (_dirs / customer_dir_name("Acme AS") / "2026-09-30_120000").exists()


def test_a_save_without_a_rename_moves_nothing(_dirs):
    cid = CustomerManager.save_customer({"CustomerName": "Acme AS"}, create=True)
    run = _run(_dirs, "Acme AS")
    CustomerManager.save_customer(
        {"CustomerId": cid, "CustomerName": "Acme AS", "PrimaryDomain": "acme.example"}
    )
    assert run.exists()

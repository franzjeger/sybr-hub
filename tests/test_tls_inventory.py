"""Every TLS check leaves its reading behind, and the list is built from it.

A TLS check used to be a live scan whose answer reached the browser that asked
and nothing else, so no expiry date existed anywhere for Varsler to read. These
pin the store (app/services/tls_inventory.py), the routes that fill and read it,
and the check itself reading a certificate whose chain does not validate.
"""

from __future__ import annotations

import datetime as dt
import socket
import ssl
import threading
from datetime import UTC, datetime, timedelta

import pytest

from app.models.user import Role
from app.services import tls_inventory, tls_monitor
from tests.scope_fixtures import (  # autouse fixtures apply to this module
    ACME,
    BETA,
    _reset_middleware_state,
    _scope_env,
    assert_no_foreign,
    client,
    login,
)


def _cert(host: str, days: float, **extra) -> dict:
    """A check result as check_endpoint_tls returns one, expiring in *days*."""
    return {
        "host": host,
        "port": 443,
        "valid": True,
        "chain_valid": True,
        "chain_problem": "",
        "subject": {"commonName": host},
        "issuer": {"organizationName": "Example CA"},
        "not_after": (datetime.now(UTC) + timedelta(days=days)).isoformat(),
        "error": None,
        **extra,
    }


async def _status(host: str) -> dict:
    rows = await tls_inventory.list_endpoints(None, names={ACME: "Acme AS", BETA: "Beta AS"})
    return next(r for r in rows if r["host"] == host)


# ── The store ───────────────────────────────────────────────────────────────


async def test_each_reading_is_classified_by_what_it_says():
    await tls_inventory.record_results(
        [
            _cert("gone.example", -2),
            _cert("soon.example", 10),
            _cert("fine.example", 200),
            _cert("selfsigned.example", 200, chain_valid=False, chain_problem="self_signed"),
            {"host": "down.example", "port": 443, "valid": False, "error": "Connection refused"},
        ],
        allowed=None,
        may_add=True,
    )
    assert (await _status("gone.example"))["status"] == "expired"
    soon = await _status("soon.example")
    assert soon["status"] == "expiring" and soon["days_remaining"] in (9, 10)
    assert (await _status("fine.example"))["status"] == "ok"
    chain = await _status("selfsigned.example")
    assert chain["status"] == "invalid_chain" and chain["chain_problem"] == "self_signed"
    assert (await _status("down.example"))["status"] == "unreachable"


async def test_an_endpoint_that_stops_answering_keeps_the_expiry_it_was_seen_with():
    """Dropping the date on a failed re-check would turn "expires in five days,
    and we could not reach it today" into silence."""
    await tls_inventory.record_results([_cert("shop.example", 5)], allowed=None, may_add=True)
    await tls_inventory.record_results(
        [{"host": "shop.example", "port": 443, "valid": False, "error": "timed out"}],
        allowed=None,
        may_add=True,
    )
    row = await _status("shop.example")
    assert row["status"] == "expiring"
    assert row["stale"] is True
    assert row["error"] == "timed out"
    assert row["subject"] == "shop.example"


async def test_a_read_only_lookup_refreshes_a_known_endpoint_but_adds_none():
    await tls_inventory.record_results([_cert("known.example", 90)], allowed=None, may_add=True)
    await tls_inventory.record_results(
        [_cert("known.example", 3), _cert("new.example", 3)], allowed=None, may_add=False
    )
    rows = {r["host"]: r for r in await tls_inventory.list_endpoints(None, names={})}
    assert set(rows) == {"known.example"}
    assert rows["known.example"]["status"] == "expiring"


async def test_a_scoped_account_cannot_move_another_customers_endpoint_into_its_own():
    await tls_inventory.record_results(
        [{**_cert("fw.beta.example", 90), "customer_id": BETA}], allowed=None, may_add=True
    )
    await tls_inventory.record_results(
        [{**_cert("fw.beta.example", 80), "customer_id": ACME}], allowed={ACME}, may_add=True
    )
    row = await _status("fw.beta.example")
    assert row["customer_id"] == BETA


async def test_a_scoped_account_adds_no_endpoint_it_would_never_be_shown():
    """An endpoint with no customer is MSP-wide; a scoped account checking a
    random host must not put it on every unrestricted account's list."""
    await tls_inventory.record_results(
        [_cert("random.example", 3), {**_cert("mine.acme.example", 3), "customer_id": ACME}],
        allowed={ACME},
        may_add=True,
    )
    hosts = {r["host"] for r in await tls_inventory.list_endpoints(None, names={ACME: "Acme AS"})}
    assert hosts == {"mine.acme.example"}


async def test_a_reading_without_a_customer_keeps_the_one_it_was_filed_under():
    await tls_inventory.record_results(
        [{**_cert("fw.acme.example", 90), "customer_id": ACME}], allowed=None, may_add=True
    )
    await tls_inventory.record_results([_cert("fw.acme.example", 70)], allowed=None, may_add=True)
    assert (await _status("fw.acme.example"))["customer_id"] == ACME


# ── The routes ──────────────────────────────────────────────────────────────


@pytest.fixture()
def probe(monkeypatch):
    """check_endpoint_tls answering from a table, never the network."""
    answers: dict[str, dict] = {}

    async def _check(host, port=443, timeout=5.0):
        return dict(answers.get(host) or {"host": host, "port": port, "error": "unreachable"})

    monkeypatch.setattr("app.web.routes.tls.check_endpoint_tls", _check)
    monkeypatch.setattr("app.services.tls_monitor.check_endpoint_tls", _check)
    return answers


async def test_a_single_check_is_stored_and_listed(client, probe):
    probe["www.acme.example"] = _cert("www.acme.example", 12)
    headers = await login("tech", all_customers=True)

    r = client.post("/api/tls/check", json={"host": "www.acme.example"}, headers=headers)
    assert r.status_code == 200, r.text

    listed = client.get("/api/tls/certificates", headers=headers).json()["endpoints"]
    assert [(e["host"], e["status"]) for e in listed] == [("www.acme.example", "expiring")]


async def test_checking_a_discovered_endpoint_by_hand_keeps_where_it_was_found(client, probe):
    await tls_inventory.record_results(
        [{**_cert("fw.acme.example", 90), "customer_id": ACME, "source": "fortigate"}],
        allowed=None,
        may_add=True,
    )
    probe["fw.acme.example"] = _cert("fw.acme.example", 80)
    headers = await login("tech", all_customers=True)
    client.post("/api/tls/check", json={"host": "fw.acme.example"}, headers=headers)
    row = client.get("/api/tls/certificates", headers=headers).json()["endpoints"][0]
    assert (row["source"], row["customer_id"]) == ("fortigate", ACME)


async def test_a_read_only_accounts_check_adds_nothing(client, probe):
    probe["new.example"] = _cert("new.example", 12)
    headers = await login("reader", all_customers=True, write=False)

    r = client.post("/api/tls/check", json={"host": "new.example"}, headers=headers)
    assert r.status_code == 200, r.text
    assert client.get("/api/tls/certificates", headers=headers).json()["endpoints"] == []


async def test_a_scan_files_each_endpoint_under_its_customer(client, probe):
    probe["fw.acme.example"] = _cert("fw.acme.example", 3)
    headers = await login("tech-acme", customers=(ACME,))

    r = client.post(
        "/api/tls/scan",
        json={"endpoints": [{"host": "fw.acme.example", "port": 443, "customer_id": ACME}]},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    mine = client.get(f"/api/tls/certificates/{ACME}", headers=headers).json()["endpoints"]
    assert [e["host"] for e in mine] == ["fw.acme.example"]
    assert mine[0]["customer_name"] == "Acme AS"


async def test_a_scan_cannot_name_a_customer_the_caller_does_not_hold(client, probe):
    headers = await login("tech-acme", customers=(ACME,))
    r = client.post(
        "/api/tls/scan",
        json={"endpoints": [{"host": "fw.beta.example", "port": 443, "customer_id": BETA}]},
        headers=headers,
    )
    assert r.status_code == 403, r.text


async def test_the_list_is_scoped_and_unattributed_endpoints_are_msp_wide(client):
    await tls_inventory.record_results(
        [
            {**_cert("a.acme.example", 5), "customer_id": ACME},
            {**_cert("b.beta.example", 5), "customer_id": BETA},
            _cert("nobody.example", 5),
        ],
        allowed=None,
        may_add=True,
    )
    scoped = await login("tech-acme", customers=(ACME,))
    r = client.get("/api/tls/certificates", headers=scoped)
    assert {e["host"] for e in r.json()["endpoints"]} == {"a.acme.example"}
    assert_no_foreign(r.text)
    assert client.get(f"/api/tls/certificates/{BETA}", headers=scoped).status_code == 403

    wide = await login("tech-all", all_customers=True)
    hosts = {
        e["host"] for e in client.get("/api/tls/certificates", headers=wide).json()["endpoints"]
    }
    assert hosts == {"a.acme.example", "b.beta.example", "nobody.example"}


async def test_a_viewer_does_not_reach_the_tls_list(client):
    headers = await login("viewer", role=Role.viewer, all_customers=True)
    assert client.get("/api/tls/certificates", headers=headers).status_code == 403


async def test_forgetting_an_endpoint_takes_it_off_the_list(client):
    await tls_inventory.record_results(
        [{**_cert("typo.example", 50), "customer_id": ACME}], allowed=None, may_add=True
    )
    foreign = await login("tech-beta", customers=(BETA,))
    r = client.delete("/api/tls/certificates?host=typo.example&port=443", headers=foreign)
    assert r.status_code == 404, "an endpoint the caller cannot see is not theirs to remove"

    headers = await login("tech-acme", customers=(ACME,))
    r = client.delete("/api/tls/certificates?host=typo.example&port=443", headers=headers)
    assert r.status_code == 200, r.text
    assert client.get("/api/tls/certificates", headers=headers).json()["endpoints"] == []


async def test_discovery_lists_only_the_callers_customers(client, monkeypatch):
    customers = [
        {"_id": ACME, "CustomerName": "Acme AS", "FortiGateHost": "fw.acme.example"},
        {"_id": BETA, "CustomerName": "Beta AS", "FortiGateHost": "fw.beta.example"},
    ]
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.list_customers",
        staticmethod(lambda: [dict(c) for c in customers]),
    )
    headers = await login("tech-acme", customers=(ACME,))
    r = client.get("/api/tls/auto-discover", headers=headers)
    assert r.status_code == 200, r.text
    assert [(e["host"], e["customer_id"]) for e in r.json()["endpoints"]] == [
        ("fw.acme.example", ACME)
    ]
    assert "fw.beta.example" not in r.text


# ── The daily job ───────────────────────────────────────────────────────────


async def test_the_daily_certificate_check_rechecks_stored_and_configured_endpoints(
    monkeypatch, probe
):
    from app.services import scheduler

    await tls_inventory.record_results([_cert("stored.example", 40)], allowed=None, may_add=True)
    probe["stored.example"] = _cert("stored.example", 2)
    probe["fw.acme.example"] = _cert("fw.acme.example", 100)
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.list_customers",
        staticmethod(
            lambda: [{"_id": ACME, "CustomerName": "Acme AS", "FortiGateHost": "fw.acme.example"}]
        ),
    )

    async def _no_ssh_hosts():
        return []

    monkeypatch.setattr("app.services.ssh_manager.list_hosts", _no_ssh_hosts)

    result = await scheduler._do_cert_expiry_check()

    assert result.startswith("2 endpoints checked")
    stored = await _status("stored.example")
    assert stored["status"] == "expiring"
    discovered = await _status("fw.acme.example")
    assert discovered["customer_id"] == ACME and discovered["source"] == "fortigate"


# ── The check reads a certificate whose chain does not validate ─────────────


def _self_signed(tmp_path):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "fw.acme.example")])
    not_after = datetime.now(UTC) + timedelta(days=12)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(not_after)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("fw.acme.example")]), False)
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return cert_path, key_path, not_after


def test_a_self_signed_certificate_still_reports_its_expiry(tmp_path):
    """The verifying handshake stops at the failure and hands over nothing, so
    a self-signed certificate used to be only an error: no expiry, nothing to
    store. The check now reads it with a second handshake and says why the
    chain failed."""
    cert_path, key_path, not_after = _self_signed(tmp_path)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert_path, key_path)
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(4)
    port = server.getsockname()[1]
    stop = threading.Event()

    def serve():
        server.settimeout(0.2)
        while not stop.is_set():
            try:
                conn, _ = server.accept()
            except TimeoutError:
                continue
            try:
                with ctx.wrap_socket(conn, server_side=True) as tls:
                    tls.recv(1)
            except (ssl.SSLError, OSError):
                pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        result = tls_monitor._blocking_tls_check("127.0.0.1", port, 5.0)
    finally:
        stop.set()
        thread.join(timeout=2)
        server.close()

    assert result["error"] is None
    assert result["chain_valid"] is False
    assert result["chain_problem"] == "self_signed"
    assert result["valid"] is False
    assert result["subject"] == {"commonName": "fw.acme.example"}
    assert result["san"] == ["fw.acme.example"]
    assert dt.datetime.fromisoformat(result["not_after"]).date() == not_after.date()
    assert result["expiring_soon"] is True


@pytest.mark.parametrize(
    "code,expected",
    [
        (18, "self_signed"),
        (20, "incomplete_chain"),
        (62, "hostname_mismatch"),
        (10, "expired"),
        (99, "other"),
    ],
)
def test_a_failed_chain_is_named_by_its_openssl_code(code, expected):
    exc = ssl.SSLCertVerificationError("verify failed")
    exc.verify_code = code
    assert tls_monitor._chain_problem(exc) == expected

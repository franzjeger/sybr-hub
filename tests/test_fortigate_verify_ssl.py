"""The two live FortiGate poll paths must agree on the verify_ssl default.

A FortiGate almost always presents a self-signed certificate, so verifying the
chain fails the TLS handshake and a healthy firewall reports as offline. The
fleet view (poll_all_fortigates) defaulted verify_ssl=True while the dashboard
poller defaulted False, so a customer whose config never set the key showed the
same firewall online in one view and errored in the other — false offline
alarms. Both now resolve through the same builder / the same False default.
"""

from __future__ import annotations

import inspect

from app.services.fortigate_api import _build_client, poll_all_fortigates


def _capture_client(monkeypatch) -> dict:
    captured: dict = {}

    class _Spy:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("app.services.fortigate_api.FortiGateClient", _Spy)
    return captured


def test_build_client_defaults_verify_ssl_false(monkeypatch):
    captured = _capture_client(monkeypatch)
    _build_client({"FortiGateHost": "fw.example"}, "token")
    assert captured["verify_ssl"] is False


def test_build_client_honours_an_explicit_true(monkeypatch):
    captured = _capture_client(monkeypatch)
    _build_client({"FortiGateHost": "fw.example", "FortiGateVerifySSL": True}, "token")
    assert captured["verify_ssl"] is True


def test_poll_all_fortigates_builds_through_the_shared_helper():
    # Routed through _build_client so its default can't drift from the dashboard
    # poller again; it must not construct its own client with its own default.
    src = inspect.getsource(poll_all_fortigates)
    assert "_build_client(" in src
    assert "FortiGateClient(" not in src


def test_no_live_poll_path_defaults_verify_ssl_true():
    import app.services.dashboard_poller as dp
    import app.services.fortigate_api as fa

    for mod in (fa, dp):
        src = inspect.getsource(mod)
        assert 'FortiGateVerifySSL", True' not in src, (
            f"{mod.__name__} still defaults verify_ssl True — the two views will disagree"
        )

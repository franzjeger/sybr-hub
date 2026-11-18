"""A server that still accepts TLS 1.0/1.1 must be reported as accepting it.

OpenSSL 3 refuses TLS 1.0 and 1.1 at its default security level on the
*client* side, before anything is sent. The pentest auditor pinned a context to
the old version without lowering that level, so the probe answered "not
accepted" for every server there is; the certificate monitor judged the
protocol by what a default (TLS 1.2+) handshake negotiated, so its weak-protocol
flag could never be set either. Both read as a clean result. These run the real
probes against a real local server that accepts TLS 1.0 through 1.3.
"""

from __future__ import annotations

import contextlib
import datetime
import socket
import ssl
import threading

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.modules.pentest.tls_auditor import _PROTOCOLS, _probe_protocol
from app.services import tls_monitor

_V = ssl.TLSVersion


def _self_signed(tmp_path) -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=90))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = tmp_path / "c.pem", tmp_path / "k.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    return str(cert_path), str(key_path)


def _serve(tmp_path, lowest: ssl.TLSVersion, highest: ssl.TLSVersion):
    """A TLS server on a free local port. Returns (port, close)."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    try:
        ctx.set_ciphers("DEFAULT:@SECLEVEL=0")
        ctx.minimum_version, ctx.maximum_version = lowest, highest
    except (ssl.SSLError, ValueError, OSError):
        pytest.skip("this OpenSSL build cannot serve legacy TLS")
    ctx.load_cert_chain(*_self_signed(tmp_path))
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(20)

    def _loop() -> None:
        while True:
            try:
                conn, _ = listener.accept()
            except OSError:
                return
            with contextlib.suppress(OSError), ctx.wrap_socket(conn, server_side=True) as tls:
                tls.settimeout(1)
                tls.recv(1)  # hold the session until the client is done

    threading.Thread(target=_loop, daemon=True).start()
    return listener.getsockname()[1], listener.close


def _control_negotiates_tls10(port: int) -> bool:
    """Whether TLS 1.0 can be spoken in this environment at all."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        ctx.set_ciphers("DEFAULT:@SECLEVEL=0")
        ctx.minimum_version = ctx.maximum_version = _V.TLSv1
        with (
            socket.create_connection(("127.0.0.1", port), timeout=3) as raw,
            ctx.wrap_socket(raw) as tls,
        ):
            return tls.version() == "TLSv1"
    except (OSError, ValueError):
        return False


@pytest.fixture
def legacy_server(tmp_path):
    port, close = _serve(tmp_path, _V.TLSv1, _V.TLSv1_3)
    if not _control_negotiates_tls10(port):
        close()
        pytest.skip("TLS 1.0 is compiled out of this OpenSSL build")
    yield port
    close()


@pytest.fixture
def modern_server(tmp_path):
    port, close = _serve(tmp_path, _V.TLSv1_2, _V.TLSv1_3)
    yield port
    close()


def test_the_auditor_reports_tls10_and_tls11_when_the_server_accepts_them(legacy_server):
    accepted = {
        name: _probe_protocol("127.0.0.1", legacy_server, version, 3)
        for name, version in _PROTOCOLS.items()
    }
    assert accepted == {"TLSv1.0": True, "TLSv1.1": True, "TLSv1.2": True, "TLSv1.3": True}


def test_the_auditor_reports_no_legacy_protocol_for_a_modern_server(modern_server):
    assert _probe_protocol("127.0.0.1", modern_server, _V.TLSv1, 3) is False
    assert _probe_protocol("127.0.0.1", modern_server, _V.TLSv1_1, 3) is False
    assert _probe_protocol("127.0.0.1", modern_server, _V.TLSv1_2, 3) is True


def test_the_monitor_flags_an_endpoint_that_still_accepts_legacy_tls(legacy_server):
    result = tls_monitor._blocking_tls_check("127.0.0.1", legacy_server, 3)
    # Self-signed, so the chain is invalid, but the certificate is still read.
    assert not result.get("error")
    assert result["weak_protocol"] is True
    assert result["legacy_protocol"] in ("TLSv1", "TLSv1.1")
    # The version a modern client negotiates stays what it was.
    assert result["protocol_version"] in ("TLSv1.2", "TLSv1.3")


def test_the_monitor_does_not_flag_a_modern_endpoint(modern_server):
    result = tls_monitor._blocking_tls_check("127.0.0.1", modern_server, 3)
    assert not result.get("error")
    assert result["weak_protocol"] is False
    assert "legacy_protocol" not in result

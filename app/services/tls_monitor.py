"""TLS/Certificate health monitoring service.

Scans endpoints for certificate validity, expiration, protocol strength,
and cipher security using only Python stdlib (ssl + socket).
"""

from __future__ import annotations

import asyncio
import logging
import socket
import ssl
from datetime import UTC, datetime

log = logging.getLogger(__name__)

_WEAK_CIPHER_TOKENS = {"RC4", "DES", "NULL", "EXPORT", "MD5", "ANON"}


def _parse_x509_name(x509_tuples: tuple) -> dict:
    """Flatten an ssl peer cert subject/issuer into a simple dict."""
    out: dict[str, str] = {}
    for rdn in x509_tuples:
        for key, value in rdn:
            out[key] = value
    return out


def _extract_san(cert: dict) -> list[str]:
    """Extract Subject Alt Names from a parsed certificate dict."""
    san_entries = cert.get("subjectAltName", ())
    return [value for _typ, value in san_entries]


def _is_weak_cipher(cipher_name: str) -> bool:
    upper = cipher_name.upper()
    return any(token in upper for token in _WEAK_CIPHER_TOKENS)


def _is_weak_protocol(version_str: str) -> bool:
    """TLS < 1.2 is considered weak (SSLv2, SSLv3, TLSv1.0, TLSv1.1)."""
    weak = {"SSLv2", "SSLv3", "TLSv1", "TLSv1.0", "TLSv1.1"}
    return version_str in weak


# OpenSSL's X509_V_ERR codes, as the problem a person acts on. A chain that
# does not validate is worth knowing about, but "self-signed" on a firewall's
# management page and "the intermediate is missing" on a customer's web shop
# are different news, so the code says which.
_CHAIN_PROBLEMS = {
    9: "not_yet_valid",
    10: "expired",
    18: "self_signed",
    19: "untrusted",
    20: "incomplete_chain",
    21: "incomplete_chain",
    23: "revoked",
    62: "hostname_mismatch",
}


def _chain_problem(exc: ssl.SSLCertVerificationError) -> str:
    code = getattr(exc, "verify_code", None)
    if code in _CHAIN_PROBLEMS:
        return _CHAIN_PROBLEMS[code]
    text = str(exc).lower()
    if "self-signed" in text or "self signed" in text:
        return "self_signed"
    if "hostname mismatch" in text:
        return "hostname_mismatch"
    if "expired" in text:
        return "expired"
    return "other"


def _details(
    host: str,
    port: int,
    *,
    subject: dict,
    issuer: dict,
    not_before: datetime,
    not_after: datetime,
    serial: str,
    san: list[str],
    cipher_info: tuple | None,
    version: str | None,
) -> dict:
    """The result shape both handshakes produce, verified or not."""
    cipher_name = cipher_info[0] if cipher_info else "UNKNOWN"
    protocol_version = cipher_info[1] if cipher_info else version or "UNKNOWN"
    key_bits = cipher_info[2] if cipher_info else None

    now = datetime.now(UTC)
    days_remaining = (not_after - now).days
    expired = now > not_after
    weak_proto = _is_weak_protocol(protocol_version)
    return {
        "host": host,
        "port": port,
        "valid": not expired and not weak_proto,
        "chain_valid": True,
        "chain_problem": "",
        "subject": subject,
        "issuer": issuer,
        "not_before": not_before.isoformat(),
        "not_after": not_after.isoformat(),
        "days_remaining": days_remaining,
        "expired": expired,
        "expiring_soon": days_remaining < 30 and not expired,
        "serial_number": serial,
        "san": san,
        "protocol_version": protocol_version,
        "cipher": cipher_name,
        "key_bits": key_bits,
        "weak_protocol": weak_proto,
        "weak_cipher": _is_weak_cipher(cipher_name),
        "error": None,
    }


def _x509_name(name) -> dict:
    """A cryptography Name as the flat dict getpeercert() gives."""
    from cryptography.x509.oid import NameOID

    keys = {
        NameOID.COMMON_NAME: "commonName",
        NameOID.ORGANIZATION_NAME: "organizationName",
        NameOID.COUNTRY_NAME: "countryName",
    }
    out: dict[str, str] = {}
    for attr in name:
        key = keys.get(attr.oid)
        if key:
            out[key] = str(attr.value)
    return out


def _certificate_details(host: str, port: int, der: bytes, cipher_info, version) -> dict:
    """Details of a DER certificate, in the shape _details gives."""
    from cryptography import x509

    cert = x509.load_der_x509_certificate(der)
    try:
        ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        san = [str(v) for v in ext.value.get_values_for_type(x509.DNSName)]
    except x509.ExtensionNotFound:
        san = []
    return _details(
        host,
        port,
        subject=_x509_name(cert.subject),
        issuer=_x509_name(cert.issuer),
        not_before=cert.not_valid_before_utc,
        not_after=cert.not_valid_after_utc,
        serial=format(cert.serial_number, "X"),
        san=san,
        cipher_info=cipher_info,
        version=version,
    )


def _unverified_details(host: str, port: int, timeout: float) -> dict | None:
    """Read the certificate of an endpoint whose chain did not validate.

    The verifying handshake stops at the failure, so it never hands over the
    certificate. A second one that does not verify does, which is what lets a
    self-signed or incompletely chained certificate still report its expiry.
    None when that handshake fails too.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with (
            socket.create_connection((host, port), timeout=timeout) as raw,
            ctx.wrap_socket(raw, server_hostname=host) as conn,
        ):
            der = conn.getpeercert(binary_form=True)
            cipher_info = conn.cipher()
            version = conn.version()
        if not der:
            return None
        return _certificate_details(host, port, der, cipher_info, version)
    except (OSError, ValueError) as exc:
        log.debug("Unverified TLS read of %s:%s failed: %s", host, port, exc)
        return None


def _blocking_tls_check(host: str, port: int, timeout: float) -> dict:
    """Perform a blocking TLS connection and return certificate details.

    Runs inside a thread executor so the event loop stays free.
    """
    ctx = ssl.create_default_context()

    try:
        with (
            socket.create_connection((host, port), timeout=timeout) as raw,
            ctx.wrap_socket(raw, server_hostname=host) as conn,
        ):
            cert = conn.getpeercert()
            if not cert:
                return {
                    "host": host,
                    "port": port,
                    "valid": False,
                    "error": "No certificate returned by peer",
                }

            # Python's ssl module uses the format: 'Mon DD HH:MM:SS YYYY GMT'
            date_fmt = "%b %d %H:%M:%S %Y %Z"
            return _details(
                host,
                port,
                subject=_parse_x509_name(cert.get("subject", ())),
                issuer=_parse_x509_name(cert.get("issuer", ())),
                not_before=datetime.strptime(cert.get("notBefore", ""), date_fmt).replace(
                    tzinfo=UTC
                ),
                not_after=datetime.strptime(cert.get("notAfter", ""), date_fmt).replace(tzinfo=UTC),
                serial=cert.get("serialNumber", ""),
                san=_extract_san(cert),
                cipher_info=conn.cipher(),
                version=conn.version(),
            )

    except ssl.SSLCertVerificationError as exc:
        problem = _chain_problem(exc)
        details = _unverified_details(host, port, timeout)
        if details is not None:
            details["valid"] = False
            details["chain_valid"] = False
            details["chain_problem"] = problem
            return details
        # Make the message readable
        msg = str(exc)
        if "CERTIFICATE_VERIFY_FAILED" in msg:
            msg = "Certificate not trusted (self-signed or unknown CA)"
        elif "certificate has expired" in msg.lower():
            msg = "Certificate has expired"
        return {
            "host": host,
            "port": port,
            "valid": False,
            "chain_valid": False,
            "chain_problem": problem,
            "error": f"Certificate verification failed — {msg}",
        }
    except ssl.SSLError as exc:
        msg = str(exc)
        if "WRONG_VERSION_NUMBER" in msg:
            msg = "Not a TLS service (port may serve plain HTTP)"
        elif "SSLV3_ALERT_HANDSHAKE_FAILURE" in msg:
            msg = "TLS handshake rejected by server"
        return {
            "host": host,
            "port": port,
            "valid": False,
            "error": f"SSL error — {msg}",
        }
    except TimeoutError:
        return {
            "host": host,
            "port": port,
            "valid": False,
            "error": f"Connection timed out ({timeout}s) — host may be unreachable or port blocked",
        }
    except socket.gaierror:
        return {
            "host": host,
            "port": port,
            "valid": False,
            "error": f"DNS lookup failed — hostname '{host}' could not be resolved",
        }
    except ConnectionRefusedError:
        return {
            "host": host,
            "port": port,
            "valid": False,
            "error": f"Connection refused — port {port} is closed or not accepting TLS",
        }
    except OSError as exc:
        msg = str(exc)
        if "Errno -2" in msg or "Name or service not known" in msg:
            msg = f"DNS lookup failed — hostname '{host}' could not be resolved"
        elif "Errno 111" in msg or "Connection refused" in msg:
            msg = f"Connection refused — port {port} is closed"
        elif "Errno 113" in msg or "No route" in msg:
            msg = f"No route to host — '{host}' is unreachable"
        else:
            msg = f"Connection failed — {msg}"
        return {
            "host": host,
            "port": port,
            "valid": False,
            "error": msg,
        }


async def check_endpoint_tls(host: str, port: int = 443, timeout: float = 5.0) -> dict:
    """Check TLS certificate health for a single endpoint.

    Runs the blocking SSL handshake in a thread executor.
    """
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _blocking_tls_check, host, port, timeout)
    return result


async def discover_tls_endpoints(allowed: set[str] | None = None) -> list[dict]:
    """Auto-discover TLS endpoints from configured SSH hosts, FortiGate, and UniFi.

    Scans the customers in *allowed* (None: every customer) for network
    appliances and web-facing services that should be monitored for TLS
    certificate health. Returns a deduplicated list of
    {host, port, label, source, customer_id} dicts; customer_id is None for an
    SSH host nobody assigned, which only an unrestricted caller is shown.

    It used to list every customer's firewall and controller addresses to
    anybody who could open the TLS tab, whatever customers they held.
    """
    from app.core.customer import CustomerManager
    from app.core.rbac import customer_in_scope

    endpoints: list[dict] = []
    seen: set[str] = set()

    def _add(host: str, port: int, label: str, source: str, customer_id: str | None) -> None:
        """Add endpoint if not already seen (dedup by host:port)."""
        host = host.strip().lower()
        if not host or not customer_in_scope(customer_id, allowed):
            return
        # Strip protocol prefix if present
        if "://" in host:
            from urllib.parse import urlparse

            parsed = urlparse(host if host.startswith("http") else f"https://{host}")
            host = parsed.hostname or host
            if parsed.port:
                port = parsed.port
        # Strip trailing slashes / paths
        host = host.rstrip("/").split("/")[0]
        key = f"{host}:{port}"
        if key in seen:
            return
        seen.add(key)
        endpoints.append(
            {
                "host": host,
                "port": port,
                "label": label,
                "source": source,
                "customer_id": customer_id or None,
            }
        )

    # ── SSH hosts: network appliances have web UIs on 443 ──────────────────
    try:
        from app.services.ssh_manager import list_hosts as ssh_list_hosts

        ssh_hosts = await ssh_list_hosts()
        for h in ssh_hosts:
            if h.device_type.value in ("fortigate", "unifi", "pfsense", "openwrt"):
                web_port = 443 if h.port == 22 else h.port
                _add(
                    h.hostname,
                    web_port,
                    f"{h.label} (SSH/{h.device_type.value})",
                    "ssh",
                    h.customer_id,
                )
    except Exception as exc:
        log.warning("TLS auto-discover: failed to read SSH hosts: %s", exc)

    # ── FortiGate hosts from customer configs ──────────────────────────────
    try:
        customers = CustomerManager.list_customers()
        for c in customers:
            cust_name = c.get("CustomerName", "Unknown")
            cid = c.get("_id") or None

            # FortiGate
            fg_host = c.get("FortiGateHost", "")
            if fg_host:
                fg_port = int(c.get("FortiGatePort", 443))
                _add(fg_host, fg_port, f"{cust_name} FortiGate", "fortigate", cid)

            # UniFi controller
            unifi_host = c.get("UniFiHost", "")
            if unifi_host:
                _add(unifi_host, 443, f"{cust_name} UniFi Controller", "unifi", cid)

            # UniFi direct devices
            for dev in c.get("UniFiDirectDevices", []):
                dev_host = dev.get("host", "") if isinstance(dev, dict) else str(dev)
                if dev_host:
                    _add(dev_host, 443, f"{cust_name} UniFi Device", "unifi", cid)
    except Exception as exc:
        log.warning("TLS auto-discover: failed to read customer configs: %s", exc)

    return endpoints


async def scan_customer_endpoints(endpoints: list[dict]) -> dict:
    """Scan multiple endpoints concurrently and return an aggregate summary.

    Each entry in *endpoints* should have keys: host, port (optional, default 443),
    label (optional).
    """
    # Keep each task paired with the endpoint it came from. Skipping host-less
    # entries made the results list shorter than `endpoints`, but the labels
    # were still read with endpoints[idx] — so one blank host shifted every
    # later result onto the wrong endpoint (a success wearing another host's
    # label, an error reporting the wrong host/port). Index the filtered list.
    pending: list[dict] = []
    tasks = []
    for ep in endpoints:
        host = ep.get("host", "").strip()
        if not host:
            continue
        port = int(ep.get("port", 443))
        pending.append(ep)
        tasks.append(check_endpoint_tls(host, port))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    processed: list[dict] = []
    for ep, res in zip(pending, results, strict=True):
        label = ep.get("label", "")
        if isinstance(res, Exception):
            entry = {
                "host": ep.get("host", ""),
                "port": int(ep.get("port", 443)),
                "valid": False,
                "error": str(res),
            }
            if label:
                entry["label"] = label
            res = entry
        elif label:
            res["label"] = label
        # Who the endpoint belongs to and where it was found travel with the
        # result, so whoever stores it can file it under the right customer.
        for key in ("customer_id", "source"):
            if ep.get(key):
                res[key] = ep[key]
        processed.append(res)

    valid_count = sum(1 for r in processed if r.get("valid"))
    expired_count = sum(1 for r in processed if r.get("expired"))
    expiring_count = sum(1 for r in processed if r.get("expiring_soon"))
    weak_count = sum(1 for r in processed if r.get("weak_protocol") or r.get("weak_cipher"))
    chain_count = sum(1 for r in processed if r.get("chain_valid") is False)
    error_count = sum(1 for r in processed if r.get("error"))

    return {
        "total": len(processed),
        "valid": valid_count,
        "expired": expired_count,
        "expiring_soon": expiring_count,
        "weak_tls": weak_count,
        "invalid_chain": chain_count,
        "errors": error_count,
        "results": processed,
        "scanned_at": datetime.now(UTC).isoformat(),
    }

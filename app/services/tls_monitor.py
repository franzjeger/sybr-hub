"""TLS/Certificate health monitoring service.

Scans endpoints for certificate validity, expiration, protocol strength,
and cipher security using only Python stdlib (ssl + socket).
"""

from __future__ import annotations

import asyncio
import logging
import socket
import ssl
from datetime import datetime, timezone

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


def _blocking_tls_check(host: str, port: int, timeout: float) -> dict:
    """Perform a blocking TLS connection and return certificate details.

    Runs inside a thread executor so the event loop stays free.
    """
    ctx = ssl.create_default_context()

    try:
        with socket.create_connection((host, port), timeout=timeout) as raw:
            with ctx.wrap_socket(raw, server_hostname=host) as conn:
                cert = conn.getpeercert()
                if not cert:
                    return {
                        "host": host,
                        "port": port,
                        "valid": False,
                        "error": "No certificate returned by peer",
                    }

                cipher_info = conn.cipher()  # (name, version, bits)
                cipher_name = cipher_info[0] if cipher_info else "UNKNOWN"
                protocol_version = cipher_info[1] if cipher_info else conn.version() or "UNKNOWN"
                key_bits = cipher_info[2] if cipher_info else None

                subject = _parse_x509_name(cert.get("subject", ()))
                issuer = _parse_x509_name(cert.get("issuer", ()))
                san = _extract_san(cert)
                serial = cert.get("serialNumber", "")

                not_before_str = cert.get("notBefore", "")
                not_after_str = cert.get("notAfter", "")

                # Python's ssl module uses the format: 'Mon DD HH:MM:SS YYYY GMT'
                date_fmt = "%b %d %H:%M:%S %Y %Z"
                not_before = datetime.strptime(not_before_str, date_fmt).replace(tzinfo=timezone.utc)
                not_after = datetime.strptime(not_after_str, date_fmt).replace(tzinfo=timezone.utc)

                now = datetime.now(timezone.utc)
                days_remaining = (not_after - now).days
                expired = now > not_after
                expiring_soon = days_remaining < 30 and not expired

                weak_proto = _is_weak_protocol(protocol_version)
                weak_ciph = _is_weak_cipher(cipher_name)

                return {
                    "host": host,
                    "port": port,
                    "valid": not expired and not weak_proto,
                    "subject": subject,
                    "issuer": issuer,
                    "not_before": not_before.isoformat(),
                    "not_after": not_after.isoformat(),
                    "days_remaining": days_remaining,
                    "expired": expired,
                    "expiring_soon": expiring_soon,
                    "serial_number": serial,
                    "san": san,
                    "protocol_version": protocol_version,
                    "cipher": cipher_name,
                    "key_bits": key_bits,
                    "weak_protocol": weak_proto,
                    "weak_cipher": weak_ciph,
                    "error": None,
                }

    except ssl.SSLCertVerificationError as exc:
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
    except socket.timeout:
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


async def discover_tls_endpoints() -> list[dict]:
    """Auto-discover TLS endpoints from configured SSH hosts, FortiGate, and UniFi.

    Scans all customers for network appliances and web-facing services
    that should be monitored for TLS certificate health.
    Returns a deduplicated list of {host, port, label, source} dicts.
    """
    from app.core.customer import CustomerManager

    endpoints: list[dict] = []
    seen: set[str] = set()

    def _add(host: str, port: int, label: str, source: str) -> None:
        """Add endpoint if not already seen (dedup by host:port)."""
        host = host.strip().lower()
        if not host:
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
        endpoints.append({"host": host, "port": port, "label": label, "source": source})

    # ── SSH hosts: network appliances have web UIs on 443 ──────────────────
    try:
        from app.services.ssh_manager import list_hosts as ssh_list_hosts
        ssh_hosts = await ssh_list_hosts()
        for h in ssh_hosts:
            if h.device_type.value in ("fortigate", "unifi", "pfsense", "openwrt"):
                web_port = 443 if h.port == 22 else h.port
                _add(h.hostname, web_port, f"{h.label} (SSH/{h.device_type.value})", "ssh")
    except Exception as exc:
        log.warning("TLS auto-discover: failed to read SSH hosts: %s", exc)

    # ── FortiGate hosts from customer configs ──────────────────────────────
    try:
        customers = CustomerManager.list_customers()
        for c in customers:
            cust_name = c.get("CustomerName", "Unknown")

            # FortiGate
            fg_host = c.get("FortiGateHost", "")
            if fg_host:
                fg_port = int(c.get("FortiGatePort", 443))
                _add(fg_host, fg_port, f"{cust_name} FortiGate", "fortigate")

            # UniFi controller
            unifi_host = c.get("UniFiHost", "")
            if unifi_host:
                _add(unifi_host, 443, f"{cust_name} UniFi Controller", "unifi")

            # UniFi direct devices
            for dev in c.get("UniFiDirectDevices", []):
                dev_host = dev.get("host", "") if isinstance(dev, dict) else str(dev)
                if dev_host:
                    _add(dev_host, 443, f"{cust_name} UniFi Device", "unifi")
    except Exception as exc:
        log.warning("TLS auto-discover: failed to read customer configs: %s", exc)

    return endpoints


async def scan_customer_endpoints(endpoints: list[dict]) -> dict:
    """Scan multiple endpoints concurrently and return an aggregate summary.

    Each entry in *endpoints* should have keys: host, port (optional, default 443),
    label (optional).
    """
    tasks = []
    for ep in endpoints:
        host = ep.get("host", "").strip()
        port = int(ep.get("port", 443))
        if not host:
            continue
        tasks.append(check_endpoint_tls(host, port))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    processed: list[dict] = []
    for idx, res in enumerate(results):
        if isinstance(res, Exception):
            ep = endpoints[idx]
            processed.append({
                "host": ep.get("host", ""),
                "port": int(ep.get("port", 443)),
                "valid": False,
                "error": str(res),
            })
        else:
            # Attach label from original endpoint list
            label = endpoints[idx].get("label", "")
            if label:
                res["label"] = label
            processed.append(res)

    valid_count = sum(1 for r in processed if r.get("valid"))
    expired_count = sum(1 for r in processed if r.get("expired"))
    expiring_count = sum(1 for r in processed if r.get("expiring_soon"))
    weak_count = sum(1 for r in processed if r.get("weak_protocol") or r.get("weak_cipher"))
    error_count = sum(1 for r in processed if r.get("error"))

    return {
        "total": len(processed),
        "valid": valid_count,
        "expired": expired_count,
        "expiring_soon": expiring_count,
        "weak_tls": weak_count,
        "errors": error_count,
        "results": processed,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    }

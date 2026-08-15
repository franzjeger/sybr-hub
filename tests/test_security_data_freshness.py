"""Security findings must say how sure they are, and stale data must fail closed.

Before SR-007 several conclusions were stated as fact from shaky inputs: a
self-reported version banner became a definitive CVE, a WordPress version at or
above a fixed threshold was "current" forever, TLS checks never validated the
chain / a weak signature algorithm / IP SANs, and the manually maintained UniFi
firmware table would happily call a device up to date from months-old data.

These pin: every finding carries confidence/source/as_of; internal reachability
is separated from internet exposure; a stale firmware table returns unknown
(never "ok") for an up-to-date claim while still catching behind/EOL; the WP
floor only flags below-floor and never claims "current"; and the TLS cert logic
flags expiry, weak signatures, hostname/IP-SAN mismatch, self-signed, and an
untrusted chain — exercised with explicit certificate fixtures.
"""

from __future__ import annotations

import datetime
import ipaddress
from datetime import date

from app.modules.pentest import cms_scanner as cms
from app.modules.pentest import tls_auditor as tls
from app.modules.pentest import vuln_checker as vc
from app.modules.pentest.finding import CONFIRMED, UNVERIFIED
from app.modules.unifi_audit import firmware_db as fdb

_FRESH = date(2026, 4, 1)     # 2 days after LAST_UPDATED 2026-03-30
_STALE = date(2026, 12, 1)    # > FRESHNESS_DAYS after


# ── Firmware DB: fail closed on staleness, keep valid lower bounds ────────────

def test_firmware_freshness_window():
    assert fdb.is_stale(_FRESH) is False
    assert fdb.is_stale(_STALE) is True


def test_unparseable_last_updated_is_treated_as_stale(monkeypatch):
    monkeypatch.setattr(fdb, "LAST_UPDATED", "not-a-date")
    assert fdb.db_age_days(_FRESH) is None
    assert fdb.is_stale(_FRESH) is True   # fail closed


def test_a_negative_age_fails_closed(monkeypatch):
    # A clock behind LAST_UPDATED, or a future-dated table, must not read as
    # fresh (SR-007 review — that was a fail-open).
    assert fdb.db_age_days(date(2020, 1, 1)) < 0
    assert fdb.is_stale(date(2020, 1, 1)) is True
    # A "current-version" device from that anomalous state is unknown, not ok.
    r = fdb.check_firmware("U6-Pro", "6.6.77", today=date(2020, 1, 1))
    assert r["severity"] == "unknown" and r["up_to_date"] is None


def test_up_to_date_from_a_fresh_table_is_ok():
    r = fdb.check_firmware("U6-Pro", "6.6.77", today=_FRESH)
    assert r["severity"] == "ok"
    assert r["up_to_date"] is True
    assert r["stale"] is False
    assert r["as_of"] == fdb.LAST_UPDATED and r["source"]


def test_up_to_date_from_a_stale_table_is_unknown_not_ok():
    r = fdb.check_firmware("U6-Pro", "6.6.77", today=_STALE)
    assert r["severity"] == "unknown"
    assert r["up_to_date"] is None
    assert r["stale"] is True
    assert "utdatert" in r["reason"].lower()


def test_behind_is_reported_even_from_a_stale_table():
    # A device behind our (stale) "latest" is behind the real latest too.
    r = fdb.check_firmware("U6-Pro", "6.0.0", today=_STALE)
    assert r["up_to_date"] is False
    assert r["severity"] in ("warning", "critical")


def test_major_version_behind_is_critical():
    r = fdb.check_firmware("UDM", "3.0.0", today=_FRESH)   # latest 4.0.21
    assert r["severity"] == "critical" and r["up_to_date"] is False


def test_eol_is_reported_regardless_of_staleness():
    r = fdb.check_firmware("UAP", "6.6.77", today=_STALE)   # eol=True
    assert r["eol"] is True and r["severity"] == "critical" and r["up_to_date"] is False


def test_unknown_model_is_unknown_with_a_reason():
    r = fdb.check_firmware("NoSuchModel-9000", "1.0.0", today=_FRESH)
    assert r["severity"] == "unknown"
    assert r["latest"] is None
    assert "tabellen" in r["reason"].lower()


def test_unparseable_firmware_version_is_unknown():
    r = fdb.check_firmware("U6-Pro", "not-a-version", today=_FRESH)
    assert r["severity"] == "unknown" and r["reason"]


# ── vuln_checker: internal vs internet, banner leads, provenance ─────────────

def _scan(ip, port, product="", version=""):
    return {"hosts": [{"ip": ip, "hostname": "", "ports": [
        {"port": port, "service": "svc", "product": product, "version": version}]}]}


def test_internal_reachability_is_not_called_internet_exposure():
    findings = vc.analyze_scan_results(_scan("192.168.1.10", 445))
    exposed = [f for f in findings if f["category"] == "exposed_service"]
    assert exposed
    f = exposed[0]
    assert f["exposure"] == "internal"
    assert "internett-eksponering er ikke verifisert" in f["detail"]
    assert f["confidence"] == CONFIRMED   # the open port itself is observed


def test_public_address_is_labelled_public():
    findings = vc.analyze_scan_results(_scan("8.8.8.8", 445))
    f = next(f for f in findings if f["category"] == "exposed_service")
    assert f["exposure"] == "public"
    assert "internett-eksponering er ikke verifisert" not in f["detail"]


def test_exposure_classification_edge_cases():
    from app.modules.pentest.finding import exposure_for_target
    assert exposure_for_target("192.168.1.1") == "internal"
    assert exposure_for_target("10.0.0.1") == "internal"
    assert exposure_for_target("100.64.0.1") == "internal"    # CGNAT (SR-007 review)
    assert exposure_for_target("fd00::1") == "internal"        # IPv6 ULA
    assert exposure_for_target("127.0.0.1") == "internal"
    assert exposure_for_target("8.8.8.8") == "public"
    assert exposure_for_target("2606:4700:4700::1111") == "public"
    assert exposure_for_target("example.com") == "unknown"     # a hostname
    assert exposure_for_target("") == "unknown"


def test_banner_version_cve_is_an_unverified_lead():
    findings = vc.analyze_scan_results(_scan("10.0.0.9", 22, product="OpenSSH", version="7.9"))
    outdated = [f for f in findings if f["category"] == "outdated_version"]
    assert outdated
    f = outdated[0]
    assert f["confidence"] == UNVERIFIED
    assert f["source"] == "scan:banner-version"
    assert f["as_of"] == vc.VULN_DB_AS_OF


def test_every_vuln_finding_carries_provenance():
    findings = vc.analyze_scan_results(_scan("192.168.1.10", 445))
    assert findings
    for f in findings:
        assert f["confidence"] and f["source"] and "exposure" in f


# ── cms_scanner: the WP floor flags below, never claims "current" ────────────

def test_wp_below_floor_is_flagged_as_a_dated_lead():
    f = cms._wp_outdated_finding("https://x", "5.9")
    assert f is not None
    assert f["confidence"] == UNVERIFIED and f["as_of"] == cms.CMS_DATA_AS_OF
    assert "sanntidssjekk" in f["detail"]   # explicitly not a live check


def test_wp_at_or_above_floor_makes_no_claim():
    assert cms._wp_outdated_finding("https://x", "6.4") is None   # at floor
    assert cms._wp_outdated_finding("https://x", "6.5") is None   # above
    assert cms._wp_outdated_finding("https://x", "7.0") is None


def test_wp_just_below_floor_is_flagged():
    assert cms._wp_outdated_finding("https://x", "6.3") is not None


def test_wp_unparseable_version_makes_no_claim():
    assert cms._wp_outdated_finding("https://x", "bogus") is None


def test_cms_finalize_tags_provenance():
    findings = cms._finalize([
        {"category": "cms_detection", "detail": "d"},
        {"category": "cms_vuln", "detail": "d"},
    ])
    assert findings[0]["confidence"] and findings[0]["source"]
    assert all("evidence" in f for f in findings)


# ── TLS: cert fixtures for expiry / signature / hostname / IP SAN / trust ─────

def _cert(*, subject="example.com", issuer="Trusted CA", notafter="Jan 01 00:00:00 2035 GMT",
          dns=(), ips=(), sig="sha256"):
    san = tuple(("DNS", d) for d in dns) + tuple(("IP Address", i) for i in ips)
    return {
        "subject": [(("commonName", subject),)],
        "issuer": [(("commonName", issuer),)],
        "notBefore": "Jan 01 00:00:00 2020 GMT",
        "notAfter": notafter,
        "subjectAltName": san,
        "signature_algorithm": sig,
    }


_NOW = datetime.datetime(2026, 6, 1, tzinfo=datetime.UTC)


def _titles(findings):
    return [f["title"] for f in findings]


def test_expired_certificate_is_critical():
    fs = tls._cert_findings("example.com", 443,
                            _cert(notafter="Jan 01 00:00:00 2021 GMT", dns=("example.com",)),
                            trusted=False, now=_NOW)
    assert any("utløpt" in t for t in _titles(fs))


def test_weak_signature_algorithm_is_flagged():
    fs = tls._cert_findings("example.com", 443, _cert(dns=("example.com",), sig="sha1"),
                            trusted=True, now=_NOW)
    assert any("signaturalgoritme" in t for t in _titles(fs))


def test_hostname_mismatch_against_dns_sans():
    fs = tls._cert_findings("example.com", 443, _cert(dns=("other.com",)), trusted=True, now=_NOW)
    assert any("Hostname mismatch" in t for t in _titles(fs))


def test_ip_san_match_and_mismatch():
    ok = tls._cert_findings("10.0.0.5", 443, _cert(ips=("10.0.0.5",)), trusted=True, now=_NOW)
    assert not any("Hostname mismatch" in t for t in _titles(ok))
    bad = tls._cert_findings("10.0.0.5", 443, _cert(ips=("10.0.0.6",)), trusted=True, now=_NOW)
    assert any("Hostname mismatch" in t for t in _titles(bad))


def test_self_signed_is_flagged_and_suppresses_the_generic_untrusted_finding():
    fs = tls._cert_findings("example.com", 443,
                            _cert(subject="example.com", issuer="example.com", dns=("example.com",)),
                            trusted=False, now=_NOW)
    assert any("Selvsignert" in t for t in _titles(fs))
    assert not any("ikke betrodd" in t for t in _titles(fs))   # self-signed explains it


def test_untrusted_chain_is_flagged_when_not_otherwise_explained():
    # Valid-looking cert (trusted CA name, matches host, not expired) that still
    # fails verification — an unknown CA or incomplete chain.
    fs = tls._cert_findings("example.com", 443, _cert(dns=("example.com",)),
                            trusted=False, now=_NOW, trust_error="unable to get local issuer")
    assert any("ikke betrodd" in t for t in _titles(fs))


def test_expiry_does_not_hide_an_independent_untrusted_chain():
    # A cert can be expired AND chain to an unknown CA — the untrusted-chain
    # finding must still appear alongside the expiry (SR-007 review).
    fs = tls._cert_findings("example.com", 443,
                            _cert(notafter="Jan 01 00:00:00 2021 GMT", dns=("example.com",)),
                            trusted=False, now=_NOW, trust_error="unable to get local issuer")
    titles = _titles(fs)
    assert any("utløpt" in t for t in titles)
    assert any("ikke betrodd" in t for t in titles)


def test_trusted_cert_produces_no_trust_finding():
    fs = tls._cert_findings("example.com", 443, _cert(dns=("example.com",)), trusted=True, now=_NOW)
    assert not any("ikke betrodd" in t for t in _titles(fs))


def test_hostname_matcher_wildcards_and_ips():
    assert tls._hostname_matches("a.example.com", ["*.example.com"], [])
    assert not tls._hostname_matches("example.com", ["*.example.com"], [])
    assert not tls._hostname_matches("a.b.example.com", ["*.example.com"], [])
    assert tls._hostname_matches("host.example.com", ["host.example.com"], [])
    assert tls._hostname_matches("10.0.0.5", [], ["10.0.0.5"])
    assert not tls._hostname_matches("10.0.0.5", ["10.0.0.5"], [])   # DNS SAN never covers an IP


def _make_der(cn="example.com", dns=(), ips=(), hash_alg=None):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    san = [x509.DNSName(d) for d in dns] + [x509.IPAddress(ipaddress.ip_address(i)) for i in ips]
    nb = datetime.datetime(2025, 1, 1, tzinfo=datetime.UTC)
    builder = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
               .public_key(key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(nb).not_valid_after(nb + datetime.timedelta(days=3650)))
    if san:
        builder = builder.add_extension(x509.SubjectAlternativeName(san), critical=False)
    return builder.sign(key, hash_alg or hashes.SHA256()).public_bytes(serialization.Encoding.DER)


def test_der_parser_extracts_dns_and_ip_sans():
    cert = tls._parse_der_cert(_make_der(dns=("a.example.com",), ips=("10.0.0.5",)))
    sans = cert["subjectAltName"]
    assert ("DNS", "a.example.com") in sans
    assert ("IP Address", "10.0.0.5") in sans
    assert tls._san_list(cert) == ["a.example.com"]
    assert tls._ip_san_list(cert) == ["10.0.0.5"]

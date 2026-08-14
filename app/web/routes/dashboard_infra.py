"""Dashboard infrastructure, network, VPN, domains, compliance, assets, and security endpoints.

Split from dashboard.py for maintainability.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.core.exceptions import (
    AuthError,
    ConflictError,
    IntegrationError,
    NotFoundError,
    ValidationError,
)
from app.core.rbac import check_customer_access, filter_customers, get_accessible_customer_ids
from app.models.user import Role
from app.web.middleware.auth import get_current_user, require_customer_access

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Unified cost overview ───────────────────────────────────────────────────

@router.get("/dashboard/costs")
async def dashboard_costs(user=Depends(get_current_user)):
    """Aggregate ALSO MRR + Uniweb monthly costs per customer."""
    import json

    from app.core.customer import CustomerManager
    from app.core.database import get_db

    allowed = await get_accessible_customer_ids(user)
    customers = filter_customers(CustomerManager.list_customers(), allowed)
    customer_map = {}
    for c in customers:
        cid = c.get("_id", "")
        if cid:
            customer_map[cid] = c.get("CustomerName", "Unknown")

    # ── ALSO MRR per customer ──
    also_by_customer: dict[str, dict] = {}
    try:
        async with get_db() as db:
            async with db.execute(
                """SELECT r.customer_id, r.customer_name,
                          d.monthly_cost, d.currency
                   FROM also_renewals r
                   LEFT JOIN also_subscription_details d
                       ON r.subscription_id = d.subscription_id"""
            ) as cur:
                for row in await cur.fetchall():
                    r = dict(row)
                    cid = r["customer_id"] or ""
                    if not cid:
                        continue
                    if cid not in also_by_customer:
                        also_by_customer[cid] = {
                            "mrr": 0.0,
                            "count": 0,
                            "currency": "",
                            "name": r.get("customer_name", ""),
                        }
                    also_by_customer[cid]["count"] += 1
                    also_by_customer[cid]["mrr"] += r.get("monthly_cost") or 0
                    if r.get("currency") and not also_by_customer[cid]["currency"]:
                        also_by_customer[cid]["currency"] = r["currency"]
    except Exception as exc:
        logger.warning("Failed to read ALSO renewals for costs: %s", exc)

    # ── Uniweb monthly costs per customer ──
    uniweb_by_customer: dict[str, dict] = {}
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT customer_id, name, data_json FROM uniweb_accounts WHERE customer_id IS NOT NULL"
            ) as cur:
                for row in await cur.fetchall():
                    r = dict(row)
                    cid = r["customer_id"] or ""
                    if not cid:
                        continue
                    data = {}
                    if r["data_json"]:
                        try:
                            data = json.loads(r["data_json"])
                        except json.JSONDecodeError:
                            pass
                    subs = data.get("subscriptions", [])
                    monthly = 0.0
                    for sub in subs:
                        price_str = sub.get("Price per month", sub.get("price_monthly", ""))
                        try:
                            cleaned = str(price_str).replace(",", ".").replace(" ", "").replace("NOK", "").replace("kr", "")
                            cleaned = "".join(ch for ch in cleaned if ch.isdigit() or ch == ".")
                            if cleaned:
                                monthly += float(cleaned)
                        except (ValueError, TypeError):
                            pass
                    if cid not in uniweb_by_customer:
                        uniweb_by_customer[cid] = {"monthly": 0.0, "count": 0}
                    uniweb_by_customer[cid]["monthly"] += monthly
                    uniweb_by_customer[cid]["count"] += len(subs)
    except Exception as exc:
        logger.warning("Failed to read Uniweb accounts for costs: %s", exc)

    # ── Merge into per-customer results ──
    all_cids = set(also_by_customer.keys()) | set(uniweb_by_customer.keys())
    results: list[dict] = []

    for cid in all_cids:
        also = also_by_customer.get(cid, {})
        uniweb = uniweb_by_customer.get(cid, {})
        also_mrr = round(also.get("mrr", 0), 2)
        uniweb_monthly = round(uniweb.get("monthly", 0), 2)
        total = round(also_mrr + uniweb_monthly, 2)
        name = customer_map.get(cid, also.get("name", ""))
        currency = also.get("currency", "") or "NOK"

        results.append({
            "customer_id": cid,
            "customer_name": name,
            "also_mrr": also_mrr,
            "uniweb_monthly": uniweb_monthly,
            "total_monthly": total,
            "also_subscriptions": also.get("count", 0),
            "uniweb_subscriptions": uniweb.get("count", 0),
            "currency": currency,
        })

    results.sort(key=lambda x: x["total_monthly"], reverse=True)

    total_also = round(sum(r["also_mrr"] for r in results), 2)
    total_uniweb = round(sum(r["uniweb_monthly"] for r in results), 2)

    return {
        "customers": results,
        "totals": {
            "also_mrr": total_also,
            "uniweb_monthly": total_uniweb,
            "total_monthly": round(total_also + total_uniweb, 2),
            "customer_count": len(results),
        },
    }


# ── Domain health dashboard ─────────────────────────────────────────────────

@router.get("/dashboard/domains")
async def dashboard_domains(user=Depends(get_current_user)):
    """Unified domain health: Uniweb domains + TLS status + DNS summary."""
    import asyncio

    from app.core.customer import CustomerManager
    from app.core.database import get_db
    from app.services.tls_monitor import check_endpoint_tls

    now = datetime.now(timezone.utc)

    # ── Load all Uniweb accounts ──
    async with get_db() as db:
        async with db.execute(
            "SELECT id, name, customer_id, data_json FROM uniweb_accounts"
        ) as cur:
            rows = await cur.fetchall()

    # Resolve customer names
    customer_names: dict[str, str] = {}
    cids = {r["customer_id"] for r in rows if r["customer_id"]}
    if cids:
        for cid in cids:
            cust = CustomerManager.get_customer(cid)
            if cust:
                customer_names[cid] = cust.get("CustomerName", "")

    # ── Collect all domains ──
    domain_entries: list[dict] = []
    tls_hosts: list[str] = []

    for row in rows:
        data: dict = {}
        if row["data_json"]:
            try:
                data = json.loads(row["data_json"])
            except json.JSONDecodeError:
                continue

        acct_name = row["name"]
        cust_name = customer_names.get(row["customer_id"], "") if row["customer_id"] else ""
        display_name = cust_name or acct_name

        for dom in data.get("domains", []):
            domain_name = dom.get("domain") or dom.get("") or ""
            if not domain_name:
                vals = list(dom.values())
                domain_name = vals[0] if vals and isinstance(vals[0], str) else ""
            if not domain_name:
                continue

            # Parse expiry
            expiry_str = (dom.get("expiry") or "").strip()
            days_until_expiry = None
            if expiry_str and len(expiry_str) >= 10:
                try:
                    exp_date = datetime.fromisoformat(expiry_str[:10])
                    exp_date = exp_date.replace(tzinfo=timezone.utc)
                    days_until_expiry = (exp_date - now).days
                except (ValueError, TypeError):
                    pass

            # DNS records analysis
            dns_records = dom.get("dns", [])
            has_spf = False
            has_dkim = False
            has_dmarc = False
            for rec in dns_records:
                rtype = (rec.get("type") or "").upper()
                val = (rec.get("value") or "").lower()
                hostname = (rec.get("hostname") or "").lower()
                if rtype == "TXT":
                    if "v=spf1" in val:
                        has_spf = True
                    if "v=dmarc1" in val:
                        has_dmarc = True
                # DKIM: TXT with k=rsa or CNAME for _domainkey selector
                if "_domainkey" in hostname:
                    if rtype == "CNAME" or (rtype == "TXT" and "k=rsa" in val):
                        has_dkim = True

            # Match SSL from Uniweb ssl section
            ssl_info = None
            for cert in data.get("ssl", []):
                cert_domain = (cert.get("domain") or "").strip().lower()
                if cert_domain == domain_name.lower() or cert_domain == f"*.{domain_name.lower()}":
                    cert_expiry = (cert.get("expiry") or "").strip()
                    ssl_days = None
                    if cert_expiry and len(cert_expiry) >= 10:
                        try:
                            dt = datetime.fromisoformat(cert_expiry[:10])
                            dt = dt.replace(tzinfo=timezone.utc)
                            ssl_days = (dt - now).days
                        except (ValueError, TypeError):
                            pass
                    ssl_info = {
                        "issuer": cert.get("issuer", ""),
                        "valid_until": cert_expiry[:10] if cert_expiry else "",
                        "days_remaining": ssl_days,
                        "grade": None,
                    }
                    break

            entry = {
                "domain": domain_name,
                "customer_name": display_name,
                "customer_id": row["customer_id"] or "",
                "source": "uniweb",
                "registrar": "Uniweb",
                "expiry": expiry_str[:10] if expiry_str else "",
                "days_until_expiry": days_until_expiry,
                "ssl": ssl_info,
                "dns_records": len(dns_records),
                "has_spf": has_spf,
                "has_dkim": has_dkim,
                "has_dmarc": has_dmarc,
                "_uniweb_dns": dns_records,  # passed to live DNS checker for selector discovery
                "health": "good",  # computed below
            }
            domain_entries.append(entry)
            tls_hosts.append(domain_name)

    # ── Add M365 customer primary domains not already covered by Uniweb ──
    existing_domains = {e["domain"].lower() for e in domain_entries}
    allowed_ids = await get_accessible_customer_ids(user)
    all_customers = filter_customers(CustomerManager.list_customers(), allowed_ids)
    for c in all_customers:
        pd = (c.get("PrimaryDomain") or "").strip().lower()
        if pd and pd not in existing_domains and not pd.endswith(".onmicrosoft.com"):
            cid = c.get("_id", "")
            name = c.get("CustomerName", "Unknown")
            domain_entries.append({
                "domain": pd,
                "customer_name": name,
                "customer_id": cid,
                "source": "m365",
                "registrar": "",
                "expiry": "",
                "days_until_expiry": None,
                "ssl": None,
                "dns_records": 0,
                "has_spf": False,
                "has_dkim": False,
                "has_dmarc": False,
                "health": "unknown",
            })
            existing_domains.add(pd)

    # ── Live TLS checks (concurrent, with timeout) ──
    tls_results: dict[str, dict] = {}
    if tls_hosts:
        tasks = [check_endpoint_tls(h, 443, timeout=4.0) for h in tls_hosts]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, res in enumerate(results):
            host = tls_hosts[i]
            if isinstance(res, Exception):
                tls_results[host] = {"valid": False, "error": str(res)}
            else:
                tls_results[host] = res

    # ── Live DNS email-security checks (SPF/DKIM/DMARC) ──
    # Pass Uniweb zone records so the checker can discover custom DKIM selectors
    from app.services.dns_checker import check_domain as dns_check_domain
    loop = asyncio.get_event_loop()
    domain_dns_map: dict[str, list[dict]] = {}
    for entry in domain_entries:
        if entry.get("_uniweb_dns"):
            domain_dns_map[entry["domain"]] = entry["_uniweb_dns"]
    all_domain_names = [e["domain"] for e in domain_entries if e["domain"]]
    dns_tasks = [
        loop.run_in_executor(None, dns_check_domain, d, domain_dns_map.get(d))
        for d in all_domain_names[:100]
    ]
    dns_results_list = await asyncio.gather(*dns_tasks, return_exceptions=True)
    dns_results: dict[str, dict] = {}
    for i, res in enumerate(dns_results_list):
        if not isinstance(res, Exception):
            dns_results[all_domain_names[i]] = res

    # ── Merge TLS + DNS results into entries and compute health ──
    for entry in domain_entries:
        # Enrich with live DNS results
        dns = dns_results.get(entry["domain"])
        if dns:
            entry["has_spf"] = dns["spf"]["status"] not in ("fail",)
            entry["has_dkim"] = dns["dkim"]["status"] in ("pass",)
            entry["has_dmarc"] = dns["dmarc"]["status"] not in ("fail",)
            # "unverifiable" DKIM = we couldn't find a selector but one may exist
            entry["dkim_unverifiable"] = dns["dkim"]["status"] == "unverifiable"
            entry["dns_live"] = {
                "grade": dns.get("grade"),
                "spf": dns["spf"],
                "dkim": dns["dkim"],
                "dmarc": dns["dmarc"],
                "mx": dns["mx"],
            }
        domain = entry["domain"]
        tls = tls_results.get(domain)

        # If live TLS gave us data, prefer it over Uniweb ssl section
        if tls and not tls.get("error"):
            issuer_info = tls.get("issuer", {})
            issuer_name = (
                issuer_info.get("organizationName", issuer_info.get("commonName", ""))
                if isinstance(issuer_info, dict)
                else str(issuer_info)
            )
            days_rem = tls.get("days_remaining")
            not_after = tls.get("not_after", "")

            # Determine grade
            grade = "A+"
            if tls.get("weak_cipher"):
                grade = "B"
            if tls.get("weak_protocol"):
                grade = "C"
            if tls.get("expired"):
                grade = "F"
            elif days_rem is not None and days_rem < 30:
                grade = "B"

            entry["ssl"] = {
                "issuer": issuer_name,
                "valid_until": not_after[:10] if not_after else "",
                "days_remaining": days_rem,
                "grade": grade,
            }
        elif tls and tls.get("error"):
            # TLS check failed — mark as unknown if no Uniweb SSL data
            if not entry["ssl"]:
                entry["ssl"] = {
                    "issuer": "",
                    "valid_until": "",
                    "days_remaining": None,
                    "grade": None,
                }

        # ── Compute health status ──
        ssl = entry.get("ssl")
        ssl_ok = True
        ssl_expiring = False

        if ssl and ssl.get("days_remaining") is not None:
            if ssl["days_remaining"] < 0:
                ssl_ok = False
            elif ssl["days_remaining"] < 30:
                ssl_expiring = True

        domain_expired = False
        if entry.get("days_until_expiry") is not None and entry["days_until_expiry"] < 0:
            domain_expired = True

        if not ssl_ok or domain_expired:
            entry["health"] = "critical"
        elif ssl_expiring or not entry["has_spf"] or not entry["has_dmarc"]:
            entry["health"] = "warning"
        else:
            entry["health"] = "good"

    # ── Sort: critical first, then warning, then good ──
    health_order = {"critical": 0, "warning": 1, "good": 2}
    domain_entries.sort(key=lambda e: (health_order.get(e["health"], 9), e["domain"]))

    # ── Summary ──
    total = len(domain_entries)
    healthy = sum(1 for e in domain_entries if e["health"] == "good")
    warning = sum(1 for e in domain_entries if e["health"] == "warning")
    critical = sum(1 for e in domain_entries if e["health"] == "critical")
    missing_spf = sum(1 for e in domain_entries if not e["has_spf"])
    missing_dmarc = sum(1 for e in domain_entries if not e["has_dmarc"])
    ssl_expiring_30d = sum(
        1 for e in domain_entries
        if e.get("ssl") and e["ssl"].get("days_remaining") is not None
        and 0 <= e["ssl"]["days_remaining"] < 30
    )

    return {
        "domains": domain_entries,
        "summary": {
            "total": total,
            "healthy": healthy,
            "warning": warning,
            "critical": critical,
            "missing_spf": missing_spf,
            "missing_dmarc": missing_dmarc,
            "ssl_expiring_30d": ssl_expiring_30d,
        },
    }


# ── Network Inventory ───────────────────────────────────────────────────────


async def _build_network_inventory_for_customer(cust: dict) -> dict | None:
    """Build network inventory data for a single customer.

    Fetches UniFi devices (APs, switches, gateways) and FortiGate status,
    then computes capacity metrics and firmware alerts.

    Returns None if the customer has no network devices configured.
    """
    import asyncio

    from app.core.credentials import get_secret
    from app.modules.unifi_audit.firmware_db import check_firmware

    cust_id = cust.get("_id", "")
    name = cust.get("CustomerName", "Unknown")

    aps: list[dict] = []
    switches: list[dict] = []
    gateways: list[dict] = []
    firewalls: list[dict] = []
    alerts: list[str] = []
    # True when a controller or firewall was configured but its read was
    # refused. It keeps the customer in the inventory (with the alert visible)
    # instead of dropping the row as if no network were configured.
    read_unavailable = False

    # ── UniFi ──
    uf_host = cust.get("UniFiHost")
    uf_mode = cust.get("UniFiMode", "controller")

    if uf_host and uf_mode == "controller":
        try:
            from app.services.unifi_api import _controller_for_customer, _default_site
            client = await _controller_for_customer(cust_id)
            site = _default_site(cust_id)
            try:
                devices_raw, clients_raw = await asyncio.gather(
                    client.get_devices(site),
                    client.get_clients(site),
                )
            finally:
                await client.close()

            # A refused device read would otherwise drop this customer's APs
            # and switches from the inventory silently — no row, no firmware
            # alert, reading as a customer with no UniFi rather than one whose
            # controller could not be reached. Surface it as an alert so the
            # gap is visible.
            from app.modules.api_result import read_failed
            if read_failed(devices_raw):
                read_unavailable = True
                alerts.append(
                    f"UniFi-kontrolleren kunne ikke leses ({cust.get('UniFiHost', '?')}) "
                    "— enheter mangler i oversikten"
                )

            # Build AP → client count map
            clients_by_ap: dict[str, int] = {}
            for c in clients_raw:
                ap_mac = c.get("ap_mac", "")
                if ap_mac:
                    clients_by_ap[ap_mac] = clients_by_ap.get(ap_mac, 0) + 1

            for d in devices_raw:
                mac = d.get("mac", "")
                dev_name = d.get("name", d.get("hostname", mac or "unknown"))
                model = d.get("model", "")
                firmware = d.get("version", "")
                state_val = d.get("state", 0)
                status = "online" if state_val == 1 else "offline"
                dev_type = d.get("type", "")

                # Firmware check
                fw_info = check_firmware(model, firmware)
                fw_status = fw_info.get("severity", "unknown")
                if fw_status in ("warning", "critical"):
                    latest = fw_info.get("latest", "?")
                    alerts.append(f"{dev_name} firmware outdated ({firmware} \u2192 {latest})")

                if dev_type == "uap":
                    num_clients = clients_by_ap.get(mac, d.get("num_sta", 0))
                    aps.append({
                        "name": dev_name,
                        "model": model,
                        "firmware": firmware,
                        "clients": num_clients,
                        "status": status,
                        "fw_status": fw_status,
                    })
                    # Capacity alert: typical AP max ~60-80 clients
                    if num_clients > 50:
                        alerts.append(f"{dev_name} high client load ({num_clients} clients)")
                elif dev_type == "usw":
                    port_table = d.get("port_table", [])
                    ports_total = len(port_table) if port_table else d.get("port_overrides", 0)
                    ports_used = sum(1 for p in port_table if p.get("up", False)) if port_table else 0
                    switches.append({
                        "name": dev_name,
                        "model": model,
                        "firmware": firmware,
                        "ports_used": ports_used,
                        "ports_total": ports_total,
                        "status": status,
                        "fw_status": fw_status,
                    })
                    if ports_total > 0:
                        usage_pct = round(ports_used / ports_total * 100)
                        if usage_pct >= 80:
                            alerts.append(f"{dev_name} port usage {usage_pct}%")
                elif dev_type == "ugw":
                    gateways.append({
                        "name": dev_name,
                        "model": model,
                        "firmware": firmware,
                        "status": status,
                        "wan_ip": d.get("wan1", {}).get("ip", d.get("ip", "")),
                        "fw_status": fw_status,
                    })

        except Exception as e:
            logger.debug("UniFi fetch failed for %s: %s", name, e)

    # ── FortiGate ──
    fg_host = cust.get("FortiGateHost")
    fg_token = get_secret(cust_id, "fortigate_api_token") if fg_host else None

    if fg_host and fg_token:
        try:
            from app.services.fortigate_api import get_dashboard as fg_dashboard
            fg_data = await fg_dashboard(cust, fg_token)
            # Symmetric with UniFi above: an unreachable firewall must not be
            # appended as a healthy row (hostname falls back to the host, cpu/vpn
            # read as 0/None) — that reads as an online firewall with nothing on
            # it. Surface the gap as an alert instead.
            if fg_data.get("unavailable"):
                read_unavailable = True
                alerts.append(
                    f"FortiGate kunne ikke leses ({fg_host}) — brannmur mangler i oversikten"
                )
            else:
                firewalls.append({
                    "name": fg_data.get("hostname", fg_host),
                    "model": fg_data.get("model", "FortiGate"),
                    "firmware": fg_data.get("firmware", ""),
                    "ha": fg_data.get("ha_mode", "standalone"),
                    "vpn_tunnels": fg_data.get("vpn_tunnels", 0),
                    "active_sessions": fg_data.get("active_sessions", 0),
                    "cpu_percent": fg_data.get("cpu_percent", 0),
                    "memory_percent": fg_data.get("memory_percent", 0),
                    "serial": fg_data.get("serial", ""),
                    "wan_ip": fg_data.get("wan_ip", ""),
                    "uptime": fg_data.get("uptime", ""),
                })
        except Exception as e:
            logger.debug("FortiGate fetch failed for %s: %s", name, e)

    total_clients = sum(ap.get("clients", 0) for ap in aps)
    has_devices = bool(aps or switches or gateways or firewalls)

    # Drop the customer only when nothing was configured to read. A customer
    # whose controller or firewall refused the read (read_unavailable) stays in
    # the inventory so the alert is seen — dropping the row would render an
    # unreachable network as "no network".
    if not has_devices and not read_unavailable:
        return None

    return {
        "customer_id": cust_id,
        "customer_name": name,
        "unavailable": read_unavailable,
        "devices": {
            "aps": aps,
            "switches": switches,
            "gateways": gateways,
            "firewalls": firewalls,
        },
        "totals": {
            "aps": len(aps),
            "switches": len(switches),
            "gateways": len(gateways),
            "firewalls": len(firewalls),
            "total_clients": total_clients,
        },
        "alerts": alerts,
    }


@router.get("/dashboard/network-inventory")
async def get_network_inventory(user=Depends(get_current_user)):
    """Aggregate network inventory across all customers.

    For each customer that has UniFi and/or FortiGate configured, fetch
    device data, capacity metrics, and firmware alerts.
    """
    import asyncio

    from app.core.customer import CustomerManager

    allowed = await get_accessible_customer_ids(user)
    customers = filter_customers(CustomerManager.list_customers(), allowed)

    # Only query customers that have network devices configured
    net_customers = [
        c for c in customers
        if c.get("UniFiHost") or c.get("FortiGateHost")
    ]

    if not net_customers:
        return {"customers": [], "summary": {"total_devices": 0, "outdated_firmware": 0, "high_utilization": 0}}

    tasks = [_build_network_inventory_for_customer(c) for c in net_customers]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    customer_data: list[dict] = []
    total_devices = 0
    outdated_firmware = 0
    high_utilization = 0

    for r in results:
        if isinstance(r, Exception):
            logger.warning("Network inventory task failed: %s", r)
            continue
        if r is None:
            continue
        customer_data.append(r)
        t = r["totals"]
        total_devices += t["aps"] + t["switches"] + t["gateways"] + t["firewalls"]
        outdated_firmware += sum(
            1 for dev_list in r["devices"].values()
            for dev in dev_list
            if dev.get("fw_status") in ("warning", "critical")
        )
        high_utilization += sum(
            1 for a in r["alerts"]
            if "port usage" in a or "high client load" in a
        )

    return {
        "customers": customer_data,
        "summary": {
            "total_devices": total_devices,
            "outdated_firmware": outdated_firmware,
            "high_utilization": high_utilization,
        },
    }


@router.get("/dashboard/network-inventory/{customer_id}")
async def get_network_inventory_customer(
    customer_id: str, user=Depends(require_customer_access(Role.viewer))
):
    """Network inventory for a single customer."""
    from app.core.customer import CustomerManager

    if not await check_customer_access(user, customer_id):
        raise AuthError("Ingen tilgang til denne kunden")
    cust = CustomerManager.get_customer(customer_id)
    if not cust:
        raise NotFoundError("Kunde ikke funnet")

    result = await _build_network_inventory_for_customer(cust)
    if result is None:
        return {
            "customer_id": customer_id,
            "customer_name": cust.get("CustomerName", "Unknown"),
            "devices": {"aps": [], "switches": [], "gateways": [], "firewalls": []},
            "totals": {"aps": 0, "switches": 0, "gateways": 0, "firewalls": 0, "total_clients": 0},
            "alerts": [],
        }
    return result


# ── Security Report ─────────────────────────────────────────────────────────

@router.get("/dashboard/security-report")
async def dashboard_security_report(user=Depends(get_current_user)):
    """Per-customer security overview: MFA, SPF/DKIM/DMARC, FortiGate firmware, threats, grade."""
    from app.core.customer import CustomerManager
    from app.core.database import get_db

    now = datetime.now(timezone.utc)
    allowed = await get_accessible_customer_ids(user)
    customers = filter_customers(CustomerManager.list_customers(), allowed)

    # ── Pre-fetch: latest audit metrics per customer ──
    metrics_by_customer: dict[str, dict] = {}
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT customer_id, risk_grade, risk_score, secure_score_pct, "
                "mfa_coverage_pct, total_users, users_no_mfa, audit_date "
                "FROM audit_metrics ORDER BY audit_date DESC"
            ) as cur:
                for r in await cur.fetchall():
                    row = dict(r)
                    cid = row["customer_id"]
                    if cid not in metrics_by_customer:
                        # Add staleness info
                        audit_date_str = row.get("audit_date", "")
                        if audit_date_str:
                            try:
                                ad = datetime.fromisoformat(audit_date_str[:10]).replace(tzinfo=timezone.utc)
                                row["audit_age_days"] = (datetime.now(timezone.utc) - ad).days
                                row["is_stale"] = row["audit_age_days"] > 30
                            except (ValueError, TypeError):
                                row["audit_age_days"] = None
                                row["is_stale"] = True
                        else:
                            row["audit_age_days"] = None
                            row["is_stale"] = True
                        metrics_by_customer[cid] = row
    except Exception as exc:
        logger.warning("security-report: failed to read audit_metrics: %s", exc)

    # ── Pre-fetch: Uniweb data per customer (DNS records) ──
    uniweb_by_cust: dict[str, dict] = {}
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT customer_id, data_json FROM uniweb_accounts "
                "WHERE customer_id IS NOT NULL"
            ) as cur:
                for r in await cur.fetchall():
                    cid = r["customer_id"]
                    if cid and r["data_json"]:
                        try:
                            uniweb_by_cust[cid] = json.loads(r["data_json"])
                        except json.JSONDecodeError:
                            pass
    except Exception as exc:
        logger.warning("security-report: failed to read uniweb_accounts: %s", exc)

    # ── Pre-fetch: FortiGate status for all customers ──
    fg_by_cust: dict[str, dict] = {}
    try:
        from app.services.fortigate_api import poll_all_fortigates
        fg_results = await poll_all_fortigates()
        for fg in fg_results:
            cid = fg.get("customer_id", "")
            if cid:
                fg_by_cust[cid] = fg
    except Exception as exc:
        logger.warning("security-report: failed to poll FortiGates: %s", exc)

    results: list[dict] = []

    for c in customers:
        cid = c.get("_id", "")
        name = c.get("CustomerName", "Unknown")

        # ── MFA coverage ──
        audit = metrics_by_customer.get(cid)
        mfa_pct = None
        if audit and audit.get("mfa_coverage_pct") is not None:
            mfa_pct = round(audit["mfa_coverage_pct"], 1)

        # ── SPF / DKIM / DMARC from Uniweb DNS ──
        has_spf = False
        has_dkim = False
        has_dmarc = False
        uw_data = uniweb_by_cust.get(cid)
        if uw_data:
            for dom in uw_data.get("domains", []):
                for rec in dom.get("dns", []):
                    rtype = (rec.get("type") or "").upper()
                    val = (rec.get("value") or "").lower()
                    hostname = (rec.get("hostname") or "").lower()
                    if rtype == "TXT":
                        if "v=spf1" in val:
                            has_spf = True
                        if "v=dmarc1" in val:
                            has_dmarc = True
                    # DKIM: TXT with k=rsa or CNAME for _domainkey selector
                    if "_domainkey" in hostname:
                        if rtype == "CNAME" or (rtype == "TXT" and "k=rsa" in val):
                            has_dkim = True

        # ── FortiGate firmware + threat count ──
        fg = fg_by_cust.get(cid)
        firmware = None
        firmware_outdated = False
        threat_count = None
        if fg and fg.get("status") == "online":
            firmware = fg.get("firmware", "")
            # Flag outdated if major version < 7.4
            if firmware:
                try:
                    parts = firmware.replace("v", "").split(".")
                    major = int(parts[0])
                    minor = int(parts[1]) if len(parts) > 1 else 0
                    if major < 7 or (major == 7 and minor < 4):
                        firmware_outdated = True
                except (ValueError, IndexError):
                    pass
            # Not zero. Nothing here reads a threat log — get_threat_summary()
            # does that, and this route does not call it. A hardcoded 0 was
            # rendered as a green "0 threats" for every online firewall, which
            # is a measurement nobody took. None makes the card omit the
            # figure, which the frontend already handles.
            threat_count = None
        elif c.get("FortiGateHost"):
            firmware = "offline"

        # ── Security grade ──
        score = 0
        max_score = 0

        # MFA (25 pts)
        max_score += 25
        if mfa_pct is not None:
            if mfa_pct >= 100:
                score += 25
            elif mfa_pct >= 80:
                score += 20
            elif mfa_pct >= 50:
                score += 10

        # SPF (10), DKIM (10), DMARC (10)
        max_score += 30
        if uw_data:
            if has_spf:
                score += 10
            if has_dkim:
                score += 10
            if has_dmarc:
                score += 10
        else:
            max_score -= 30

        # FortiGate firmware (15)
        max_score += 15
        if firmware and firmware != "offline":
            score += 15 if not firmware_outdated else 5
        elif not c.get("FortiGateHost"):
            max_score -= 15

        # Audit risk grade (20)
        max_score += 20
        if audit:
            grade = (audit.get("risk_grade") or "").upper()
            grade_pts = {"A": 20, "B": 15, "C": 10, "D": 5, "F": 0}
            score += grade_pts.get(grade, 0)

        pct = round((score / max_score) * 100) if max_score > 0 else 0
        if pct >= 90:
            sec_grade = "A"
        elif pct >= 75:
            sec_grade = "B"
        elif pct >= 50:
            sec_grade = "C"
        else:
            sec_grade = "D"

        results.append({
            "customer_id": cid,
            "customer_name": name,
            "mfa_pct": mfa_pct,
            "has_spf": has_spf,
            "has_dkim": has_dkim,
            "has_dmarc": has_dmarc,
            "firmware": firmware,
            "firmware_outdated": firmware_outdated,
            "threat_count": threat_count,
            "security_grade": sec_grade,
            "security_score": pct,
        })

    grade_order = {"D": 0, "C": 1, "B": 2, "A": 3}
    results.sort(key=lambda x: (grade_order.get(x["security_grade"], 9), x["security_score"]))

    summary = {
        "total": len(results),
        "grade_a": sum(1 for r in results if r["security_grade"] == "A"),
        "grade_b": sum(1 for r in results if r["security_grade"] == "B"),
        "grade_c": sum(1 for r in results if r["security_grade"] == "C"),
        "grade_d": sum(1 for r in results if r["security_grade"] == "D"),
        "avg_score": round(sum(r["security_score"] for r in results) / len(results), 1) if results else 0,
    }

    return {"customers": results, "summary": summary}


# ── VPN Monitoring ──────────────────────────────────────────────────────────

@router.get("/dashboard/vpn-status")
async def dashboard_vpn_status(user=Depends(get_current_user)):
    """Per-customer VPN tunnel status from FortiGate devices."""
    import asyncio

    from app.core.credentials import get_secret
    from app.core.customer import CustomerManager
    from app.modules.fortigate_audit.client import FortiGateClient

    allowed = await get_accessible_customer_ids(user)
    customers = filter_customers(CustomerManager.list_customers(), allowed)
    fg_customers = []
    for c in customers:
        if not c.get("FortiGateHost"):
            continue
        cid = c.get("_id", "")
        token = get_secret(cid, "fortigate_api_token")
        if token:
            fg_customers.append((c, token))

    if not fg_customers:
        return {"customers": [], "total_customers": 0, "total_tunnels": 0}

    async def _get_vpn(cust: dict, token: str) -> dict:
        cid = cust.get("_id", "")
        name = cust.get("CustomerName", "Unknown")
        try:
            async with FortiGateClient(
                cust.get("FortiGateHost", ""),
                token,
                port=int(cust.get("FortiGatePort", 443)),
                vdom=cust.get("FortiGateVDOM", "root"),
                verify_ssl=cust.get("FortiGateVerifySSL", False),
            ) as fg:
                ipsec, ssl_vpn = await asyncio.gather(
                    fg.get_monitor("vpn/ipsec"),
                    fg.get_monitor("vpn.ssl/monitor"),
                    return_exceptions=True,
                )

                # The IPsec read carries the tunnel list. If it refused, this
                # firewall's VPN status is unknown — not "online with 0
                # tunnels", which is how an empty result read and which looks
                # like every tunnel is down rather than unread.
                from app.modules.api_result import read_error, read_failed
                if isinstance(ipsec, Exception) or read_failed(ipsec):
                    reason = str(ipsec) if isinstance(ipsec, Exception) else read_error(ipsec)
                    return {
                        "customer_id": cid, "customer_name": name,
                        "status": "error", "error": reason, "tunnels": [],
                    }

                tunnels: list[dict] = []

                # IPsec tunnels
                ipsec_list = []
                if isinstance(ipsec, list):
                    ipsec_list = ipsec
                elif isinstance(ipsec, dict):
                    ipsec_list = ipsec.get("results", ipsec.get("tunnel", []))

                for tun in ipsec_list:
                    tname = tun.get("name", tun.get("p2name", ""))
                    proxyid = tun.get("proxyid", [])
                    tun_status = "up" if tun.get("status", "") == "up" or tun.get("incoming_bytes", 0) > 0 else "down"
                    bytes_in = tun.get("incoming_bytes", 0)
                    bytes_out = tun.get("outgoing_bytes", 0)

                    if isinstance(proxyid, list) and proxyid:
                        for p in proxyid:
                            p_status = "up" if p.get("status", "") == "up" else "down"
                            tunnels.append({
                                "name": p.get("p2name", tname),
                                "type": "IPsec",
                                "status": p_status,
                                "bytes_in": p.get("incoming_bytes", bytes_in),
                                "bytes_out": p.get("outgoing_bytes", bytes_out),
                            })
                    else:
                        tunnels.append({
                            "name": tname,
                            "type": "IPsec",
                            "status": tun_status,
                            "bytes_in": bytes_in,
                            "bytes_out": bytes_out,
                        })

                # SSL VPN users. A refused read here (an empty ApiDict, which is
                # still a dict) would silently contribute no SSL-VPN sessions —
                # reading as "nobody on SSL-VPN" rather than "unread". IPsec
                # already answered, so we keep those tunnels but flag the gap.
                ssl_vpn_unavailable = isinstance(ssl_vpn, Exception) or read_failed(ssl_vpn)
                if isinstance(ssl_vpn, dict) and not read_failed(ssl_vpn):
                    ssl_users = ssl_vpn.get("results", ssl_vpn.get("users", []))
                    if isinstance(ssl_users, list):
                        for u in ssl_users:
                            tunnels.append({
                                "name": u.get("user_name", u.get("username", "unknown")),
                                "type": "SSL-VPN",
                                "status": "up",
                                "bytes_in": u.get("incoming_bytes", 0),
                                "bytes_out": u.get("outgoing_bytes", 0),
                            })

                result = {
                    "customer_id": cid,
                    "customer_name": name,
                    "status": "online",
                    "tunnels": tunnels,
                }
                if ssl_vpn_unavailable:
                    result["ssl_vpn_unavailable"] = True
                return result
        except Exception as e:
            return {
                "customer_id": cid,
                "customer_name": name,
                "status": "error",
                "error": str(e),
                "tunnels": [],
            }

    async def _with_timeout(cust, token):
        try:
            return await asyncio.wait_for(_get_vpn(cust, token), timeout=10)
        except asyncio.TimeoutError:
            return {
                "customer_id": cust.get("_id", ""),
                "customer_name": cust.get("CustomerName", "Unknown"),
                "status": "error",
                "error": "Timeout (10s)",
                "tunnels": [],
            }

    all_results = await asyncio.gather(*[_with_timeout(c, t) for c, t in fg_customers])
    results = [r for r in all_results if r is not None]
    results.sort(key=lambda x: (0 if x["status"] == "error" else 1, x["customer_name"].lower()))

    total_tunnels = sum(len(r.get("tunnels", [])) for r in results)
    # Only customers that actually have at least one VPN tunnel count toward
    # the "customers with VPN" stat. Counting all scanned customers made the
    # number visually useless (e.g. "258 customers" when only 8 had tunnels).
    customers_with_vpn = sum(1 for r in results if r.get("tunnels"))
    errors = [r for r in results if r.get("status") == "error"]
    warnings = []
    if errors:
        names = ", ".join(r["customer_name"] for r in errors[:3])
        suffix = f" +{len(errors) - 3}" if len(errors) > 3 else ""
        warnings.append(f"{len(errors)} enheter utilgjengelig: {names}{suffix}")

    return {
        "customers": results,
        # How many FortiGate customers we scanned (backward-compat field).
        "total_customers": len(results),
        # How many of those actually have at least one VPN tunnel up/known.
        "customers_with_vpn": customers_with_vpn,
        "total_tunnels": total_tunnels,
        "warnings": warnings,
        "partial": len(errors) > 0,
    }


# ── Domain-Email-License Chain Detection ──────────────────────────────────

@router.get("/dashboard/domain-email-chain")
async def dashboard_domain_email_chain(user=Depends(get_current_user)):
    """Detect domain-email-license mismatches: double-paying, missing M365, etc."""
    from app.core.customer import CustomerManager
    from app.core.database import get_db

    allowed = await get_accessible_customer_ids(user)
    customers = filter_customers(CustomerManager.list_customers(), allowed)
    customer_map = {}
    for c in customers:
        cid = c.get("_id", "")
        if cid:
            customer_map[cid] = c.get("CustomerName", "Unknown")

    # ── Load Uniweb + ALSO data in single DB connection ──
    uniweb_by_cust: dict[str, dict] = {}
    also_by_cust: dict[str, list[dict]] = {}
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT customer_id, name, data_json FROM uniweb_accounts "
                "WHERE customer_id IS NOT NULL"
            ) as cur:
                for r in await cur.fetchall():
                    cid = r["customer_id"]
                    if cid and r["data_json"]:
                        try:
                            uniweb_by_cust[cid] = json.loads(r["data_json"])
                        except json.JSONDecodeError:
                            pass
            async with db.execute(
                "SELECT customer_id, customer_name, service_name, service_display FROM also_renewals"
            ) as cur:
                for r in await cur.fetchall():
                    row = dict(r)
                    cid = row["customer_id"]
                    also_by_cust.setdefault(cid, []).append(row)
    except Exception as exc:
        logger.warning("domain-email-chain: failed to read data: %s", exc)

    # Build normalized lookup: strip special chars so "A_S" matches "AS"
    import re as _re
    def _norm(s: str) -> str:
        return _re.sub(r'[^a-z0-9]', '', s.lower())

    _also_norm_map: dict[str, str] = {}  # normalized → original cid
    for acid in also_by_cust:
        _also_norm_map[_norm(acid)] = acid

    def _has_m365_license(cid: str) -> bool:
        """Check if customer has any M365/Exchange license in ALSO."""
        # Try exact match first, then normalized match
        also_cid = cid
        if cid not in also_by_cust:
            also_cid = _also_norm_map.get(_norm(cid), "")
        subs = also_by_cust.get(also_cid, [])
        m365_keywords = (
            "microsoft 365", "office 365", "exchange online",
            "business basic", "business standard", "business premium",
            "e1", "e3", "e5", "f1", "f3",
        )
        for s in subs:
            # Check both internal service_name and human-readable service_display
            combined = (
                (s.get("service_name") or "") + " " + (s.get("service_display") or "")
            ).lower()
            if any(kw in combined for kw in m365_keywords):
                return True
        return False

    def _get_uniweb_email_domains(email_data: list[dict]) -> list[str]:
        """Extract domains with active email hosting in Uniweb."""
        email_domains = []
        for e in email_data:
            dom = e.get("domain", e.get("username_domain", ""))
            if dom and "@" in dom:
                dom = dom.split("@")[-1]
            if dom:
                email_domains.append(dom.lower())
        return email_domains

    chain_items: list[dict] = []

    for cid, uw_data in uniweb_by_cust.items():
        name = customer_map.get(cid, "")
        domains = uw_data.get("domains", [])
        email_data = uw_data.get("email", [])
        subs = uw_data.get("subscriptions", [])
        has_m365 = _has_m365_license(cid)

        uniweb_email_domains = _get_uniweb_email_domains(email_data)

        # Check email-type subscriptions in Uniweb
        email_sub_domains: list[str] = []
        for sub in subs:
            stype = (sub.get("Service type", sub.get("service_type", "")) or "").lower()
            sdomain = (sub.get("Username/domain", sub.get("username_domain", "")) or "").lower()
            if "e-post" in stype or "email" in stype or "mail" in stype:
                if sdomain:
                    email_sub_domains.append(sdomain)

        for dom in domains:
            domain_name = dom.get("domain") or ""
            if not domain_name:
                vals = list(dom.values())
                domain_name = vals[0] if vals and isinstance(vals[0], str) else ""
            if not domain_name:
                continue

            dns_records = dom.get("dns", [])
            mx_exchange = False
            mx_values: list[str] = []

            for rec in dns_records:
                if rec.get("type") == "MX":
                    mx_val = (rec.get("value") or "").lower()
                    mx_values.append(mx_val)
                    if "mail.protection.outlook.com" in mx_val:
                        mx_exchange = True

            dom_lower = domain_name.lower()
            has_uniweb_email = (
                dom_lower in uniweb_email_domains
                or dom_lower in email_sub_domains
            )

            alerts: list[dict] = []

            # Double-paying: domain uses Exchange (MX) AND has Uniweb email hosting
            if has_uniweb_email and mx_exchange:
                alerts.append({
                    "type": "double_paying",
                    "severity": "warning",
                    "message": "Domenet bruker Exchange Online men har også Uniweb e-posthosting — mulig dobbeltbetaling",
                })

            if alerts:
                chain_items.append({
                    "customer_id": cid,
                    "customer_name": name,
                    "domain": domain_name,
                    "mx_exchange": mx_exchange,
                    "mx_records": mx_values,
                    "has_m365": has_m365,
                    "has_uniweb_email": has_uniweb_email,
                    "alerts": alerts,
                })

    severity_order = {"critical": 0, "warning": 1, "info": 2}
    chain_items.sort(key=lambda x: min(
        severity_order.get(a["severity"], 9) for a in x["alerts"]
    ) if x["alerts"] else 9)

    summary = {
        "total_alerts": len(chain_items),
        "double_paying": sum(1 for i in chain_items if any(a["type"] == "double_paying" for a in i["alerts"])),
    }

    return {"items": chain_items, "summary": summary}


# ── Customer Infrastructure ─────────────────────────────────────────────────

@router.get("/dashboard/customer-infra/{customer_id}")
async def get_customer_infra(
    customer_id: str, user=Depends(require_customer_access(Role.viewer))
):
    """Return all infrastructure linked to a customer: SSH hosts, VPN profiles,
    FortiGate and UniFi config."""
    from app.core.customer import CustomerManager
    from app.services.ssh_manager import list_hosts
    from app.services.vpn_manager import list_profiles

    if not await check_customer_access(user, customer_id):
        raise AuthError("Ingen tilgang til denne kunden")
    cust = CustomerManager.get_customer(customer_id)
    if not cust:
        raise NotFoundError("Customer not found")

    # SSH hosts linked to this customer
    hosts = await list_hosts(customer_id=customer_id)
    ssh_hosts = [
        {
            "id": h.id,
            "label": h.label,
            "hostname": h.hostname,
            "port": h.port,
            "username": h.username,
            "device_type": h.device_type.value,
            "group_name": h.group_name,
            "is_reachable": h.is_reachable,
        }
        for h in hosts
    ]

    # VPN profiles linked to this customer
    all_profiles = await list_profiles()
    vpn_profiles = [
        {
            "id": p.id,
            "name": p.name,
            "protocol": p.protocol.value,
            "description": p.description,
            "customer_id": p.customer_id,
        }
        for p in all_profiles
        if p.customer_id == customer_id
    ]

    # FortiGate config from customer record
    fg_host = cust.get("FortiGateHost")
    fortigate = None
    if fg_host:
        fortigate = {
            "host": fg_host,
            "port": cust.get("FortiGatePort", 443),
            "vdom": cust.get("FortiGateVdom", "root"),
        }

    # UniFi config from customer record
    uf_host = cust.get("UniFiHost")
    unifi = None
    if uf_host:
        unifi = {
            "host": uf_host,
            "site": cust.get("UniFiSite", "default"),
            "mode": cust.get("UniFiMode", "controller"),
        }

    return {
        "ssh_hosts": ssh_hosts,
        "vpn_profiles": vpn_profiles,
        "fortigate": fortigate,
        "unifi": unifi,
    }


# ── Compliance dashboard ────────────────────────────────────────────────────

@router.get("/dashboard/compliance")
async def dashboard_compliance(user=Depends(get_current_user)):
    """Cross-customer compliance overview from latest audit metrics."""
    from app.core.customer import CustomerManager
    from app.core.database import get_db

    allowed = await get_accessible_customer_ids(user)
    customers = filter_customers(CustomerManager.list_customers(), allowed)
    customer_map = {c.get("_id", ""): c.get("CustomerName", "") for c in customers}

    results = []
    totals = {"pass": 0, "partial": 0, "warn": 0, "fail": 0, "info": 0}

    try:
        async with get_db() as db:
            for cid, name in customer_map.items():
                async with db.execute(
                    "SELECT metrics_json, audit_date, risk_grade, risk_score "
                    "FROM audit_metrics WHERE customer_id = ? ORDER BY audit_date DESC LIMIT 1",
                    (cid,),
                ) as cur:
                    row = await cur.fetchone()
                    if not row or not row["metrics_json"]:
                        continue
                    try:
                        metrics = json.loads(row["metrics_json"])
                    except json.JSONDecodeError:
                        continue

                    compliance = metrics.get("compliance", {})
                    if not compliance:
                        continue

                    entry = {
                        "customer_id": cid,
                        "customer_name": name,
                        "audit_date": row["audit_date"],
                        "risk_grade": row["risk_grade"],
                        "risk_score": row["risk_score"],
                        "pass_count": compliance.get("pass", 0),
                        "partial_count": compliance.get("partial", 0) + compliance.get("warn", 0),
                        "fail_count": compliance.get("fail", 0),
                        "info_count": compliance.get("info", 0),
                        "total_controls": compliance.get("total", 0),
                        "pass_pct": compliance.get("pct", 0),
                        "by_category": compliance.get("by_category", {}),
                    }
                    results.append(entry)
                    totals["pass"] += entry["pass_count"]
                    totals["fail"] += entry["fail_count"]
                    totals["partial"] += entry["partial_count"]
    except Exception as exc:
        logger.warning("Compliance dashboard failed: %s", exc)

    results.sort(key=lambda x: x.get("pass_pct", 0))

    avg_pct = round(sum(r["pass_pct"] for r in results) / max(len(results), 1), 1) if results else 0

    return {
        "customers": results,
        "summary": {
            "total_customers": len(results),
            "avg_compliance_pct": avg_pct,
            "totals": totals,
        },
    }


# ── Unified asset inventory ────────────────────────────────────────────────

@router.get("/dashboard/assets")
async def dashboard_assets(user=Depends(get_current_user)):
    """Unified asset inventory across all customers and integrations."""
    from app.core.customer import CustomerManager
    from app.core.database import get_db
    from app.services.ssh_manager import list_hosts
    from app.services.vpn_manager import list_profiles

    allowed = await get_accessible_customer_ids(user)
    customers = filter_customers(CustomerManager.list_customers(), allowed)
    customer_map = {c.get("_id", ""): c.get("CustomerName", "") for c in customers}

    assets = {
        "network_devices": [],
        "ssh_hosts": [],
        "vpn_profiles": [],
        "domains": [],
        "subscriptions": [],
    }
    counts = {"network": 0, "ssh": 0, "vpn": 0, "domains": 0, "subscriptions": 0, "customers": len(customers)}

    # SSH hosts
    try:
        hosts = await list_hosts()
        for h in hosts:
            if allowed is not None and h.customer_id and h.customer_id not in allowed:
                continue
            assets["ssh_hosts"].append({
                "id": h.id,
                "label": h.label,
                "hostname": h.hostname,
                "port": h.port,
                "device_type": h.device_type.value if hasattr(h.device_type, "value") else str(h.device_type),
                "customer_id": h.customer_id,
                "customer_name": customer_map.get(h.customer_id, ""),
                "is_reachable": h.is_reachable,
                "last_seen": h.last_seen,
            })
        counts["ssh"] = len(assets["ssh_hosts"])
    except Exception as exc:
        logger.debug("Asset inventory SSH failed: %s", exc)

    # VPN profiles
    try:
        profiles = await list_profiles()
        for p in profiles:
            if allowed is not None and p.customer_id and p.customer_id not in allowed:
                continue
            assets["vpn_profiles"].append({
                "id": p.id,
                "name": p.name,
                "protocol": p.protocol.value if hasattr(p.protocol, "value") else str(p.protocol),
                "customer_id": p.customer_id,
                "customer_name": customer_map.get(p.customer_id, ""),
            })
        counts["vpn"] = len(assets["vpn_profiles"])
    except Exception as exc:
        logger.debug("Asset inventory VPN failed: %s", exc)

    # Network devices (FortiGate + UniFi from poller cache)
    try:
        from app.web.routes.dashboard_ws import _poller
        if _poller:
            for dev in _poller.get_devices():
                cid = dev.get("customer_id", "")
                if allowed is not None and cid not in allowed:
                    continue
                assets["network_devices"].append({
                    "name": dev.get("name", ""),
                    "vendor": dev.get("vendor", ""),
                    "model": dev.get("model", ""),
                    "firmware": dev.get("firmware", ""),
                    "serial": dev.get("serial", ""),
                    "status": dev.get("status", ""),
                    "customer_id": cid,
                    "customer_name": customer_map.get(cid, ""),
                    "wan_ip": dev.get("wan_ip", ""),
                })
        counts["network"] = len(assets["network_devices"])
    except Exception as exc:
        logger.debug("Asset inventory network failed: %s", exc)

    # Domains (from Uniweb)
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT name, customer_id, data_json FROM uniweb_accounts WHERE customer_id IS NOT NULL"
            ) as cur:
                for r in await cur.fetchall():
                    cid = r["customer_id"]
                    if allowed is not None and cid not in allowed:
                        continue
                    data = json.loads(r["data_json"]) if r["data_json"] else {}
                    for dom in data.get("domains", []):
                        domain_name = dom.get("domain", "")
                        if domain_name:
                            assets["domains"].append({
                                "domain": domain_name,
                                "expiry": (dom.get("expiry") or "")[:10],
                                "customer_id": cid,
                                "customer_name": customer_map.get(cid, ""),
                                "source": "uniweb",
                            })
        counts["domains"] = len(assets["domains"])
    except Exception as exc:
        logger.debug("Asset inventory domains failed: %s", exc)

    # Subscriptions (from ALSO)
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT r.customer_id, r.customer_name, r.service_display, r.contract_end, r.account_state, "
                "d.quantity, d.monthly_cost, d.currency "
                "FROM also_renewals r LEFT JOIN also_subscription_details d ON r.subscription_id = d.subscription_id"
            ) as cur:
                for r in await cur.fetchall():
                    cid = r["customer_id"]
                    if allowed is not None and cid not in allowed:
                        continue
                    assets["subscriptions"].append({
                        "service": r["service_display"],
                        "customer_id": cid,
                        "customer_name": r["customer_name"],
                        "contract_end": (r["contract_end"] or "")[:10],
                        "state": r["account_state"],
                        "quantity": r["quantity"],
                        "monthly_cost": r["monthly_cost"],
                        "currency": r["currency"],
                    })
        counts["subscriptions"] = len(assets["subscriptions"])
    except Exception as exc:
        logger.debug("Asset inventory subscriptions failed: %s", exc)

    return {
        "assets": assets,
        "counts": counts,
    }

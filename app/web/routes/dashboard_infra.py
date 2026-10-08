"""Dashboard infrastructure, network, VPN, domains, compliance, assets, and security endpoints.

Split from dashboard.py for maintainability.
"""

from __future__ import annotations

import contextlib
import json
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends

from app.core.exceptions import (
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.core.rbac import (
    check_customer_access,
    customer_in_scope,
    filter_customers,
    get_accessible_customer_ids,
)
from app.models.user import Role
from app.web.i18n import refusal
from app.web.middleware.auth import get_current_user, require_customer_access

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Unified cost overview ───────────────────────────────────────────────────


@router.get("/dashboard/costs")
async def dashboard_costs(user=Depends(get_current_user)):
    """Aggregate ALSO MRR + Uniweb monthly costs per customer."""
    import json

    from app.core.customer import CustomerManager

    allowed = await get_accessible_customer_ids(user)
    customers = filter_customers(CustomerManager.list_customers(), allowed)
    customer_map = {}
    for c in customers:
        cid = c.get("_id", "")
        if cid:
            customer_map[cid] = c.get("CustomerName", "Unknown")

    from sqlmodel import select

    from app.core.orm import get_session
    from app.models.integrations import AlsoRenewal, AlsoSubscriptionDetail, UniwebAccount

    # ── ALSO MRR per customer ──
    also_by_customer: dict[str, dict] = {}
    try:
        async with get_session() as session:
            stmt = select(
                AlsoRenewal.customer_id,
                AlsoRenewal.customer_name,
                AlsoSubscriptionDetail.monthly_cost,
                AlsoSubscriptionDetail.currency,
            ).join(
                AlsoSubscriptionDetail,
                AlsoRenewal.subscription_id == AlsoSubscriptionDetail.subscription_id,
                isouter=True,
            )
            result = await session.execute(stmt)
            for row in result.mappings().all():
                r = dict(row)
                cid = r["customer_id"] or ""
                if not cid or not customer_in_scope(cid, allowed):
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
        async with get_session() as session:
            stmt = select(
                UniwebAccount.customer_id, UniwebAccount.name, UniwebAccount.data_json
            ).where(UniwebAccount.customer_id.is_not(None))
            result = await session.execute(stmt)
            for row in result.mappings().all():
                r = dict(row)
                cid = r["customer_id"] or ""
                if not cid or not customer_in_scope(cid, allowed):
                    continue
                data = {}
                if r["data_json"]:
                    with contextlib.suppress(json.JSONDecodeError):
                        data = json.loads(r["data_json"])
                subs = data.get("subscriptions", [])
                monthly = 0.0
                for sub in subs:
                    price_str = sub.get("Price per month", sub.get("price_monthly", ""))
                    try:
                        cleaned = (
                            str(price_str)
                            .replace(",", ".")
                            .replace(" ", "")
                            .replace("NOK", "")
                            .replace("kr", "")
                        )
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

        results.append(
            {
                "customer_id": cid,
                "customer_name": name,
                "also_mrr": also_mrr,
                "uniweb_monthly": uniweb_monthly,
                "total_monthly": total,
                "also_subscriptions": also.get("count", 0),
                "uniweb_subscriptions": uniweb.get("count", 0),
                "currency": currency,
            }
        )

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
    from app.services.tls_monitor import check_endpoint_tls

    now = datetime.now(UTC)
    allowed_ids = await get_accessible_customer_ids(user)

    from sqlmodel import select

    from app.core.orm import get_session
    from app.models.integrations import UniwebAccount

    # ── Load the Uniweb accounts this caller may see ──
    # Filtered before any live check, so a scoped caller neither sees another
    # customer's domains nor makes the hub probe them.
    async with get_session() as session:
        result = await session.execute(
            select(
                UniwebAccount.id,
                UniwebAccount.name,
                UniwebAccount.customer_id,
                UniwebAccount.data_json,
            )
        )
        rows = [
            r for r in result.mappings().all() if customer_in_scope(r["customer_id"], allowed_ids)
        ]

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
                    exp_date = exp_date.replace(tzinfo=UTC)
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
                if "_domainkey" in hostname and (
                    rtype == "CNAME" or (rtype == "TXT" and "k=rsa" in val)
                ):
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
                            dt = dt.replace(tzinfo=UTC)
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
    all_customers = filter_customers(CustomerManager.list_customers(), allowed_ids)
    for c in all_customers:
        pd = (c.get("PrimaryDomain") or "").strip().lower()
        if pd and pd not in existing_domains and not pd.endswith(".onmicrosoft.com"):
            cid = c.get("_id", "")
            name = c.get("CustomerName", "Unknown")
            domain_entries.append(
                {
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
                }
            )
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
        1
        for e in domain_entries
        if e.get("ssl")
        and e["ssl"].get("days_remaining") is not None
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
            from app.modules.api_result import read_error, read_failed
            from app.services import firmware_inventory

            if read_failed(devices_raw):
                await firmware_inventory.record_quietly(
                    firmware_inventory.record_read_failure,
                    cust_id,
                    "unifi",
                    read_error(devices_raw) or "read failed",
                    key="controller",
                    name=str(uf_host),
                )
                read_unavailable = True
                alerts.append(
                    f"UniFi-kontrolleren kunne ikke leses ({cust.get('UniFiHost', '?')}) "
                    "— enheter mangler i oversikten"
                )
            else:
                await firmware_inventory.record_quietly(
                    firmware_inventory.record_unifi_devices, cust_id, list(devices_raw)
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
                    aps.append(
                        {
                            "name": dev_name,
                            "model": model,
                            "firmware": firmware,
                            "clients": num_clients,
                            "status": status,
                            "fw_status": fw_status,
                        }
                    )
                    # Capacity alert: typical AP max ~60-80 clients
                    if num_clients > 50:
                        alerts.append(f"{dev_name} high client load ({num_clients} clients)")
                elif dev_type == "usw":
                    port_table = d.get("port_table", [])
                    ports_total = len(port_table) if port_table else d.get("port_overrides", 0)
                    ports_used = (
                        sum(1 for p in port_table if p.get("up", False)) if port_table else 0
                    )
                    switches.append(
                        {
                            "name": dev_name,
                            "model": model,
                            "firmware": firmware,
                            "ports_used": ports_used,
                            "ports_total": ports_total,
                            "status": status,
                            "fw_status": fw_status,
                        }
                    )
                    if ports_total > 0:
                        usage_pct = round(ports_used / ports_total * 100)
                        if usage_pct >= 80:
                            alerts.append(f"{dev_name} port usage {usage_pct}%")
                elif dev_type == "ugw":
                    gateways.append(
                        {
                            "name": dev_name,
                            "model": model,
                            "firmware": firmware,
                            "status": status,
                            "wan_ip": d.get("wan1", {}).get("ip", d.get("ip", "")),
                            "fw_status": fw_status,
                        }
                    )

        except (NotFoundError, ValidationError) as e:
            # Not configured (no host, no stored credentials): nothing was read.
            logger.debug("UniFi fetch skipped for %s: %s", name, e)
        except Exception as e:
            logger.debug("UniFi fetch failed for %s: %s", name, e)
            from app.services import firmware_inventory

            await firmware_inventory.record_quietly(
                firmware_inventory.record_read_failure,
                cust_id,
                "unifi",
                str(e),
                key="controller",
                name=str(uf_host),
            )

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
                firewalls.append(
                    {
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
                    }
                )
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
    net_customers = [c for c in customers if c.get("UniFiHost") or c.get("FortiGateHost")]

    if not net_customers:
        return {
            "customers": [],
            "summary": {"total_devices": 0, "outdated_firmware": 0, "high_utilization": 0},
        }

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
            1
            for dev_list in r["devices"].values()
            for dev in dev_list
            if dev.get("fw_status") in ("warning", "critical")
        )
        high_utilization += sum(
            1 for a in r["alerts"] if "port usage" in a or "high client load" in a
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
        raise refusal(ForbiddenError, "err_customer_no_access")
    cust = CustomerManager.get_customer(customer_id)
    if not cust:
        raise refusal(NotFoundError, "err_customer_not_found")

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


# ── Domain-Email-License Chain Detection ──────────────────────────────────


@router.get("/dashboard/domain-email-chain")
async def dashboard_domain_email_chain(user=Depends(get_current_user)):
    """Detect domain-email-license mismatches: double-paying, missing M365, etc."""
    from app.core.customer import CustomerManager

    allowed = await get_accessible_customer_ids(user)
    customers = filter_customers(CustomerManager.list_customers(), allowed)
    customer_map = {}
    for c in customers:
        cid = c.get("_id", "")
        if cid:
            customer_map[cid] = c.get("CustomerName", "Unknown")

    # ── Load Uniweb + ALSO data ──
    uniweb_by_cust: dict[str, dict] = {}
    also_by_cust: dict[str, list[dict]] = {}
    try:
        from sqlmodel import select

        from app.core.orm import get_session
        from app.models.integrations import AlsoRenewal, UniwebAccount

        async with get_session() as session:
            stmt_uniweb = select(
                UniwebAccount.customer_id, UniwebAccount.name, UniwebAccount.data_json
            ).where(UniwebAccount.customer_id.is_not(None))
            res_uniweb = await session.execute(stmt_uniweb)
            for r in res_uniweb.mappings().all():
                cid = r["customer_id"]
                if cid and r["data_json"] and customer_in_scope(cid, allowed):
                    with contextlib.suppress(json.JSONDecodeError):
                        uniweb_by_cust[cid] = json.loads(r["data_json"])

            stmt_also = select(
                AlsoRenewal.customer_id,
                AlsoRenewal.customer_name,
                AlsoRenewal.service_name,
                AlsoRenewal.service_display,
            )
            res_also = await session.execute(stmt_also)
            for r in res_also.mappings().all():
                row = dict(r)
                cid = row["customer_id"]
                if customer_in_scope(cid, allowed):
                    also_by_cust.setdefault(cid, []).append(row)
    except Exception as exc:
        logger.warning("domain-email-chain: failed to read data: %s", exc)

    # Build normalized lookup: strip special chars so "A_S" matches "AS"
    import re as _re

    def _norm(s: str) -> str:
        return _re.sub(r"[^a-z0-9]", "", s.lower())

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
            "microsoft 365",
            "office 365",
            "exchange online",
            "business basic",
            "business standard",
            "business premium",
            "e1",
            "e3",
            "e5",
            "f1",
            "f3",
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
            if ("e-post" in stype or "email" in stype or "mail" in stype) and sdomain:
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
            has_uniweb_email = dom_lower in uniweb_email_domains or dom_lower in email_sub_domains

            alerts: list[dict] = []

            # Double-paying: domain uses Exchange (MX) AND has Uniweb email hosting
            if has_uniweb_email and mx_exchange:
                alerts.append(
                    {
                        "type": "double_paying",
                        "severity": "warning",
                        "message": "Domenet bruker Exchange Online, men har også e-posthosting hos Uniweb. Mulig dobbeltbetaling.",
                    }
                )

            if alerts:
                chain_items.append(
                    {
                        "customer_id": cid,
                        "customer_name": name,
                        "domain": domain_name,
                        "mx_exchange": mx_exchange,
                        "mx_records": mx_values,
                        "has_m365": has_m365,
                        "has_uniweb_email": has_uniweb_email,
                        "alerts": alerts,
                    }
                )

    severity_order = {"critical": 0, "warning": 1, "info": 2}
    chain_items.sort(
        key=lambda x: (
            min(severity_order.get(a["severity"], 9) for a in x["alerts"]) if x["alerts"] else 9
        )
    )

    summary = {
        "total_alerts": len(chain_items),
        "double_paying": sum(
            1 for i in chain_items if any(a["type"] == "double_paying" for a in i["alerts"])
        ),
    }

    return {"items": chain_items, "summary": summary}


# ── Customer Infrastructure ─────────────────────────────────────────────────


@router.get("/dashboard/customer-infra/{customer_id}")
async def get_customer_infra(customer_id: str, user=Depends(require_customer_access(Role.viewer))):
    """Return all infrastructure linked to a customer: SSH hosts, VPN profiles,
    FortiGate and UniFi config."""
    from app.core.customer import CustomerManager
    from app.services.ssh_manager import list_hosts
    from app.services.vpn_manager import list_profiles

    if not await check_customer_access(user, customer_id):
        raise refusal(ForbiddenError, "err_customer_no_access")
    cust = CustomerManager.get_customer(customer_id)
    if not cust:
        raise refusal(NotFoundError, "err_customer_not_found")

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

    allowed = await get_accessible_customer_ids(user)
    customers = filter_customers(CustomerManager.list_customers(), allowed)
    customer_map = {c.get("_id", ""): c.get("CustomerName", "") for c in customers}

    results = []
    totals = {"pass": 0, "partial": 0, "warn": 0, "fail": 0, "info": 0}

    try:
        from sqlmodel import select

        from app.core.orm import get_session
        from app.models.audit import AuditMetric

        async with get_session() as session:
            for cid, name in customer_map.items():
                stmt = (
                    select(AuditMetric)
                    .where(AuditMetric.customer_id == cid)
                    .order_by(AuditMetric.audit_date.desc())
                    .limit(1)
                )
                result = await session.execute(stmt)
                row = result.scalars().first()
                if not row or not row.metrics_json:
                    continue
                try:
                    metrics = json.loads(row.metrics_json)
                except json.JSONDecodeError:
                    continue

                compliance = metrics.get("compliance", {})
                if not compliance:
                    continue

                entry = {
                    "customer_id": cid,
                    "customer_name": name,
                    "audit_date": row.audit_date,
                    "risk_grade": row.risk_grade,
                    "risk_score": row.risk_score,
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
    counts: dict[str, int | None] = {
        "network": 0,
        "ssh": 0,
        "vpn": 0,
        "domains": 0,
        "subscriptions": 0,
        "customers": len(customers),
    }
    # Sections whose source could not be read; their count is None, not 0.
    unavailable: list[str] = []

    # SSH hosts
    try:
        hosts = await list_hosts()
        for h in hosts:
            if not customer_in_scope(h.customer_id, allowed):
                continue
            assets["ssh_hosts"].append(
                {
                    "id": h.id,
                    "label": h.label,
                    "hostname": h.hostname,
                    "port": h.port,
                    "device_type": h.device_type.value
                    if hasattr(h.device_type, "value")
                    else str(h.device_type),
                    "customer_id": h.customer_id,
                    "customer_name": customer_map.get(h.customer_id, ""),
                    "is_reachable": h.is_reachable,
                    "last_seen": h.last_seen,
                }
            )
        counts["ssh"] = len(assets["ssh_hosts"])
    except Exception as exc:
        logger.debug("Asset inventory SSH failed: %s", exc)

    # VPN profiles
    try:
        profiles = await list_profiles()
        for p in profiles:
            if not customer_in_scope(p.customer_id, allowed):
                continue
            assets["vpn_profiles"].append(
                {
                    "id": p.id,
                    "name": p.name,
                    "protocol": p.protocol.value
                    if hasattr(p.protocol, "value")
                    else str(p.protocol),
                    "customer_id": p.customer_id,
                    "customer_name": customer_map.get(p.customer_id, ""),
                }
            )
        counts["vpn"] = len(assets["vpn_profiles"])
    except Exception as exc:
        logger.debug("Asset inventory VPN failed: %s", exc)

    # Network devices: FortiGate and UniFi as each was last read, from the
    # stored readings (device_firmware). The daily firmware check reads every
    # firewall and controller the hub reaches, and the pollers and audits add
    # theirs, so this survives a restart; the dashboard poller's cache holds
    # only what somebody polled since. A store that cannot be read is said so
    # (count None, "network_devices" in unavailable), never shown as no devices.
    try:
        from app.services import firmware_inventory

        stored = await firmware_inventory.list_devices(allowed, names=customer_map)
    except Exception:
        logger.exception("Asset inventory: the stored device readings could not be read")
        unavailable.append("network_devices")
        counts["network"] = None
    else:
        for dev in stored:
            assets["network_devices"].append(
                {
                    "name": dev["device_name"],
                    "vendor": dev["vendor"],
                    "model": dev["model"],
                    "firmware": dev["version"],
                    "firmware_status": dev["status"],
                    "latest": dev["latest"],
                    "device_key": dev["device_key"],
                    "read_at": dev["read_at"],
                    "read_error": dev["read_error"],
                    "customer_id": dev["customer_id"],
                    "customer_name": dev["customer_name"],
                }
            )
        counts["network"] = len(assets["network_devices"])

    # Domains (from Uniweb)
    try:
        from sqlmodel import select

        from app.core.orm import get_session
        from app.models.integrations import AlsoRenewal, AlsoSubscriptionDetail, UniwebAccount

        async with get_session() as session:
            stmt = select(
                UniwebAccount.name, UniwebAccount.customer_id, UniwebAccount.data_json
            ).where(UniwebAccount.customer_id.is_not(None))
            res = await session.execute(stmt)
            for r in res.mappings().all():
                cid = r["customer_id"]
                if not customer_in_scope(cid, allowed):
                    continue
                data = json.loads(r["data_json"]) if r["data_json"] else {}
                for dom in data.get("domains", []):
                    domain_name = dom.get("domain", "")
                    if domain_name:
                        assets["domains"].append(
                            {
                                "domain": domain_name,
                                "expiry": (dom.get("expiry") or "")[:10],
                                "customer_id": cid,
                                "customer_name": customer_map.get(cid, ""),
                                "source": "uniweb",
                            }
                        )
        counts["domains"] = len(assets["domains"])
    except Exception as exc:
        logger.debug("Asset inventory domains failed: %s", exc)

    # Subscriptions (from ALSO)
    try:
        async with get_session() as session:
            stmt = select(
                AlsoRenewal.customer_id,
                AlsoRenewal.customer_name,
                AlsoRenewal.service_display,
                AlsoRenewal.contract_end,
                AlsoRenewal.account_state,
                AlsoSubscriptionDetail.quantity,
                AlsoSubscriptionDetail.monthly_cost,
                AlsoSubscriptionDetail.currency,
            ).join(
                AlsoSubscriptionDetail,
                AlsoRenewal.subscription_id == AlsoSubscriptionDetail.subscription_id,
                isouter=True,
            )
            res = await session.execute(stmt)
            for r in res.mappings().all():
                cid = r["customer_id"]
                if not customer_in_scope(cid, allowed):
                    continue
                assets["subscriptions"].append(
                    {
                        "service": r["service_display"],
                        "customer_id": cid,
                        "customer_name": r["customer_name"],
                        "contract_end": (r["contract_end"] or "")[:10],
                        "state": r["account_state"],
                        "quantity": r["quantity"],
                        "monthly_cost": r["monthly_cost"],
                        "currency": r["currency"],
                    }
                )
        counts["subscriptions"] = len(assets["subscriptions"])
    except Exception as exc:
        logger.debug("Asset inventory subscriptions failed: %s", exc)

    return {
        "assets": assets,
        "counts": counts,
        "unavailable": unavailable,
    }

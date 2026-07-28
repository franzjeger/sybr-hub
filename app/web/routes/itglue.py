"""IT Glue integration route handlers."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

import app.web.state as state
from app.core.config import load_app_settings
from app.core.exceptions import (
    AuthError,
    ConflictError,
    IntegrationError,
    NotFoundError,
    ValidationError,
)
from app.web.i18n import ui_t
from app.models.user import Role
from app.web.middleware.auth import get_current_user, require_customer_access

router = APIRouter(dependencies=[Depends(get_current_user)])
logger = logging.getLogger(__name__)


@router.post("/itglue/test")
async def itglue_test(request: Request):
    """Test IT Glue API connection."""
    from app.integrations.itglue import ITGlueClient
    body = await request.json()
    api_key = body.get("api_key", "")
    region = body.get("region", "eu")
    if not api_key:
        settings = load_app_settings()
        api_key = settings.get("itglue_api_key", "")
        region = settings.get("itglue_region", "eu")
    if not api_key:
        return {"ok": False, "error": ui_t("err_no_api_key", request)}
    client = ITGlueClient(api_key=api_key, region=region)
    try:
        result = await client.test_connection()
        return result
    finally:
        await client.close()


@router.post("/itglue/organizations")
async def itglue_organizations():
    """List IT Glue organizations."""
    from app.integrations.itglue import ITGlueClient
    settings = load_app_settings()
    api_key = settings.get("itglue_api_key", "")
    region = settings.get("itglue_region", "eu")
    if not api_key:
        raise ValidationError(ui_t("err_no_api_key"))
    client = ITGlueClient(api_key=api_key, region=region)
    try:
        orgs = await client.list_organizations()
        return {"organizations": [{"id": o["id"], "name": o["attributes"]["name"]} for o in orgs]}
    finally:
        await client.close()


@router.get("/itglue/inspect")
async def itglue_inspect():
    """Inspect IT Glue Flexible Asset Types and their fields."""
    from app.integrations.itglue import ITGlueClient
    settings = load_app_settings()
    api_key = settings.get("itglue_api_key", "")
    region = settings.get("itglue_region", "eu")
    if not api_key:
        raise ValidationError(ui_t("err_no_api_key"))
    client = ITGlueClient(api_key=api_key, region=region)
    try:
        types = await client.inspect_all_types()
        return {"types": types}
    finally:
        await client.close()


@router.post("/customers/import-itglue")
async def import_customers_from_itglue(request: Request):
    """Import selected IT Glue organizations as customers (name + itglue_org_id only)."""
    from app.core.customer import CustomerManager

    body = await request.json()
    orgs = body.get("organizations", [])
    if not orgs:
        raise ValidationError(ui_t("err_no_orgs_selected", request))

    existing = CustomerManager.list_customers()
    existing_names = {c.get("CustomerName", "").lower() for c in existing}

    imported = []
    skipped = []

    for org in orgs:
        name = org.get("name", "").strip()
        itglue_id = org.get("id", "")
        if not name:
            continue
        if name.lower() in existing_names:
            skipped.append(name)
            continue

        # Create a minimal customer entry — no tenant/credentials yet
        config = {
            "CustomerName": name,
            "TenantId": "",
            "ClientId": "",
            "PrimaryDomain": "",
            "InitialDomain": "",
            "AppObjectId": "",
            "SubscriptionId": "",
            "SetupDate": "",
            "SecretExpiry": "",
            "CertExpiry": "",
            "ITGlueOrgId": str(itglue_id),
        }
        cust_id = CustomerManager.save_customer(config)
        imported.append({"name": name, "id": cust_id})
        existing_names.add(name.lower())

    try:
        from app.core.activity_log import log_activity
        _user = getattr(getattr(request.state, "user", None), "username", "")
        log_activity("itglue_import", detail=f"Importerte {len(imported)} kunde(r) fra IT Glue", user=_user)
    except Exception as e:
        logger.warning("Failed to log IT Glue import activity: %s", e)

    return {"ok": True, "imported": len(imported), "skipped": len(skipped),
            "imported_names": [i["name"] for i in imported],
            "skipped_names": skipped}


@router.post("/itglue/upload/audit")
async def itglue_upload_audit(request: Request):
    """Upload audit data and report to IT Glue."""
    from app.core.encryption import encrypted_read_json
    from app.integrations.itglue import ITGlueClient
    body = await request.json()
    org_id = body.get("org_id")
    if not org_id:
        raise ValidationError("org_id er påkrevd")

    settings = load_app_settings()
    client = ITGlueClient(
        api_key=settings.get("itglue_api_key", ""),
        region=settings.get("itglue_region", "eu"),
    )
    try:
        out_dir = _resolve_audit_out_dir()
        if not out_dir:
            raise ValidationError(ui_t("err_no_audit_data"))

        # Load metrics
        metrics_path = out_dir / "_audit_metrics.json"
        metrics = encrypted_read_json(metrics_path) if metrics_path.exists() else {}

        # Find PDF report
        pdf_files = list(out_dir.glob("*_customer_*.pdf")) + list(out_dir.glob("*_tech_*.pdf"))
        pdf_path = pdf_files[0] if pdf_files else None

        # Build executive summary and recommendations text
        exec_summary = ""
        recs_text = ""
        recs = metrics.get("recommendations", [])
        if recs:
            recs_text = "\n".join(
                f"[{r.get('priority','').upper()}] {r.get('title','')}"
                for r in recs
            )
        if metrics.get("risk_grade"):
            exec_summary = (
                f"Risk Grade: {metrics.get('risk_grade')} (Score: {metrics.get('risk_score', 0)})\n"
                f"MFA Coverage: {metrics.get('mfa_coverage_pct', 0)}%\n"
                f"Secure Score: {metrics.get('secure_score_pct', 0)}%\n"
                f"Users: {metrics.get('total_users', 0)} (without MFA: {metrics.get('users_no_mfa', 0)})\n"
                f"Warnings: {metrics.get('total_warns', 0)}"
            )

        result = await client.upload_audit(
            org_id=int(org_id),
            audit_date=metrics.get("timestamp", "")[:10],
            metrics=metrics,
            executive_summary=exec_summary,
            recommendations=recs_text,
            report_pdf_path=pdf_path,
        )

        from app.core.activity_log import log_activity as _log_itg
        _log_itg("itglue_uploaded", detail="audit data")

        return {"ok": True, "asset_id": result.get("id")}
    except Exception as e:
        logger.error("IT Glue upload failed: %s", e)
        raise IntegrationError("IT Glue upload failed")
    finally:
        await client.close()


def _resolve_audit_out_dir() -> Optional[Path]:
    """Return current audit dir, or find latest run for active customer."""
    if state.audit_out_dir and state.audit_out_dir.exists():
        return state.audit_out_dir
    # Fallback: find latest audit run for active customer
    try:
        from app.core.config import get_audit_dir
        from app.core.customer import CustomerManager
        active = CustomerManager.get_active()
        if not active:
            return None
        name = active.get("CustomerName", "")
        sanitized = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name).replace(" ", "_")
        customer_dir = get_audit_dir() / sanitized
        if not customer_dir.exists():
            return None
        runs = sorted([d for d in customer_dir.iterdir() if d.is_dir()], reverse=True)
        return runs[0] if runs else None
    except Exception as e:
        logger.debug("Failed to resolve audit output dir: %s", e)
        return None


@router.get("/itglue/available-reports")
async def itglue_available_reports():
    """List HTML/PDF reports available for upload."""
    out_dir = _resolve_audit_out_dir()
    if not out_dir:
        return {"files": []}
    files = []
    for f in sorted(out_dir.iterdir()):
        if f.suffix.lower() in (".html", ".pdf"):
            size_kb = f.stat().st_size / 1024
            size_str = f"{size_kb:.0f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
            files.append({"name": f.name, "size": size_str, "path": str(f)})
    return {"files": files, "audit_dir": str(out_dir), "audit_date": out_dir.name}


@router.post("/itglue/upload/reports")
async def itglue_upload_reports(request: Request):
    """Upload selected audit reports to IT Glue Documents folder."""
    from app.integrations.itglue import ITGlueClient

    body = await request.json()
    org_id = body.get("org_id")
    file_names = body.get("files", [])  # list of filenames to upload
    if not org_id:
        raise ValidationError("org_id er påkrevd")

    out_dir = _resolve_audit_out_dir()
    if not out_dir:
        raise ValidationError(ui_t("err_no_audit_data"))

    settings = load_app_settings()
    client = ITGlueClient(
        api_key=settings.get("itglue_api_key", ""),
        region=settings.get("itglue_region", "eu"),
    )
    try:
        audit_date = out_dir.name

        # If specific files requested, filter; otherwise upload all HTML/PDF
        if file_names:
            report_files = []
            for name in file_names:
                fp = out_dir / name
                try:
                    fp.resolve().relative_to(out_dir.resolve())
                except ValueError:
                    continue  # Path traversal attempt — skip
                if fp.exists() and fp.suffix.lower() in (".html", ".pdf"):
                    report_files.append(fp)
        else:
            report_files = [f for f in sorted(out_dir.iterdir()) if f.suffix.lower() in (".html", ".pdf")]

        if not report_files:
            raise ValidationError(ui_t("err_no_report_files"))

        results = await client.upload_audit_reports(
            org_id=int(org_id),
            report_files=report_files,
            audit_date=audit_date,
        )
        uploaded = [r["name"] for r in results]

        try:
            from app.core.activity_log import log_activity
            _user = getattr(getattr(request.state, "user", None), "username", "")
            log_activity("itglue_uploaded", detail=f"{len(uploaded)} rapporter til Documents", user=_user)
        except Exception as e:
            logger.warning("Failed to log IT Glue upload activity: %s", e)

        return {"ok": True, "uploaded": len(uploaded), "files": uploaded}
    except Exception as e:
        logger.error("IT Glue document upload failed: %s", e)
        raise IntegrationError("IT Glue document upload failed")
    finally:
        await client.close()


@router.post("/itglue/upload/credentials")
async def itglue_upload_credentials(request: Request):
    """Upload tenant credentials to IT Glue."""
    from app.core.credentials import get_secret, load_config
    from app.core.customer import CustomerManager
    from app.integrations.itglue import ITGlueClient
    body = await request.json()
    org_id = body.get("org_id")
    if not org_id:
        raise ValidationError("org_id er påkrevd")

    settings = load_app_settings()
    client = ITGlueClient(
        api_key=settings.get("itglue_api_key", ""),
        region=settings.get("itglue_region", "eu"),
    )
    try:
        cfg = load_config()
        if not cfg:
            raise ValidationError(ui_t("err_no_customer_config"))

        tenant_id = cfg.get("TenantId", "")
        secret = get_secret(tenant_id, "client_secret") or ""
        active_id = CustomerManager.get_active_id()
        cert_path = CustomerManager.get_cert_path(active_id) if active_id else None

        result = await client.upload_credentials(
            org_id=int(org_id),
            config=cfg,
            client_secret=secret,
            cert_path=cert_path,
        )
        return {"ok": True, "asset_id": result.get("id")}
    except Exception as e:
        logger.error("IT Glue credential upload failed: %s", e)
        raise IntegrationError("IT Glue credential upload failed")
    finally:
        await client.close()


# ── Documentation sync ──────────────────────────────────────────────────────


async def _sync_customer_documentation(customer_id: str, client) -> dict:
    """Sync network inventory, domain overview, and license summary for one customer.

    Returns a dict with results per asset type and any errors.
    """
    from app.core.customer import CustomerManager
    from app.core.database import get_db

    cust = CustomerManager.get_customer(customer_id)
    if not cust:
        return {"error": "Customer not found", "customer_id": customer_id}

    org_id_str = cust.get("ITGlueOrgId", "")
    if not org_id_str:
        return {"error": "No ITGlueOrgId mapped", "customer_id": customer_id}

    org_id = int(org_id_str)
    customer_name = cust.get("CustomerName", "Unknown")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    synced = []
    errors = []

    # ── 1. Network Inventory ────────────────────────────────────────────────
    try:
        if cust.get("UniFiHost") or cust.get("FortiGateHost"):
            from app.web.routes.dashboard_infra import _build_network_inventory_for_customer
            net_data = await _build_network_inventory_for_customer(cust)
            if net_data:
                type_id = await client.ensure_network_inventory_type()
                totals = net_data.get("totals", {})
                total_devs = (
                    totals.get("aps", 0) + totals.get("switches", 0)
                    + totals.get("gateways", 0) + totals.get("firewalls", 0)
                )
                # Build device list HTML
                device_lines = []
                for cat in ("aps", "switches", "gateways", "firewalls"):
                    for dev in net_data.get("devices", {}).get(cat, []):
                        name = dev.get("name", dev.get("hostname", "?"))
                        model = dev.get("model", "")
                        fw = dev.get("firmware", "")
                        fw_st = dev.get("fw_status", "")
                        line = f"{name} | {model} | FW: {fw}"
                        if fw_st and fw_st != "ok":
                            line += f" [{fw_st.upper()}]"
                        device_lines.append(line)

                outdated = sum(
                    1 for cat in net_data.get("devices", {}).values()
                    for dev in cat
                    if dev.get("fw_status") in ("warning", "critical")
                )
                alerts_text = "\n".join(net_data.get("alerts", [])) or "None"

                traits = {
                    "customer": customer_name,
                    "last-updated": today,
                    "total-devices": total_devs,
                    "aps": totals.get("aps", 0),
                    "switches": totals.get("switches", 0),
                    "gateways": totals.get("gateways", 0),
                    "firewalls": totals.get("firewalls", 0),
                    "outdated-firmware": outdated,
                    "device-list": "\n".join(device_lines) or "No devices",
                    "alerts": alerts_text,
                }
                result = await client.upsert_flexible_asset(type_id, org_id, customer_name, traits)
                synced.append({
                    "type": "network_inventory",
                    "asset_id": result.get("id"),
                    "action": result.get("upserted", "synced"),
                    "devices": total_devs,
                })
    except Exception as e:
        logger.warning("Network inventory sync failed for %s: %s", customer_id, e)
        errors.append({"type": "network_inventory", "error": str(e)})

    # ── 2. Domain Overview (Uniweb) ─────────────────────────────────────────
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT data_json FROM uniweb_accounts WHERE customer_id = ?",
                (customer_id,),
            ) as cur:
                uniweb_rows = [dict(r) for r in await cur.fetchall()]

        all_domains = []
        all_ssl = []
        for row in uniweb_rows:
            if not row.get("data_json"):
                continue
            try:
                data = json.loads(row["data_json"])
            except json.JSONDecodeError:
                continue
            for dom in data.get("domains", []):
                domain_name = dom.get("domain", "")
                if not domain_name:
                    vals = list(dom.values())
                    domain_name = vals[0] if vals and isinstance(vals[0], str) else ""
                if not domain_name:
                    continue
                expiry = (dom.get("expiry") or "").strip()[:10]

                # DNS summary
                dns_records = dom.get("dns", [])
                has_spf = any("v=spf1" in (r.get("value", "")).lower() for r in dns_records if r.get("type") == "TXT")
                has_dmarc = any("v=dmarc1" in (r.get("value", "")).lower() for r in dns_records if r.get("type") == "TXT")

                dns_flags = []
                if has_spf:
                    dns_flags.append("SPF")
                if has_dmarc:
                    dns_flags.append("DMARC")

                all_domains.append(f"{domain_name} | Exp: {expiry or '?'} | DNS: {', '.join(dns_flags) or 'none'}")

            for ssl in data.get("ssl", []):
                ssl_dom = ssl.get("domain", "")
                ssl_exp = ssl.get("expiry", "")
                ssl_type = ssl.get("type", "")
                if ssl_dom:
                    all_ssl.append(f"{ssl_dom} | {ssl_type} | Exp: {ssl_exp}")

        if all_domains:
            type_id = await client.ensure_domain_overview_type()
            now = datetime.now(timezone.utc)
            expiring_soon = 0
            for row in uniweb_rows:
                if not row.get("data_json"):
                    continue
                try:
                    data = json.loads(row["data_json"])
                except json.JSONDecodeError:
                    continue
                for dom in data.get("domains", []):
                    exp_str = (dom.get("expiry") or "").strip()
                    if exp_str and len(exp_str) >= 10:
                        try:
                            exp_date = datetime.fromisoformat(exp_str[:10]).replace(tzinfo=timezone.utc)
                            if 0 <= (exp_date - now).days <= 90:
                                expiring_soon += 1
                        except (ValueError, TypeError):
                            pass

            traits = {
                "customer": customer_name,
                "last-updated": today,
                "total-domains": len(all_domains),
                "domain-list": "\n".join(all_domains),
                "ssl-status": "\n".join(all_ssl) or "No SSL data",
                "expiring-soon": expiring_soon,
            }
            result = await client.upsert_flexible_asset(type_id, org_id, customer_name, traits)
            synced.append({
                "type": "domain_overview",
                "asset_id": result.get("id"),
                "action": result.get("upserted", "synced"),
                "domains": len(all_domains),
            })
    except Exception as e:
        logger.warning("Domain overview sync failed for %s: %s", customer_id, e)
        errors.append({"type": "domain_overview", "error": str(e)})

    # ── 3. License Summary (ALSO renewals) ──────────────────────────────────
    try:
        also_id = cust.get("AlsoAccountId", "")
        if also_id or True:  # Check DB regardless — customer_id may be linked
            async with get_db() as db:
                async with db.execute(
                    """SELECT r.service_name, r.contract_end, r.account_state,
                              d.quantity, d.unit_price, d.monthly_cost, d.currency
                       FROM also_renewals r
                       LEFT JOIN also_subscription_details d
                           ON r.subscription_id = d.subscription_id
                       WHERE r.customer_id = ?
                       ORDER BY r.contract_end ASC""",
                    (customer_id,),
                ) as cur:
                    renewals = [dict(r) for r in await cur.fetchall()]

            if renewals:
                type_id = await client.ensure_license_summary_type()
                total_mrr = sum(r.get("monthly_cost") or 0 for r in renewals)
                currency = next((r.get("currency") for r in renewals if r.get("currency")), "NOK")
                now = datetime.now(timezone.utc)

                sub_lines = []
                expiring_soon = 0
                for r in renewals:
                    name = r.get("service_name", "?")
                    cost = r.get("monthly_cost")
                    cost_str = f"{cost:.2f}" if cost else "?"
                    qty = r.get("quantity", "")
                    end = r.get("contract_end", "")
                    line = f"{name} | Qty: {qty} | {cost_str} {currency}/mnd | End: {end or '?'}"
                    sub_lines.append(line)
                    if end:
                        try:
                            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
                            if end_dt.tzinfo is None:
                                end_dt = end_dt.replace(tzinfo=timezone.utc)
                            if 0 <= (end_dt - now).days <= 90:
                                expiring_soon += 1
                        except (ValueError, TypeError):
                            pass

                traits = {
                    "customer": customer_name,
                    "last-updated": today,
                    "total-subscriptions": len(renewals),
                    "monthly-cost": round(total_mrr, 2),
                    "currency": currency,
                    "subscription-list": "\n".join(sub_lines),
                    "expiring-soon": expiring_soon,
                }
                result = await client.upsert_flexible_asset(type_id, org_id, customer_name, traits)
                synced.append({
                    "type": "license_summary",
                    "asset_id": result.get("id"),
                    "action": result.get("upserted", "synced"),
                    "subscriptions": len(renewals),
                    "mrr": round(total_mrr, 2),
                })
    except Exception as e:
        logger.warning("License summary sync failed for %s: %s", customer_id, e)
        errors.append({"type": "license_summary", "error": str(e)})

    return {
        "customer_id": customer_id,
        "customer_name": customer_name,
        "synced": synced,
        "errors": errors,
    }


@router.post("/itglue/sync-documentation/{customer_id}")
async def itglue_sync_documentation(
    customer_id: str,
    request: Request,
    _user=Depends(require_customer_access(Role.technician)),
):
    """Sync network inventory, domains, and licenses to IT Glue for one customer."""
    from app.integrations.itglue import ITGlueClient

    settings = load_app_settings()
    api_key = settings.get("itglue_api_key", "")
    region = settings.get("itglue_region", "eu")
    if not api_key:
        raise ValidationError(ui_t("err_no_api_key", request))

    client = ITGlueClient(api_key=api_key, region=region)
    try:
        result = await _sync_customer_documentation(customer_id, client)
        if result.get("error"):
            raise ValidationError(result["error"])

        try:
            from app.core.activity_log import log_activity
            _user = getattr(getattr(request.state, "user", None), "username", "")
            synced_types = [s["type"] for s in result.get("synced", [])]
            log_activity(
                "itglue_uploaded",
                detail=f"Doc sync: {result['customer_name']} ({', '.join(synced_types)})",
                user=_user,
            )
        except Exception as e:
            logger.warning("Failed to log IT Glue doc sync activity: %s", e)

        return {"ok": True, **result}
    except Exception as e:
        logger.error("IT Glue doc sync failed for %s: %s", customer_id, e)
        raise IntegrationError(f"IT Glue sync failed: {e}")
    finally:
        await client.close()


@router.post("/itglue/sync-all")
async def itglue_sync_all(request: Request):
    """Sync documentation to IT Glue for all customers with ITGlueOrgId mapped."""
    from app.core.customer import CustomerManager
    from app.integrations.itglue import ITGlueClient

    settings = load_app_settings()
    api_key = settings.get("itglue_api_key", "")
    region = settings.get("itglue_region", "eu")
    if not api_key:
        raise ValidationError(ui_t("err_no_api_key", request))

    customers = CustomerManager.list_customers()
    eligible = [c for c in customers if c.get("ITGlueOrgId")]
    if not eligible:
        raise ValidationError("No customers have IT Glue organization mapped")

    client = ITGlueClient(api_key=api_key, region=region)
    try:
        results = []
        error_count = 0
        for c in eligible:
            cid = c.get("_id", "")
            if not cid:
                continue
            try:
                r = await _sync_customer_documentation(cid, client)
                results.append(r)
                if r.get("errors"):
                    error_count += len(r["errors"])
            except Exception as e:
                logger.warning("Sync failed for customer %s: %s", cid, e)
                results.append({
                    "customer_id": cid,
                    "customer_name": c.get("CustomerName", "?"),
                    "synced": [],
                    "errors": [{"type": "general", "error": str(e)}],
                })
                error_count += 1

        synced_count = sum(1 for r in results if r.get("synced"))

        try:
            from app.core.activity_log import log_activity
            _user = getattr(getattr(request.state, "user", None), "username", "")
            log_activity(
                "itglue_uploaded",
                detail=f"Bulk doc sync: {synced_count}/{len(eligible)} customers",
                user=_user,
            )
        except Exception as e:
            logger.warning("Failed to log IT Glue bulk sync activity: %s", e)

        return {
            "ok": True,
            "total": len(eligible),
            "synced": synced_count,
            "errors": error_count,
            "results": results,
        }
    except Exception as e:
        logger.error("IT Glue bulk sync failed: %s", e)
        raise IntegrationError(f"IT Glue bulk sync failed: {e}")
    finally:
        await client.close()

"""IT Glue integration route handlers."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Request

from app.core import job_state as state
from app.core.config import load_app_settings
from app.core.customer import CustomerManager
from app.core.exceptions import (
    ForbiddenError,
    IntegrationError,
    NotFoundError,
    ToolkitError,
    ValidationError,
)
from app.core.rbac import filter_customers, get_accessible_customer_ids
from app.models.integrations import (
    ITGlueImportRequest,
    ITGlueReportUpload,
    ITGlueTestRequest,
    ITGlueUploadRequest,
)
from app.models.user import Role, User
from app.web.i18n import keyed, refusal, ui_t
from app.web.middleware.auth import get_current_user, require_customer_access, require_role

router = APIRouter(dependencies=[Depends(get_current_user)])
logger = logging.getLogger(__name__)


@router.post("/itglue/test")
async def itglue_test(
    body: ITGlueTestRequest, request: Request, _user: User = Depends(require_role(Role.admin))
):
    """Test IT Glue API connection."""
    from app.integrations.itglue import ITGlueClient

    api_key = body.api_key
    region = body.region
    if not api_key:
        settings = load_app_settings()
        api_key = settings.get("itglue_api_key", "")
        region = settings.get("itglue_region", "eu")
    if not api_key:
        return {"ok": False, **keyed("error", "err_no_api_key", request)}
    client = ITGlueClient(api_key=api_key, region=region)
    try:
        result = await client.test_connection()
        return result
    finally:
        await client.close()


@router.post("/itglue/organizations")
async def itglue_organizations(_user: User = Depends(require_role(Role.technician))):
    """List IT Glue organizations, by id and name, for binding a customer.

    Every organization the MSP documents, so the floor is technician.
    """
    from app.integrations.itglue import ITGlueClient

    settings = load_app_settings()
    api_key = settings.get("itglue_api_key", "")
    region = settings.get("itglue_region", "eu")
    if not api_key:
        raise refusal(ValidationError, "err_no_api_key")
    client = ITGlueClient(api_key=api_key, region=region)
    try:
        orgs = await client.list_organizations()
        return {"organizations": [{"id": o["id"], "name": o["attributes"]["name"]} for o in orgs]}
    finally:
        await client.close()


@router.get("/itglue/inspect")
async def itglue_inspect(_user: User = Depends(require_role(Role.technician))):
    """Inspect IT Glue Flexible Asset Types and their fields.

    Account-wide schema rather than any one customer's records; technician
    floor, like the organization list.
    """
    from app.integrations.itglue import ITGlueClient

    settings = load_app_settings()
    api_key = settings.get("itglue_api_key", "")
    region = settings.get("itglue_region", "eu")
    if not api_key:
        raise refusal(ValidationError, "err_no_api_key")
    client = ITGlueClient(api_key=api_key, region=region)
    try:
        types = await client.inspect_all_types()
        return {"types": types}
    finally:
        await client.close()


@router.post("/customers/import-itglue")
async def import_customers_from_itglue(
    body: ITGlueImportRequest,
    request: Request,
    _user: User = Depends(require_role(Role.technician)),
):
    """Import selected IT Glue organizations as customers (name + itglue_org_id only)."""
    from app.core.customer import CustomerManager

    orgs = body.organizations
    if not orgs:
        raise ValidationError(ui_t("err_no_orgs_selected", request))

    existing = CustomerManager.list_customers()
    existing_names = {c.get("CustomerName", "").lower() for c in existing}

    imported = []
    skipped = []

    for org in orgs:
        name = org.name.strip()
        itglue_id = org.id
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
        cust_id = CustomerManager.save_customer(config, create=True)
        imported.append({"name": name, "id": cust_id})
        existing_names.add(name.lower())

    try:
        from app.core.activity_log import log_activity

        _user = getattr(getattr(request.state, "user", None), "username", "")
        log_activity(
            "itglue_import", detail=f"Importerte {len(imported)} kunde(r) fra IT Glue", user=_user
        )
    except Exception as e:
        logger.warning("Failed to log IT Glue import activity: %s", e)

    return {
        "ok": True,
        "imported": len(imported),
        "skipped": len(skipped),
        "imported_names": [i["name"] for i in imported],
        "skipped_names": skipped,
    }


async def _require_customer(user: User, customer_id: str) -> dict:
    """The named customer, if the caller may act on it."""
    from app.core.rbac import check_customer_access

    if not await check_customer_access(user, customer_id):
        raise refusal(ForbiddenError, "err_customer_no_access")
    customer = CustomerManager.get_customer(customer_id)
    if customer is None:
        raise refusal(NotFoundError, "err_customer_not_found")
    return customer


async def _require_customers_org(user: User, customer: dict, org_id) -> None:
    """A scoped caller may upload only into this customer's own org.

    The upload carries this customer's audit, so any other organization
    would put one customer's findings in another customer's documentation.
    """
    if await get_accessible_customer_ids(user) is None:
        return
    if str(customer.get("ITGlueOrgId") or "") != str(org_id):
        raise refusal(ForbiddenError, "err_itglue_org_not_linked")


@router.post("/itglue/upload/audit")
async def itglue_upload_audit(
    body: ITGlueUploadRequest, user: User = Depends(require_role(Role.technician))
):
    """Upload audit data and report to IT Glue."""
    from app.core.encryption import encrypted_read_json
    from app.integrations.itglue import ITGlueClient

    org_id = body.org_id
    if not org_id:
        raise refusal(ValidationError, "err_itglue_org_id_required")
    customer = await _require_customer(user, body.customer_id)
    await _require_customers_org(user, customer, org_id)

    settings = load_app_settings()
    client = ITGlueClient(
        api_key=settings.get("itglue_api_key", ""),
        region=settings.get("itglue_region", "eu"),
    )
    try:
        out_dir = await _resolve_audit_out_dir(user, customer)
        if not out_dir:
            raise refusal(ValidationError, "err_no_audit_data")

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
                f"[{r.get('priority', '').upper()}] {r.get('title', '')}" for r in recs
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

        _log_itg("itglue_uploaded", detail="audit data", customer=customer.get("CustomerName", ""))

        return {"ok": True, "asset_id": result.get("id")}
    except ToolkitError:
        # A refusal of our own, not IT Glue failing: the reader needs its
        # reason, not "upload failed" and a 502.
        raise
    except Exception as e:
        logger.error("IT Glue upload failed: %s", e)
        raise refusal(IntegrationError, "err_itglue_upload_failed") from e
    finally:
        await client.close()


async def _resolve_audit_out_dir(user, customer: dict) -> Path | None:
    """The run this user selected for this customer, else the customer's latest."""
    try:
        from app.core.config import get_audit_dir
        from app.core.customer import customer_dir_name
        from app.core.rbac import check_audit_path_access

        selected = state.get_user_audit(user.id, customer.get("_id", ""))
        if (
            selected
            and selected.out_dir
            and selected.out_dir.exists()
            and await check_audit_path_access(user, str(selected.out_dir))
        ):
            return selected.out_dir
        name = customer.get("CustomerName", "")
        customer_dir = get_audit_dir() / customer_dir_name(name)
        if not customer_dir.exists():
            return None
        runs = sorted([d for d in customer_dir.iterdir() if d.is_dir()], reverse=True)
        return runs[0] if runs else None
    except Exception as e:
        logger.debug("Failed to resolve audit output dir: %s", e)
        return None


@router.get("/itglue/available-reports")
async def itglue_available_reports(
    customer_id: str, user: User = Depends(require_customer_access(Role.viewer))
):
    """List one customer's HTML/PDF reports available for upload."""
    customer = await _require_customer(user, customer_id)
    out_dir = await _resolve_audit_out_dir(user, customer)
    if not out_dir:
        return {"files": []}
    files = []
    for f in sorted(out_dir.iterdir()):
        if f.suffix.lower() in (".html", ".pdf"):
            size_kb = f.stat().st_size / 1024
            size_str = f"{size_kb:.0f} KB" if size_kb < 1024 else f"{size_kb / 1024:.1f} MB"
            files.append({"name": f.name, "size": size_str, "path": str(f)})
    return {"files": files, "audit_dir": str(out_dir), "audit_date": out_dir.name}


@router.post("/itglue/upload/reports")
async def itglue_upload_reports(
    body: ITGlueReportUpload,
    request: Request,
    user: User = Depends(require_role(Role.technician)),
):
    """Upload selected audit reports to IT Glue Documents folder."""
    from app.integrations.itglue import ITGlueClient

    org_id = body.org_id
    file_names = body.files  # list of filenames to upload
    if not org_id:
        raise refusal(ValidationError, "err_itglue_org_id_required")
    customer = await _require_customer(user, body.customer_id)
    await _require_customers_org(user, customer, org_id)

    out_dir = await _resolve_audit_out_dir(user, customer)
    if not out_dir:
        raise refusal(ValidationError, "err_no_audit_data")

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
            report_files = [
                f for f in sorted(out_dir.iterdir()) if f.suffix.lower() in (".html", ".pdf")
            ]

        if not report_files:
            raise refusal(ValidationError, "err_no_report_files")

        results = await client.upload_audit_reports(
            org_id=int(org_id),
            report_files=report_files,
            audit_date=audit_date,
        )
        uploaded = [r["name"] for r in results]

        try:
            from app.core.activity_log import log_activity

            _user = getattr(getattr(request.state, "user", None), "username", "")
            log_activity(
                "itglue_uploaded", detail=f"{len(uploaded)} rapporter til Documents", user=_user
            )
        except Exception as e:
            logger.warning("Failed to log IT Glue upload activity: %s", e)

        return {"ok": True, "uploaded": len(uploaded), "files": uploaded}
    except ToolkitError:
        raise
    except Exception as e:
        logger.error("IT Glue document upload failed: %s", e)
        raise refusal(IntegrationError, "err_itglue_document_upload_failed") from e
    finally:
        await client.close()


@router.post("/itglue/upload/credentials")
async def itglue_upload_credentials(
    body: ITGlueUploadRequest, request: Request, _user: User = Depends(require_role(Role.admin))
):
    """Upload the named customer's tenant credentials to IT Glue."""
    from app.core.credentials import get_secret
    from app.integrations.itglue import ITGlueClient

    org_id = body.org_id
    if not org_id:
        raise refusal(ValidationError, "err_itglue_org_id_required")
    cfg = await _require_customer(_user, body.customer_id)
    await _require_customers_org(_user, cfg, org_id)

    settings = load_app_settings()
    client = ITGlueClient(
        api_key=settings.get("itglue_api_key", ""),
        region=settings.get("itglue_region", "eu"),
    )
    try:
        tenant_id = cfg.get("TenantId", "")
        if not tenant_id:
            raise ValidationError(ui_t("err_no_customer_config", request))
        secret = get_secret(tenant_id, "client_secret") or ""
        cert_path = CustomerManager.get_cert_path(body.customer_id)

        result = await client.upload_credentials(
            org_id=int(org_id),
            config=cfg,
            client_secret=secret,
            cert_path=cert_path,
        )
        return {"ok": True, "asset_id": result.get("id")}
    except ToolkitError:
        raise
    except Exception as e:
        logger.error("IT Glue credential upload failed: %s", e)
        raise refusal(IntegrationError, "err_itglue_credential_upload_failed") from e
    finally:
        await client.close()


# ── Documentation sync ──────────────────────────────────────────────────────


async def _sync_customer_documentation(
    customer_id: str, client, request: Request | None = None
) -> dict:
    """Sync network inventory, domain overview, and license summary for one customer.

    Returns a dict with results per asset type and any errors. A customer that
    cannot be synced at all comes back as ``error`` and ``error_key``, in the
    language of *request*.
    """
    from app.core.customer import CustomerManager

    cust = CustomerManager.get_customer(customer_id)
    if not cust:
        return {**keyed("error", "err_customer_not_found", request), "customer_id": customer_id}

    org_id_str = cust.get("ITGlueOrgId", "")
    if not org_id_str:
        return {
            **keyed("error", "err_itglue_customer_not_mapped", request),
            "customer_id": customer_id,
        }

    try:
        org_id = int(org_id_str)
    except (TypeError, ValueError):
        # A hand-edited mapping used to surface as a 502 quoting int().
        return {
            **keyed("error", "err_itglue_org_id_invalid", request, org_id=str(org_id_str)),
            "customer_id": customer_id,
        }
    customer_name = cust.get("CustomerName", "Unknown")
    today = datetime.now(UTC).strftime("%Y-%m-%d")
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
                    totals.get("aps", 0)
                    + totals.get("switches", 0)
                    + totals.get("gateways", 0)
                    + totals.get("firewalls", 0)
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
                    1
                    for cat in net_data.get("devices", {}).values()
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
                synced.append(
                    {
                        "type": "network_inventory",
                        "asset_id": result.get("id"),
                        "action": result.get("upserted", "synced"),
                        "devices": total_devs,
                    }
                )
    except Exception as e:
        logger.warning("Network inventory sync failed for %s: %s", customer_id, e)
        errors.append({"type": "network_inventory", "error": str(e)})

    # ── 2. Domain Overview (Uniweb) ─────────────────────────────────────────
    try:
        from sqlmodel import select

        from app.core.orm import get_session
        from app.models.integrations import UniwebAccount

        async with get_session() as session:
            stmt = select(UniwebAccount.data_json).where(UniwebAccount.customer_id == customer_id)
            res = await session.execute(stmt)
            uniweb_rows = [dict(r) for r in res.mappings().all()]

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
                has_spf = any(
                    "v=spf1" in (r.get("value", "")).lower()
                    for r in dns_records
                    if r.get("type") == "TXT"
                )
                has_dmarc = any(
                    "v=dmarc1" in (r.get("value", "")).lower()
                    for r in dns_records
                    if r.get("type") == "TXT"
                )

                dns_flags = []
                if has_spf:
                    dns_flags.append("SPF")
                if has_dmarc:
                    dns_flags.append("DMARC")

                all_domains.append(
                    f"{domain_name} | Exp: {expiry or '?'} | DNS: {', '.join(dns_flags) or 'none'}"
                )

            for ssl in data.get("ssl", []):
                ssl_dom = ssl.get("domain", "")
                ssl_exp = ssl.get("expiry", "")
                ssl_type = ssl.get("type", "")
                if ssl_dom:
                    all_ssl.append(f"{ssl_dom} | {ssl_type} | Exp: {ssl_exp}")

        if all_domains:
            type_id = await client.ensure_domain_overview_type()
            now = datetime.now(UTC)
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
                            exp_date = datetime.fromisoformat(exp_str[:10]).replace(tzinfo=UTC)
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
            synced.append(
                {
                    "type": "domain_overview",
                    "asset_id": result.get("id"),
                    "action": result.get("upserted", "synced"),
                    "domains": len(all_domains),
                }
            )
    except Exception as e:
        logger.warning("Domain overview sync failed for %s: %s", customer_id, e)
        errors.append({"type": "domain_overview", "error": str(e)})

    # ── 3. License Summary (ALSO renewals) ──────────────────────────────────
    try:
        cust.get("AlsoAccountId", "")
        if True:  # Check DB regardless — customer_id may be linked
            from sqlmodel import select

            from app.core.orm import get_session
            from app.models.integrations import AlsoRenewal, AlsoSubscriptionDetail

            async with get_session() as session:
                stmt = (
                    select(
                        AlsoRenewal.service_name,
                        AlsoRenewal.contract_end,
                        AlsoRenewal.account_state,
                        AlsoSubscriptionDetail.quantity,
                        AlsoSubscriptionDetail.unit_price,
                        AlsoSubscriptionDetail.monthly_cost,
                        AlsoSubscriptionDetail.currency,
                    )
                    .join(
                        AlsoSubscriptionDetail,
                        AlsoRenewal.subscription_id == AlsoSubscriptionDetail.subscription_id,
                        isouter=True,
                    )
                    .where(AlsoRenewal.customer_id == customer_id)
                    .order_by(AlsoRenewal.contract_end.asc())
                )
                res = await session.execute(stmt)
                renewals = [dict(r) for r in res.mappings().all()]

            if renewals:
                type_id = await client.ensure_license_summary_type()
                total_mrr = sum(r.get("monthly_cost") or 0 for r in renewals)
                currency = next((r.get("currency") for r in renewals if r.get("currency")), "NOK")
                now = datetime.now(UTC)

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
                                end_dt = end_dt.replace(tzinfo=UTC)
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
                synced.append(
                    {
                        "type": "license_summary",
                        "asset_id": result.get("id"),
                        "action": result.get("upserted", "synced"),
                        "subscriptions": len(renewals),
                        "mrr": round(total_mrr, 2),
                    }
                )
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
        result = await _sync_customer_documentation(customer_id, client, request)
        if result.get("error"):
            raise ValidationError(result["error"], message_key=result["error_key"])

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
    except ToolkitError:
        raise
    except Exception as e:
        logger.error("IT Glue doc sync failed for %s: %s", customer_id, e)
        raise refusal(IntegrationError, "err_itglue_sync_failed", error=e) from e
    finally:
        await client.close()


@router.post("/itglue/sync-all")
async def itglue_sync_all(request: Request, user: User = Depends(require_role(Role.technician))):
    """Sync documentation to IT Glue for the caller's customers with ITGlueOrgId mapped.

    The response carries one summary per customer (name, licence count, MRR),
    so a scoped caller syncs and hears about their own customers only.
    """
    from app.core.customer import CustomerManager
    from app.integrations.itglue import ITGlueClient

    settings = load_app_settings()
    api_key = settings.get("itglue_api_key", "")
    region = settings.get("itglue_region", "eu")
    if not api_key:
        raise ValidationError(ui_t("err_no_api_key", request))

    allowed = await get_accessible_customer_ids(user)
    customers = filter_customers(CustomerManager.list_customers(), allowed)
    eligible = [c for c in customers if c.get("ITGlueOrgId")]
    if not eligible:
        raise refusal(ValidationError, "err_itglue_no_mapped_customers")

    client = ITGlueClient(api_key=api_key, region=region)
    try:
        results = []
        error_count = 0
        for c in eligible:
            cid = c.get("_id", "")
            if not cid:
                continue
            try:
                r = await _sync_customer_documentation(cid, client, request)
                results.append(r)
                if r.get("errors"):
                    error_count += len(r["errors"])
            except Exception as e:
                logger.warning("Sync failed for customer %s: %s", cid, e)
                results.append(
                    {
                        "customer_id": cid,
                        "customer_name": c.get("CustomerName", "?"),
                        "synced": [],
                        "errors": [{"type": "general", "error": str(e)}],
                    }
                )
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
        raise refusal(IntegrationError, "err_itglue_bulk_sync_failed", error=e) from e
    finally:
        await client.close()

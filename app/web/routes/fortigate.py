"""FortiGate route handlers."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    AuthError,
    ConflictError,
    IntegrationError,
    NotFoundError,
    ValidationError,
)
from app.models.user import Role, User
from app.web.middleware.auth import get_current_user, require_role

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/fortigate/test")
async def fortigate_test(request: Request, user: User = Depends(get_current_user)):
    """Test FortiGate API connectivity."""
    from app.modules.fortigate_audit.client import FortiGateClient

    body = await request.json()
    host = body.get("host", "").strip()
    token = body.get("api_token", "").strip()
    port = int(body.get("port", 443))
    vdom = body.get("vdom", "root")
    verify_ssl = body.get("verify_ssl", True)

    if not host or not token:
        raise ValidationError("Host og API-token er påkrevd")

    try:
        async with FortiGateClient(host, token, port=port, vdom=vdom, verify_ssl=verify_ssl) as fg:
            result = await fg.test_connection()
            return result
    except Exception as e:
        logger.exception("FortiGate test connection failed for %s", host)
        return {"ok": False, "error": str(e)}


@router.post("/fortigate/save")
async def fortigate_save(request: Request, user: User = Depends(get_current_user)):
    """Save FortiGate config for the active customer."""
    from app.core.credentials import store_secret
    from app.core.customer import CustomerManager

    body = await request.json()
    active = CustomerManager.get_active()
    if not active:
        raise ValidationError("Ingen aktiv kunde")

    cust_id = active["_id"]
    config = CustomerManager.get_customer(cust_id)
    if not config:
        raise NotFoundError("Kunde ikke funnet")

    # Update network fields
    config["FortiGateHost"] = body.get("host", "").strip()
    config["FortiGatePort"] = int(body.get("port", 443))
    config["FortiGateVDOM"] = body.get("vdom", "root")
    config["FortiGateVerifySSL"] = body.get("verify_ssl", True)

    # Save token to keyring
    token = body.get("api_token", "").strip()
    if token:
        store_secret(cust_id, "fortigate_api_token", token)

    # Save config (strip internal fields)
    save_data = {k: v for k, v in config.items() if not k.startswith("_")}
    CustomerManager.save_customer(save_data)

    return {"ok": True}


# ── Helper: resolve FortiGate connection info for a customer ─────────────────

def _get_fg_config(customer_id: str) -> tuple[dict, str]:
    """Return (customer_config, api_token) or raise HTTPException."""
    from fastapi import HTTPException

    from app.core.credentials import get_secret
    from app.core.customer import CustomerManager

    config = CustomerManager.get_customer(customer_id)
    if not config:
        raise HTTPException(status_code=404, detail="Kunde ikke funnet")

    host = config.get("FortiGateHost", "")
    if not host:
        raise HTTPException(status_code=400, detail="FortiGate-host er ikke konfigurert for denne kunden")

    token = get_secret(customer_id, "fortigate_api_token")
    if not token:
        raise HTTPException(status_code=400, detail="FortiGate API-token er ikke konfigurert for denne kunden")

    return config, token


# ── Enhanced endpoints ───────────────────────────────────────────────────────

@router.get("/fortigate/dashboard/{customer_id}")
async def fortigate_dashboard(
    customer_id: str,
    _user=Depends(require_role(Role.technician)),
):
    """Live FortiGate dashboard stats."""
    from app.services.fortigate_api import get_dashboard

    config, token = _get_fg_config(customer_id)
    try:
        return await get_dashboard(config, token)
    except Exception as e:
        logger.exception("Dashboard fetch failed for %s", customer_id)
        raise IntegrationError(str(e))


@router.post("/fortigate/backup/{customer_id}")
async def fortigate_backup(
    customer_id: str,
    _user=Depends(require_role(Role.technician)),
):
    """Trigger a FortiGate config backup."""
    from app.services.fortigate_api import backup_config

    config, token = _get_fg_config(customer_id)
    try:
        result = await backup_config(config, token, customer_id)
        status = 200 if result.get("ok") else 502
        return JSONResponse(result, status_code=status)
    except Exception as e:
        logger.exception("Backup failed for %s", customer_id)
        raise IntegrationError(str(e))


@router.get("/fortigate/backups/{customer_id}")
async def fortigate_list_backups(
    customer_id: str,
    _user=Depends(require_role(Role.technician)),
):
    """List available FortiGate config backups."""
    from app.services.fortigate_api import list_backups

    return await list_backups(customer_id)


@router.get("/fortigate/backup/{customer_id}/{filename}")
async def fortigate_download_backup(
    customer_id: str,
    filename: str,
    _user=Depends(require_role(Role.technician)),
):
    """Download a specific backup file (decrypted)."""
    from app.services.fortigate_api import read_backup

    content = await read_backup(customer_id, filename)
    if content is None:
        raise NotFoundError("Sikkerhetskopi ikke funnet")
    return JSONResponse({"filename": filename, "content": content})


@router.get("/fortigate/diff/{customer_id}")
async def fortigate_diff(
    customer_id: str,
    file1: str = Query(..., description="First backup filename"),
    file2: str = Query(..., description="Second backup filename"),
    _user=Depends(require_role(Role.technician)),
):
    """Compare two FortiGate config backups."""
    from app.services.fortigate_api import diff_configs

    result = await diff_configs(customer_id, file1, file2)
    status = 200 if result.get("ok") else 404
    return JSONResponse(result, status_code=status)


@router.post("/fortigate/deploy-key/{customer_id}")
async def fortigate_deploy_key(
    customer_id: str,
    request: Request,
    _user=Depends(require_role(Role.technician)),
):
    """Push an SSH public key to a FortiGate admin user via REST API."""
    from app.services.fortigate_api import deploy_ssh_key

    body = await request.json()
    admin_user = body.get("admin_user", "").strip()
    public_key = body.get("public_key", "").strip()

    if not admin_user or not public_key:
        raise ValidationError("admin_user og public_key er påkrevd")

    config, token = _get_fg_config(customer_id)
    result = await deploy_ssh_key(config, token, admin_user, public_key)
    status = 200 if result.get("ok") else 502
    return JSONResponse(result, status_code=status)


@router.post("/fortigate/generate-token/{customer_id}")
async def fortigate_generate_token(
    customer_id: str,
    request: Request,
    _user=Depends(require_role(Role.technician)),
):
    """Create a FortiGate REST API token via SSH."""
    from app.services.fortigate_api import generate_api_token

    body = await request.json()
    ssh_host = body.get("ssh_host", "").strip()
    ssh_port = int(body.get("ssh_port", 22))
    ssh_user = body.get("ssh_user", "admin").strip()
    ssh_password = body.get("ssh_password", "").strip()
    api_admin_name = body.get("api_admin_name", "msp_api_admin").strip()
    vdom = body.get("vdom", "root")
    trusted_hosts = body.get("trusted_hosts", "0.0.0.0/0")
    accprofile = body.get("accprofile", "super_admin")

    if not ssh_host or not ssh_password:
        raise ValidationError("ssh_host og ssh_password er påkrevd")

    result = await generate_api_token(
        ssh_host=ssh_host,
        ssh_port=ssh_port,
        ssh_user=ssh_user,
        ssh_password=ssh_password,
        api_admin_name=api_admin_name,
        vdom=vdom,
        trusted_hosts=trusted_hosts,
        accprofile=accprofile,
    )
    status = 200 if result.get("ok") else 502
    return JSONResponse(result, status_code=status)


@router.post("/fortigate/bootstrap")
async def fortigate_bootstrap(
    request: Request,
    user: User = Depends(require_role(Role.technician)),
):
    """Bootstrap a factory-default FortiGate: set password, create API token.

    Connects via SSH with admin/empty password, sets a random admin password,
    applies basic hardening, creates a REST API user, and returns all credentials.
    On success, credentials are persisted to keyring and the active customer's
    config is updated so the credentials can be retrieved later if lost.
    """
    from app.core.activity_log import log_activity
    from app.core.credentials import store_secret
    from app.core.customer import CustomerManager
    from app.services.fortigate_api import factory_bootstrap

    body = await request.json()
    host = body.get("host", "").strip()
    ssh_port = int(body.get("ssh_port", 22))
    hostname = body.get("hostname", "").strip() or None
    api_admin_name = body.get("api_admin_name", "msp_api_admin").strip()

    if not host:
        raise ValidationError("host (IP-adresse) er påkrevd")

    result = await factory_bootstrap(
        host=host,
        port=ssh_port,
        hostname=hostname,
        api_admin_name=api_admin_name,
    )

    # Persist credentials so they can be recovered later (e.g. PC crash)
    if result.get("ok"):
        active = CustomerManager.get_active()
        if active:
            cust_id = active["_id"]
            cust_name = active.get("CustomerName", "")
            try:
                store_secret(cust_id, "fortigate_api_token", result.get("api_token", ""))
                store_secret(cust_id, "fortigate_admin_password", result.get("admin_password", ""))
                store_secret(cust_id, "fortigate_admin_user", "admin")

                # Update config: bootstrap moved admin GUI from 443 → 8443
                cfg = CustomerManager.get_customer(cust_id) or {}
                cfg["FortiGateHost"] = host
                cfg["FortiGatePort"] = 8443
                cfg["FortiGateVDOM"] = cfg.get("FortiGateVDOM") or "root"
                cfg["FortiGateVerifySSL"] = cfg.get("FortiGateVerifySSL", True)
                cfg["FortiGateAdminUser"] = "admin"
                cfg["FortiGateApiUser"] = api_admin_name
                cfg["FortiGateBootstrappedAt"] = (
                    __import__("datetime").datetime.now(
                        __import__("datetime").timezone.utc
                    ).isoformat()
                )
                save_data = {k: v for k, v in cfg.items() if not k.startswith("_")}
                CustomerManager.save_customer(save_data)

                log_activity(
                    "fortigate_bootstrapped",
                    detail=f"FortiGate {host}:8443 — admin/API-credentials lagret i keyring",
                    customer=cust_name,
                    user=user.username,
                )
                result["persisted"] = True
            except Exception as e:
                logger.exception("Failed to persist bootstrap credentials")
                result["persisted"] = False
                result["persist_error"] = str(e)
        else:
            result["persisted"] = False
            result["persist_error"] = "Ingen aktiv kunde — credentials ble ikke lagret"

    status = 200 if result.get("ok") else 502
    return JSONResponse(result, status_code=status)


@router.get("/fortigate/credentials/{customer_id}")
async def fortigate_credentials(
    customer_id: str,
    user: User = Depends(require_role(Role.technician)),
):
    """Return stored FortiGate credentials for a customer (host, port, admin/password, API token).

    Used to recover credentials after a bootstrap if the browser/PC was lost.
    Returns 404 if no credentials are stored.
    """
    from app.core.activity_log import log_activity
    from app.core.credentials import get_secret
    from app.core.customer import CustomerManager

    config = CustomerManager.get_customer(customer_id)
    if not config:
        raise NotFoundError("Kunde ikke funnet")

    api_token = get_secret(customer_id, "fortigate_api_token") or ""
    admin_pw = get_secret(customer_id, "fortigate_admin_password") or ""
    admin_user = get_secret(customer_id, "fortigate_admin_user") or "admin"

    if not (api_token or admin_pw):
        raise NotFoundError("Ingen lagrede credentials for denne FortiGaten")

    log_activity(
        "fortigate_credentials_viewed",
        detail=f"FortiGate-credentials hentet for {config.get('FortiGateHost', '')}",
        customer=config.get("CustomerName", ""),
        user=user.username,
    )

    return {
        "ok": True,
        "customer_name": config.get("CustomerName", ""),
        "host": config.get("FortiGateHost", ""),
        "port": int(config.get("FortiGatePort", 8443)),
        "admin_user": admin_user,
        "admin_password": admin_pw,
        "api_user": config.get("FortiGateApiUser", "msp_api_admin"),
        "api_token": api_token,
        "bootstrapped_at": config.get("FortiGateBootstrappedAt", ""),
    }


@router.get("/fortigate/compliance/{customer_id}")
async def fortigate_compliance(
    customer_id: str,
    _user=Depends(require_role(Role.technician)),
):
    """Run CIS compliance checks against the FortiGate."""
    from app.services.fortigate_api import check_compliance

    config, token = _get_fg_config(customer_id)
    try:
        return await check_compliance(config, token)
    except Exception as e:
        logger.exception("Compliance check failed for %s", customer_id)
        raise IntegrationError(str(e))


@router.get("/fortigate/threats/{customer_id}")
async def fortigate_threats(
    customer_id: str,
    _user=Depends(require_role(Role.technician)),
):
    """Fetch threat log summary for a customer's FortiGate."""
    from app.services.fortigate_api import get_threat_summary

    config, token = _get_fg_config(customer_id)
    try:
        return await get_threat_summary(config, token, days=7)
    except Exception as e:
        logger.exception("Threat summary failed for %s", customer_id)
        raise IntegrationError(str(e))


@router.get("/fortigate/firewall-audit/{customer_id}")
async def fortigate_firewall_audit(
    customer_id: str,
    _user=Depends(require_role(Role.technician)),
):
    """Audit firewall policies for a customer's FortiGate."""
    from app.services.fortigate_api import audit_firewall_rules

    config, token = _get_fg_config(customer_id)
    try:
        return await audit_firewall_rules(config, token)
    except Exception as e:
        logger.exception("Firewall audit failed for %s", customer_id)
        raise IntegrationError(str(e))


@router.get("/fortigate/all")
async def fortigate_all(user: User = Depends(get_current_user)):
    """Get FortiGate status for ALL customers that have a FortiGate configured."""
    from app.services.fortigate_api import poll_all_fortigates

    results = await poll_all_fortigates()
    return {"fortigates": results, "count": len(results)}


@router.post("/fortigate/backup-all")
async def fortigate_backup_all(user: User = Depends(require_role(Role.admin))):
    """Trigger config backup for ALL FortiGates. Returns per-customer results."""
    import asyncio

    from app.core.credentials import get_secret
    from app.core.customer import CustomerManager
    from app.services.fortigate_api import backup_config

    customers = CustomerManager.list_customers()
    results = []

    async def _backup_one(c):
        cid = c.get("_id", "")
        name = c.get("CustomerName", "")
        host = c.get("FortiGateHost", "")
        # Must match how fortigate_save/_get_fg_config store it: keyed by the
        # customer id under "fortigate_api_token". Looking up "fortigate_token"
        # under TenantId found nothing, so backup-all silently backed up
        # zero devices while reporting success.
        token = get_secret(cid, "fortigate_api_token") if cid else None
        if not host or not token:
            logger.warning(
                "Skipping FortiGate backup for %s — %s",
                name or cid,
                "no host configured" if not host else "no API token stored",
            )
            return None
        config = c
        try:
            result = await backup_config(config, token, cid)
            return {"customer_id": cid, "customer_name": name, **result}
        except Exception as e:
            return {"customer_id": cid, "customer_name": name, "ok": False, "error": str(e)}

    tasks = [_backup_one(c) for c in customers if c.get("FortiGateHost")]
    raw = await asyncio.gather(*tasks)
    results = [r for r in raw if r is not None]

    ok_count = sum(1 for r in results if r.get("ok"))
    return {
        "results": results,
        "total": len(results),
        "success": ok_count,
        "failed": len(results) - ok_count,
    }

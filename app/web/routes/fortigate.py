"""FortiGate route handlers."""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    ForbiddenError,
    IntegrationError,
    NotFoundError,
    ValidationError,
)
from app.models.network import (
    FortiGateBootstrap,
    FortiGateDeployKey,
    FortiGateGenerateToken,
    FortiGateSaveRequest,
    FortiGateTestRequest,
)
from app.models.user import Role, User
from app.web.i18n import refusal, ui_t
from app.web.middleware.auth import (
    get_current_user,
    require_customer_access,
    require_role,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/fortigate/test")
async def fortigate_test(
    body: FortiGateTestRequest,
    request: Request,
    user: User = Depends(require_role(Role.technician)),
):
    """Test FortiGate API connectivity with a token the caller supplies.

    The hub makes the request, from inside the MSP's network, to an address the
    caller picks. So: technician only, a validated host, and a failure reported
    as a category rather than the client's exception text, since telling
    "refused" from "timed out" from "TLS error" maps out what listens on any
    host:port the caller names. The detail goes to the server log.
    """
    from app.core.validation import validate_host, validate_identifier
    from app.modules.fortigate_audit.client import FortiGateClient

    host = (body.host or "").strip()
    token = (body.api_token or "").strip()
    vdom = (body.vdom or "").strip() or "root"
    verify_ssl = body.verify_ssl

    if not host or not token:
        raise refusal(ValidationError, "err_fortigate_host_token_required")
    validate_host(host, "host")
    validate_identifier(vdom, "vdom")
    port = _parse_port(body.port, default=443)

    try:
        async with FortiGateClient(host, token, port=port, vdom=vdom, verify_ssl=verify_ssl) as fg:
            result = await fg.test_connection()
    except Exception as e:
        result = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    if result.get("ok"):
        return result
    logger.warning("FortiGate test for %s:%d failed: %s", host, port, result.get("error"))
    return _device_test_failure(result.get("error"), request)


# A device that answers with one of these is reachable and refused the login.
# Everything else (refused, timed out, TLS, DNS) is reported as unreachable.
_REJECTED_LOGIN = re.compile(r"\bHTTP 40[013]\b")


def _device_test_failure(detail: str | None, request: Request) -> dict:
    key = (
        "err_device_test_auth"
        if detail and _REJECTED_LOGIN.search(detail)
        else "err_device_test_unreachable"
    )
    return {"ok": False, "error": ui_t(key, request), "error_key": key}


def _parse_port(raw, *, default: int) -> int:
    if raw is None or str(raw).strip() == "":
        return default
    try:
        port = int(raw)
    except (TypeError, ValueError) as e:
        raise refusal(ValidationError, "err_port_invalid", port=raw) from e
    if not 1 <= port <= 65535:
        raise refusal(ValidationError, "err_port_out_of_range", port=port)
    return port


@router.post("/fortigate/save/{customer_id}")
async def fortigate_save(
    customer_id: str,
    body: FortiGateSaveRequest,
    # Was get_current_user, so a viewer could rewrite which address a
    # customer's firewall credentials travel to and store a new API token
    # under that customer. The sibling /unifi/save has always been technician.
    user: User = Depends(require_customer_access(Role.technician)),
):
    """Save FortiGate config for the customer named in the path.

    The stored API token was entered for one address. Changing the host or
    port without supplying a token in the same request deletes it, so the
    next dashboard, compliance or backup call cannot send ``Bearer <token>``
    to an address the caller chose (with verify_ssl off, to anything that
    answers). That holds for admins too. The bootstrap admin password cannot
    be re-entered here and deleting it would lose the firewall's only copy,
    so while one is stored only an admin may repoint the device.
    """
    from app.core.activity_log import log_activity
    from app.core.credentials import delete_secret, get_secret, store_secret
    from app.core.customer import CustomerManager
    from app.core.validation import validate_host

    # Named in the path. This saved to "the active customer", so a switch in
    # another tab between opening the form and pressing Lagre sent this
    # firewall's address and token to a different customer.
    cust_id = customer_id
    config = CustomerManager.get_customer(cust_id)
    if not config:
        raise refusal(NotFoundError, "err_customer_not_found")

    # Update network fields.
    #
    # Every one of these used to be written unconditionally from the body, so a
    # request that omitted a field reset it: no "host" blanked FortiGateHost, no
    # "port" dropped a hardened 8443 back to 443, no "verify_ssl" turned
    # certificate checking back on. The blanking matters most — the keyring
    # secrets survive it, which leaves a customer holding firewall credentials
    # with no address recorded for them, and that is exactly the state
    # provisioning now has to refuse. Absent means "leave alone"; only a field
    # that is actually present is written.
    # A null is treated as absent too, so a form that always serialises every
    # key does not depend on which of them it managed to fill in. An empty
    # *string* host is the one deliberate clear, since that is the only way to
    # unset an address on purpose.
    old_host = (config.get("FortiGateHost") or "").strip()
    old_port = _configured_port(config)
    if body.host is not None:
        host = body.host.strip()
        if host:
            validate_host(host, "host")
        config["FortiGateHost"] = host
    raw_port = body.port
    if raw_port is not None and str(raw_port).strip() != "":
        try:
            port = int(raw_port)
        except (TypeError, ValueError) as e:
            # int("abc") used to reach the client as a 500 "internal error".
            raise refusal(ValidationError, "err_port_invalid", port=raw_port) from e
        if not 1 <= port <= 65535:
            raise refusal(ValidationError, "err_port_out_of_range", port=port)
        config["FortiGatePort"] = port
    if body.vdom is not None:
        config["FortiGateVDOM"] = body.vdom.strip() or "root"
    if body.verify_ssl is not None:
        config["FortiGateVerifySSL"] = body.verify_ssl

    token = (body.api_token or "").strip()
    new_host = (config.get("FortiGateHost") or "").strip()
    # Clearing the address sends nothing anywhere; setting one, including on a
    # customer that had none, is where the stored secrets would travel next.
    retargeted = bool(new_host) and (
        new_host.casefold() != old_host.casefold() or _configured_port(config) != old_port
    )
    token_cleared = False
    if retargeted:
        if user.role < Role.admin and get_secret(cust_id, "fortigate_admin_password"):
            raise refusal(ForbiddenError, "err_fortigate_address_admin_only")
        if not token and get_secret(cust_id, "fortigate_api_token"):
            delete_secret(cust_id, "fortigate_api_token")
            token_cleared = True

    if token:
        store_secret(cust_id, "fortigate_api_token", token)

    # Save config (strip internal fields)
    save_data = {k: v for k, v in config.items() if not k.startswith("_")}
    CustomerManager.save_customer(save_data)

    detail = f"Lagret FortiGate-oppsett for {config.get('CustomerName', cust_id)}"
    if new_host != old_host:
        # The one change worth being able to reconstruct afterwards: it decides
        # where this customer's stored firewall credentials are sent.
        detail += f" — adresse endret fra {old_host or '(ingen)'} til {new_host or '(ingen)'}"
    if token:
        detail += " — nytt API-token lagret"
    if token_cleared:
        detail += "; lagret API-token slettet fordi adressen ble endret"
    log_activity("fortigate_save", detail=detail, customer=cust_id, user=user.username)

    return {"ok": True, "token_cleared": token_cleared}


def _configured_port(config: dict) -> int:
    """The port the API client will actually use (see fortigate_api._build_client)."""
    try:
        return int(config.get("FortiGatePort") or 443)
    except (TypeError, ValueError):
        return 443


# ── Helper: resolve FortiGate connection info for a customer ─────────────────


def _get_fg_config(customer_id: str) -> tuple[dict, str]:
    """Return (customer_config, api_token), or refuse with a 404 or a 400."""
    from app.core.credentials import get_secret
    from app.core.customer import CustomerManager

    config = CustomerManager.get_customer(customer_id)
    if not config:
        raise refusal(NotFoundError, "err_customer_not_found")

    host = config.get("FortiGateHost", "")
    if not host:
        raise refusal(ValidationError, "err_fortigate_host_missing")

    token = get_secret(customer_id, "fortigate_api_token")
    if not token:
        raise refusal(ValidationError, "err_fortigate_token_missing")

    return config, token


# ── Enhanced endpoints ───────────────────────────────────────────────────────


@router.get("/fortigate/dashboard/{customer_id}")
async def fortigate_dashboard(
    customer_id: str,
    _user=Depends(require_customer_access(Role.technician)),
):
    """Live FortiGate dashboard stats."""
    from app.services.fortigate_api import get_dashboard

    config, token = _get_fg_config(customer_id)
    try:
        return await get_dashboard(config, token)
    except Exception as e:
        logger.exception("Dashboard fetch failed for %s", customer_id)
        raise IntegrationError(str(e)) from e


@router.post("/fortigate/backup/{customer_id}")
async def fortigate_backup(
    customer_id: str,
    _user=Depends(require_customer_access(Role.technician)),
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
        raise IntegrationError(str(e)) from e


@router.get("/fortigate/backups/{customer_id}")
async def fortigate_list_backups(
    customer_id: str,
    _user=Depends(require_customer_access(Role.technician)),
):
    """List available FortiGate config backups."""
    from app.services.fortigate_api import list_backups

    return await list_backups(customer_id)


@router.get("/fortigate/backup/{customer_id}/{filename}")
async def fortigate_download_backup(
    customer_id: str,
    filename: str,
    _user=Depends(require_customer_access(Role.technician)),
):
    """Download a specific backup file (decrypted)."""
    from app.services.fortigate_api import read_backup

    content = await read_backup(customer_id, filename)
    if content is None:
        raise refusal(NotFoundError, "err_fortigate_backup_not_found")
    return JSONResponse({"filename": filename, "content": content})


@router.get("/fortigate/diff/{customer_id}")
async def fortigate_diff(
    customer_id: str,
    file1: str = Query(..., description="First backup filename"),
    file2: str = Query(..., description="Second backup filename"),
    _user=Depends(require_customer_access(Role.technician)),
):
    """Compare two FortiGate config backups."""
    from app.services.fortigate_api import diff_configs

    result = await diff_configs(customer_id, file1, file2)
    status = 200 if result.get("ok") else 404
    return JSONResponse(result, status_code=status)


@router.post("/fortigate/deploy-key/{customer_id}")
async def fortigate_deploy_key(
    customer_id: str,
    body: FortiGateDeployKey,
    _user=Depends(require_customer_access(Role.technician)),
):
    """Push an SSH public key to a FortiGate admin user via REST API."""
    from app.services.fortigate_api import deploy_ssh_key

    admin_user = body.admin_user.strip()
    public_key = body.public_key.strip()

    if not admin_user or not public_key:
        raise refusal(ValidationError, "err_fortigate_admin_key_required")

    config, token = _get_fg_config(customer_id)
    result = await deploy_ssh_key(config, token, admin_user, public_key)
    status = 200 if result.get("ok") else 502
    return JSONResponse(result, status_code=status)


@router.post("/fortigate/generate-token/{customer_id}")
async def fortigate_generate_token(
    customer_id: str,
    body: FortiGateGenerateToken,
    _user=Depends(require_customer_access(Role.technician)),
):
    """Create a FortiGate REST API token via SSH."""
    from app.services.fortigate_api import generate_api_token

    ssh_host = body.ssh_host.strip()
    ssh_port = body.ssh_port
    ssh_user = body.ssh_user.strip()
    ssh_password = body.ssh_password.strip()
    api_admin_name = body.api_admin_name.strip()
    vdom = body.vdom
    trusted_hosts = body.trusted_hosts
    accprofile = body.accprofile

    if not ssh_host or not ssh_password:
        raise refusal(ValidationError, "err_fortigate_ssh_required")

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
    body: FortiGateBootstrap,
    user: User = Depends(require_role(Role.technician)),
):
    """Bootstrap a factory-default FortiGate: set password, create API token.

    Connects via SSH with admin/empty password, sets a random admin password,
    applies basic hardening, creates a REST API user, and returns all credentials.
    On success, when the body names a customer, the credentials are persisted
    to the keyring and that customer's config is updated so they can be
    retrieved later if lost. Without a customer nothing is stored: the
    operator copies them from the answer.
    """
    from app.core.activity_log import log_activity
    from app.core.credentials import store_secret
    from app.core.customer import CustomerManager
    from app.core.rbac import check_customer_access
    from app.core.validation import validate_host
    from app.services.fortigate_api import factory_bootstrap

    host = body.host.strip()
    try:
        ssh_port = int(body.ssh_port or 22)
    except (TypeError, ValueError) as e:
        raise refusal(ValidationError, "err_fortigate_invalid_ssh_port", port=body.ssh_port) from e
    hostname = body.hostname.strip() or None
    api_admin_name = body.api_admin_name.strip()

    if not host:
        raise refusal(ValidationError, "err_fortigate_host_ip_required")
    validate_host(host, "host")

    # The success path overwrites this customer's stored API token and admin
    # password with the newly minted ones. On the wrong customer that is a
    # destructive write against credentials the caller may not be allowed near,
    # so the customer is named by the caller and checked before anything runs.
    # It used to be the caller's active customer, which another tab could
    # change while the form was open.
    active = None
    if body.customer_id:
        if not await check_customer_access(user, body.customer_id):
            raise refusal(ForbiddenError, "err_fortigate_customer_forbidden")
        active = CustomerManager.get_customer(body.customer_id)
        if active is None:
            raise refusal(NotFoundError, "err_customer_not_found")

    result = await factory_bootstrap(
        host=host,
        port=ssh_port,
        hostname=hostname,
        api_admin_name=api_admin_name,
    )

    # Persist credentials so they can be recovered later (e.g. PC crash), to
    # the *same* customer the access check above ran against.
    if result.get("ok"):
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
                    __import__("datetime")
                    .datetime.now(__import__("datetime").timezone.utc)
                    .isoformat()
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
            result["persist_error"] = "Ingen kunde valgt, så credentials ble ikke lagret"

    status = 200 if result.get("ok") else 502
    return JSONResponse(result, status_code=status)


@router.get("/fortigate/credentials/{customer_id}")
async def fortigate_credentials(
    customer_id: str,
    user: User = Depends(require_customer_access(Role.admin)),
):
    """Return stored FortiGate credentials for a customer (host, port, admin/password, API token).

    Used to recover credentials after a bootstrap if the browser/PC was lost.
    Returns 404 if no credentials are stored.

    Admin-only: this hands back a firewall's plaintext admin password and API
    token. Day-to-day FortiGate work goes through the other endpoints, which
    use the stored token without ever disclosing it, so a technician has no
    routine need for this. Every call is recorded in the activity log.
    """
    from app.core.activity_log import log_activity
    from app.core.credentials import get_secret
    from app.core.customer import CustomerManager

    config = CustomerManager.get_customer(customer_id)
    if not config:
        raise refusal(NotFoundError, "err_customer_not_found")

    api_token = get_secret(customer_id, "fortigate_api_token") or ""
    admin_pw = get_secret(customer_id, "fortigate_admin_password") or ""
    admin_user = get_secret(customer_id, "fortigate_admin_user") or "admin"

    if not (api_token or admin_pw):
        raise refusal(NotFoundError, "err_fortigate_no_credentials")

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
    _user=Depends(require_customer_access(Role.technician)),
):
    """Run CIS compliance checks against the FortiGate."""
    from app.services.fortigate_api import check_compliance

    config, token = _get_fg_config(customer_id)
    try:
        return await check_compliance(config, token)
    except Exception as e:
        logger.exception("Compliance check failed for %s", customer_id)
        raise IntegrationError(str(e)) from e


@router.get("/fortigate/threats/{customer_id}")
async def fortigate_threats(
    customer_id: str,
    _user=Depends(require_customer_access(Role.technician)),
):
    """Fetch threat log summary for a customer's FortiGate."""
    from app.services.fortigate_api import get_threat_summary

    config, token = _get_fg_config(customer_id)
    try:
        return await get_threat_summary(config, token, days=7)
    except Exception as e:
        logger.exception("Threat summary failed for %s", customer_id)
        raise IntegrationError(str(e)) from e


@router.get("/fortigate/firewall-audit/{customer_id}")
async def fortigate_firewall_audit(
    customer_id: str,
    _user=Depends(require_customer_access(Role.technician)),
):
    """Audit firewall policies for a customer's FortiGate."""
    from app.services.fortigate_api import audit_firewall_rules

    config, token = _get_fg_config(customer_id)
    try:
        return await audit_firewall_rules(config, token)
    except Exception as e:
        logger.exception("Firewall audit failed for %s", customer_id)
        raise IntegrationError(str(e)) from e


@router.get("/fortigate/all")
async def fortigate_all(user: User = Depends(get_current_user)):
    """FortiGate status for every customer this caller may see.

    Scoped before polling, not after: each poll authenticates with that
    customer's stored token, so a firewall outside the caller's customers is
    not contacted on their behalf at all.
    """
    from app.core.rbac import get_accessible_customer_ids
    from app.services.fortigate_api import poll_all_fortigates

    results = await poll_all_fortigates(customer_ids=await get_accessible_customer_ids(user))
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

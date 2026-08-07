"""Asking a Global Admin for a permission the app cannot grant itself.

Sybr HUB holds twenty-two Graph permissions and every one ends in ``.Read.All``.
It deliberately does not hold ``AppRoleAssignment.ReadWrite.All``, so it cannot
widen its own access — which is the property that makes a compromised toolkit
merely embarrassing rather than a way into every customer's tenant.

That leaves exactly one honest way to gain a write permission: a human with the
authority to grant it signs in and grants it. This is that flow, in the
product, rather than a page of portal instructions.

Device code, because the operator is usually at a different machine from the
one the toolkit runs on, and because it is what the first-run setup already
uses. The sign-in is delegated and short-lived: the token exists for the length
of one grant and is never stored.

Both halves are idempotent. Declaring a permission that is already declared and
granting a role that is already assigned are the normal states when somebody
re-runs this after an interruption, and neither should read as an error.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GRAPH = "https://graph.microsoft.com/v1.0"
GRAPH_APP_ID = "00000003-0000-0000-c000-000000000000"

# Microsoft Graph PowerShell: a first-party public client that supports device
# code and is pre-consented for delegated Graph in every tenant. Using the
# customer's own app registration would need public-client flows enabled on it,
# which is a permanent change to a confidential client made for a one-off task.
DEVICE_CODE_CLIENT = "14d82eec-204b-4c2f-b7e8-296a70dab67e"

# What the *operator* signs in with, not what the app ends up holding. Adding an
# app role needs to edit the registration and to assign the role.
DELEGATED_SCOPES = [
    "https://graph.microsoft.com/Application.ReadWrite.All",
    "https://graph.microsoft.com/AppRoleAssignment.ReadWrite.All",
]


class ConsentError(Exception):
    """The grant could not be completed, with a reason for an operator."""


def start_device_flow(tenant_id: str) -> dict[str, Any]:
    """Begin an interactive sign-in. Returns the code and where to enter it."""
    import msal

    app = msal.PublicClientApplication(
        DEVICE_CODE_CLIENT, authority=f"https://login.microsoftonline.com/{tenant_id}"
    )
    flow = app.initiate_device_flow(scopes=DELEGATED_SCOPES)
    if "user_code" not in flow:
        raise ConsentError(
            f"Could not start the sign-in: {flow.get('error_description', flow)}"
        )
    return flow


def complete_device_flow(tenant_id: str, flow: dict) -> str:
    """Wait for the operator to finish signing in, and return their token."""
    import msal

    app = msal.PublicClientApplication(
        DEVICE_CODE_CLIENT, authority=f"https://login.microsoftonline.com/{tenant_id}"
    )
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        raise ConsentError(
            result.get("error_description") or "Sign-in did not complete"
        )
    return str(result["access_token"])


async def _get(client: httpx.AsyncClient, path: str, **kw) -> dict:
    resp = await client.get(f"{GRAPH}/{path.lstrip('/')}", **kw)
    resp.raise_for_status()
    return resp.json()


async def grant_application_permission(
    token: str, client_id: str, permission: str
) -> dict[str, Any]:
    """Declare an application permission on a registration and assign it.

    Two separate things that both have to happen, and the portal does them
    together so they are easy to conflate. Declaring puts the permission on the
    registration's list; assigning is the consent that makes it real. A
    registration that declares a permission nobody assigned is a registration
    whose audit says "missing consent" — which is the exact state this is here
    to leave behind.
    """
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=60, headers=headers) as client:
        apps = await _get(client, "applications", params={"$filter": f"appId eq '{client_id}'"})
        if not apps.get("value"):
            raise ConsentError(
                f"No application registration with client id {client_id!r} is visible "
                f"to the account that signed in."
            )
        application = apps["value"][0]
        app_object_id = application["id"]

        graph_sps = await _get(
            client, "servicePrincipals", params={"$filter": f"appId eq '{GRAPH_APP_ID}'"}
        )
        if not graph_sps.get("value"):
            raise ConsentError("Microsoft Graph has no service principal in this tenant")
        graph_sp = graph_sps["value"][0]

        role = next(
            (
                r for r in graph_sp.get("appRoles", [])
                if r.get("value") == permission and "Application" in (r.get("allowedMemberTypes") or [])
            ),
            None,
        )
        if role is None:
            raise ConsentError(
                f"Microsoft Graph publishes no application permission called {permission!r}"
            )

        # ── 1. Declare it on the registration ──
        required = application.get("requiredResourceAccess") or []
        graph_entry = next((r for r in required if r.get("resourceAppId") == GRAPH_APP_ID), None)
        if graph_entry is None:
            graph_entry = {"resourceAppId": GRAPH_APP_ID, "resourceAccess": []}
            required.append(graph_entry)

        already_declared = any(
            a.get("id") == role["id"] for a in graph_entry.get("resourceAccess", [])
        )
        if not already_declared:
            graph_entry.setdefault("resourceAccess", []).append(
                {"id": role["id"], "type": "Role"}
            )
            resp = await client.patch(
                f"{GRAPH}/applications/{app_object_id}",
                json={"requiredResourceAccess": required},
            )
            resp.raise_for_status()

        # ── 2. Assign it, which is the consent ──
        own_sps = await _get(
            client, "servicePrincipals", params={"$filter": f"appId eq '{client_id}'"}
        )
        if not own_sps.get("value"):
            raise ConsentError(
                f"The application {client_id!r} has no service principal in this tenant, "
                f"so there is nothing to assign the permission to."
            )
        own_sp_id = own_sps["value"][0]["id"]

        assignments = await _get(
            client, f"servicePrincipals/{own_sp_id}/appRoleAssignments"
        )
        already_assigned = any(
            a.get("appRoleId") == role["id"] and a.get("resourceId") == graph_sp["id"]
            for a in assignments.get("value", [])
        )
        if not already_assigned:
            resp = await client.post(
                f"{GRAPH}/servicePrincipals/{own_sp_id}/appRoleAssignments",
                json={
                    "principalId": own_sp_id,
                    "resourceId": graph_sp["id"],
                    "appRoleId": role["id"],
                },
            )
            resp.raise_for_status()

    logger.warning(
        "granted %s to application %s (declared=%s assigned=%s)",
        permission, client_id, not already_declared, not already_assigned,
    )
    return {
        "permission": permission,
        "declared": not already_declared,
        "assigned": not already_assigned,
        "already_complete": already_declared and already_assigned,
    }

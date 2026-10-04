"""Network provisioning wizard — 5-step guided setup.

Ported from SuperManager's provisioning wizard.  Walks a technician through
customer details, network topology, services, security hardening, and finally
generates FortiGate CLI / UniFi JSON configs ready for deployment.

Supports deployment via SSH CLI or REST API (PUT /api/v2/cmdb/).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
import string
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, NoReturn

from app.modules.api_result import ApiList, read_failed

logger = logging.getLogger(__name__)

# In-memory wizard sessions (session_id -> WizardState)
_sessions: dict[str, dict] = {}
_SESSION_TTL = 3600  # 1 hour
_SESSION_MAX = 50


def _cleanup_sessions() -> None:
    """Remove expired sessions to prevent memory leaks."""
    now = datetime.now(UTC)
    expired = []
    for sid, s in _sessions.items():
        try:
            created = datetime.fromisoformat(s.get("created_at", ""))
            if (now - created).total_seconds() > _SESSION_TTL:
                expired.append(sid)
        except (ValueError, TypeError):
            expired.append(sid)
    for sid in expired:
        _sessions.pop(sid, None)
    # Cap total sessions
    while len(_sessions) > _SESSION_MAX:
        _sessions.pop(next(iter(_sessions)))


_SECRET_KEYS = re.compile(r"password|passphrase|token|secret|api[_-]?key|psk", re.IGNORECASE)


def _redact(value):
    """Mask credential values by key name, recursively; structure preserved.

    The wizard collects a device password and API token in its steps, and the
    client-facing getters used to hand them straight back (SR-001 #4). The raw
    values stay in the server-side session for the deploy that needs them.
    """
    if isinstance(value, dict):
        return {
            k: (
                "••••••" if isinstance(v, str) and v and _SECRET_KEYS.search(str(k)) else _redact(v)
            )
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


class WizardStep:
    CUSTOMER = 1
    NETWORK = 2
    SERVICES = 3
    SECURITY = 4
    REVIEW = 5


# ── Session Lifecycle ────────────────────────────────────────────────────────


def start_session(user_id: str, customer_id: str = "") -> dict:
    """Start a new wizard session, bound to its owner and customer.

    customer_id is the customer active when the wizard began; every later
    operation is checked against it, and the deploy resolves that customer's
    credentials rather than whichever customer happens to be active later
    (SR-001 #1).
    """
    _cleanup_sessions()
    session_id = str(uuid.uuid4())
    _sessions[session_id] = {
        "id": session_id,
        "user_id": user_id,
        "customer_id": customer_id,
        "current_step": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "steps": {1: None, 2: None, 3: None, 4: None, 5: None},
        "generated": None,
    }
    return {"session_id": session_id, "current_step": 1}


def get_session_raw(session_id: str) -> dict | None:
    """The unredacted session, for internal ownership/authorization checks."""
    return _sessions.get(session_id)


def get_session(session_id: str) -> dict | None:
    """Client-facing session state, with step credentials masked (SR-001 #4)."""
    session = _sessions.get(session_id)
    if session is None:
        return None
    view = dict(session)
    view["steps"] = _redact(session.get("steps", {}))
    return view


def submit_step(session_id: str, step: int, data: dict) -> dict:
    """Submit data for a wizard step."""
    from app.core.exceptions import NotFoundError, ValidationError

    session = _sessions.get(session_id)
    if not session:
        raise NotFoundError("Session not found")
    if step < 1 or step > 5:
        raise ValidationError("Invalid step")
    session["steps"][step] = data
    session["current_step"] = min(step + 1, 5)
    return {"ok": True, "current_step": session["current_step"]}


def get_summary(session_id: str) -> dict:
    """Return a summary of all steps for review."""
    from app.core.exceptions import NotFoundError

    session = _sessions.get(session_id)
    if not session:
        raise NotFoundError("Session not found")
    return {
        "session_id": session_id,
        "steps": _redact(session["steps"]),
        "complete": all(session["steps"][i] is not None for i in range(1, 5)),
    }


def delete_session(session_id: str) -> bool:
    return _sessions.pop(session_id, None) is not None


def list_sessions(user_id: str | None = None) -> list[dict]:
    sessions = list(_sessions.values())
    if user_id:
        sessions = [s for s in sessions if s["user_id"] == user_id]
    return [
        {"id": s["id"], "current_step": s["current_step"], "created_at": s["created_at"]}
        for s in sessions
    ]


# ── Config Generation ────────────────────────────────────────────────────────


async def generate_configs(session_id: str, use_ai: bool = False) -> dict:
    """Generate FortiGate CLI and/or UniFi JSON configs from wizard data."""
    from app.core.exceptions import NotFoundError

    session = _sessions.get(session_id)
    if not session:
        raise NotFoundError("Session not found")

    steps = session["steps"]
    customer = steps.get(1, {}) or {}
    network = steps.get(2, {}) or {}
    services = steps.get(3, {}) or {}
    security = steps.get(4, {}) or {}

    device_type = customer.get("device_type", "fortigate")
    result: dict = {"session_id": session_id, "configs": {}}

    if use_ai:
        result["configs"] = await _generate_with_ai(
            customer,
            network,
            services,
            security,
            device_type,
        )
    else:
        if device_type in ("fortigate", "both"):
            result["configs"]["fortigate_cli"] = _generate_fortigate_cli(
                customer,
                network,
                services,
                security,
            )
        if device_type in ("unifi", "both"):
            result["configs"]["unifi_json"] = _generate_unifi_json(
                customer,
                network,
                services,
                security,
            )

    session["generated"] = result["configs"]
    return result


# ── Deployment ───────────────────────────────────────────────────────────────


def _resolve_fortigate_conn(steps: dict, target_host: str = "", customer_id: str = "") -> dict:
    """Resolve all FortiGate connection variables with consistent precedence.

    Order (most → least specific):
      1. Wizard step 1 (customer) — explicit user input
      2. The session's customer config (FortiGateHost/Port/VDOM/VerifySSL/AdminUser/ApiUser)
      3. Keyring secrets (fortigate_api_token, fortigate_admin_password, fortigate_admin_user)
      4. Hardcoded defaults (port 8443 post-bootstrap, vdom root, verify False, user admin)

    Returns a dict with all keys populated — never returns None values.
    """
    customer_step = steps.get(1, {}) or {}
    security_step = steps.get(4, {}) or {}

    # The session customer's config + keyring lookups
    active_cfg: dict = {}
    cust_id = ""
    try:
        from app.core.customer import CustomerManager

        # The session's bound customer — the deploy must use the credentials of
        # the customer the wizard was started for (SR-001 #1/#5). A session
        # bound to none uses no stored credentials.
        customer = CustomerManager.get_customer(customer_id) if customer_id else None
        if customer:
            cust_id = customer.get("_id", "")
            active_cfg = customer
    except Exception as e:
        logger.warning("Failed to read customer for FortiGate conn resolve: %s", e)

    def _from_keyring(name: str) -> str:
        if not cust_id:
            return ""
        try:
            from app.core.credentials import get_secret

            return get_secret(cust_id, name) or ""
        except Exception:
            logger.debug("Keyring lookup failed for %s", name, exc_info=True)
            return ""

    # Host.
    #
    # A caller-supplied target_host used to win outright while the admin
    # password and API token below still came from the *customer's* keyring,
    # so pointing a deploy at an attacker-controlled address exfiltrated a
    # stored firewall credential. Reading those secrets directly needs admin
    # plus customer access and is activity-logged; deploy needs only
    # technician, which made this the cheaper route to the same material.
    #
    # The guard keys on whether a *stored credential* will be used, not on
    # whether a host happens to be configured. Those are independent:
    # /fortigate/save writes FortiGateHost unconditionally from the request
    # body, so an omitted "host" field blanks it while the keyring secrets
    # stay — and a host-keyed check would then wave the request through.
    #
    # Only the body-supplied override is constrained. The wizard's own Step 1
    # "Target host" is the operator typing an address into the form in front
    # of them, which is the documented precedence and not the exfiltration
    # path; constraining it too broke provisioning a replacement unit on its
    # management IP.
    configured = (active_cfg.get("FortiGateHost") or "").strip()
    wizard_host = (customer_step.get("target_host") or "").strip()
    requested = (target_host or "").strip()
    host = requested or wizard_host or configured or ""

    stored_secret_in_play = bool(
        (not customer_step.get("api_token") and _from_keyring("fortigate_api_token"))
        or (
            not customer_step.get("password")
            and not security_step.get("admin_password")
            and _from_keyring("fortigate_admin_password")
        )
    )
    # A stored credential belongs to the customer's configured device and must
    # not travel to any other address — whether that address came from the
    # deploy body or from the wizard's own "target host" field. The earlier
    # guard constrained only the body override and exempted the wizard field,
    # which reopened the exfiltration path: a Step 1 target_host pointed at an
    # attacker's IP still received the customer's stored FortiGate token
    # (SR-001 #5). Compared case-insensitively — hostnames are not case
    # sensitive, and a refusal over "FW.ACME.NO" vs "fw.acme.no" is false.
    #
    # For a genuine replacement or bootstrap unit on a different IP, the
    # operator supplies an explicit API token or admin password in the wizard;
    # that flips stored_secret_in_play to False and the deploy proceeds
    # (SR-001 #6).
    if stored_secret_in_play and host:
        if not configured:
            raise ValueError(
                "Kan ikke deploye med kundens lagrede FortiGate-legitimasjon når "
                "kunden ikke har en konfigurert adresse. Sett kundens FortiGate-"
                "adresse først, eller oppgi eksplisitt legitimasjon i wizarden."
            )
        if host.casefold() != configured.casefold():
            raise ValueError(
                f"Kan ikke deploye til {host} med kundens lagrede FortiGate-"
                f"legitimasjon: kunden er konfigurert med {configured}. For en "
                f"erstatnings-/bootstrap-enhet, oppgi eksplisitt API-token eller "
                f"admin-passord i wizarden."
            )

    # Port — bootstrap hardens admin-sport to 8443, that's the default
    raw_port = customer_step.get("port") or active_cfg.get("FortiGatePort") or 8443
    try:
        port = int(raw_port)
    except (TypeError, ValueError):
        port = 8443

    # VDOM
    vdom = customer_step.get("vdom") or active_cfg.get("FortiGateVDOM") or "root"

    # SSL verify
    verify_ssl = customer_step.get("verify_ssl")
    if verify_ssl is None:
        verify_ssl = active_cfg.get("FortiGateVerifySSL", False)
    verify_ssl = bool(verify_ssl)

    # API token
    api_token = customer_step.get("api_token") or _from_keyring("fortigate_api_token") or ""

    # SSH admin user — wizard "username" → keyring → "admin"
    admin_user = (
        customer_step.get("username")
        or active_cfg.get("FortiGateAdminUser")
        or _from_keyring("fortigate_admin_user")
        or "admin"
    )

    # SSH admin password — wizard step 1 "password" → step 4 "admin_password" → keyring
    admin_password = (
        customer_step.get("password")
        or security_step.get("admin_password")
        or _from_keyring("fortigate_admin_password")
        or ""
    )

    return {
        "host": host,
        "port": port,
        "vdom": vdom,
        "verify_ssl": verify_ssl,
        "api_token": api_token,
        "admin_user": admin_user,
        "admin_password": admin_password,
        "customer_id": cust_id,
        "customer_name": active_cfg.get("CustomerName", ""),
    }


# ── Deploy results ───────────────────────────────────────────────────────────
#
# deploy_config used to answer {"ok": True} whatever happened on the device.
# The REST branch's own verdict sat two levels down where only the route dug
# for it, the SSH branch counted the lines it sent rather than the ones the
# device accepted, and the REST deploy read any FortiOS 500 as "already
# exists" and papered over it with a PUT. "ok" could not tell a configured
# firewall from a half-configured one. Every deploy now returns the typed
# result below: each step applied, skipped or failed with the reason, steps
# after a failure marked as not run, and ok only when every required step got
# through.


class StepStatus(StrEnum):
    """What one step did to the device."""

    # The step did its job: the device took the change (for a step that only
    # reads or checks, the read or check succeeded).
    APPLIED = "applied"
    # Nothing to change: already in place, or not applicable to this device.
    SKIPPED = "skipped"
    # The device refused it, or never answered.
    FAILED = "failed"
    # An earlier required step failed, so this one never started.
    NOT_RUN = "not_run"


_DONE = frozenset({StepStatus.APPLIED, StepStatus.SKIPPED})
_PREFLIGHT = "Kontroll før deploy"


def _clip(text: str, limit: int = 300) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


@dataclass
class Operation:
    """One call against the device inside a step."""

    label: str
    status: StepStatus
    reason: str = ""

    def as_dict(self) -> dict:
        out: dict = {"step": self.label, "ok": self.status in _DONE, "status": self.status.value}
        if self.reason:
            out["reason"] = self.reason
            if self.status not in _DONE:
                # The wizard prints "error" in red beside the step.
                out["error"] = self.reason
        return out


@dataclass
class StepResult:
    """One named step of a deploy, and the calls it made."""

    name: str
    label: str
    status: StepStatus
    reason: str = ""
    required: bool = True
    # False for steps that only check or read: they never change the device.
    writes: bool = True
    operations: list[Operation] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "status": self.status.value,
            "reason": self.reason,
            "required": self.required,
            "operations": [op.as_dict() for op in self.operations],
        }


@dataclass
class DeployResult:
    """What one deploy did to one device, step by step."""

    target: str
    method: str
    steps: list[StepResult] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """Every required step got through. A deploy that ran nothing is not ok."""
        return bool(self.steps) and all(s.status in _DONE for s in self.steps if s.required)

    @property
    def stopped_at(self) -> StepResult | None:
        """The required step that failed and ended the run, if one did."""
        return next((s for s in self.steps if s.required and s.status is StepStatus.FAILED), None)

    @property
    def warnings(self) -> list[StepResult]:
        """Optional steps that failed without stopping the run."""
        return [s for s in self.steps if not s.required and s.status is StepStatus.FAILED]

    @property
    def applied_steps(self) -> list[str]:
        """The steps that changed the device: what is now on it."""
        return [s.name for s in self.steps if s.writes and s.status is StepStatus.APPLIED]

    @property
    def error(self) -> str:
        step = self.stopped_at
        return f"{step.label}: {step.reason}" if step else ""

    def details(self) -> list[dict]:
        """One row per call, the flat list the wizard renders."""
        rows: list[dict] = []
        for step in self.steps:
            if step.operations:
                rows.extend(op.as_dict() for op in step.operations)
            else:
                rows.append(Operation(step.label, step.status, step.reason).as_dict())
        return rows

    def summary(self) -> str:
        done = sum(1 for s in self.steps if s.status in _DONE)
        text = f"{done}/{len(self.steps)} steg OK"
        stop = self.stopped_at
        if stop is not None:
            text += f", stoppet ved «{stop.label}»: {_clip(stop.reason)}"
            not_run = sum(1 for s in self.steps if s.status is StepStatus.NOT_RUN)
            if not_run:
                text += f" ({not_run} steg ikke kjørt)"
        for warn in self.warnings:
            text += f"; valgfritt steg feilet, «{warn.label}»: {_clip(warn.reason)}"
        return text

    def as_dict(self) -> dict:
        rows = self.details()
        stop = self.stopped_at
        return {
            "ok": self.ok,
            "target": self.target,
            "method": self.method,
            "error": self.error,
            "stopped_at": stop.name if stop else None,
            "applied_steps": self.applied_steps,
            "steps": [s.as_dict() for s in self.steps],
            # The per-call view and its counts, which the wizard renders.
            "details": rows,
            "total": len(rows),
            "success": sum(1 for r in rows if r["ok"]),
            "failed": sum(1 for r in rows if r["status"] == StepStatus.FAILED.value),
            "not_run": sum(1 for r in rows if r["status"] == StepStatus.NOT_RUN.value),
            **self.extra,
        }


@dataclass
class DeployReport:
    """The answer to one deploy request: each device's result, or why none was tried."""

    results: dict[str, DeployResult] = field(default_factory=dict)
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and bool(self.results) and all(r.ok for r in self.results.values())

    @property
    def changed_device(self) -> bool:
        """Whether any device took any change, failed run or not."""
        return any(r.applied_steps for r in self.results.values())

    def summary(self) -> str:
        if self.error:
            return self.error
        return "; ".join(f"{target}: {r.summary()}" for target, r in self.results.items())

    def as_dict(self) -> dict:
        error = self.error or next(
            (f"{target}: {r.error}" for target, r in self.results.items() if r.error), ""
        )
        return {
            "ok": self.ok,
            "error": error,
            "results": {target: r.as_dict() for target, r in self.results.items()},
        }


def _refused(name: str, label: str, reason: str) -> StepResult:
    """A check that failed before anything was sent to the device."""
    return StepResult(name, label, StepStatus.FAILED, reason, writes=False)


# ── Step runner ──────────────────────────────────────────────────────────────


class _StepFailed(Exception):
    """A call inside a step failed; the runner records the step and stops."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _Recorder:
    """The calls the current step makes, and how each went."""

    def __init__(self) -> None:
        self.ops: list[Operation] = []

    def applied(self, label: str, reason: str = "") -> None:
        self.ops.append(Operation(label, StepStatus.APPLIED, reason))

    def skipped(self, label: str, reason: str) -> None:
        self.ops.append(Operation(label, StepStatus.SKIPPED, reason))

    def fail(self, label: str, reason: str) -> NoReturn:
        self.ops.append(Operation(label, StepStatus.FAILED, reason))
        raise _StepFailed(f"{label}: {reason}")


@dataclass(frozen=True)
class _Step:
    """A named unit of a deploy: one small function of (device, plan)."""

    name: str
    label: str
    run: Callable[[Any, Any], Awaitable[None]]
    required: bool = True
    writes: bool = True


async def _run_steps(steps: Sequence[_Step], device: _Recorder, plan: Any) -> list[StepResult]:
    """Run *steps* in order, stopping at the first required step that fails.

    The steps after the stop are reported as not run, so the result always
    lists every step and an operator can see how far the device got. An
    optional step that fails is recorded and the run goes on.
    """
    results: list[StepResult] = []
    stop: _Step | None = None
    for step in steps:
        if stop is not None:
            results.append(
                StepResult(
                    step.name,
                    step.label,
                    StepStatus.NOT_RUN,
                    f"Ikke kjørt fordi «{stop.label}» feilet",
                    step.required,
                    step.writes,
                )
            )
            continue
        device.ops = []
        failure = ""
        try:
            await step.run(device, plan)
        except _StepFailed as exc:
            failure = exc.reason
        except Exception as exc:
            # A bug or an answer nobody expected must not lose the record of
            # what the earlier steps already did to the device.
            logger.exception("Provisioning step %s crashed", step.name)
            failure = f"Uventet feil: {type(exc).__name__}: {exc}"
            device.ops.append(Operation(step.label, StepStatus.FAILED, failure))
        ops = device.ops
        if failure:
            status, reason = StepStatus.FAILED, failure
        elif any(op.status is StepStatus.APPLIED for op in ops):
            status, reason = StepStatus.APPLIED, ""
        else:
            status = StepStatus.SKIPPED
            reason = "; ".join(op.reason for op in ops if op.reason) or "Ingenting å endre"
        results.append(
            StepResult(step.name, step.label, status, reason, step.required, step.writes, ops)
        )
        if status is StepStatus.FAILED and step.required:
            stop = step
    return results


# ── Deploy entry point ───────────────────────────────────────────────────────


_DEPLOY_METHODS = ("ssh", "rest")


async def deploy_config(
    session_id: str,
    method: str = "ssh",
    target_host: str = "",
) -> DeployReport:
    """Deploy the generated config to the session's devices via SSH or REST API.

    Returns a DeployReport: per device, every step and what it did. Its ok is
    true only when every device got every required step.
    """
    from app.core.exceptions import ValidationError

    if method not in _DEPLOY_METHODS:
        # An unknown method used to run nothing and still answer ok.
        raise ValidationError(f"Ukjent deploy-metode «{method}». Bruk «ssh» eller «rest».")

    session = _sessions.get(session_id)
    if not session or not session.get("generated"):
        raise ValidationError(
            "Ingen generert konfigurasjon å deploye. Generer konfigurasjonen først."
        )

    configs = session["generated"]
    steps = session["steps"]
    customer = steps.get(1, {}) or {}

    conn = _resolve_fortigate_conn(steps, target_host, customer_id=session.get("customer_id", ""))

    if not conn["host"]:
        return DeployReport(
            error="Ingen FortiGate-host konfigurert (verken i wizard, kunde-config eller mål)"
        )

    logger.info(
        "Deploy via %s to %s:%d (vdom=%s, customer=%s, has_token=%s, has_pw=%s)",
        method,
        conn["host"],
        conn["port"],
        conn["vdom"],
        conn["customer_name"] or "(none)",
        bool(conn["api_token"]),
        bool(conn["admin_password"]),
    )

    results: dict[str, DeployResult] = {}
    if method == "ssh" and "fortigate_cli" in configs:
        results["fortigate"] = await _deploy_via_ssh(
            conn,
            configs["fortigate_cli"],
            new_admin_password=(steps.get(4, {}) or {}).get("admin_password", ""),
        )
    elif method == "rest":
        results["fortigate"] = await _deploy_via_rest(
            conn["host"],
            conn["api_token"],
            steps,
            conn=conn,
        )

    if "unifi_json" in configs:
        results["unifi"] = _unifi_result(
            await _deploy_unifi(
                conn["host"],
                configs["unifi_json"],
                customer,
                customer_id=session.get("customer_id", ""),
            )
        )

    if not results:
        return DeployReport(
            error=f"Ingenting å deploye med metoden «{method}» for denne konfigurasjonen."
        )
    return DeployReport(results=results)


def _unifi_result(raw: dict) -> DeployResult:
    """_deploy_unifi's answer in the same typed shape as the FortiGate result."""
    ops = [
        Operation(
            str(row.get("step", "")),
            StepStatus.APPLIED if row.get("ok") else StepStatus.FAILED,
            "" if row.get("ok") else str(row.get("error") or "Ukjent feil"),
        )
        for row in (raw.get("steps") or raw.get("partial_results") or [])
    ]
    if raw.get("error"):
        ops.append(Operation("UniFi-kontroller", StepStatus.FAILED, str(raw["error"])))
        status, reason = StepStatus.FAILED, str(raw["error"])
    else:
        failed = [op for op in ops if op.status is StepStatus.FAILED]
        if failed or not raw.get("ok"):
            status = StepStatus.FAILED
            reason = failed[0].reason if failed else "Ukjent feil"
        elif ops:
            status, reason = StepStatus.APPLIED, ""
        else:
            status, reason = StepStatus.SKIPPED, "Ingen nettverk i konfigurasjonen"
    step = StepResult("unifi_networks", "UniFi-nettverk", status, reason, operations=ops)
    return DeployResult("unifi", "api", [step])


# ── SSH (CLI) Deployment ─────────────────────────────────────────────────────
#
# Two things made the SSH deploy report success it had not earned. A line the
# allowlist refused was logged and skipped, and the deploy went on; and the
# device's answer to each line was never read, so a line FortiOS rejected
# counted as sent and the result was ok with a command count.
#
# Now the whole CLI is checked before anything is sent (a refused line fails
# the deploy with nothing sent), and the device's answer to each command is
# read for FortiOS's error output.
#
# Each top-level "config ... end" block goes as one command. SshSession.exec
# opens a new channel per call, and a FortiOS config context does not carry
# from one channel to the next, so a lone "set" line arrives at the top level
# where FortiOS refuses it. Whole blocks are how the rest of the app talks to
# FortiOS over SSH (fortigate_api.generate_api_token sends its "config system
# api-user" block the same way).

# Only FortiGate config commands are sent: a keyword and its arguments, or one
# of the bare block keywords.
_CLI_ALLOWED_PREFIXES = ("config ", "edit ", "set ", "append ", "unset ", "get ", "show ")
_CLI_ALLOWED_WORDS = frozenset({"next", "end"})

# How FortiOS says a CLI line was refused. It reports through the output, not
# reliably through the exit status: "Command fail. Return code -61", "command
# parse error before 'x'", "value parse error before 'x'", "Unknown action 0",
# "entry not found in datasource", "node_check_object fail! for name ...",
# "Attribute 'x' MUST be set.".
_CLI_ERROR = re.compile(
    r"command fail|parse error|unknown action|entry not found|node_check_object fail"
    r"|return code -\d+|must be set",
    re.IGNORECASE,
)
_SSH_BLOCK_TIMEOUT = 30
_PASSWORD_MASK = "********"
_NOTHING_SENT = "Ingenting er sendt til enheten."


def _cli_line_allowed(line: str) -> bool:
    return line in _CLI_ALLOWED_WORDS or line.startswith(_CLI_ALLOWED_PREFIXES)


def _cli_preflight(lines: list[str], new_admin_password: str) -> str:
    """Why this CLI must not be sent, or "" when it may."""
    if not lines:
        return f"Konfigurasjonen inneholder ingen kommandoer. {_NOTHING_SENT}"
    refused = [line for line in lines if not _cli_line_allowed(line)]
    if refused:
        shown = ", ".join(f"«{_clip(line, 60)}»" for line in refused[:5])
        more = f" og {len(refused) - 5} til" if len(refused) > 5 else ""
        return (
            f"{len(refused)} linje(r) er ikke tillatt over SSH: {shown}{more}. "
            f"Fjern dem fra konfigurasjonen. {_NOTHING_SENT}"
        )
    depth = 0
    for line in lines:
        if line.startswith("config "):
            depth += 1
        elif line == "end":
            depth -= 1
            if depth < 0:
                return f"Konfigurasjonen har en «end» uten «config» foran. {_NOTHING_SENT}"
    if depth:
        return f"Konfigurasjonen har en «config» uten avsluttende «end». {_NOTHING_SENT}"
    if any(_PASSWORD_MASK in line for line in lines):
        if not new_admin_password:
            return (
                "Konfigurasjonen setter et nytt admin-passord, men wizarden har ikke "
                f"noe admin-passord i steg 4. {_NOTHING_SENT}"
            )
        if any(c in new_admin_password for c in '"\\\r\n'):
            return (
                "Admin-passordet kan ikke inneholde anførselstegn, omvendt skråstrek "
                f"eller linjeskift når det settes over SSH. {_NOTHING_SENT}"
            )
    return ""


def _cli_blocks(lines: list[str]) -> list[list[str]]:
    """Split checked CLI into top-level units: each config...end, or a lone line."""
    blocks: list[list[str]] = []
    current: list[str] = []
    depth = 0
    for line in lines:
        current.append(line)
        if line.startswith("config "):
            depth += 1
        elif line == "end":
            depth -= 1
        if depth <= 0:
            blocks.append(current)
            current, depth = [], 0
    if current:
        blocks.append(current)
    return blocks


def _cli_refusal(out) -> str:
    """The device's refusal in *out*, or "" when it took the command."""
    text = "\n".join(part for part in (out.stdout, out.stderr) if part)
    hits = [line.strip() for line in text.splitlines() if _CLI_ERROR.search(line)]
    if hits:
        return _clip(" / ".join(hits))
    # FortiOS does not reliably send an exit status (SshSession then reports
    # -1), so only a positive code counts as a refusal on its own.
    if out.exit_code > 0:
        detail = f": {_clip(text)}" if text.strip() else ""
        return f"avsluttet med kode {out.exit_code}{detail}"
    return ""


class _CliDevice(_Recorder):
    """The FortiGate side of an SSH deploy."""

    def __init__(self, ssh, new_admin_password: str) -> None:
        super().__init__()
        self.ssh = ssh
        self.secret = new_admin_password
        self.lines_applied = 0

    def _redact(self, text: str) -> str:
        return text.replace(self.secret, _PASSWORD_MASK) if self.secret else text

    async def send_block(self, block: list[str], label: str) -> None:
        script = "\n".join(
            line.replace(_PASSWORD_MASK, self.secret) if self.secret else line for line in block
        )
        try:
            out = await self.ssh.exec(script, timeout=_SSH_BLOCK_TIMEOUT)
        except Exception as exc:
            self.fail(label, self._redact(f"Ingen bekreftelse fra enheten: {exc}"))
        refusal = _cli_refusal(out)
        if refusal:
            self.fail(
                label,
                self._redact(
                    f"Enheten avviste en linje: {refusal}. "
                    "Andre linjer i samme blokk kan være utført."
                ),
            )
        self.lines_applied += len(block)
        self.applied(label, f"{len(block)} linjer")


def _cli_step(index: int, block: list[str]) -> _Step:
    label = f"Blokk {index}: {block[0]}"

    async def run(device: _CliDevice, _plan: Any) -> None:
        await device.send_block(block, label)

    return _Step(f"cli_{index:02d}", label, run)


async def _deploy_via_ssh(conn: dict, cli: str, new_admin_password: str = "") -> DeployResult:
    """Send the generated CLI over SSH, block by block, checking every answer.

    The masked admin password in the CLI is the new password from the wizard's
    security step, the one that made the generator emit that block. It used to
    be filled from the login password when one was typed in step 1, which left
    the admin password unchanged and the deploy reporting success.
    """
    result = DeployResult("fortigate", "ssh")
    if not conn["admin_password"]:
        result.steps.append(
            _refused(
                "preflight",
                _PREFLIGHT,
                "Ingen admin-passord tilgjengelig (verken i wizard eller keyring)",
            )
        )
        return result

    lines = [line.strip() for line in cli.strip().splitlines()]
    lines = [line for line in lines if line and not line.startswith("#")]
    problem = _cli_preflight(lines, new_admin_password)
    if problem:
        result.steps.append(_refused("preflight", _PREFLIGHT, problem))
        return result
    blocks = _cli_blocks(lines)
    result.steps.append(
        StepResult(
            "preflight",
            _PREFLIGHT,
            StepStatus.APPLIED,
            f"{len(lines)} linjer i {len(blocks)} blokker",
            writes=False,
        )
    )

    try:
        from app.services.ssh_connection import SshSession

        ssh_conn = await SshSession.connect(
            conn["host"],
            username=conn["admin_user"],
            password=conn["admin_password"],
        )
    except Exception as exc:
        result.steps.append(_refused("connect", "SSH-tilkobling", str(exc) or type(exc).__name__))
        return result
    result.steps.append(
        StepResult(
            "connect",
            "SSH-tilkobling",
            StepStatus.APPLIED,
            f"{conn['admin_user']}@{conn['host']}",
            writes=False,
        )
    )

    async with ssh_conn as ssh:
        device = _CliDevice(ssh, new_admin_password)
        steps = [_cli_step(i, block) for i, block in enumerate(blocks, 1)]
        result.steps.extend(await _run_steps(steps, device, None))
    result.extra["commands"] = device.lines_applied
    return result


# ── UniFi Deployment ─────────────────────────────────────────────────────────


async def _deploy_unifi(host: str, unifi_json: str, customer: dict, customer_id: str = "") -> dict:
    """Deploy generated UniFi config to a controller via REST API.

    Creates networks (VLANs) via /api/s/{site}/rest/networkconf.

    Credential resolution order:
      1. Per-customer credentials from keyring (UniFiHost + unifi_username/password)
      2. Global controller settings from app settings
      3. Site Manager API key → resolve WAN IP for target host

    A customer's *stored* per-customer credentials only ever go to that
    customer's configured UniFiHost — never to a caller-supplied provisioning
    target — the same boundary the FortiGate path enforces (SR-001 #5). The
    customer is the session's bound one; a session bound to none has none.
    """
    from app.core.config import load_app_settings
    from app.core.credentials import get_secret
    from app.core.customer import CustomerManager
    from app.modules.unifi_audit.client import UniFiControllerClient

    cust = CustomerManager.get_customer(customer_id) if customer_id else None
    cust_id = cust.get("_id", "") if cust else ""
    settings = load_app_settings()

    # --- Resolve controller host + credentials ---
    unifi_host = ""
    username = ""
    password = ""
    is_unifi_os = False
    site = "default"
    configured_host = ""
    stored_creds = False  # True once we resolve the customer's keyring secret

    # 1. Per-customer credentials
    if cust:
        configured_host = cust.get("UniFiHost", "")
        _u = get_secret(cust_id, "unifi_username") or ""
        _p = get_secret(cust_id, "unifi_password") or ""
        if _u and _p:
            username, password = _u, _p
            stored_creds = True
        unifi_host = configured_host
        is_unifi_os = cust.get("UniFiIsUniFiOS", False)
        site = cust.get("UniFiSite", "default")

    # 2. Global controller settings from app settings
    if not (unifi_host and username and password):
        ctrl_host = settings.get("unifi_controller_host", "")
        ctrl_user = settings.get("unifi_controller_username", "")
        ctrl_pass = settings.get("unifi_controller_password", "")
        if ctrl_host and ctrl_user and ctrl_pass:
            unifi_host = unifi_host or ctrl_host
            username = username or ctrl_user
            password = password or ctrl_pass

    # 3. Site Manager API key → resolve WAN IP for host
    if not unifi_host:
        api_key = settings.get("unifi_site_manager_api_key", "")
        if api_key:
            try:
                from app.services.unifi_api import site_manager_list_sites

                sm_result = await site_manager_list_sites(token=api_key)
                if sm_result.get("ok"):
                    # Match by customer name or use first online host
                    cust_name = (customer.get("name", "") or "").lower()
                    for s in sm_result.get("sites", []):
                        if s.get("wan_ip") and (
                            (cust_name and cust_name in s.get("name", "").lower())
                            or s.get("status") == "online"
                        ):
                            unifi_host = s["wan_ip"]
                            break
            except Exception as e:
                logger.warning("Site Manager lookup failed: %s", e)

    # A stored per-customer credential must not travel to the caller-supplied
    # provisioning target (SR-001 #5). Only fall back to `host` when no stored
    # credential is in play, and refuse outright if a stored credential would
    # reach anything but the customer's configured UniFiHost.
    if not stored_creds:
        unifi_host = unifi_host or host
    if stored_creds:
        if not configured_host:
            return {
                "ok": False,
                "error": (
                    "Kundens UniFi-host er ikke konfigurert — kan ikke bruke "
                    "lagret legitimasjon mot en oppgitt adresse. Sett UniFi-host "
                    "først, eller oppgi eksplisitt legitimasjon."
                ),
            }
        if unifi_host.casefold() != configured_host.casefold():
            return {
                "ok": False,
                "error": (
                    f"Kan ikke sende kundens lagrede UniFi-legitimasjon til "
                    f"{unifi_host}: kunden er konfigurert med {configured_host}."
                ),
            }

    if not unifi_host:
        return {
            "ok": False,
            "error": "No UniFi controller host found — configure in Settings or per customer",
        }
    if not (username and password):
        return {
            "ok": False,
            "error": "No UniFi credentials available — set per customer or in Settings > UniFi Controller",
        }

    try:
        config = json.loads(unifi_json) if isinstance(unifi_json, str) else unifi_json
    except (json.JSONDecodeError, TypeError) as e:
        return {"ok": False, "error": f"Invalid UniFi JSON config: {e}"}

    client = UniFiControllerClient(
        host=unifi_host,
        username=username,
        password=password,
        is_unifi_os=is_unifi_os,
    )

    results: list[dict] = []
    try:
        await client._login()

        # Deploy networks (LAN + VLANs)
        for net in config.get("networks", []):
            payload = {
                "name": net.get("name", "Unnamed"),
                "purpose": net.get("purpose", "corporate"),
                "ip_subnet": net.get("subnet", ""),
                "dhcpd_enabled": net.get("dhcp_enabled", True),
                "domain_name": net.get("domain_name", ""),
            }
            if net.get("vlan_id"):
                payload["vlan"] = str(net["vlan_id"])
                payload["vlan_enabled"] = True
            if net.get("dhcp_start"):
                payload["dhcpd_start"] = net["dhcp_start"]
            if net.get("dhcp_stop"):
                payload["dhcpd_stop"] = net["dhcp_stop"]

            resp = await client._post(
                f"/api/s/{site}/rest/networkconf",
                payload,
            )
            meta = resp.get("meta", {})
            if meta.get("rc") == "ok" or resp.get("data"):
                results.append({"step": f"network:{net['name']}", "ok": True})
            else:
                results.append(
                    {
                        "step": f"network:{net['name']}",
                        "ok": False,
                        "error": meta.get("msg", "Unknown error"),
                    }
                )

        await client._logout()
    except Exception as e:
        return {"ok": False, "error": str(e), "partial_results": results}

    failed = [r for r in results if not r["ok"]]
    return {
        "ok": len(failed) == 0,
        "steps": results,
        "networks_created": len(results) - len(failed),
        "errors": len(failed),
    }


# ── Config Generators ────────────────────────────────────────────────────────


def _sanitize_fortigate_name(name: str) -> str:
    """Replace non-ASCII chars with ASCII equivalents for FortiGate."""
    import unicodedata

    # Explicit Nordic mappings (NFKD decomposition doesn't handle ø/Ø/æ/Æ)
    _map = {"ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "å": "a", "Å": "A"}
    mapped = "".join(_map.get(c, c) for c in name)
    nfkd = unicodedata.normalize("NFKD", mapped)
    return nfkd.encode("ascii", "ignore").decode("ascii")


def _cidr_to_mask(cidr: str) -> str:
    """Convert '10.25.0.0/24' to '10.25.0.0 255.255.255.0'. Pass-through if no /."""
    if "/" not in cidr:
        return cidr + " 255.255.255.0"
    network, bits = cidr.rsplit("/", 1)
    try:
        prefix = int(bits)
    except ValueError:
        return network + " 255.255.255.0"
    mask_int = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
    mask = ".".join(str((mask_int >> (8 * i)) & 0xFF) for i in range(3, -1, -1))
    return f"{network} {mask}"


def _subnet_gateway(cidr: str) -> str:
    """Return the .1 gateway address for a subnet: '10.25.10.0/24' → '10.25.10.1'."""
    network = cidr.split("/")[0]
    parts = network.rsplit(".", 1)
    return f"{parts[0]}.1"


def _generate_fortigate_cli(
    customer: dict,
    network: dict,
    services: dict,
    security: dict,
) -> str:
    """Generate FortiGate CLI commands following CIS benchmarks."""
    raw_name = customer.get("name", "FW")
    hostname = _sanitize_fortigate_name(raw_name).replace(" ", "-")[:35]

    # Number of physical ports on the FortiGate
    fg_ports = int(network.get("fg_ports", 10))
    # Last port = dedicated MGMT access (untagged, same subnet as VLAN99)
    mgmt_phys_port = f"port{fg_ports}"

    # FortiOS timezone IDs: 26 = Brussels/Copenhagen/Madrid/Paris (CET, Norway).
    # Override via services["fortigate_timezone_id"] if customer is in another TZ.
    tz_id = int(services.get("fortigate_timezone_id", 26))

    lines: list[str] = [
        "# FortiGate Configuration",
        f"# Customer: {raw_name}",
        f"# Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        "#",
        f"# MGMT access port: {mgmt_phys_port} — plug laptop here, get IP via DHCP",
        "# FortiGate admin: https://<mgmt-port-ip>:8443",
        "",
        "# ━━ SYSTEM HARDENING ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "config system global",
        f'    set hostname "{hostname}"',
        f"    set timezone {tz_id}",
        "    set admin-sport 8443",
        "    set admintimeout 15",
        "    set admin-ssh-grace-time 60",
        "    set admin-ssh-v2 enable",
        "    set admin-scp enable",
        "    set strong-crypto enable",
        "    set auto-auth-extension-device disable",
        "    set usb-auto-install disable",
        "end",
        "",
        "# Pre-login banner (CIS)",
        "config system replacemsg admin pre_admin-disclaimer-text",
        '    set buffer "ADVARSEL: Uautorisert tilgang er forbudt. All aktivitet logges og overvakes. Ved a fortsette aksepterer du vilkarene for bruk."',
        "end",
        "",
        "config system global",
        "    set pre-login-banner enable",
        "end",
        "",
    ]

    # Admin password
    if security.get("admin_password"):
        lines.extend(
            [
                "config system admin",
                "    edit admin",
                '        set password "********"',  # actual password injected at deploy time
                "    next",
                "end",
                "",
            ]
        )

    # Password policy (CIS)
    lines.extend(
        [
            "config system password-policy",
            "    set status enable",
            "    set min-length 12",
            "    set min-upper-case-letter 1",
            "    set min-lower-case-letter 1",
            "    set min-number 1",
            "    set min-non-alphanumeric 1",
            "    set expire-status enable",
            "    set expire-day 90",
            "end",
            "",
        ]
    )

    # NOTE: WAN interface is NOT configured here — changing WAN risks bricking
    # the device remotely.  WAN must be set up manually or via console.

    # LAN
    lan_subnet = network.get("lan_subnet", "192.168.1.0/24")
    lan_gw = _subnet_gateway(lan_subnet)
    lan_prefix = lan_subnet.split("/")[-1] if "/" in lan_subnet else "24"
    lan_mask_int = (0xFFFFFFFF << (32 - int(lan_prefix))) & 0xFFFFFFFF
    lan_mask = ".".join(str((lan_mask_int >> (8 * i)) & 0xFF) for i in range(3, -1, -1))

    lines.append("# LAN & VLAN Interfaces")
    lines.append("config system interface")
    lines.extend(
        [
            "    edit port2",
            "        set alias LAN",
            "        set mode static",
            f"        set ip {lan_gw} {lan_mask}",
            "        set allowaccess ping https ssh",
            "    next",
        ]
    )

    # VLANs — uniform interface config; admin access only via dedicated MGMT port.
    for vlan in network.get("vlans", []):
        vid = vlan.get("id", 10)
        vlan_subnet = vlan.get("subnet", "10.0.0.0/24")
        vlan_gw = _subnet_gateway(vlan_subnet)
        vlan_alias = _sanitize_fortigate_name(vlan.get("name", "VLAN"))
        lines.extend(
            [
                f"    edit VLAN{vid}",
                "        set vdom root",
                "        set interface port2",
                f"        set vlanid {vid}",
                f'        set alias "{vlan_alias}"',
                "        set mode static",
                f"        set ip {vlan_gw} 255.255.255.0",
                "        set allowaccess ping",
                "    next",
            ]
        )

    # Dedicated MGMT physical port — own /24, only path with admin access (HTTPS/SSH).
    # Default: derive from LAN by adding 100 to third octet (e.g. 10.25.0.0/24 → 10.25.100.0/24).
    # Override via network["mgmt_phys_subnet"].
    if network.get("mgmt_phys_subnet"):
        mgmt_phys_subnet = network["mgmt_phys_subnet"]
    else:
        lan_parts = lan_subnet.split("/")[0].split(".")
        mgmt_phys_subnet = f"{lan_parts[0]}.{lan_parts[1]}.{(int(lan_parts[2]) + 100) % 256}.0/24"
    mgmt_phys_gw = _subnet_gateway(mgmt_phys_subnet)
    mgmt_phys_net_prefix = mgmt_phys_subnet.split("/")[0].rsplit(".", 1)[0]
    lines.extend(
        [
            f"    edit {mgmt_phys_port}",
            "        set alias MGMT-ACCESS",
            "        set mode static",
            f"        set ip {mgmt_phys_gw} 255.255.255.0",
            "        set allowaccess ping https ssh fgfm",
            '        set description "Local MGMT port — laptop access via DHCP, isolated /24"',
            "    next",
        ]
    )
    lines.extend(["end", ""])

    # ── DHCP servers ─────────────────────────────────────────────────────
    dhcp_enabled = services.get("dhcp_enabled", True)
    if dhcp_enabled:
        dhcp_id = 1
        lines.append("# DHCP Servers")

        # LAN DHCP
        lan_net_parts = lan_subnet.split("/")[0].rsplit(".", 1)
        lines.extend(
            [
                "config system dhcp server",
                f"    edit {dhcp_id}",
                "        set interface port2",
                f"        set default-gateway {lan_gw}",
                f"        set netmask {lan_mask}",
                "        config ip-range",
                "            edit 1",
                f"                set start-ip {lan_net_parts[0]}.100",
                f"                set end-ip {lan_net_parts[0]}.250",
                "            next",
                "        end",
                f"        set dns-server1 {lan_gw}",
                "        set lease-time 86400",
                "    next",
            ]
        )
        dhcp_id += 1

        # Per-VLAN DHCP — uniform 24h lease, range .100-.250
        for vlan in network.get("vlans", []):
            vid = vlan.get("id", 10)
            vlan_subnet = vlan.get("subnet", "10.0.0.0/24")
            vlan_gw = _subnet_gateway(vlan_subnet)
            vlan_net_parts = vlan_subnet.split("/")[0].rsplit(".", 1)
            lines.extend(
                [
                    f"    edit {dhcp_id}",
                    f"        set interface VLAN{vid}",
                    f"        set default-gateway {vlan_gw}",
                    "        set netmask 255.255.255.0",
                    "        config ip-range",
                    "            edit 1",
                    f"                set start-ip {vlan_net_parts[0]}.100",
                    f"                set end-ip {vlan_net_parts[0]}.250",
                    "            next",
                    "        end",
                    f"        set dns-server1 {vlan_gw}",
                    "        set lease-time 86400",
                    "    next",
                ]
            )
            dhcp_id += 1

        # DHCP for the local MGMT port (port10) — short lease, small range.
        lines.extend(
            [
                f"    edit {dhcp_id}",
                f"        set interface {mgmt_phys_port}",
                f"        set default-gateway {mgmt_phys_gw}",
                "        set netmask 255.255.255.0",
                "        config ip-range",
                "            edit 1",
                f"                set start-ip {mgmt_phys_net_prefix}.100",
                f"                set end-ip {mgmt_phys_net_prefix}.150",
                "            next",
                "        end",
                f"        set dns-server1 {mgmt_phys_gw}",
                "        set lease-time 3600",
                "    next",
            ]
        )
        dhcp_id += 1

        lines.extend(["end", ""])

    # DNS (FortiGate as DNS forwarder for clients)
    dns = services.get("dns_servers", ["1.1.1.1", "1.0.0.1"])
    lines.extend(
        [
            "# ━━ DNS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
            "config system dns",
            f"    set primary {dns[0] if dns else '1.1.1.1'}",
            f"    set secondary {dns[1] if len(dns) > 1 else '1.0.0.1'}",
            "    set dns-over-tls enforce",
            "end",
            "",
            "# DNS Database — FortiGate forwards DNS for all internal clients",
            "config system dns-database",
            f'    edit "{hostname}"',
            # ".local" is reserved for mDNS/Bonjour and breaks Apple/Linux discovery.
            # Use customer-provided domain, else "<hostname>.lan" (RFC-safe internal TLD).
            f'        set domain "{customer.get("domain") or f"{hostname.lower()}.lan"}"',
            "        set type master",
            "        set view shadow",
            "        set ttl 600",
            "        set authoritative enable",
            "    next",
            "end",
            "",
        ]
    )

    # NTP — CIS requires ≥2 sources for redundancy
    ntp = services.get("ntp_servers", ["0.pool.ntp.org", "1.pool.ntp.org", "2.pool.ntp.org"])
    lines.extend(
        [
            "config system ntp",
            "    set type custom",
        ]
    )
    for i, server in enumerate(ntp[:3], 1):
        lines.extend(
            [
                "    config ntpserver",
                f"        edit {i}",
                f'            set server "{server}"',
                "        next",
                "    end",
            ]
        )
    lines.extend(["end", ""])

    # Logging (CIS benchmark)
    lines.extend(
        [
            "# ━━ LOGGING ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
            "config log setting",
            "    set fwpolicy-implicit-log enable",
            "    set local-in-allow enable",
            "    set local-in-deny-broadcast enable",
            "    set local-out enable",
            "end",
            "",
        ]
    )

    # ── Session TTL and FortiGuard ───────────────────────────────────────
    # No "config system session-helper / purge" here. purge deletes every
    # session helper (FTP, TFTP, SIP, DNS and the rest), not just the ones CIS
    # names, and the SSH deploy's allowlist never sent it: it was skipped while
    # the deploy reported success. Now that a refused line fails the deploy,
    # the template only holds lines the deploy will send.
    lines.extend(
        [
            "# ━━ HARDENING: SESSION TTL & FORTIGUARD ━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
            "# Session TTL — tighter than defaults",
            "config system session-ttl",
            "    set default 3600",
            "end",
            "",
            "# FortiGuard update schedule — keep AV/IPS definitions current",
            "config system autoupdate schedule",
            "    set status enable",
            "    set frequency every",
            '    set time "03:00"',
            "end",
            "",
            # Tunneling disabled by default — only enable if customer has a forwarding
            # proxy. With status=enable and no proxy configured, FortiGuard updates fail.
            "config system autoupdate tunneling",
            "    set status disable",
            "end",
            "",
        ]
    )

    # ── Security profiles ────────────────────────────────────────────────
    lines.extend(
        [
            "# Security Profiles — applied to all allow-policies",
            "# (uses built-in 'default' profiles; customise per customer as needed)",
            "",
        ]
    )

    # Collect security profile lines reused across policies
    sec_profile_lines = [
        "        set utm-status enable",
        "        set av-profile default",
        "        set dnsfilter-profile default",
        "        set application-list default",
        "        set logtraffic all",
        "        set logtraffic-start enable",
    ]
    if security.get("web_filter", True):
        sec_profile_lines.append("        set webfilter-profile default")
    if security.get("ids_ips", True):
        sec_profile_lines.append("        set ips-sensor default")
    sec_profile_lines.append("        set ssl-ssh-profile certificate-inspection")

    # ── Address objects ──────────────────────────────────────────────────
    cust_prefix = (
        _sanitize_fortigate_name(customer.get("name", "CUST")).replace(" ", "-").upper()[:12]
    )
    lines.append("# Address Objects")
    lines.append("config firewall address")
    lines.append(f'    edit "{cust_prefix}_LAN"')
    lines.append(f"        set subnet {_cidr_to_mask(lan_subnet)}")
    lines.append("    next")
    for vlan in network.get("vlans", []):
        vid = vlan.get("id", 10)
        vname = _sanitize_fortigate_name(vlan.get("name", f"VLAN{vid}")).replace(" ", "-").upper()
        lines.append(f'    edit "{cust_prefix}_{vname}"')
        lines.append(f"        set subnet {_cidr_to_mask(vlan.get('subnet', '10.0.0.0/24'))}")
        lines.append("    next")
    lines.extend(["end", ""])

    # ── Firewall policies ────────────────────────────────────────────────
    vlans = network.get("vlans", [])
    policy_id = 1

    lines.append("# Firewall Policies")
    lines.append("config firewall policy")

    # Policy: LAN → WAN (full access + security profiles)
    lines.extend(
        [
            f"    edit {policy_id}",
            f'        set name "{cust_prefix}_LAN-to-WAN"',
            "        set srcintf port2",
            "        set dstintf port1",
            f'        set srcaddr "{cust_prefix}_LAN"',
            "        set dstaddr all",
            "        set action accept",
            "        set schedule always",
            "        set service ALL",
            "        set nat enable",
            *sec_profile_lines,
            "    next",
        ]
    )
    policy_id += 1

    # Per-VLAN → WAN policy — uniform: accept all, NAT, full UTM.
    # Tweak per-VLAN behaviour (web-only, no-UTM, etc.) in FortiGate GUI after generation.
    for vlan in vlans:
        vid = vlan.get("id", 10)
        vname = _sanitize_fortigate_name(vlan.get("name", f"VLAN{vid}")).replace(" ", "-").upper()
        addr = f"{cust_prefix}_{vname}"
        lines.extend(
            [
                f"    edit {policy_id}",
                f'        set name "{cust_prefix}_{vname}-to-WAN"',
                f"        set srcintf VLAN{vid}",
                "        set dstintf port1",
                f'        set srcaddr "{addr}"',
                "        set dstaddr all",
                "        set action accept",
                "        set schedule always",
                "        set service ALL",
                "        set nat enable",
                *sec_profile_lines,
                "    next",
            ]
        )
        policy_id += 1

    # MGMT physical port → all internal + WAN (admin access for tech with laptop).
    # No UTM — clean path for management traffic.
    all_internal_dstintf = ["port2"] + [f"VLAN{v.get('id')}" for v in vlans] + ["port1"]
    lines.extend(
        [
            f"    edit {policy_id}",
            f'        set name "{cust_prefix}_MGMT-ACCESS-to-ALL"',
            f"        set srcintf {mgmt_phys_port}",
            "        set dstintf " + " ".join(all_internal_dstintf),
            "        set srcaddr all",
            "        set dstaddr all",
            "        set action accept",
            "        set schedule always",
            "        set service ALL",
            "        set nat enable",
            "        set logtraffic all",
            '        set comments "Local MGMT port full access — tech laptop"',
            "    next",
        ]
    )
    policy_id += 1

    # MGMT-VLAN detection by name (mgmt/management — case-insensitive).
    # MGMT VLAN gets full access to all internal nets + WAN (no UTM).
    # All other VLANs get standard inter-VLAN deny.
    def _is_mgmt(v: dict) -> bool:
        n = (v.get("name", "") or "").lower()
        return "mgmt" in n or "management" in n

    mgmt_vlans = [v for v in vlans if _is_mgmt(v)]
    non_mgmt_vlans = [v for v in vlans if not _is_mgmt(v)]

    # Allow: MGMT VLAN → all internal + WAN (admin from MGMT-tagged network)
    for mv in mgmt_vlans:
        mv_id = mv.get("id", 99)
        mv_name = _sanitize_fortigate_name(mv.get("name", "MGMT")).replace(" ", "-").upper()
        mv_dst = (
            ["port2"]
            + [f"VLAN{v.get('id')}" for v in vlans if v.get("id") != mv_id]
            + [mgmt_phys_port, "port1"]
        )
        lines.extend(
            [
                f"    edit {policy_id}",
                f'        set name "{cust_prefix}_{mv_name}-to-ALL"',
                f"        set srcintf VLAN{mv_id}",
                "        set dstintf " + " ".join(mv_dst),
                "        set srcaddr all",
                "        set dstaddr all",
                "        set action accept",
                "        set schedule always",
                "        set service ALL",
                "        set nat enable",
                "        set logtraffic all",
                '        set comments "MGMT VLAN full access til alt"',
                "    next",
            ]
        )
        policy_id += 1

    # Deny: every non-MGMT VLAN → LAN, all other VLANs, MGMT port (zero-trust)
    for src_vlan in non_mgmt_vlans:
        src_vid = src_vlan.get("id", 10)
        src_vname = (
            _sanitize_fortigate_name(src_vlan.get("name", f"VLAN{src_vid}"))
            .replace(" ", "-")
            .upper()
        )
        deny_dst = ["port2", mgmt_phys_port] + [
            f"VLAN{v.get('id')}" for v in vlans if v.get("id") != src_vid
        ]
        lines.extend(
            [
                f"    edit {policy_id}",
                f'        set name "{cust_prefix}_{src_vname}-INTERNAL_DENY"',
                f"        set srcintf VLAN{src_vid}",
                "        set dstintf " + " ".join(deny_dst),
                "        set srcaddr all",
                "        set dstaddr all",
                "        set action deny",
                "        set schedule always",
                "        set service ALL",
                "        set logtraffic all",
                f'        set comments "Zero-trust: blokker all intern trafikk fra {src_vname}"',
                "    next",
            ]
        )
        policy_id += 1

    # LAN → all VLANs deny (admin tilgang går via MGMT-port eller MGMT-VLAN)
    if vlans:
        lines.extend(
            [
                f"    edit {policy_id}",
                f'        set name "{cust_prefix}_LAN-INTERNAL_DENY"',
                "        set srcintf port2",
                "        set dstintf "
                + " ".join([f"VLAN{v.get('id')}" for v in vlans] + [mgmt_phys_port]),
                "        set srcaddr all",
                "        set dstaddr all",
                "        set action deny",
                "        set schedule always",
                "        set service ALL",
                "        set logtraffic all",
                '        set comments "Zero-trust: LAN kan ikke nå VLANs/MGMT — bruk port10 for admin"',
                "    next",
            ]
        )
        policy_id += 1

    lines.extend(["end", ""])

    # Syslog
    if services.get("syslog_server"):
        lines.extend(
            [
                "config log syslogd setting",
                "    set status enable",
                f'    set server "{services["syslog_server"]}"',
                "    set port 514",
                "end",
                "",
            ]
        )

    return "\n".join(lines)


def _generate_unifi_json(
    customer: dict,
    network: dict,
    services: dict,
    security: dict,
) -> str:
    """Generate UniFi network configuration as JSON."""
    config: dict = {
        "site": {
            "name": customer.get("name", "Default"),
            "description": f"Provisioned {datetime.now(UTC).strftime('%Y-%m-%d')}",
        },
        "networks": [],
        "wlans": [],
    }

    # Default LAN
    config["networks"].append(
        {
            "name": "Default",
            "purpose": "corporate",
            "subnet": network.get("lan_subnet", "192.168.1.0/24"),
            "dhcp_enabled": services.get("dhcp_enabled", True),
            "dhcp_start": network.get("dhcp_start", "192.168.1.100"),
            "dhcp_stop": network.get("dhcp_stop", "192.168.1.254"),
            "domain_name": customer.get("domain", "local"),
        }
    )

    # VLANs
    for vlan in network.get("vlans", []):
        config["networks"].append(
            {
                "name": vlan.get("name", f"VLAN{vlan.get('id')}"),
                "purpose": "corporate",
                "vlan_id": vlan.get("id"),
                "subnet": vlan.get("subnet", "10.0.0.0/24"),
                "dhcp_enabled": True,
            }
        )

    return json.dumps(config, indent=2, ensure_ascii=False)


# ── AI-Assisted Generation ───────────────────────────────────────────────────


async def _generate_with_ai(
    customer: dict,
    network: dict,
    services: dict,
    security: dict,
    device_type: str,
) -> dict:
    """Use Claude to generate production-ready configs."""
    from app.services.claude_console import _get_api_key, is_available

    if not is_available():
        return _fallback_generate(customer, network, services, security, device_type)

    try:
        import anthropic
    except ImportError:
        return _fallback_generate(customer, network, services, security, device_type)

    api_key = _get_api_key()
    client = anthropic.Anthropic(api_key=api_key)

    context = json.dumps(
        {
            "customer": customer,
            "network": network,
            "services": services,
            "security": security,
            "device_type": device_type,
        },
        indent=2,
    )

    system_prompt = (
        "You are a network engineer generating production-ready device configs "
        "following CIS benchmarks. Output FortiGate configs as pure CLI commands "
        "(no markdown). Output UniFi configs as JSON. Use EXACT subnet values from "
        "input. Mark placeholders with CHANGE-ME. Include a deployment checklist at "
        "the end as comments."
    )

    message = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": f"Generate configs for:\n{context}"}],
    )

    content = message.content[0].text if message.content else ""
    result: dict = {}
    if device_type in ("fortigate", "both"):
        result["fortigate_cli"] = content
    if device_type in ("unifi", "both"):
        result["unifi_json"] = content
    return result


def _fallback_generate(
    customer: dict,
    network: dict,
    services: dict,
    security: dict,
    device_type: str,
) -> dict:
    """Template-based fallback when AI is unavailable."""
    result: dict = {}
    if device_type in ("fortigate", "both"):
        result["fortigate_cli"] = _generate_fortigate_cli(customer, network, services, security)
    if device_type in ("unifi", "both"):
        result["unifi_json"] = _generate_unifi_json(customer, network, services, security)
    return result


# ── Subnet Auto-Generation ──────────────────────────────────────────────────


def generate_subnets(customer_name: str) -> dict:
    """Generate deterministic subnets from customer name.

    Uses a hash of the name to pick a unique second octet (10.X.0.0/24).
    Returns LAN subnet + standard VLANs.
    """
    h = int(hashlib.sha256(customer_name.lower().encode()).hexdigest()[:4], 16)
    # Second octet 1-254 (avoid 0 and 255)
    octet2 = (h % 254) + 1

    return {
        "lan_subnet": f"10.{octet2}.0.0/24",
        "lan_gateway": f"10.{octet2}.0.1",
        "vlans": [
            {"name": "Servere", "id": 10, "subnet": f"10.{octet2}.10.0/24"},
            {"name": "Gjest", "id": 20, "subnet": f"10.{octet2}.20.0/24"},
            {"name": "IoT", "id": 30, "subnet": f"10.{octet2}.30.0/24"},
            {"name": "Management", "id": 99, "subnet": f"10.{octet2}.99.0/24"},
        ],
    }


# ── REST API Deployment ─────────────────────────────────────────────────────
#
# The REST deploy is the ordered list of named steps in _REST_STEPS. Each step
# is a small function of (device, plan): _RestDevice makes the calls and
# records what each did, _RestPlan holds every name and address worked out
# from the wizard before the device is touched. _run_steps stops at the first
# required step that fails, so the LAN address (the last step, and the one
# that can cut the connection) only changes on a device that took everything
# before it.

# FortiOS answers a POST for an object that already exists with HTTP 500 and
# a numeric "error" in the body, e.g.
#   {"http_method": "POST", "status": "error", "http_status": 500, "error": -5, ...}
# Fortinet's REST error table (KB "Troubleshooting Tip: Rest-API response
# error codes") gives these as the "already exists" codes:
#   -5 a duplicate entry already exists, -15 duplicate entry found,
#   -82 tunnel already exists, -100 a duplicate user name already exists.
# Any other 500 is a real failure. -651 ("input value is invalid") in
# particular used to be taken for a duplicate and overwritten with a PUT.
_FORTIOS_DUPLICATE = frozenset({-5, -15, -82, -100})
_FORTIOS_ERRORS = {
    -3: "objektet finnes ikke",
    -5: "objektet finnes fra før",
    -15: "duplikat finnes",
    -23: "objektet er i bruk",
    -37: "ingen tilgang",
    -82: "tunnelen finnes fra før",
    -100: "brukernavnet finnes fra før",
    -651: "ugyldig verdi",
}
# Some FortiOS versions name the existing object's id in the duplicate text
# ("... already used by policy '12'"); when present it is the PUT target.
_USED_BY_ID = re.compile(r"already used by \S+ '(\d+)'")
# Tables keyed by an id rather than the name, so an existing object is found
# by name before it can be updated. A PUT to firewall/policy/<name> can never
# match: the policy key is its policyid.
_ID_KEYED_TABLES = {"firewall/policy": "policyid"}


def _fortios_body(r) -> dict:
    try:
        body = r.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _fortios_code(body: dict) -> int | None:
    code = body.get("error")
    if isinstance(code, bool):
        return None
    if isinstance(code, int):
        return code
    if isinstance(code, str) and re.fullmatch(r"-?\d+", code.strip()):
        return int(code)
    return None


def _is_duplicate(r) -> bool:
    return r.status_code == 500 and _fortios_code(_fortios_body(r)) in _FORTIOS_DUPLICATE


def _describe_failure(r) -> str:
    """A refused call as an operator reads it: HTTP status, FortiOS code, CLI text."""
    body = _fortios_body(r)
    text = f"HTTP {r.status_code}"
    code = _fortios_code(body)
    if code is not None:
        meaning = _FORTIOS_ERRORS.get(code)
        text += f", FortiOS-feil {code}" + (f" ({meaning})" if meaning else "")
    elif isinstance(body.get("error"), str) and body["error"].strip():
        text += f", {_clip(body['error'], 200)}"
    cli_error = str(body.get("cli_error") or "").strip()
    if cli_error:
        text += f": {_clip(cli_error, 200)}"
    return text


def _transport_reason(exc: Exception) -> str:
    import httpx

    detail = str(exc) or type(exc).__name__
    if isinstance(exc, httpx.TimeoutException):
        return f"Tidsavbrudd: FortiGate svarte ikke ({detail})"
    if isinstance(exc, httpx.TransportError):
        return f"Mistet forbindelsen med FortiGate ({detail})"
    return f"{type(exc).__name__}: {exc}"


class _RestDevice(_Recorder):
    """The FortiGate side of a REST deploy: every read and write goes through here."""

    def __init__(self, fg, vdom: str) -> None:
        super().__init__()
        self.fg = fg
        self.vdom = vdom

    async def read(self, path: str, params: dict | None = None):
        """A read the caller can do without: a failure comes back carrying .error."""
        try:
            return await self.fg.get_cmdb(path, params)
        except Exception as exc:
            return ApiList(error=_transport_reason(exc))

    async def read_required(self, path: str, label: str):
        """A read the step cannot go on without: a failure fails the step."""
        data = await self.read(path)
        if read_failed(data):
            self.fail(label, f"Kunne ikke lese {path}: {data.error}")
        return data

    async def _send(self, method: str, path: str, payload: dict, label: str, no_answer: str):
        try:
            return await getattr(self.fg._client, method)(
                f"/api/v2/cmdb/{path}",
                json=payload,
                params={"vdom": self.vdom},
            )
        except Exception as exc:
            reason = _transport_reason(exc)
            self.fail(label, f"{no_answer} {reason}" if no_answer else reason)

    async def put(
        self, path: str, payload: dict, label: str, *, note: str = "", no_answer: str = ""
    ) -> None:
        r = await self._send("put", path, payload, label, no_answer)
        if not r.is_success:
            self.fail(label, _describe_failure(r))
        self.applied(label, note)

    async def post(
        self, path: str, payload: dict, label: str, *, update_existing: bool = True
    ) -> None:
        """Create; when FortiOS says the named object exists, update it instead."""
        r = await self._send("post", path, payload, label, "")
        if r.is_success:
            self.applied(label)
            return
        name = payload.get("name", "")
        if update_existing and name and _is_duplicate(r):
            target = await self._existing_path(path, name, r, label)
            await self.put(target, payload, label, note="Fantes fra før, oppdatert")
            return
        self.fail(label, _describe_failure(r))

    async def _existing_path(self, path: str, name: str, r, label: str) -> str:
        match = _USED_BY_ID.search(r.text.lower())
        if match:
            return f"{path}/{match.group(1)}"
        key = _ID_KEYED_TABLES.get(path)
        if key is None:
            return f"{path}/{name}"
        found = await self.read(path, {"filter": f"name=={name}"})
        ids = [
            obj.get(key)
            for obj in found
            if isinstance(obj, dict) and obj.get("name") == name and obj.get(key) is not None
        ]
        if not ids:
            self.fail(label, f"Finnes fra før, men fant ikke {key} for «{name}» å oppdatere")
        return f"{path}/{ids[0]}"


# FortiGate only allows A-Z a-z 0-9 - _ in names
_REST_NAME_MAP = str.maketrans("æøåÆØÅéèêëüöäÉÈÊËÜÖÄ", "aoaAOAeeeeuoaEEEEUOA")


def _rest_name(s: str) -> str:
    s = s.translate(_REST_NAME_MAP)
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in s).strip("-")


def _gen_password(length: int = 24) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _net_base(subnet: str) -> str:
    """The first three octets: '10.42.10.0/24' -> '10.42.10'."""
    return subnet.split("/")[0].rsplit(".", 1)[0]


def _vlan_iface_name(vid, vname: str) -> str:
    return f"V{vid:03d}_{vname.replace(' ', '-')[:12].upper()}"


def _vlan_addr_name(cust_prefix: str, vname: str) -> str:
    # Named address per subnet: never raw IPs in policies
    return f"NET_{cust_prefix}_{vname.replace(' ', '-').upper()}"


def _is_mgmt_vlan(vlan: dict) -> bool:
    """MGMT VLAN detection by name (mgmt/management, case-insensitive)."""
    name = (vlan.get("name", "") or "").lower()
    return "mgmt" in name or "management" in name


def _inform_host_setting() -> str:
    from app.core.config import load_app_settings

    return str(load_app_settings().get("unifi_inform_host") or "").strip()


def _unifi_option43(host: str) -> str:
    """DHCP option 43 pointing UniFi devices at the controller, or "" if unresolvable.

    Sub-option 1, length 4, the IPv4 address: 203.0.113.10 -> 0104cb00710a.
    No host is no option: gethostbyname("") answers 0.0.0.0.
    """
    import socket

    if not host:
        return ""
    try:
        ip = socket.gethostbyname(host)
        octets = [int(o) for o in ip.split(".")]
    except Exception as e:
        logger.warning("Failed to resolve UniFi controller host %s for Option 43: %s", host, e)
        return ""
    value = "0104" + "".join(f"{o:02x}" for o in octets)
    logger.info("DHCP Option 43: %s → %s → %s", host, ip, value)
    return value


@dataclass
class _RestPlan:
    """Everything a REST deploy writes, worked out before the device is touched.

    The fields after the VPN ones are learned from the device as the steps run.
    """

    host: str
    port: int
    customer_id: str
    customer: dict
    network: dict
    services: dict
    security: dict
    cust_prefix: str
    hostname: str
    wan_type: str
    lan_subnet: str
    lan_base: str
    lan_gw: str
    vlans: list[dict]
    vlan_iface_names: dict
    vlan_addr_names: dict
    addr_lan: str
    all_internal: str
    dns: list
    ntp: list
    mgmt_phys_base: str
    mgmt_phys_gw: str
    unifi_controller_host: str
    vpn_name: str
    vpn_user: str
    vpn_group: str
    vpn_psk: str
    vpn_user_pw: str
    vpn_start: str
    vpn_end: str
    vpn_pool_addr: str
    vpn_split_addr: str
    wan_iface: str = "wan1"
    lan_iface: str = "internal"
    current_tz: Any = None
    mgmt_phys_port: str = ""
    unifi_opt43_hex: str = ""
    lan_ip_changed: bool = False

    @property
    def sec_profiles(self) -> dict:
        """Security profiles on every allow-policy.

        CRITICAL: utm-status must be "enable" or FortiGate ignores all the
        profile assignments, silently. CIS-baseline stack: AV + IPS +
        webfilter + DNS-filter + app-list, with certificate-inspection SSL.
        """
        profiles: dict = {
            "utm-status": "enable",
            "logtraffic": "all",
            "logtraffic-start": "enable",
            "av-profile": "default",
            "dnsfilter-profile": "default",
            "application-list": "default",
            "ssl-ssh-profile": "certificate-inspection",
        }
        if self.security.get("web_filter", True):
            profiles["webfilter-profile"] = "default"
        if self.security.get("ids_ips", True):
            profiles["ips-sensor"] = "default"
        return profiles


# MGMT policy profile set: no UTM, no SSL inspection. UniFi inform/STUN and
# similar L3-discovery traffic breaks under UTM/SSL-inspection.
_MGMT_PROFILES = {"utm-status": "disable", "logtraffic": "all", "ssl-ssh-profile": "no-inspection"}


def _build_rest_plan(steps: dict, conn: dict) -> _RestPlan:
    customer = steps.get(1, {}) or {}
    network = steps.get(2, {}) or {}
    services = steps.get(3, {}) or {}
    security = steps.get(4, {}) or {}

    cust_prefix = _rest_name(customer.get("name") or conn.get("customer_name") or "FW")[:15].upper()

    lan_subnet = network.get("lan_subnet", "192.168.1.0/24")
    lan_base = _net_base(lan_subnet)

    vlans = network.get("vlans", [])
    vlan_iface_names: dict = {}
    vlan_addr_names: dict = {}
    for vlan in vlans:
        vid = vlan.get("id", 10)
        vname = vlan.get("name", f"VLAN{vid}")
        vlan_iface_names[vid] = _vlan_iface_name(vid, vname)
        vlan_addr_names[vid] = _vlan_addr_name(cust_prefix, vname)

    # NTP: CIS wants at least two sources. Pad with pool servers if fewer are
    # given. A copy, so the session's own list is not padded in place.
    ntp = list(services.get("ntp_servers") or [])
    defaults = ["0.pool.ntp.org", "1.pool.ntp.org", "2.pool.ntp.org"]
    while len(ntp) < 3:
        for d in defaults:
            if d not in ntp:
                ntp.append(d)
            if len(ntp) >= 3:
                break

    # Dedicated local MGMT port: its own /24, by default the LAN's third octet
    # plus 100 (10.25.0.0/24 -> 10.25.100.0/24).
    mgmt_phys_subnet = network.get("mgmt_phys_subnet") or ""
    if not mgmt_phys_subnet:
        lan_parts = lan_subnet.split("/")[0].split(".")
        mgmt_phys_subnet = f"{lan_parts[0]}.{lan_parts[1]}.{(int(lan_parts[2]) + 100) % 256}.0/24"
    mgmt_phys_base = _net_base(mgmt_phys_subnet)

    # IPsec VPN for remote admin. FortiOS interface names max 15 chars, so the
    # VPN name stays short. Tunnel pool .240-.254 of the LAN unless
    # network["vpn_pool_subnet"] names a dedicated /24.
    vpn_name = f"{cust_prefix[:8]}_VPN"
    vpn_subnet = network.get("vpn_pool_subnet", "")
    vpn_base = _net_base(vpn_subnet) if vpn_subnet else lan_base
    vpn_psk = _gen_password(32)
    vpn_user_pw = _gen_password(20)

    return _RestPlan(
        host=conn["host"],
        port=conn["port"],
        customer_id=conn.get("customer_id", ""),
        customer=customer,
        network=network,
        services=services,
        security=security,
        cust_prefix=cust_prefix,
        hostname=_rest_name(customer.get("name", "FW"))[:35],
        wan_type=network.get("wan_type", "dhcp"),
        lan_subnet=lan_subnet,
        lan_base=lan_base,
        lan_gw=f"{lan_base}.1",
        vlans=vlans,
        vlan_iface_names=vlan_iface_names,
        vlan_addr_names=vlan_addr_names,
        addr_lan=f"NET_{cust_prefix}_LAN",
        all_internal=f"GRP_{cust_prefix}_ALL-INTERNAL",
        dns=services.get("dns_servers", ["1.1.1.1", "1.0.0.1"]),
        ntp=ntp,
        mgmt_phys_base=mgmt_phys_base,
        mgmt_phys_gw=f"{mgmt_phys_base}.1",
        # The wizard's own value, else the inform host set in Administrasjon >
        # Integrasjoner > UniFi. It was one MSP's own controller, written into
        # the code, for every installation; with neither, option 43 is left out.
        unifi_controller_host=services.get("unifi_controller_host") or _inform_host_setting(),
        vpn_name=vpn_name,
        vpn_user="sybr_admin",
        vpn_group=f"{cust_prefix}_VPN-ADMINS",
        vpn_psk=vpn_psk,
        vpn_user_pw=vpn_user_pw,
        vpn_start=f"{vpn_base}.240",
        vpn_end=f"{vpn_base}.254",
        vpn_pool_addr=f"NET_{cust_prefix}_VPN-POOL",
        vpn_split_addr=f"GRP_{cust_prefix}_VPN-SPLIT",
    )


# ── REST steps ───────────────────────────────────────────────────────────────


async def _step_discover(dev: _RestDevice, plan: _RestPlan) -> None:
    """Read the timezone format and pick the WAN and LAN interfaces.

    The interface list is required: writing to guessed interface names on a
    device that could not be read is how a deploy half-configures the wrong
    port. An unreachable device or a bad token also stops here, before any
    write, with one reason instead of forty.
    """
    glob = await dev.read("system/global")
    if isinstance(glob, list) and glob:
        glob = glob[0]
    if isinstance(glob, dict):
        plan.current_tz = glob.get("timezone")
    else:
        logger.debug("Could not read current timezone from system/global")

    ifaces = await dev.read_required("system/interface", "Les grensesnitt")
    wan_candidates = []
    lan_candidates = []
    for iface in ifaces:
        name = iface.get("name", "")
        itype = iface.get("type", "")
        role = (iface.get("role", "") or "").lower()
        ip = iface.get("ip", "")
        if role == "wan" and itype == "physical":
            has_ip = ip and not ip.startswith("0.0.0.0")
            wan_candidates.append((0 if has_ip else 1, name))
        if role == "lan" and itype in ("hard-switch", "switch"):
            lan_candidates.insert(0, name)
        elif role == "lan" and itype == "physical":
            lan_candidates.append(name)
    wan_candidates.sort()
    if wan_candidates:
        plan.wan_iface = wan_candidates[0][1]
    if lan_candidates:
        plan.lan_iface = lan_candidates[0]
    logger.info("Discovered: WAN=%s LAN=%s tz=%s", plan.wan_iface, plan.lan_iface, plan.current_tz)
    dev.applied("Les grensesnitt", f"WAN={plan.wan_iface}, LAN={plan.lan_iface}")


async def _step_system_global(dev: _RestDevice, plan: _RestPlan) -> None:
    cfg: dict = {
        "hostname": plan.hostname,
        "admintimeout": 15,
        "admin-ssh-grace-time": 60,
        "admin-ssh-v2": "enable",
        "admin-scp": "enable",
        "admin-sport": 8443,
        "admin-maintainer": "disable",
        "post-login-banner": "enable",
        "pre-login-banner": "enable",
        "strong-crypto": "enable",
        "auto-auth-extension-device": "disable",
        "usb-auto-install": "disable",
    }
    if isinstance(plan.current_tz, str):
        cfg["timezone"] = "Europe/Oslo"
    elif isinstance(plan.current_tz, int):
        # FortiOS timezone 26 = Brussels/Copenhagen/Madrid/Paris (Norway)
        cfg["timezone"] = 26
    await dev.put("system/global", cfg, "System hardening")
    # Login banner text is not supported on all firmware via REST, so the
    # pre_admin-disclaimer-text replacemsg is not written here.


async def _step_password_policy(dev: _RestDevice, plan: _RestPlan) -> None:
    await dev.put(
        "system/password-policy",
        {
            "status": "enable",
            "min-length": 14,
            "min-upper-case-letter": 1,
            "min-lower-case-letter": 1,
            "min-number": 1,
            "min-non-alphanumeric": 1,
            "expire-status": "enable",
            "expire-day": 90,
            "reuse-password": "disable",
        },
        "Passordpolicy (CIS 5.1)",
    )


async def _step_dns(dev: _RestDevice, plan: _RestPlan) -> None:
    dns = plan.dns
    await dev.put(
        "system/dns",
        {
            "primary": dns[0] if dns else "1.1.1.1",
            "secondary": dns[1] if len(dns) > 1 else "1.0.0.1",
            "dns-over-tls": "enforce",
        },
        "DNS (m/ DoT)",
    )


async def _step_ntp(dev: _RestDevice, plan: _RestPlan) -> None:
    await dev.put(
        "system/ntp",
        {
            "type": "custom",
            "ntpserver": [{"id": i + 1, "server": s} for i, s in enumerate(plan.ntp[:3])],
        },
        "NTP (3 servere)",
    )


async def _step_wan_interface(dev: _RestDevice, plan: _RestPlan) -> None:
    wan_cfg: dict = {
        "alias": f"{plan.cust_prefix}-WAN",
        "allowaccess": "ping",
        "description": f"WAN uplink — {plan.customer.get('name', '')}",
    }
    if plan.wan_type == "dhcp":
        wan_cfg["mode"] = "dhcp"
    elif plan.wan_type == "static":
        wan_cfg["mode"] = "static"
        if plan.network.get("wan_ip"):
            wan_cfg["ip"] = plan.network["wan_ip"]
    await dev.put(f"system/interface/{plan.wan_iface}", wan_cfg, f"WAN ({plan.wan_iface})")


async def _step_vlan_interfaces(dev: _RestDevice, plan: _RestPlan) -> None:
    if not plan.vlans:
        dev.skipped("VLAN-grensesnitt", "Ingen VLAN i planen")
        return
    for vlan in plan.vlans:
        vid = vlan.get("id", 10)
        vname = vlan.get("name", f"VLAN{vid}")
        vlan_subnet = vlan.get("subnet", "10.0.0.0/24")
        await dev.post(
            "system/interface",
            {
                "name": _vlan_iface_name(vid, vname),
                "vdom": "root",
                "type": "vlan",
                "interface": plan.lan_iface,
                "vlanid": vid,
                "alias": f"{plan.cust_prefix}-{vname.upper()}",
                "mode": "static",
                "ip": f"{_net_base(vlan_subnet)}.1 255.255.255.0",
                "allowaccess": "ping",
                "description": f"VLAN {vid} — {vname} — {vlan_subnet}",
            },
            f"VLAN {vid} ({vname})",
        )


async def _step_address_objects(dev: _RestDevice, plan: _RestPlan) -> None:
    await dev.post(
        "firewall/address",
        {
            "name": plan.addr_lan,
            "subnet": f"{plan.lan_base}.0 255.255.255.0",
            "comment": f"LAN subnet {plan.lan_subnet}",
        },
        f"Adresseobjekt {plan.addr_lan}",
    )
    for vlan in plan.vlans:
        vid = vlan.get("id", 10)
        vname = vlan.get("name", f"VLAN{vid}")
        vlan_subnet = vlan.get("subnet", "10.0.0.0/24")
        addr_name = _vlan_addr_name(plan.cust_prefix, vname)
        await dev.post(
            "firewall/address",
            {
                "name": addr_name,
                "subnet": f"{_net_base(vlan_subnet)}.0 255.255.255.0",
                "comment": f"VLAN {vid} — {vname} — {vlan_subnet}",
            },
            f"Adresseobjekt {addr_name}",
        )


async def _step_address_group(dev: _RestDevice, plan: _RestPlan) -> None:
    members = [{"name": plan.addr_lan}] + [{"name": v} for v in plan.vlan_addr_names.values()]
    await dev.post(
        "firewall/addrgrp",
        {
            "name": plan.all_internal,
            "member": members,
            "comment": f"Alle interne nett — {plan.customer.get('name', '')}",
        },
        f"Adressegruppe {plan.all_internal}",
    )


async def _dhcp_server(
    dev: _RestDevice, plan: _RestPlan, iface: str, gw: str, base: str, label: str
) -> None:
    """Create the DHCP server for *iface*, or update the one already there.

    dns-server1 = gateway (FortiGate forwards DNS for internal clients).
    Option 43 points UniFi devices at the controller via inform-URL.
    """
    dhcp_cfg: dict = {
        "status": "enable",
        "interface": iface,
        "default-gateway": gw,
        "netmask": "255.255.255.0",
        "dns-service": "specify",
        "dns-server1": gw,
        "ip-range": [{"start-ip": f"{base}.100", "end-ip": f"{base}.250"}],
        "lease-time": 86400,
    }
    if plan.unifi_opt43_hex:
        dhcp_cfg["options"] = [{"id": 1, "code": 43, "type": "hex", "value": plan.unifi_opt43_hex}]
    # Which interfaces already have a server. A read that failed used to look
    # like "none", and the deploy then created a second server for the same
    # interface; now it fails the step instead.
    existing = await dev.read_required("system.dhcp/server", label)
    for srv in existing:
        srv_iface = srv.get("interface", "")
        if isinstance(srv_iface, dict):
            srv_iface = srv_iface.get("name", "")
        if srv_iface == iface:
            await dev.put(f"system.dhcp/server/{srv['id']}", dhcp_cfg, label)
            return
    await dev.post("system.dhcp/server", dhcp_cfg, label, update_existing=False)


async def _step_dhcp_servers(dev: _RestDevice, plan: _RestPlan) -> None:
    plan.unifi_opt43_hex = _unifi_option43(plan.unifi_controller_host)
    await _dhcp_server(
        dev, plan, plan.lan_iface, plan.lan_gw, plan.lan_base, f"DHCP server LAN ({plan.lan_iface})"
    )
    for vlan in plan.vlans:
        vid = vlan.get("id", 10)
        vname = vlan.get("name", f"VLAN{vid}")
        base = _net_base(vlan.get("subnet", "10.0.0.0/24"))
        await _dhcp_server(
            dev,
            plan,
            plan.vlan_iface_names.get(vid, f"VLAN{vid}"),
            f"{base}.1",
            base,
            f"DHCP server VLAN {vid} ({vname})",
        )


async def _step_mgmt_port(dev: _RestDevice, plan: _RestPlan) -> None:
    """Make the last free physical port a standalone MGMT port with its own DHCP.

    On a 60F this is typically internal5, a member of the 'internal'
    hard-switch; on other models port10, port7 and so on. A hard-switch
    member is taken out of the switch first. The port is only recorded in
    the plan (and so given its policy) once all of this went through.
    """
    all_ifaces = await dev.read_required("system/interface", "Finn ledig port")
    # Candidates: physical ports NOT currently wan/lan/dmz/modem/fortilink/mgmt
    reserved = {plan.wan_iface, plan.lan_iface, "dmz", "modem", "fortilink", "mgmt"}
    candidates = [
        i.get("name", "")
        for i in all_ifaces
        if i.get("type", "") == "physical"
        and i.get("name", "") not in reserved
        and not i.get("name", "").startswith("wan")
    ]
    # Prefer internal-member ports sorted descending (pick highest number)
    candidates.sort(key=lambda n: (not n.startswith("internal"), n), reverse=True)
    if not candidates:
        dev.skipped("MGMT-port", "Fant ingen ledig fysisk port")
        return
    port = candidates[0]
    logger.info("MGMT physical port selected: %s (candidates=%s)", port, candidates)

    vsw = await dev.read(f"system/virtual-switch/{plan.lan_iface}")
    if isinstance(vsw, list) and vsw:
        vsw = vsw[0]
    if isinstance(vsw, dict):
        members = [p.get("name") or p.get("interface-name") for p in vsw.get("port", [])]
        if port in members:
            await dev.put(
                f"system/virtual-switch/{plan.lan_iface}",
                {"port": [{"name": m} for m in members if m != port]},
                f"Fjern {port} fra hard-switch {plan.lan_iface}",
            )

    await dev.put(
        f"system/interface/{port}",
        {
            "alias": "MGMT-ACCESS",
            "mode": "static",
            "ip": f"{plan.mgmt_phys_gw} 255.255.255.0",
            "allowaccess": "ping https ssh fgfm",
            "description": "Local MGMT port — laptop access via DHCP",
        },
        f"MGMT port ({port}) {plan.mgmt_phys_gw}/24",
    )
    # DHCP for MGMT port: short lease, dedicated small range
    await _dhcp_server(
        dev, plan, port, plan.mgmt_phys_gw, plan.mgmt_phys_base, f"DHCP server MGMT port ({port})"
    )
    plan.mgmt_phys_port = port


async def _step_logging(dev: _RestDevice, plan: _RestPlan) -> None:
    await dev.put(
        "log/setting",
        {
            "fwpolicy-implicit-log": "enable",
            "local-in-allow": "enable",
            "local-in-deny-broadcast": "enable",
            "local-out": "enable",
        },
        "Logging (CIS 2.1)",
    )
    if plan.services.get("syslog_server"):
        await dev.put(
            "log.syslogd/setting",
            {"status": "enable", "server": plan.services["syslog_server"], "port": 514},
            "Syslog",
        )


def _policy_payloads(plan: _RestPlan) -> list[tuple[dict, str]]:
    """The firewall policies in the order they are created, with their labels."""
    p = plan.cust_prefix
    lan, wan = plan.lan_iface, plan.wan_iface
    names, addrs = plan.vlan_iface_names, plan.vlan_addr_names
    sec = plan.sec_profiles
    vlans = plan.vlans
    mgmt_vlans = [v for v in vlans if _is_mgmt_vlan(v)]
    non_mgmt_vlans = [v for v in vlans if not _is_mgmt_vlan(v)]
    out: list[tuple[dict, str]] = []

    # LAN -> WAN (full access + security profiles)
    out.append(
        (
            {
                "name": f"{p}_LAN-to-WAN_ALLOW",
                "srcintf": [{"name": lan}],
                "dstintf": [{"name": wan}],
                "srcaddr": [{"name": plan.addr_lan}],
                "dstaddr": [{"name": "all"}],
                "action": "accept",
                "schedule": "always",
                "service": [{"name": "ALL"}],
                "nat": "enable",
                **sec,
            },
            f"Policy: {p} LAN→WAN",
        )
    )

    # Per-non-MGMT-VLAN -> WAN with full UTM
    for vlan in non_mgmt_vlans:
        vid = vlan.get("id", 10)
        vname = vlan.get("name", f"VLAN{vid}").replace(" ", "-").upper()
        out.append(
            (
                {
                    "name": f"{p}_{vname}-to-WAN",
                    "srcintf": [{"name": names.get(vid, f"VLAN{vid}")}],
                    "dstintf": [{"name": wan}],
                    "srcaddr": [{"name": addrs.get(vid, "all")}],
                    "dstaddr": [{"name": "all"}],
                    "action": "accept",
                    "schedule": "always",
                    "service": [{"name": "ALL"}],
                    "nat": "enable",
                    **sec,
                },
                f"Policy: {vname}→WAN",
            )
        )

    # MGMT VLAN -> all internal + WAN. No UTM: UniFi inform/STUN and similar
    # cloud broker traffic breaks under UTM/SSL-inspection.
    for mv in mgmt_vlans:
        mv_id = mv.get("id", 99)
        mv_name = mv.get("name", "MGMT").replace(" ", "-").upper()
        mv_iface = names.get(mv_id)
        mv_addr = addrs.get(mv_id)
        if not mv_iface or not mv_addr:
            continue
        mv_dst = [{"name": lan}, {"name": wan}] + [
            {"name": names[v.get("id")]}
            for v in vlans
            if v.get("id") != mv_id and v.get("id") in names
        ]
        out.append(
            (
                {
                    "name": f"{p}_{mv_name}-to-ALL",
                    "srcintf": [{"name": mv_iface}],
                    "dstintf": mv_dst,
                    "srcaddr": [{"name": mv_addr}],
                    "dstaddr": [{"name": "all"}],
                    "action": "accept",
                    "schedule": "always",
                    "service": [{"name": "ALL"}],
                    "nat": "enable",
                    "comments": "MGMT VLAN full access (ingen UTM — UniFi-vennlig sti)",
                    **_MGMT_PROFILES,
                },
                f"Policy: {mv_name}→ALL (MGMT)",
            )
        )

    # Local MGMT port (dedicated physical): full access, no UTM
    if plan.mgmt_phys_port:
        port = plan.mgmt_phys_port
        out.append(
            (
                {
                    "name": f"{p}_MGMT-PORT-to-ALL",
                    "srcintf": [{"name": port}],
                    "dstintf": [{"name": lan}, {"name": wan}]
                    + [{"name": names[v.get("id")]} for v in vlans if v.get("id") in names],
                    "srcaddr": [{"name": "all"}],
                    "dstaddr": [{"name": "all"}],
                    "action": "accept",
                    "schedule": "always",
                    "service": [{"name": "ALL"}],
                    "nat": "enable",
                    "comments": f"Lokal MGMT-port ({port}) — tech-laptop full tilgang",
                    **_MGMT_PROFILES,
                },
                f"Policy: MGMT-PORT ({port})→ALL",
            )
        )

    # Deny: each non-MGMT VLAN -> LAN + all other VLANs
    for src in non_mgmt_vlans:
        src_vid = src.get("id", 10)
        src_vname = src.get("name", f"VLAN{src_vid}").replace(" ", "-").upper()
        src_iface = names.get(src_vid)
        src_addr = addrs.get(src_vid)
        if not src_iface or not src_addr:
            continue
        deny_dst = [{"name": lan}] + [
            {"name": names[v.get("id")]}
            for v in vlans
            if v.get("id") != src_vid and v.get("id") in names
        ]
        out.append(
            (
                {
                    "name": f"{p}_{src_vname}-INTERNAL_DENY",
                    "srcintf": [{"name": src_iface}],
                    "dstintf": deny_dst,
                    "srcaddr": [{"name": src_addr}],
                    "dstaddr": [{"name": "all"}],
                    "action": "deny",
                    "schedule": "always",
                    "service": [{"name": "ALL"}],
                    "logtraffic": "all",
                    "comments": f"Zero-trust: blokker all intern trafikk fra {src_vname}",
                },
                f"Policy: {src_vname}→INTERNAL DENY",
            )
        )

    # LAN -> non-MGMT VLANs deny (admin via MGMT VLAN/port)
    lan_deny_dst = [{"name": names[v.get("id")]} for v in non_mgmt_vlans if v.get("id") in names]
    if lan_deny_dst:
        out.append(
            (
                {
                    "name": f"{p}_LAN-INTERNAL_DENY",
                    "srcintf": [{"name": lan}],
                    "dstintf": lan_deny_dst,
                    "srcaddr": [{"name": plan.addr_lan}],
                    "dstaddr": [{"name": "all"}],
                    "action": "deny",
                    "schedule": "always",
                    "service": [{"name": "ALL"}],
                    "logtraffic": "all",
                    "comments": "Zero-trust: LAN kan ikke nå VLANs (admin via MGMT)",
                },
                "Policy: LAN→VLANs DENY",
            )
        )
    return out


async def _step_firewall_policies(dev: _RestDevice, plan: _RestPlan) -> None:
    for payload, label in _policy_payloads(plan):
        await dev.post("firewall/policy", payload, label)


async def _step_vpn(dev: _RestDevice, plan: _RestPlan) -> None:
    """IKEv2 dial-up IPsec VPN with mode-cfg for remote admin access."""
    await dev.post(
        "user/local",
        {
            "name": plan.vpn_user,
            "type": "password",
            "passwd": plan.vpn_user_pw,
            "status": "enable",
            "two-factor": "disable",
        },
        f"VPN bruker: {plan.vpn_user}",
    )
    await dev.post(
        "user/group",
        {"name": plan.vpn_group, "group-type": "firewall", "member": [{"name": plan.vpn_user}]},
        f"VPN gruppe: {plan.vpn_group}",
    )
    await dev.post(
        "firewall/address",
        {
            "name": plan.vpn_pool_addr,
            "type": "iprange",
            "start-ip": plan.vpn_start,
            "end-ip": plan.vpn_end,
            "comment": f"IPsec VPN client-pool for {plan.vpn_name}",
        },
        f"Adresseobjekt {plan.vpn_pool_addr}",
    )
    # Split-tunnel address group (all internal nets)
    await dev.post(
        "firewall/addrgrp",
        {
            "name": plan.vpn_split_addr,
            "member": [{"name": plan.addr_lan}]
            + [{"name": v} for v in plan.vlan_addr_names.values()],
            "comment": "Split-tunnel: alle interne nett for VPN-klienter",
        },
        "VPN split-tunnel adressegruppe",
    )
    # Phase 1: IKEv2, AES256-SHA256, DH group 14+20
    await dev.post(
        "vpn.ipsec/phase1-interface",
        {
            "name": plan.vpn_name,
            "type": "dynamic",
            "interface": plan.wan_iface,
            "ike-version": "2",
            "peertype": "any",
            "mode-cfg": "enable",
            "proposal": "aes256-sha256",
            "dhgrp": "14 20",
            "psksecret": plan.vpn_psk,
            "dpd": "on-idle",
            "dpd-retryinterval": 10,
            "ipv4-start-ip": plan.vpn_start,
            "ipv4-end-ip": plan.vpn_end,
            "ipv4-netmask": "255.255.255.0",
            "dns-mode": "auto",
            "ipv4-split-include": plan.vpn_split_addr,
            "save-password": "enable",
            "net-device": "disable",
            "comments": f"SYBR admin VPN — {plan.customer.get('name', '')}",
        },
        f"IPsec Phase 1: {plan.vpn_name}",
    )
    # Phase 2: AES256-SHA256, PFS DH14
    await dev.post(
        "vpn.ipsec/phase2-interface",
        {
            "name": f"{plan.vpn_name}_P2",
            "phase1name": plan.vpn_name,
            "proposal": "aes256-sha256",
            "dhgrp": "14 20",
            "auto-negotiate": "enable",
            "comments": f"Phase 2 for {plan.vpn_name}",
        },
        f"IPsec Phase 2: {plan.vpn_name}_P2",
    )


async def _step_vpn_policies(dev: _RestDevice, plan: _RestPlan) -> None:
    # VPN -> all internal nets
    await dev.post(
        "firewall/policy",
        {
            "name": f"{plan.cust_prefix}_VPN-to-ALL_ADMIN",
            "srcintf": [{"name": plan.vpn_name}],
            "dstintf": [{"name": plan.lan_iface}]
            + [{"name": n} for n in plan.vlan_iface_names.values()],
            "srcaddr": [{"name": plan.vpn_pool_addr}],
            "dstaddr": [{"name": plan.all_internal}],
            "action": "accept",
            "schedule": "always",
            "service": [{"name": "ALL"}],
            "groups": [{"name": plan.vpn_group}],
            "logtraffic": "all",
            "logtraffic-start": "enable",
            "comments": "SYBR admin full tilgang via IPsec VPN",
        },
        "Policy: VPN→Alle nett (admin)",
    )
    # VPN -> WAN (internet via tunnel)
    await dev.post(
        "firewall/policy",
        {
            "name": f"{plan.cust_prefix}_VPN-to-WAN_NAT",
            "srcintf": [{"name": plan.vpn_name}],
            "dstintf": [{"name": plan.wan_iface}],
            "srcaddr": [{"name": plan.vpn_pool_addr}],
            "dstaddr": [{"name": "all"}],
            "action": "accept",
            "schedule": "always",
            "service": [{"name": "ALL"}],
            "nat": "enable",
            "groups": [{"name": plan.vpn_group}],
            "logtraffic": "all",
            **plan.sec_profiles,
        },
        "Policy: VPN→WAN (internett)",
    )


async def _step_lan_address(dev: _RestDevice, plan: _RestPlan) -> None:
    """Move the LAN to its planned gateway address. This MUST be the last call.

    Changing the LAN address cuts the connection when HUB reaches the device
    through that subnet, so the answer may never arrive even though the
    change was made. That is reported as unconfirmed, not as applied.
    """
    cur = await dev.read(f"system/interface/{plan.lan_iface}")
    if isinstance(cur, list) and cur:
        cur = cur[0]
    cur_ip = str(cur.get("ip") or "") if isinstance(cur, dict) else ""
    # Unreadable counts as changed: re-applying the address is harmless,
    # skipping it when it did change leaves the device unreachable.
    tokens = cur_ip.split()
    plan.lan_ip_changed = not tokens or tokens[0] != plan.lan_gw

    no_answer = ""
    if plan.lan_ip_changed:
        no_answer = (
            "Ingen bekreftelse fra enheten. Når HUB når brannmuren via LAN, bryter "
            "selve IP-endringen forbindelsen, så endringen kan være utført. Sjekk "
            f"enheten på https://{plan.lan_gw}:8443 før du deployer på nytt."
        )
    await dev.put(
        f"system/interface/{plan.lan_iface}",
        {
            "alias": f"{plan.cust_prefix}-LAN",
            "mode": "static",
            "ip": f"{plan.lan_gw} 255.255.255.0",
            "allowaccess": "ping https ssh",
            "description": f"LAN — {plan.lan_subnet}",
        },
        f"LAN IP-endring ({plan.lan_iface} → {plan.lan_gw}) ⚠ SISTE STEG",
        no_answer=no_answer,
    )


# The REST deploy, in order. Optional steps are the ones nothing later builds
# on and that leave the device reachable when they fail: the run records the
# failure and goes on. Every other step stops the run, so the LAN address is
# never moved on a device that is missing anything before it.
_REST_STEPS: tuple[_Step, ...] = (
    _Step("discover", "Les enheten", _step_discover, writes=False),
    _Step("system_global", "Systemherding", _step_system_global),
    _Step("password_policy", "Passordpolicy", _step_password_policy),
    _Step("dns", "DNS", _step_dns),
    _Step("ntp", "NTP", _step_ntp),
    _Step("wan_interface", "WAN-grensesnitt", _step_wan_interface),
    _Step("vlan_interfaces", "VLAN-grensesnitt", _step_vlan_interfaces),
    _Step("address_objects", "Adresseobjekter", _step_address_objects),
    _Step("address_group", "Adressegruppe for interne nett", _step_address_group),
    _Step("dhcp_servers", "DHCP-servere", _step_dhcp_servers),
    _Step("mgmt_port", "Lokal MGMT-port", _step_mgmt_port, required=False),
    _Step("logging", "Logging", _step_logging, required=False),
    _Step("firewall_policies", "Brannmurregler", _step_firewall_policies),
    _Step("vpn", "IPsec-VPN for administrasjon", _step_vpn),
    _Step("vpn_policies", "Brannmurregler for VPN", _step_vpn_policies),
    _Step("lan_address", "LAN-adresse (siste steg)", _step_lan_address),
)


def _record_new_address(plan: _RestPlan) -> bool:
    """Point the session's customer at the device's new LAN address.

    Only called once the LAN step is confirmed. This used to run whether or
    not the change went through, and on whichever customer happened to be
    active rather than the one the wizard was started for.
    """
    if not plan.customer_id:
        return False
    try:
        from app.core.customer import CustomerManager

        cust = CustomerManager.get_customer(plan.customer_id)
        if not cust:
            return False
        # Bootstrap moved admin GUI to 8443; LAN IP now = gateway. Persist both.
        if plan.lan_ip_changed:
            cust["FortiGateHost"] = plan.lan_gw
        cust["FortiGatePort"] = 8443
        cust["FortiGateVDOM"] = cust.get("FortiGateVDOM") or "root"
        cust["FortiGateVerifySSL"] = cust.get("FortiGateVerifySSL", False)
        CustomerManager.save_customer({k: v for k, v in cust.items() if not k.startswith("_")})
        logger.info(
            "Updated customer config: FortiGateHost=%s FortiGatePort=8443",
            cust.get("FortiGateHost"),
        )
        return True
    except Exception as e:
        logger.warning("Could not update customer FortiGate config: %s", e)
        return False


def _config_summary(plan: _RestPlan, vpn_applied: bool) -> dict:
    """What the deploy set up, for the operator's record.

    The VPN credentials are only included when the VPN step went through: a
    PSK and password for a tunnel that does not exist would mislead.
    """
    security = plan.security
    summary: dict = {
        "customer": plan.customer.get("name", ""),
        "fortigate_host": plan.host,
        "fortigate_port": plan.port,
        "hostname": plan.hostname,
        "wan_interface": plan.wan_iface,
        "wan_mode": plan.wan_type,
        "lan_interface": plan.lan_iface,
        "lan_subnet": plan.lan_subnet,
        "lan_gateway": plan.lan_gw,
        "dns": plan.dns,
        "ntp": plan.ntp,
        "vlans": [
            {
                "id": v.get("id"),
                "name": v.get("name"),
                "interface": plan.vlan_iface_names.get(v.get("id"), ""),
                "subnet": v.get("subnet"),
                "gateway": v.get("subnet", "").split("/")[0].rsplit(".", 1)[0] + ".1",
                "dhcp_range": ".100-.250",
                "address_object": plan.vlan_addr_names.get(v.get("id"), ""),
            }
            for v in plan.vlans
        ],
        "security_profiles": {
            "antivirus": "default",
            "webfilter": "default" if security.get("web_filter", True) else "none",
            "ips": "default" if security.get("ids_ips", True) else "none",
            "dns_filter": "default",
            "app_control": "default",
            "ssl_inspection": "certificate-inspection",
        },
        "hardening": {
            "password_policy": "14 chars, complexity, 90-day expiry",
            "admin_timeout": "15 min",
            "strong_crypto": "enabled",
            "login_banner": "enabled",
            "implicit_deny_log": "enabled",
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }
    if vpn_applied:
        summary["vpn"] = {
            "name": plan.vpn_name,
            "type": "IKEv2 IPsec",
            "wan_interface": plan.wan_iface,
            "proposal": "AES256-SHA256",
            "dh_group": "14, 20",
            "psk": plan.vpn_psk,
            "tunnel_pool": f"{plan.vpn_start}-{plan.vpn_end}",
            "split_tunnel": plan.vpn_split_addr,
            "user": plan.vpn_user,
            "user_password": plan.vpn_user_pw,
            "user_group": plan.vpn_group,
        }
    return summary


async def _deploy_via_rest(
    host: str,
    api_token: str,
    steps: dict,
    conn: dict | None = None,
) -> DeployResult:
    """Deploy the full best-practice FortiGate config via the REST API.

    `conn` is the dict `_resolve_fortigate_conn()` produced, and it is
    required: port, VDOM, TLS verification and the customer to update all come
    from it. Without it this raises ValueError rather than resolving one here,
    because resolving without the session's customer would lose the customer
    whose keyring it may use and skip the stored-credential host guard.

    Runs `_REST_STEPS` in order and returns what each did. The FortiOS calls
    and payloads are the ones this function always sent, with two exceptions:
    an existing firewall policy is found by name (its key is the policyid,
    so a PUT to its name could never match), and an unused read of the WAN
    interface is gone.
    """
    from app.modules.fortigate_audit.client import FortiGateClient

    if conn is None:
        # Never silently resolve here: without the session's customer_id this
        # would fall back to the *active* customer's keyring and skip the
        # host-mismatch guard, the exact SR-001 #5 shape the caller closes.
        raise ValueError("Intern feil: FortiGate-tilkobling ikke oppløst før REST-deploy.")

    result = DeployResult("fortigate", "rest")
    if not api_token:
        result.steps.append(
            _refused("preflight", _PREFLIGHT, "Ingen API-token tilgjengelig for REST-deploy")
        )
        return result
    try:
        plan = _build_rest_plan(steps, conn)
    except (ValueError, TypeError, AttributeError, IndexError, KeyError) as exc:
        result.steps.append(
            _refused("preflight", _PREFLIGHT, f"Ugyldige verdier i wizarden: {exc}")
        )
        return result

    async with FortiGateClient(
        host, api_token, port=conn["port"], vdom=conn["vdom"], verify_ssl=conn["verify_ssl"]
    ) as fg:
        result.steps = await _run_steps(_REST_STEPS, _RestDevice(fg, conn["vdom"]), plan)

    status = {s.name: s.status for s in result.steps}
    lan_applied = status["lan_address"] is StepStatus.APPLIED
    result.extra = {
        "config_summary": _config_summary(plan, status["vpn"] is StepStatus.APPLIED),
        "lan_ip_changed": lan_applied and plan.lan_ip_changed,
        "old_ip": host,
        "new_ip": plan.lan_gw,
        "customer_updated": _record_new_address(plan) if lan_applied else False,
    }
    return result

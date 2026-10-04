"""The firmware each customer device was last seen running, kept between reads.

The FortiGate poller, the UniFi firmware check, the network audit and the
network inventory all read firmware versions and judged them, and all of them
threw the answer away. Varsler could only show outdated firmware if the alert
engine had sent an alert about it, which it records only when a Teams or
e-mail channel accepted it.

Each of those readers now leaves its reading here, one row per device:

* ``current``   confirmed up to date;
* ``outdated``  a newer release exists for it;
* ``eol``       the model or branch is past end of life;
* ``unknown``   not confirmed either way: the model is not in the table, the
  table is stale, the version could not be parsed, or the device could not be
  read at all.

**A device whose read failed is never "current".** A failed read keeps the
version that was last seen, so the list can still say what it ran, but a
"current" verdict becomes "unknown": a device nobody could reach this time has
not been confirmed current. An "eol" or "outdated" verdict stays, with the
failure beside it, because those are true lower bounds: an end-of-life model
does not stop being one because the controller was down this morning.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime

from app.core.database import get_db
from app.core.rbac import customer_in_scope

log = logging.getLogger(__name__)

VENDORS = ("fortigate", "unifi")
STATUSES = ("current", "outdated", "eol", "unknown")

_COLUMNS = (
    "customer_id",
    "vendor",
    "device_key",
    "device_name",
    "model",
    "version",
    "latest",
    "status",
    "reason",
    "source",
    "read_error",
    "checked_at",
    "read_at",
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


# ── Judging a reading ───────────────────────────────────────────────────────


def unifi_reading(
    *,
    key: str,
    name: str,
    model: str,
    version: str,
    upgrade_to: str | None = None,
) -> dict:
    """A UniFi device's row, judged by the firmware table.

    The controller's own ``upgrade_to_firmware`` counts as well: when it offers
    a newer release, the device is behind whatever the table says, including
    for a model the table has never heard of.
    """
    from app.modules.unifi_audit.firmware_db import check_firmware

    if not model or not version:
        return {
            "key": key,
            "name": name,
            "model": model,
            "version": version,
            "status": "unknown",
            "reason": "version_missing",
            "latest": "",
            "source": "",
        }
    fw = check_firmware(model, version)
    if fw.get("eol"):
        status, reason = "eol", ""
    elif fw.get("up_to_date") is True:
        status, reason = "current", ""
    elif fw.get("up_to_date") is False:
        status, reason = "outdated", ""
    elif not fw.get("latest"):
        status, reason = "unknown", "model_unknown"
    elif fw.get("stale"):
        status, reason = "unknown", "table_stale"
    else:
        status, reason = "unknown", "version_unparsed"
    latest = fw.get("latest") or ""
    if upgrade_to and status in ("current", "unknown"):
        status, reason, latest = "outdated", "", str(upgrade_to)
    return {
        "key": key,
        "name": name,
        "model": fw.get("model") or model,
        "version": version,
        "status": status,
        "reason": reason,
        "latest": latest,
        "source": f"{fw.get('source', '')} {fw.get('as_of', '')}".strip(),
    }


def fortigate_reading(
    *, key: str, name: str, model: str, version: str, available: list | None
) -> dict:
    """A FortiGate's row, judged by the FortiOS life cycle and FortiGuard's list."""
    from app.modules.fortigate_audit.firmware_lifecycle import check_fortios

    verdict = check_fortios(version, available)
    return {
        "key": key,
        "name": name,
        "model": model,
        "version": version,
        "status": verdict["status"],
        "reason": verdict["reason"],
        "latest": verdict["latest"],
        "source": verdict["source"],
    }


def unread(*, key: str, name: str = "", model: str = "", error: str) -> dict:
    """A device that was there to read and could not be."""
    return {"key": key, "name": name, "model": model, "read_error": error or "read failed"}


# ── Storing ─────────────────────────────────────────────────────────────────


async def record(
    customer_id: str,
    vendor: str,
    devices: list[dict],
    *,
    complete: bool = True,
) -> None:
    """Store one read of *vendor*'s devices at *customer_id*.

    Each entry is a reading (``unifi_reading``/``fortigate_reading``) or a
    device that could not be read (``unread``). *complete* says the read listed
    every device the customer has from this vendor, so a stored device missing
    from it has gone and its row goes too.
    """
    if vendor not in VENDORS:
        raise ValueError(f"unknown vendor {vendor!r}")
    now = _now()
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM device_firmware WHERE customer_id = ? AND vendor = ?",
            (customer_id, vendor),
        ) as cur:
            existing = {r["device_key"]: dict(r) for r in await cur.fetchall()}
        keep: set[str] = set()
        for d in devices:
            key = str(d.get("key") or "").strip().lower()
            if not key:
                continue
            keep.add(key)
            old = existing.get(key)
            if d.get("read_error"):
                if old:
                    row = dict(old)
                    if row["status"] == "current":
                        row["status"], row["reason"] = "unknown", "read_failed"
                else:
                    row = {c: "" for c in _COLUMNS}
                    row.update(status="unknown", reason="read_failed", read_at=None)
                    row["device_name"] = str(d.get("name") or "")
                    row["model"] = str(d.get("model") or "")
                row["read_error"] = str(d["read_error"])[:500]
            else:
                row = {
                    "device_name": str(d.get("name") or ""),
                    "model": str(d.get("model") or ""),
                    "version": str(d.get("version") or ""),
                    "latest": str(d.get("latest") or ""),
                    "status": d.get("status") if d.get("status") in STATUSES else "unknown",
                    "reason": str(d.get("reason") or ""),
                    "source": str(d.get("source") or ""),
                    "read_error": "",
                    "read_at": now,
                }
            row.update(customer_id=customer_id, vendor=vendor, device_key=key, checked_at=now)
            await db.execute(
                f"INSERT OR REPLACE INTO device_firmware ({', '.join(_COLUMNS)}) "
                f"VALUES ({', '.join('?' for _ in _COLUMNS)})",
                tuple(row.get(c) for c in _COLUMNS),
            )
        if complete:
            for key in set(existing) - keep:
                await db.execute(
                    "DELETE FROM device_firmware "
                    "WHERE customer_id = ? AND vendor = ? AND device_key = ?",
                    (customer_id, vendor, key),
                )
        await db.commit()


async def record_read_failure(
    customer_id: str, vendor: str, error: str, *, key: str, name: str = ""
) -> None:
    """The whole read failed: the controller or firewall did not answer.

    Every device stored for this customer and vendor carries the failure, and
    none of them stays "current". With nothing stored yet, one row stands for
    the device that was configured and could not be read, so the gap shows.
    """
    async with (
        get_db() as db,
        db.execute(
            "SELECT device_key FROM device_firmware WHERE customer_id = ? AND vendor = ?",
            (customer_id, vendor),
        ) as cur,
    ):
        keys = [r["device_key"] for r in await cur.fetchall()]
    if keys:
        await record(
            customer_id,
            vendor,
            [unread(key=k, error=error) for k in keys],
            complete=False,
        )
    else:
        await record(customer_id, vendor, [unread(key=key, name=name, error=error)])


async def forget(customer_id: str, vendor: str) -> None:
    """Drop every reading of *vendor*'s devices at *customer_id*.

    For a device the customer no longer has (its FortiGate removed, its UniFi
    unlinked): nobody will read it again, so its last reading, or the failed
    read standing in for it, would stay in Varsler for good.
    """
    if vendor not in VENDORS:
        raise ValueError(f"unknown vendor {vendor!r}")
    async with get_db() as db:
        await db.execute(
            "DELETE FROM device_firmware WHERE customer_id = ? AND vendor = ?",
            (customer_id, vendor),
        )
        await db.commit()


async def record_quietly(coro_fn, *args, **kwargs) -> None:
    """Run a recorder where the caller's own answer must not depend on it.

    A poll or an audit that worked is still an answer for the person who asked
    for it, even if the database refused the reading. The failure goes to the
    log at warning level, never silently.
    """
    try:
        await coro_fn(*args, **kwargs)
    except Exception as exc:
        log.warning("Firmware reading not stored: %s", exc)


# ── Reading ─────────────────────────────────────────────────────────────────


def _customer_names() -> dict[str, str]:
    from app.core.customer import CustomerManager

    return {c.get("_id", ""): c.get("CustomerName", "") for c in CustomerManager.list_customers()}


async def list_devices(
    allowed: set[str] | None,
    customer_id: str | None = None,
    *,
    names: dict[str, str] | None = None,
) -> list[dict]:
    """Every stored device the caller may see: end of life first, then
    outdated, unknown, current. Devices of a retired customer are left out."""
    names = names if names is not None else _customer_names()
    query = "SELECT * FROM device_firmware"
    params: tuple = ()
    if customer_id is not None:
        query += " WHERE customer_id = ?"
        params = (customer_id,)
    async with get_db() as db, db.execute(query, params) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    order = {"eol": 0, "outdated": 1, "unknown": 2, "current": 3}
    out = []
    for row in rows:
        cid = row["customer_id"]
        if not customer_in_scope(cid, allowed) or cid not in names:
            continue
        row["customer_name"] = names[cid]
        out.append(row)
    out.sort(
        key=lambda r: (
            order.get(r["status"], 4),
            r["customer_name"].lower(),
            r["vendor"],
            r["device_name"].lower(),
        )
    )
    return out


async def attention(allowed: set[str] | None, names: dict[str, str] | None = None) -> list[dict]:
    """What Varsler lists: devices at end of life or behind on firmware."""
    return [
        {
            "customer_id": d["customer_id"],
            "customer_name": d["customer_name"],
            "vendor": d["vendor"],
            "device_key": d["device_key"],
            "device_name": d["device_name"] or d["device_key"],
            "model": d["model"],
            "version": d["version"],
            "latest": d["latest"],
            "status": d["status"],
            "category": "critical" if d["status"] == "eol" else "warning",
            "checked_at": d["read_at"] or d["checked_at"],
            "read_error": d["read_error"],
        }
        for d in await list_devices(allowed, names=names)
        if d["status"] in ("eol", "outdated")
    ]


def _today() -> date:
    return date.today()


def stale_tables(vendors: set[str]) -> list[dict]:
    """The firmware tables past their freshness window, for *vendors* only.

    A stale table turns every "current" verdict into "unknown" (SR-007), so a
    list full of unconfirmed devices needs this beside it to be understood.
    """
    from app.modules.fortigate_audit import firmware_lifecycle
    from app.modules.unifi_audit import firmware_db

    tables = {"fortigate": firmware_lifecycle, "unifi": firmware_db}
    today = _today()
    return [
        {"vendor": vendor, "as_of": tables[vendor].LAST_UPDATED}
        for vendor in VENDORS
        if vendor in vendors and tables[vendor].is_stale(today)
    ]


async def coverage(allowed: set[str] | None, names: dict[str, str] | None = None) -> dict:
    devices = await list_devices(allowed, names=names)
    read = [d["read_at"] for d in devices if d.get("read_at")]
    return {
        "devices": len(devices),
        "unknown": sum(1 for d in devices if d["status"] == "unknown"),
        "last_read": max(read) if read else None,
        "stale_tables": stale_tables({d["vendor"] for d in devices}),
    }


# ── The readers' side ───────────────────────────────────────────────────────


async def record_fortigate_poll(results: list[dict]) -> None:
    """Store what poll_all_fortigates found, one firewall per customer."""
    for fg in results:
        cid = fg.get("customer_id") or ""
        host = str(fg.get("host") or "").strip().lower()
        if not cid or not host:
            continue
        if fg.get("status") != "online":
            await record_read_failure(
                cid, "fortigate", str(fg.get("error") or "unreachable"), key=host, name=host
            )
            continue
        await record(
            cid,
            "fortigate",
            [
                fortigate_reading(
                    key=host,
                    name=str(fg.get("hostname") or host),
                    model=str(fg.get("model") or ""),
                    version=str(fg.get("firmware") or ""),
                    available=fg.get("firmware_available"),
                )
            ],
        )


async def record_unifi_devices(customer_id: str, devices: list[dict]) -> None:
    """Store a controller's device list (the controller API's own shape)."""
    readings = []
    for d in devices:
        mac = str(d.get("mac") or "")
        name = str(d.get("name") or d.get("hostname") or mac or "?")
        readings.append(
            unifi_reading(
                key=mac or name,
                name=name,
                model=str(d.get("model") or ""),
                version=str(d.get("version") or ""),
                upgrade_to=d.get("upgrade_to_firmware") or None,
            )
        )
    await record(customer_id, "unifi", readings)


async def refresh_all() -> dict:
    """Read every customer's firmware from where it can be read directly.

    The daily job. FortiGates through the fleet poller, which records each one
    as it goes; UniFi controllers one customer at a time. A customer reachable
    only over VPN fails here and is recorded as unread, which is the truth from
    where the hub stands; the site collector reads it over the tunnel.
    Customers in direct UniFi mode are read by the network audit, which has to
    log in to each device, and are left to it.
    """
    from app.core.credentials import get_secret
    from app.core.customer import CustomerManager
    from app.services.fortigate_api import poll_all_fortigates

    fortigates = await poll_all_fortigates()
    unifi = failed = 0
    for cust in CustomerManager.list_customers():
        cid = cust.get("_id", "")
        host = cust.get("UniFiHost")
        if not cid or not host or cust.get("UniFiMode", "controller") != "controller":
            continue
        if not (get_secret(cid, "unifi_username") and get_secret(cid, "unifi_password")):
            continue
        from app.services.unifi_api import firmware_check_all

        try:
            result = await firmware_check_all(cid)
        except Exception as exc:
            log.warning("Firmware read failed for %s: %s", cid, exc)
            failed += 1
            continue
        if result.get("unavailable"):
            failed += 1
        else:
            unifi += 1
    return {"fortigates": len(fortigates), "unifi_controllers": unifi, "unread": failed}

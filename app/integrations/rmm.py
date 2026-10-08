"""RMM deep-link: the provider interface, and how hub devices meet RMM devices.

Workshop direction (ROADMAP v0.5.0): leverage the RMM's own Web Remote rather
than building remote control. The Hub never opens a session. It finds the
RMM's record for a device the Hub already knows, and offers that record's own
Web Remote link, which the RMM serves behind its own sign-in. Nothing the Hub
holds travels in that link.

**One provider today.** ``RMMProvider`` is what a driver implements; Datto RMM
(``app/integrations/datto_rmm.py``) is the only one. Another RMM is a new
driver behind the same five methods, not a change to the routes or the page.

**Matching is exact or nothing.** A button that opens a remote session on the
wrong machine is worse than no button, so a hub device gets one only when:

* its whole name equals exactly one RMM device's host name in the customer's
  RMM site, compared without regard to letter case (as Windows and DNS compare
  host names), with no prefix, truncation or domain stripped; or, failing that,
* one of its MAC addresses identifies exactly one RMM device in that site.

Two RMM devices with the name, a MAC that finds two devices, or one RMM device
claimed by two hub devices: no button, and the page says why. A device found in
another site is not this customer's, and is ignored as if not found.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

MatchStatus = Literal["matched", "ambiguous", "not_found", "not_checked"]
MatchedBy = Literal["hostname", "mac", ""]

# The operating systems an RMM agent runs on. A phone in the hub's device list
# is not a machine anyone remotes into through the RMM, so it is not listed.
# Datto RMM's agent runs on Windows, macOS and Linux:
# https://rmm.datto.com/help/en/Content/1INTRODUCTION/Requirements/AgentRequirements.htm
_AGENT_PLATFORMS = ("windows", "mac", "linux")

# How many MAC lookups one page view may cost. Each is one RMM request, and the
# RMM's rate limit is shared with every other integration the MSP runs.
MAX_MAC_LOOKUPS = 20

_MAC_SEPARATORS = re.compile(r"[\s:.\-]")
_MAC = re.compile(r"[0-9A-F]{12}")
_NOT_A_MAC = {"000000000000", "FFFFFFFFFFFF"}


class RMMError(Exception):
    """An RMM call failed. Never an empty answer: the caller says it could not read."""


@dataclass(frozen=True)
class RMMSite:
    uid: str
    name: str


@dataclass(frozen=True)
class RMMDevice:
    uid: str
    hostname: str
    site_uid: str
    # The RMM's own link to a remote session on this device; "" when it gave none.
    web_remote_url: str
    online: bool | None
    operating_system: str


class RMMProvider(Protocol):
    """What an RMM driver offers the Hub. Every read raises RMMError on failure."""

    label: str

    async def test_connection(self) -> dict[str, Any]: ...

    async def list_sites(self) -> list[RMMSite]: ...

    async def get_site(self, site_uid: str) -> RMMSite | None: ...

    async def list_site_devices(self, site_uid: str) -> list[RMMDevice]: ...

    async def devices_by_mac(self, mac: str) -> list[RMMDevice]: ...

    async def close(self) -> None: ...


@dataclass(frozen=True)
class HubDevice:
    """A device the Hub knows for a customer, from its own records."""

    name: str
    os: str
    sources: tuple[str, ...]
    macs: tuple[str, ...] = ()


@dataclass
class DeviceMatch:
    device: HubDevice
    status: MatchStatus = "not_found"
    by: MatchedBy = ""
    rmm: RMMDevice | None = None
    # RMM devices that made the match ambiguous, for the count on the page.
    candidates: int = 0


def normalise_mac(text: str) -> str | None:
    """A MAC address as twelve upper-case hex digits, or None.

    The all-zero and broadcast addresses are placeholders, never a device.
    """
    mac = _MAC_SEPARATORS.sub("", str(text or "")).upper()
    if not _MAC.fullmatch(mac) or mac in _NOT_A_MAC:
        return None
    return mac


def _host_key(name: str) -> str:
    return str(name or "").strip().casefold()


def on_agent_platform(os_name: str) -> bool:
    low = str(os_name or "").casefold()
    return any(p in low for p in _AGENT_PLATFORMS)


def match_by_hostname(devices: Iterable[HubDevice], rmm: Iterable[RMMDevice]) -> list[DeviceMatch]:
    """Each hub device against the site's RMM devices, by whole host name."""
    by_host: dict[str, list[RMMDevice]] = {}
    for candidate in rmm:
        key = _host_key(candidate.hostname)
        if key:
            by_host.setdefault(key, []).append(candidate)
    out: list[DeviceMatch] = []
    for device in devices:
        found = by_host.get(_host_key(device.name), [])
        if len(found) == 1:
            out.append(DeviceMatch(device, "matched", "hostname", found[0]))
        elif found:
            out.append(DeviceMatch(device, "ambiguous", "hostname", candidates=len(found)))
        else:
            out.append(DeviceMatch(device))
    return out


async def match_by_mac(
    matches: list[DeviceMatch],
    provider: RMMProvider,
    site_uid: str,
    *,
    limit: int = MAX_MAC_LOOKUPS,
) -> None:
    """Try the MACs of the devices no host name found, in place.

    Only devices still not found are looked up, and at most ``limit`` lookups
    are spent; a device past the limit reads "not checked", not "not found".
    """
    spent = 0
    for match in matches:
        if match.status != "not_found" or not match.device.macs:
            continue
        if spent + len(match.device.macs) > limit:
            match.status = "not_checked"
            continue
        uids: dict[str, RMMDevice] = {}
        for mac in match.device.macs:
            spent += 1
            for candidate in await provider.devices_by_mac(mac):
                if candidate.site_uid == site_uid:
                    uids[candidate.uid] = candidate
        if len(uids) == 1:
            match.status, match.by, match.rmm = "matched", "mac", next(iter(uids.values()))
        elif uids:
            match.status, match.by, match.candidates = "ambiguous", "mac", len(uids)


def claim_once(matches: list[DeviceMatch]) -> None:
    """One RMM device answers for one hub device. Two claims cancel both."""
    claims: dict[str, list[DeviceMatch]] = {}
    for match in matches:
        if match.status == "matched" and match.rmm is not None:
            claims.setdefault(match.rmm.uid, []).append(match)
    for claimed in claims.values():
        if len(claimed) > 1:
            for match in claimed:
                match.status, match.rmm, match.candidates = "ambiguous", None, len(claimed)

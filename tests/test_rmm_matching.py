"""Hub devices meet RMM devices: exact or nothing (TODO D19).

A Web Remote button on the wrong machine opens a session on somebody else's
computer. So a hub device gets one only for a whole-name match on exactly one
RMM device in the customer's site, or a MAC address that finds exactly one.
These tests pin each way a near miss could have become a button.
"""

from __future__ import annotations

import pytest

from app.integrations.rmm import (
    HubDevice,
    RMMDevice,
    claim_once,
    match_by_hostname,
    match_by_mac,
    normalise_mac,
)


def _hub(name: str, *macs: str, os: str = "Windows") -> HubDevice:
    return HubDevice(name=name, os=os, sources=("intune",), macs=tuple(macs))


def _rmm(uid: str, hostname: str, site: str = "site-a") -> RMMDevice:
    return RMMDevice(
        uid=uid,
        hostname=hostname,
        site_uid=site,
        web_remote_url=f"https://rmm.example/remote/{uid}",
        online=True,
        operating_system="Windows",
    )


class _Provider:
    """devices_by_mac from a table, counting the lookups."""

    label = "Fake RMM"

    def __init__(self, by_mac: dict[str, list[RMMDevice]]) -> None:
        self.by_mac = by_mac
        self.asked: list[str] = []

    async def devices_by_mac(self, mac: str) -> list[RMMDevice]:
        self.asked.append(mac)
        return self.by_mac.get(mac, [])


def test_the_whole_name_matches_whatever_its_case():
    """Windows and DNS compare host names without case; so does the match."""
    [match] = match_by_hostname([_hub("pc-01")], [_rmm("d1", "PC-01"), _rmm("d2", "PC-02")])

    assert (match.status, match.by, match.rmm.uid) == ("matched", "hostname", "d1")


@pytest.mark.parametrize(
    "rmm_name",
    ["PC-0", "PC-010", "PC-01.acme.example", "PC 01", " ", ""],
    ids=["prefix", "longer", "with-domain", "space-for-dash", "blank", "empty"],
)
def test_a_near_name_is_no_match(rmm_name):
    """No prefix, truncation or domain stripping: a near name is another machine."""
    [match] = match_by_hostname([_hub("PC-01")], [_rmm("d1", rmm_name)])

    assert match.status == "not_found" and match.rmm is None


def test_two_rmm_devices_with_the_name_give_no_button():
    [match] = match_by_hostname([_hub("PC-01")], [_rmm("d1", "PC-01"), _rmm("d2", "pc-01")])

    assert (match.status, match.rmm, match.candidates) == ("ambiguous", None, 2)


async def test_a_mac_finds_the_device_the_name_did_not():
    """A Mac's device name is not its host name; its Wi-Fi address is the same."""
    matches = match_by_hostname([_hub("Kari's MacBook", "0A1B2C3D4E5F", os="macOS")], [])
    provider = _Provider({"0A1B2C3D4E5F": [_rmm("d9", "Karis-MacBook")]})

    await match_by_mac(matches, provider, "site-a")

    assert (matches[0].status, matches[0].by, matches[0].rmm.uid) == ("matched", "mac", "d9")


async def test_a_mac_found_in_another_customers_site_is_not_this_customers():
    """The lookup searches the whole account; only the customer's site counts."""
    matches = match_by_hostname([_hub("PC-01", "0A1B2C3D4E5F")], [])
    provider = _Provider({"0A1B2C3D4E5F": [_rmm("d7", "PC-01", site="site-b")]})

    await match_by_mac(matches, provider, "site-a")

    assert matches[0].status == "not_found" and matches[0].rmm is None


async def test_a_mac_that_finds_two_devices_gives_no_button():
    matches = match_by_hostname([_hub("PC-01", "0A1B2C3D4E5F", "0A1B2C3D4E60")], [])
    provider = _Provider({"0A1B2C3D4E5F": [_rmm("d1", "A")], "0A1B2C3D4E60": [_rmm("d2", "B")]})

    await match_by_mac(matches, provider, "site-a")

    assert (matches[0].status, matches[0].candidates) == ("ambiguous", 2)


async def test_a_device_the_name_found_costs_no_lookup():
    matches = match_by_hostname([_hub("PC-01", "0A1B2C3D4E5F")], [_rmm("d1", "PC-01")])
    provider = _Provider({})

    await match_by_mac(matches, provider, "site-a")

    assert provider.asked == []


async def test_lookups_past_the_limit_are_not_checked_rather_than_not_found():
    """The RMM's rate limit is shared; a device not looked up is not "absent"."""
    devices = [_hub(f"MAC-{i}", f"0A1B2C3D4E{i:02X}") for i in range(4)]
    matches = match_by_hostname(devices, [])
    provider = _Provider({})

    await match_by_mac(matches, provider, "site-a", limit=2)

    assert [m.status for m in matches] == ["not_found", "not_found", "not_checked", "not_checked"]
    assert len(provider.asked) == 2


async def test_a_refused_mac_lookup_leaves_the_name_matches_standing():
    """One refused lookup must not cost the page the matches it already has."""
    from app.integrations.rmm import RMMError

    class _Refusing(_Provider):
        async def devices_by_mac(self, mac: str) -> list[RMMDevice]:
            self.asked.append(mac)
            raise RMMError("refused (403)")

    devices = [_hub("PC-01"), _hub("MAC-1", "0A1B2C3D4E5F"), _hub("MAC-2", "0A1B2C3D4E60")]
    matches = match_by_hostname(devices, [_rmm("d1", "PC-01")])
    provider = _Refusing({})

    await match_by_mac(matches, provider, "site-a")

    assert [m.status for m in matches] == ["matched", "not_checked", "not_checked"]
    assert len(provider.asked) == 1, "no more lookups after a refusal"


def test_one_rmm_device_claimed_by_two_hub_devices_cancels_both():
    matches = match_by_hostname([_hub("PC-01"), _hub("PC-02")], [_rmm("d1", "PC-01")])
    matches[1].status, matches[1].by, matches[1].rmm = "matched", "mac", matches[0].rmm

    claim_once(matches)

    assert [(m.status, m.rmm) for m in matches] == [("ambiguous", None), ("ambiguous", None)]


@pytest.mark.parametrize(
    ("raw", "normal"),
    [
        ("0a:1b:2c:3d:4e:5f", "0A1B2C3D4E5F"),
        ("0A-1B-2C-3D-4E-5F", "0A1B2C3D4E5F"),
        ("0a1b.2c3d.4e5f", "0A1B2C3D4E5F"),
        ("00:00:00:00:00:00", None),
        ("ff:ff:ff:ff:ff:ff", None),
        ("0a:1b:2c:3d:4e", None),
        ("not a mac", None),
        ("", None),
    ],
)
def test_a_mac_address_is_twelve_hex_digits_or_nothing(raw, normal):
    assert normalise_mac(raw) == normal


# ── The hub's own device list ─────────────────────────────────────────────────


def _run(tmp_path, intune=None, entra=None):
    from app.core.encryption import encrypted_write_json

    run = tmp_path / "2026-10-01_120000"
    run.mkdir()
    if intune is not None:
        encrypted_write_json(run / "10_intune_devices.json", {"devices": intune})
    if entra is not None:
        encrypted_write_json(run / "15_entra_devices.json", {"devices": entra})
    return run


def test_intune_and_entra_merge_by_name_and_phones_are_left_out(tmp_path):
    """One row per machine, its sources named; a phone is no RMM agent's."""
    from app.services.rmm_devices import hub_devices

    run = _run(
        tmp_path,
        intune=[
            {"name": "PC-01", "os": "Windows", "wifi_mac": "0a:1b:2c:3d:4e:5f"},
            {"name": "Kari iPhone", "os": "iOS", "wifi_mac": "0a:1b:2c:3d:4e:60"},
        ],
        entra=[
            {"name": "pc-01", "os": "Windows"},
            {"name": "SRV-01", "os": "Windows Server"},
            {"name": "Kari MacBook", "os": "MacMDM"},
        ],
    )

    devices = hub_devices(run)

    assert [(d.name, d.sources, d.macs) for d in devices] == [
        ("Kari MacBook", ("entra",), ()),
        ("PC-01", ("intune", "entra"), ("0A1B2C3D4E5F",)),
        ("SRV-01", ("entra",), ()),
    ]


def test_a_run_without_either_list_has_no_list_rather_than_an_empty_one(tmp_path):
    from app.services.rmm_devices import hub_devices

    assert hub_devices(_run(tmp_path)) is None


def test_a_run_from_before_the_mac_was_kept_still_matches_by_name(tmp_path):
    """Older Intune sidecars have no wifi_mac; their devices have no MAC, no error."""
    from app.services.rmm_devices import hub_devices

    devices = hub_devices(_run(tmp_path, intune=[{"name": "PC-01", "os": "Windows"}]))

    assert [(d.name, d.macs) for d in devices] == [("PC-01", ())]

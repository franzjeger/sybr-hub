"""The UniFi firmware table, refreshed from Ubiquiti's own sources on 2026-10-04.

It had not been touched since 2026-03-30, so from 2026-09-26 every device at
its newest version read "unknown". Worse, much of it had never been right: the
U7 line was listed at 7.0.97 (it is on 8.7.11), USW-Flex-Mini at 2.8.4 (2.1.6
is the newest there is), every gateway at 4.0.21 (UniFi OS is at 5.1.33), and
it was keyed by product names while a controller reports model codes (U7PG2,
UAP6MP, US24P250), so a controller's devices mostly read "model unknown". A
SmartPower plug (UP1) was aliased to U6-Mesh and judged as an access point.

These pin the refreshed data: a device on the newest Official release is
current, one behind is outdated, a Legacy model is EOL and a Vintage one is
not, codes and product names land on the same row, and every family says where
its version came from. All verdicts use a frozen clock.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.modules.unifi_audit import firmware_db as fdb
from app.services import firmware_inventory

FRESH = date(2026, 10, 6)  # two days after the table was checked
STALE = date(2027, 6, 1)  # past FRESHNESS_DAYS


def test_the_table_was_checked_on_the_refresh_day():
    assert fdb.LAST_UPDATED == "2026-10-04"
    assert not fdb.is_stale(FRESH)
    assert fdb.is_stale(STALE)


# One model per firmware line, at the newest Official release on it.
NEWEST = [
    ("U6-Pro", "6.8.2"),
    ("UAP-AC-Pro", "6.8.2"),
    ("U6-Lite", "6.7.57"),
    ("UAP-nanoHD", "6.7.57"),
    ("U6+", "6.7.54"),
    ("U7-Pro", "8.7.11"),
    ("E7", "8.7.11"),
    ("U7-LR", "8.0.76"),
    ("USW-24-PoE", "7.5.15"),
    ("US-24-250W", "7.5.15"),
    ("USW-Flex-Mini", "2.1.6"),
    ("USW-Ultra", "2.1.8"),
    ("UDM-Pro", "5.1.33"),
    ("UCG-Ultra", "5.1.33"),
    ("UX", "4.0.21"),
    ("UXG-Lite", "5.1.26"),
]


@pytest.mark.parametrize(("model", "version"), NEWEST)
def test_a_device_on_the_newest_official_release_is_current(model, version):
    r = fdb.check_firmware(model, version, today=FRESH)
    assert r["latest"] == version
    assert r["severity"] == "ok" and r["up_to_date"] is True


@pytest.mark.parametrize(
    ("model", "version", "severity"),
    [
        ("U6-Pro", "6.6.77", "warning"),  # the old table's "latest"
        ("U7-Pro", "8.6.11", "warning"),
        ("U7-Pro", "7.0.97", "critical"),  # the old table's "latest"
        ("USW-24-PoE", "7.4.1", "warning"),
        ("USW-24-PoE", "6.6.77", "critical"),
        ("UDM-Pro", "4.0.21", "critical"),  # the old table's "latest"
        ("UXG-Lite", "4.1.13", "critical"),
    ],
)
def test_a_device_behind_the_newest_release_is_outdated(model, version, severity):
    r = fdb.check_firmware(model, version, today=FRESH)
    assert r["up_to_date"] is False and r["eol"] is False
    assert r["severity"] == severity


def test_a_device_on_a_release_candidate_newer_than_official_is_current():
    # 8.0.77 for U7-LR is a Release Candidate; the device is ahead, not behind.
    assert fdb.check_firmware("U7-LR", "8.0.77", today=FRESH)["severity"] == "ok"


@pytest.mark.parametrize(
    "model",
    ["UAP", "UAP-LR", "UAP-Pro", "UAP-AC-EDU", "UAP-AC-IW-Pro", "UAP-AC", "USG", "USG-PRO-4"],
)
def test_a_legacy_model_is_end_of_life(model):
    """Legacy on help.ui.com: no more updates. EOL whatever it runs, even from
    a stale table, and also for UAP-AC, which the feed no longer lists at all."""
    for today in (FRESH, STALE):
        r = fdb.check_firmware(model, "9.9.9", today=today)
        assert r["eol"] is True and r["severity"] == "critical" and r["up_to_date"] is False


@pytest.mark.parametrize("model", ["US-L2-24-PoE", "USW-Enterprise-8-PoE", "UAP-AC-Pro"])
def test_a_vintage_or_still_updated_model_is_not_end_of_life(model):
    """Vintage still gets critical bug and security fixes; UAP-AC-Pro got 6.8.2
    in February 2026. Calling either EOL would tell a customer to replace
    hardware Ubiquiti still supports."""
    r = fdb.check_firmware(model, "1.0.0", today=FRESH)
    assert r["eol"] is False


def test_the_inventory_reading_follows_the_new_data(monkeypatch):
    monkeypatch.setattr(fdb, "_today", lambda: FRESH)
    current = firmware_inventory.unifi_reading(key="a", name="AP", model="U7PRO", version="8.7.11")
    behind = firmware_inventory.unifi_reading(key="b", name="SW", model="USL24P", version="7.4.1")
    eol = firmware_inventory.unifi_reading(key="c", name="GW", model="UGW3", version="4.4.57")
    assert (current["status"], current["model"]) == ("current", "U7-Pro")
    assert (behind["status"], behind["latest"], behind["model"]) == (
        "outdated",
        "7.5.15",
        "USW-24-PoE",
    )
    assert (eol["status"], eol["model"]) == ("eol", "USG-3P")


@pytest.mark.parametrize(
    ("names", "code"),
    [
        (("U7PG2", "UAP-AC-Pro", "UAP-AC-Pro-Gen2", "uap-ac-pro"), "U7PG2"),
        (("UAP6MP", "U6-Pro"), "UAP6MP"),
        (("US24P250", "US-24-250W", "S224250"), "US24P250"),
        (("UDMPRO", "UDM-Pro"), "UDMPRO"),
        (("UDMPROSE", "UDM-SE", "UDM-PRO-SE"), "UDMPROSE"),
    ],
)
def test_a_controller_code_and_a_product_name_land_on_the_same_row(names, code):
    """A controller reports the code; a device read directly reports its board
    name. Both have to find the model."""
    for name in names:
        assert fdb.normalize_model(name) == code


def test_a_product_name_with_two_firmware_lines_is_not_guessed():
    """U6-Mesh is U6M (6.8.2) or UAM6 (6.7.57). Judging "U6-Mesh" 6.7.57
    against 6.8.2 would call a current device behind; it reads unknown, while
    each code is judged on its own line."""
    for name in ("U6-Mesh", "U6-IW", "U6-Extender"):
        assert name.lower() in fdb.AMBIGUOUS_NAMES
        assert fdb.check_firmware(name, "6.7.57", today=FRESH)["severity"] == "unknown"
    assert fdb.check_firmware("UAM6", "6.7.57", today=FRESH)["severity"] == "ok"
    assert fdb.check_firmware("U6M", "6.7.57", today=FRESH)["up_to_date"] is False


@pytest.mark.parametrize(
    ("model", "version"),
    [
        ("UP1", "2.2.6"),  # SmartPower Plug, was aliased to U6-Mesh
        ("UP6", "2.2.6"),  # SmartPower Strip, was aliased to U6-Enterprise
    ],
)
def test_a_device_that_is_not_an_access_point_is_not_judged_as_one(model, version):
    r = fdb.check_firmware(model, version, today=FRESH)
    assert r["severity"] == "unknown" and r["latest"] is None


def test_a_longer_model_name_is_not_matched_by_its_prefix():
    # USW-Flex-2.5G-5 runs 2.x firmware. Prefix matching sent it to USW-Flex
    # (7.x) and called it a major version behind.
    r = fdb.check_firmware("USW-Flex-2.5G-5", "2.1.8", today=FRESH)
    assert r["model"] == "USW-Flex-2.5G-5" and r["severity"] == "ok"
    assert fdb.check_firmware("USW-Flex-Unknown-9", "7.5.15", today=FRESH)["latest"] is None


def test_u2s48_is_the_first_access_point_not_a_pro_switch():
    # Ubiquiti's catalog files U2S48 under UAP; it used to alias USW-Pro-48.
    r = fdb.check_firmware("U2S48", "4.3.28", today=FRESH)
    assert r["model"] == "UAP" and r["eol"] is True


def test_every_family_says_where_its_version_came_from():
    for family in fdb._FAMILIES:
        assert family["source"].startswith("https://"), family
        if family.get("eol"):
            continue
        # Only an end-of-life family may lack a version: it has none to give.
        assert fdb._extract_version(family["latest"]), family


def test_every_model_code_is_in_one_family_only():
    codes = [code for family in fdb._FAMILIES for code in family["models"]]
    assert len(codes) == len(set(codes))
    assert len(fdb.FIRMWARE_DB) == len(codes)

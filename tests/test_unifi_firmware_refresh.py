"""scripts/refresh_unifi_firmware.py brings the UniFi table up to Ubiquiti's feed.

The table went stale once already (2026-09-26) because refreshing it was an
hour of reading a feed by hand. The script reads it for every code; these
tests hold what it may and may not do with what it reads. It records a newer
release-channel version for a code and dates the table, and nothing else: no
Release Candidate, no version for a model the table does not have (power
devices, SmartPower, LTE, Cloud Keys and AirWire stay unknown unless a person
adds them), never an end-of-life model's, never a version older than the one
the table was checked at (UXG-Pro's old code stops at 1.13.8 in the feed and is
judged against 5.1.26 on purpose), and never from an answer it does not
understand or that is one page of several.

The feed is never called. FEED below is hand-written in the feed's shape
(HAL JSON, ``_embedded.firmware``); the shape itself needs checking against a
live answer before the script is first relied on.
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import pathlib
import sys

import pytest

from app.modules.unifi_audit import firmware_db as fdb

_spec = importlib.util.spec_from_file_location(
    "refresh_unifi_firmware", pathlib.Path("scripts/refresh_unifi_firmware.py")
)
refresh = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = refresh  # its dataclasses look themselves up there
_spec.loader.exec_module(refresh)


def _build(platform, version, *, channel="release", product="unifi-firmware", created=None):
    """One entry of _embedded.firmware, as the feed lists a build."""
    major, minor, patch = (int(n) for n in version.split("+")[0].lstrip("v").split(".")[:3])
    return {
        "_links": {"data": {"href": f"https://dl.ui.example/{platform}/{version}.bin"}},
        "id": f"build-{platform}-{version}",
        "channel": channel,
        "product": product,
        "platform": platform,
        "version": version,
        "version_major": major,
        "version_minor": minor,
        "version_patch": patch,
        "created": created or "2026-09-01T08:00:00+00:00",
        "updated": created or "2026-09-01T08:00:00+00:00",
        "file_size": 1,
        "sha256_checksum": "0" * 64,
    }


def _answer(builds):
    return {
        "_links": {"self": {"href": "https://fw-update.ui.example/api/firmware-latest"}},
        "_embedded": {"firmware": builds},
    }


def _every_code_at_its_family():
    """A build for every code the table judges, at the version it was checked at."""
    builds = []
    for family in fdb._FAMILIES:
        if family.get("eol"):
            continue
        for code in family["models"]:
            builds.append(_build(code, "v" + family["latest"] + "+10000.260901.0800"))
    return builds


# The feed today, as the tests have it: every code where the table has it, then
# what moved since.
FEED = _answer(
    [b for b in _every_code_at_its_family() if b["platform"] not in ("U7PG2", "UXGPRO", "UDMPRO")]
    + [
        # U7PG2 moved on; the rest of its family did not (yet).
        _build("U7PG2", "v6.8.5+15800.261020.0900", created="2026-10-20T09:00:00+00:00"),
        _build("U7PG2", "v6.8.9+15900.261101.0900", channel="beta"),  # never latest
        _build("U7PG2", "v6.8.7+15850.261028.0900", channel="rc"),  # nor this
        # UXG-Pro's old code stopped at 1.13.8; the table judges it at 5.1.26.
        _build("UXGPRO", "v1.13.8+4567.220101.0000", product="unifi-dream"),
        # Listed under both products; the newer build wins.
        _build("UDMPRO", "v5.1.33+1.260910.0000", product="unifi-dream"),
        _build(
            "UDMPRO",
            "v5.1.40+1.261015.0000",
            product="unifi-dream",
            created="2026-10-15T00:00:00+00:00",
        ),
        _build("UDMPRO", "v5.1.20+1.260801.0000"),
        # A Legacy model that should get nothing, and does here.
        _build("UGW3", "v4.4.60+1.261001.0000"),
        # Not in the table: a SmartPower plug. It stays unknown.
        _build("UP1", "v2.2.9+1.261001.0000"),
        # Not a build this script reads.
        _build("UAP6MP", "v9.0.0+1.261001.0000", product="unifi-protect"),
    ]
)


def _write(tmp_path, name, payload):
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _load(path):
    spec = importlib.util.spec_from_file_location(f"refreshed_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def table(tmp_path):
    copy = tmp_path / "firmware_db.py"
    copy.write_text(pathlib.Path(fdb.__file__).read_text(encoding="utf-8"), encoding="utf-8")
    return copy


# ── Reading the feed ─────────────────────────────────────────────────────────


def test_only_the_newest_release_channel_build_counts():
    feed = refresh.read_feed(FEED)
    assert feed["U7PG2"] == refresh.Release((6, 8, 5), "2026-10-20")
    assert feed["UDMPRO"].text == "5.1.40"
    assert "UAP6MP" in feed and feed["UAP6MP"].text == "6.8.2"  # the protect build was skipped


@pytest.mark.parametrize(
    "answer",
    [
        [],
        {"firmware": []},
        {"_embedded": {"firmware": {"U7PG2": "6.8.2"}}},
        {"_embedded": {"firmware": ["U7PG2"]}},
        # One page of several: refreshing from part of the feed would date
        # the table with codes never checked.
        {**_answer([]), "_links": {"next": {"href": "https://fw-update.ui.example/?page=2"}}},
    ],
)
def test_an_answer_it_does_not_understand_stops_it(answer):
    with pytest.raises(refresh.FeedError):
        refresh.read_feed(answer)


# ── What it records ──────────────────────────────────────────────────────────


def test_it_records_only_what_is_newer_and_reports_the_rest():
    report = refresh.compare(refresh.read_feed(FEED))
    assert {c: r.text for c, r in report.newer.items()} == {"U7PG2": "6.8.5", "UDMPRO": "5.1.40"}
    assert set(report.older) == {"UXGPRO"}
    assert set(report.eol_updated) == {"UGW3"}
    assert set(report.not_in_table) == {"UP1"}
    assert report.missing == []


def test_writing_moves_the_codes_on_and_dates_the_table(tmp_path, table):
    feed = _write(tmp_path, "feed.json", FEED)
    assert refresh.main(["--feed", str(feed), "--table", str(table)]) == 1  # behind
    assert refresh.main(["--feed", str(feed), "--table", str(table), "--write"]) == 0
    new = _load(table)

    assert datetime.date.today().isoformat() == new.LAST_UPDATED
    assert new._NEWER_IN_FEED == {"U7PG2": "6.8.5", "UDMPRO": "5.1.40"}
    # The moved code is judged against the feed; the rest of its family is not.
    assert new.check_firmware("U7PG2", "6.8.2")["up_to_date"] is False
    assert new.check_firmware("U7PG2", "6.8.5")["severity"] == "ok"
    assert new.check_firmware("U7LT", "6.8.2")["severity"] == "ok"
    assert new.FIRMWARE_DB["U7PG2"]["source"].endswith("~~platform~~U7PG2")
    # The table's own knowledge stands.
    assert new.check_firmware("UXGPRO", "1.13.8")["up_to_date"] is False
    assert new.check_firmware("UGW3", "4.4.60")["eol"] is True
    assert new.check_firmware("UP1", "2.2.9")["severity"] == "unknown"
    assert new.check_firmware("UP1", "2.2.9")["latest"] is None
    # And a second run finds nothing more to do.
    assert refresh.main(["--feed", str(feed), "--table", str(table)]) == 0


def test_it_changes_nothing_in_the_table_but_the_block_and_the_date(tmp_path, table):
    before = table.read_text(encoding="utf-8")
    feed = _write(tmp_path, "feed.json", FEED)
    refresh.main(["--feed", str(feed), "--table", str(table), "--write"])
    after = table.read_text(encoding="utf-8")

    def outside(text):
        head, rest = text.split(refresh.BEGIN)
        return refresh._LAST_UPDATED.sub("", head) + rest.split(refresh.END)[1]

    assert outside(after) == outside(before)


def test_a_version_its_family_caught_up_with_leaves_the_block(tmp_path, table):
    moved = _write(tmp_path, "moved.json", FEED)
    refresh.main(["--feed", str(moved), "--table", str(table), "--write"])
    # The feed is back at the family's version (a pulled release, or the family
    # was brought up by hand): the entry has to go, or it would outlive it.
    back = _write(tmp_path, "back.json", _answer(_every_code_at_its_family()))
    refresh.main(["--feed", str(back), "--table", str(table), "--write"])
    assert _load(table)._NEWER_IN_FEED == {}


def test_a_code_missing_from_the_feed_stops_the_dating(tmp_path, table, capsys):
    builds = [b for b in _every_code_at_its_family() if b["platform"] != "U7LT"]
    feed = _write(tmp_path, "feed.json", _answer(builds))
    before = table.read_text(encoding="utf-8")

    assert refresh.main(["--feed", str(feed), "--table", str(table), "--write"]) == 2
    assert table.read_text(encoding="utf-8") == before
    assert "U7LT" in capsys.readouterr().out

    assert (
        refresh.main(["--feed", str(feed), "--table", str(table), "--write", "--accept-missing"])
        == 0
    )
    assert datetime.date.today().isoformat() == _load(table).LAST_UPDATED


def test_both_products_are_read_and_merged(tmp_path, table):
    devices = [b for b in FEED["_embedded"]["firmware"] if b["product"] == "unifi-firmware"]
    consoles = [b for b in FEED["_embedded"]["firmware"] if b["product"] == "unifi-dream"]
    paths = [
        _write(tmp_path, "a.json", _answer(devices)),
        _write(tmp_path, "b.json", _answer(consoles)),
    ]
    args = [a for p in paths for a in ("--feed", str(p))]
    assert refresh.main([*args, "--table", str(table), "--write"]) == 0
    assert _load(table)._NEWER_IN_FEED == {"U7PG2": "6.8.5", "UDMPRO": "5.1.40"}


def test_a_bad_answer_writes_nothing(tmp_path, table):
    before = table.read_text(encoding="utf-8")
    feed = _write(tmp_path, "feed.json", {"error": "rate limited"})
    assert refresh.main(["--feed", str(feed), "--table", str(table), "--write"]) == 2
    assert table.read_text(encoding="utf-8") == before


# ── The block in the shipped table ───────────────────────────────────────────


def test_the_shipped_block_holds_only_newer_versions_of_codes_it_judges():
    """What a refresh may put there; a hand edit that breaks it fails here."""
    families = {code: f for f in fdb._FAMILIES for code in f["models"]}
    for code, version in fdb._NEWER_IN_FEED.items():
        family = families[code]
        assert not family.get("eol"), code
        assert fdb._extract_version(version) > fdb._extract_version(family["latest"]), code


def test_the_shipped_table_has_what_the_script_writes_to():
    source = pathlib.Path(fdb.__file__).read_text(encoding="utf-8")
    assert source.count(refresh.BEGIN) == source.count(refresh.END) == 1
    assert len(refresh._LAST_UPDATED.findall(source)) == 1
    # Rewriting it with what it holds changes only the date.
    newer = {c: refresh.Release(fdb._extract_version(v), "") for c, v in fdb._NEWER_IN_FEED.items()}
    rewritten = refresh.rewrite(source, newer, datetime.date.fromisoformat(fdb.LAST_UPDATED))
    if not newer:
        assert rewritten == source

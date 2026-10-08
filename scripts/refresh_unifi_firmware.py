#!/usr/bin/env python3
"""Refresh the UniFi firmware table from Ubiquiti's firmware feed.

``app/modules/unifi_audit/firmware_db.py`` is kept by hand and trusted for 180
days; after that every device on its newest known version reads "unknown"
(SR-007). This does the part of keeping it that a person should not have to:
it asks fw-update.ui.com, the feed the UniFi Network application itself asks,
for the newest release (Official) build of every model code, and compares it
with the table.

    python scripts/refresh_unifi_firmware.py            # report only
    python scripts/refresh_unifi_firmware.py --write    # and update the table
    python scripts/refresh_unifi_firmware.py --feed firmware.json --feed dream.json

``--write`` records every version the feed has that is newer than its
family's in the table's ``_NEWER_IN_FEED`` block, drops entries a family has
caught up with, and sets ``LAST_UPDATED`` to today. It changes nothing else:
the families, their names, end-of-life flags and release-notes links are a
person's, and so is a model the table does not have, which needs a product
name and an end-of-life check before it can be judged. The report lists
those. It refuses to date the table while a code the table judges is missing
from the feed, unless ``--accept-missing`` says a person checked those by
hand: a table dated today has to have had every version in it checked today.

The feed says nothing about end of life. Before committing, compare Ubiquiti's
"Vintage and Legacy Products" list (``firmware_db._EOL_LIST``), and update
``tests/test_unifi_firmware_table.py``, which pins the date and the versions.

The feed's answer is HAL JSON: ``_embedded.firmware`` is a list of builds, each
with ``platform`` (the model code a controller reports), ``product``,
``channel``, ``version`` ("v6.8.2+15592...") and ``created``. Only builds on
the release channel count; a Release Candidate or Early Access build is never
"latest". An answer of any other shape, or one that says it has another page,
stops the script rather than refreshing from part of the feed.
"""

from __future__ import annotations

import argparse
import datetime
import importlib
import json
import pathlib
import re
import sys
from dataclasses import dataclass, field

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Imported once the checkout is on the path, which is why not at the top.
firmware_db = importlib.import_module("app.modules.unifi_audit.firmware_db")

TABLE = ROOT / "app" / "modules" / "unifi_audit" / "firmware_db.py"

# The two products the table's codes are filed under: UniFi devices, and the
# UniFi OS consoles and gateways.
PRODUCTS = ("unifi-firmware", "unifi-dream")
FEED_URLS = tuple(
    "https://fw-update.ui.com/api/firmware-latest"
    f"?filter=eq~~product~~{product}&filter=eq~~channel~~release"
    for product in PRODUCTS
)

BEGIN = "# BEGIN refresh_unifi_firmware\n"
END = "# END refresh_unifi_firmware\n"
_LAST_UPDATED = re.compile(r'^LAST_UPDATED = "[^"]*"$', re.MULTILINE)

Version = tuple[int, int, int]


class FeedError(Exception):
    """The feed's answer is not one this script can refresh the table from."""


@dataclass(frozen=True)
class Release:
    version: Version
    released: str  # the day the build was published, or ""

    @property
    def text(self) -> str:
        return ".".join(str(n) for n in self.version)


def _version(build: dict) -> Version | None:
    parsed = firmware_db._extract_version(str(build.get("version") or ""))
    if parsed:
        return parsed
    parts = [build.get(k) for k in ("version_major", "version_minor", "version_patch")]
    if all(isinstance(p, int) for p in parts):
        return (parts[0], parts[1], parts[2])
    return None


def read_feed(answer: object) -> dict[str, Release]:
    """{model code: its newest release-channel build} from one feed answer."""
    if not isinstance(answer, dict):
        raise FeedError("the answer is not a JSON object")
    links = answer.get("_links")
    if isinstance(links, dict) and links.get("next"):
        raise FeedError("the answer is one page of several; this script reads a single page")
    builds = (answer.get("_embedded") or {}).get("firmware")
    if not isinstance(builds, list):
        raise FeedError("the answer has no _embedded.firmware list")
    newest: dict[str, Release] = {}
    for build in builds:
        if not isinstance(build, dict):
            raise FeedError("a firmware entry is not an object")
        if build.get("channel") != "release" or build.get("product") not in PRODUCTS:
            continue
        code = build.get("platform")
        version = _version(build)
        if not isinstance(code, str) or not code or version is None:
            continue
        release = Release(version, str(build.get("created") or "")[:10])
        if code not in newest or release.version > newest[code].version:
            newest[code] = release
    return newest


def merge(*feeds: dict[str, Release]) -> dict[str, Release]:
    """One code may be listed under both products; the newest build wins."""
    merged: dict[str, Release] = {}
    for feed in feeds:
        for code, release in feed.items():
            if code not in merged or release.version > merged[code].version:
                merged[code] = release
    return merged


@dataclass
class Report:
    """What the feed says about the table."""

    newer: dict[str, Release] = field(default_factory=dict)  # recorded by --write
    older: dict[str, Release] = field(default_factory=dict)  # kept: the table knows better
    missing: list[str] = field(default_factory=list)  # judged by the table, absent from the feed
    eol_updated: dict[str, Release] = field(default_factory=dict)  # Legacy, yet a newer build
    not_in_table: dict[str, Release] = field(default_factory=dict)  # for a person to add


def compare(feed: dict[str, Release]) -> Report:
    report = Report()
    known: set[str] = set()
    for family in firmware_db._FAMILIES:
        checked = firmware_db._extract_version(family["latest"])
        for code in family["models"]:
            known.add(code)
            release = feed.get(code)
            if family.get("eol"):
                if release and (checked is None or release.version > checked):
                    report.eol_updated[code] = release
                continue
            if release is None:
                report.missing.append(code)
            elif checked is None or release.version > checked:
                report.newer[code] = release
            elif release.version < checked:
                report.older[code] = release
    report.not_in_table = {c: r for c, r in feed.items() if c not in known}
    return report


def render_block(newer: dict[str, Release]) -> str:
    """The table's _NEWER_IN_FEED block, markers included."""
    if not newer:
        return BEGIN + "_NEWER_IN_FEED: dict[str, str] = {}\n" + END
    lines = [BEGIN, "_NEWER_IN_FEED: dict[str, str] = {\n"]
    for code in sorted(newer):
        release = newer[code]
        note = f"  # released {release.released}" if release.released else ""
        lines.append(f'    "{code}": "{release.text}",{note}\n')
    lines += ["}\n", END]
    return "".join(lines)


def rewrite(source: str, newer: dict[str, Release], today: datetime.date) -> str:
    """The table's source with the block and LAST_UPDATED brought up to the feed."""
    start, end = source.find(BEGIN), source.find(END)
    if start < 0 or end < start:
        raise SystemExit(f"{TABLE.name} has no {BEGIN.strip()} ... {END.strip()} block")
    source = source[:start] + render_block(newer) + source[end + len(END) :]
    source, count = _LAST_UPDATED.subn(f'LAST_UPDATED = "{today.isoformat()}"', source)
    if count != 1:
        raise SystemExit(f"{TABLE.name} has no single LAST_UPDATED line")
    return source


def fetch() -> list[object]:
    """The feed's answers for both products. Only when run by a person."""
    import httpx

    answers = []
    for url in FEED_URLS:
        try:
            response = httpx.get(url, timeout=30.0, follow_redirects=False)
            response.raise_for_status()
            answers.append(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise FeedError(f"{url}: {exc}") from exc
    return answers


def _print_report(report: Report) -> None:
    def show(title: str, rows: dict[str, Release]) -> None:
        if rows:
            print(f"\n{title}:")
            for code in sorted(rows):
                name = firmware_db.FIRMWARE_DB.get(code, {}).get("name", "")
                when = f" ({rows[code].released})" if rows[code].released else ""
                print(f"  {code:<12} {name:<24} {rows[code].text}{when}")

    show("Newer in the feed than in the table (recorded by --write)", report.newer)
    show("Older in the feed than in the table (kept; see the family's note)", report.older)
    show(
        "End of life in the table, yet a newer build in the feed (check by hand)",
        report.eol_updated,
    )
    show("In the feed, not in the table (stay unknown until added by hand)", report.not_in_table)
    if report.missing:
        print("\nJudged by the table, not in the feed:\n  " + " ".join(sorted(report.missing)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--feed", action="append", type=pathlib.Path, help="a saved feed answer")
    parser.add_argument("--write", action="store_true", help="update the table")
    parser.add_argument(
        "--accept-missing",
        action="store_true",
        help="date the table although codes it judges are missing from the feed",
    )
    # A copy of the table to write instead, for the tests.
    parser.add_argument("--table", type=pathlib.Path, default=TABLE, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    try:
        if args.feed:
            try:
                answers = [json.loads(path.read_text(encoding="utf-8")) for path in args.feed]
            except (OSError, ValueError) as exc:
                raise FeedError(str(exc)) from exc
        else:
            answers = fetch()
        feed = merge(*(read_feed(answer) for answer in answers))
    except FeedError as exc:
        print(f"The feed cannot refresh the table: {exc}", file=sys.stderr)
        return 2
    report = compare(feed)
    _print_report(report)

    source = args.table.read_text(encoding="utf-8")
    if not args.write:
        behind = render_block(report.newer) not in source
        print(
            "\nThe table is behind the feed; --write records it and dates the table."
            if behind
            else "\nThe table has every version the feed has; --write dates it today."
        )
        return 1 if behind else 0
    if report.missing and not args.accept_missing:
        print(
            "\nNot written: the codes above are missing from the feed, so the table cannot be"
            " dated today. Check them by hand and pass --accept-missing.",
            file=sys.stderr,
        )
        return 2
    today = datetime.date.today()
    args.table.write_text(rewrite(source, report.newer, today), encoding="utf-8")
    print(
        f"\nWrote {args.table.name}, dated {today.isoformat()}. Before committing: compare"
        f" {firmware_db._EOL_LIST} and update tests/test_unifi_firmware_table.py."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

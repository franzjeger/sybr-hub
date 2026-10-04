"""UniFi firmware: the newest Official release per model, and which models are EOL.

A **manually maintained** table, not a live feed, so it has a shelf life. If it
is older than ``FRESHNESS_DAYS`` it is treated as stale and ``check_firmware``
**fails closed** (SR-007): it will not claim a device is up to date from data
it cannot vouch for, and reports ``severity="unknown"`` with a ``stale`` flag
instead. A device that is *behind* or EOL is still reported: those are valid
lower bounds a stale table cannot make wrong (a device behind a stale "latest"
is behind the real latest too).

Where the data comes from, all of it Ubiquiti's own:

* **Newest release per model**: Ubiquiti's firmware update service, the feed
  the UniFi Network application itself asks, on the release (Official) channel:
  ``https://fw-update.ui.com/api/firmware-latest?filter=eq~~product~~unifi-firmware&filter=eq~~channel~~release``
  (UniFi OS gateways: ``product~~unifi-dream``). Its ``platform`` is the model
  code a controller reports in ``stat/device`` (U7PG2, UAP6MP, US24P250,
  UDMPRO), which is why the table is keyed by it. Each family below links the
  community.ui.com release notes that confirm the version is the Official one;
  a Release Candidate or Early Access build is never taken as "latest".
* **Product names**: Ubiquiti's device catalog,
  ``https://static.ui.com/fingerprint/ui/public.json`` (sku, shortnames and
  board names). A device read directly reports its board name (SSH
  ``board.name``, e.g. "UAP-AC-Pro-Gen2"), which the aliases map to its code.
* **End of life**: "Ubiquiti's Vintage and Legacy Products",
  ``https://help.ui.com/hc/en-us/articles/1500001268521`` (updated
  2026-10-02). *Legacy* products "have stopped receiving updates": EOL here.
  *Vintage* products still get critical bug fixes and security updates, so they
  are **not** EOL (US-L2-24/48-PoE and USW-Enterprise-8/24/48-PoE are Vintage).

Update process: read the feed above for each family's first code, check the
release notes for that version say Official, compare the help.ui.com list, and
set ``LAST_UPDATED`` to that day. A model whose version could not be found in
one of these sources stays out of the table: "unknown" is the honest answer.
"""

from __future__ import annotations

import logging
import re
from datetime import date

log = logging.getLogger(__name__)

# The day the versions and EOL flags below were last checked against the sources.
LAST_UPDATED = "2026-10-04"

# How long the manually maintained table is trusted before it fails closed.
# UniFi ships firmware every few weeks to months; 180 days keeps a recent manual
# update usable while forcing a refresh (or an honest "unknown") before the data
# is badly out of date.
FRESHNESS_DAYS = 180

SOURCE = "unifi-firmware-db (manuell tabell)"

# Why check_firmware could not give a verdict (its "reason").
REASONS = ("model_unknown", "version_unparsed", "table_stale")

_FEED = (
    "https://fw-update.ui.com/api/firmware-latest?filter=eq~~channel~~release&filter=eq~~platform~~"
)
_EOL_LIST = "https://help.ui.com/hc/en-us/articles/1500001268521"

# One firmware line Ubiquiti ships to a set of models: its newest Official
# release, whether the models are end of life, where that was read, and the
# models as {controller model code: (product name, other names it goes by)}.
_FAMILIES: tuple[dict, ...] = (
    # ── Access points ─────────────────────────────────────────────
    {
        # Official 2026-02-03, "This release applies for these models:
        # UAP-AC-Lite/LR/Pro/M/M-PRO/IW/UK-Ultra, UAP-HD/SHD/XG/BaseStationXG,
        # U6-Pro/Mesh/IW/Extender/Enterprise/Enterprise-IW". The feed has 6.8.2
        # (2026-02-11) for every code below.
        "latest": "6.8.2",
        "source": "https://community.ui.com/releases/UniFi-Access-Point-for-U6-Pro-U6-Enterprise-U6-Mesh-and-more-6-8-2/5c86022f-7c88-4d2b-ac5b-753b95985c5a",
        "models": {
            "U7PG2": ("UAP-AC-Pro", "UAP-AC-Pro-Gen2"),
            "U7LT": ("UAP-AC-LITE",),
            "U7LR": ("UAP-AC-LR",),
            "U7MSH": ("UAP-AC-M", "UAP-AC-Mesh"),
            "U7MP": ("UAP-AC-M-PRO", "UAP-AC-Mesh-Pro"),
            "U7IW": ("UAP-AC-IW", "UAP-AC-InWall"),
            "U7UKU": ("UK-Ultra",),
            "U7HD": ("UAP-AC-HD", "UAP-HD"),
            "U7SHD": ("UAP-AC-SHD", "U7SHDv2", "UAP-SHD", "UAP-SHDv2"),
            "UCXG": ("UAP-XG",),
            "UXSDM": ("UWB-XG", "UAP-BaseStationXG"),
            "UXBSDM": ("UWB-XG-BK", "UAP-BlackBaseStationXG"),
            "UAP6MP": ("U6-Pro",),
            "U6M": ("U6-Mesh",),
            "U6IW": ("U6-IW",),
            "U6EXT": ("U6-Extender",),
            "U6ENT": ("U6-Enterprise",),
            "U6ENTIW": ("U6-Enterprise-IW",),
        },
    },
    {
        # Official 2026-08-25, "This release is only for these models:
        # U6-LR/U6-Lite, UAP-nanoHD/FlexHD/BeaconHD/IW-HD". The feed has 6.7.57
        # (2026-09-03) for these codes, including UAM6/UAE6/UAIW6: a second
        # hardware code for U6-Mesh, U6-Extender and U6-IW, whose other code is
        # on 6.8.2 above. Those three product names are therefore ambiguous and
        # resolve only by code (see _index below).
        "latest": "6.7.57",
        "source": "https://community.ui.com/releases/UniFi-Access-Point-for-U6-LR-U6-Lite-and-more-6-7-57/97000981-b2ee-4a8d-a783-ed251b8c04c1",
        "models": {
            "UAL6": ("U6-Lite",),
            "UALR6": ("U6-LR", "U6-LR-EA"),
            "UALR6v2": ("U6-LR", "UALR6v3"),
            "U7NHD": ("UAP-nanoHD",),
            "UFLHD": ("UAP-FlexHD",),
            "UDMB": ("UAP-BeaconHD",),
            "UHDIW": ("UAP-IW-HD", "UAP-HD-IW"),
            "UAM6": ("U6-Mesh", "U6-Mesh-EA"),
            "UAE6": ("U6-Extender", "U6-Extender-EA"),
            "UAIW6": ("U6-IW", "U6-IW-EA"),
        },
    },
    {
        # Official 2026-06-15, for "U6-LR/U6-Lite/U6+" and the HD models. U6+
        # did not get 6.7.57, and neither did U6-LR+ (U6-PLUS-LR): the feed
        # has 6.7.54 (2026-06-25) for both.
        "latest": "6.7.54",
        "source": "https://community.ui.com/releases/UniFi-Access-Point-for-U6-LR-U6-Lite-U6-and-more-6-7-54/758132b8-27dc-4a5f-ac6c-5b87aa80a777",
        "models": {
            "UAPL6": ("U6+",),
            "UALRPL6": ("U6-PLUS-LR",),
        },
    },
    {
        # Feed, release channel: 7.0.103 (2025-01-22). No newer Official build.
        "latest": "7.0.103",
        "source": _FEED + "U6MP",
        "models": {
            "U6MP": ("U6-Mesh-Pro",),
        },
    },
    {
        # Promoted to Official per model between 2026-07-27 and 2026-08-31,
        # "all U7 and E7 models" except U7-LR. The feed has 8.7.11 for every
        # code below.
        "latest": "8.7.11",
        "source": "https://community.ui.com/releases/UniFi-Access-Point-all-U7-and-E7-models-8-7-11/42b6f9d9-3dba-4cda-bde1-b8157edc1299",
        "models": {
            "U7PRO": ("U7-Pro",),
            "U7PROMAX": ("U7-Pro-Max",),
            "U7PIW": ("U7-Pro-Wall", "U7-Pro-IW", "U7-Pro-W"),
            "UKPW": ("U7-Outdoor", "UK-Pro"),
            "UAPA693": ("U7-Lite", "G7LT"),
            "UAPA69E": ("U7-Mesh", "U7M"),
            "UAPA6A5": ("U7-IW", "G7IW", "U7-In-Wall"),
            "UAPA6A6": ("U7-Pro-Outdoor", "U7PO"),
            "UAPA6B0": ("U7-Pro-Outdoor-EU", "U7POEU"),
            "UAPA6A9": ("U7-Pro-XG", "U7PROXG"),
            "UAPA6AE": ("U7-Pro-XG-B", "U7PROXGB"),
            "UAPA6A4": ("U7-Pro-XGS", "U7PROXGS"),
            "UAPA6AC": ("U7-Pro-XGS-B", "U7PROXGSB"),
            "UAPA6BA": ("U7-Pro-XG-Wall", "U7PROXGW"),
            "UAPA697": ("E7",),
            "UAPA698": ("E7-Campus", "E7C"),
            "UAPA6B1": ("E7-Campus-EU", "E7CEU"),
            "UAPA6BC": ("E7-Campus-Indoor", "E7CI"),
            "UAPA699": ("E7-Audience", "E7A"),
            "UAPA6AB": ("E7-Audience-EU", "E7AEU"),
            "UAPA6AF": ("E7-Audience-Indoor", "E7AI"),
        },
    },
    {
        # U7-LR has its own line. The feed has 8.0.76 (2026-09-03); 8.0.77
        # (2026-10-02) is a Release Candidate and does not count.
        "latest": "8.0.76",
        "source": "https://community.ui.com/releases/UniFi-Access-Point-for-U7-LR-8-0-76/c60a703f-fbe1-43bc-a127-702004c37ad1",
        "models": {
            "UAPA6B3": ("U7-LR", "G7LRv2"),
        },
    },
    {
        # Legacy on help.ui.com: UAP (v1+v2), UAP-LR (v1+v2), UAP-Outdoor,
        # UAP-Outdoor+, UAP-Outdoor-5, UAP-Pro, UAP-IW, UAP-AC-EDU,
        # UAP-AC-IW-PRO. Their last firmware in the feed is 4.3.28 (2021-02-10).
        "latest": "4.3.28",
        "eol": True,
        "source": _EOL_LIST,
        "models": {
            "BZ2": ("UAP", "U2S48"),
            "U2Sv2": ("UAPv2",),
            "BZ2LR": ("UAP-LR", "U2L48"),
            "U2Lv2": ("UAP-LRv2",),
            "U2O": ("UAP-Outdoor",),
            "U2HSR": ("UAP-Outdoor+",),
            "U5O": ("UAP-Outdoor-5", "UAP-Outdoor5G"),
            "U7P": ("UAP-Pro",),
            "U2IW": ("UAP-IW", "UAP-InWall"),
            "U7EDU": ("UAP-AC-EDU",),
            "U7IWP": ("UAP-AC-IW-Pro", "UAP-AC-InWall-Pro"),
        },
    },
    {
        # Legacy on help.ui.com: UAP-AC and UAP-AC-Outdoor. The feed no longer
        # carries any firmware for them, so there is no last version to give.
        "latest": None,
        "eol": True,
        "source": _EOL_LIST,
        "models": {
            "U7Ev2": ("UAP-AC", "U7E", "UAP-ACv2"),
            "U7O": ("UAP-AC-Outdoor",),
        },
    },
    # ── Switches ──────────────────────────────────────────────────
    {
        # Official 2026-09-01. The feed has 7.5.15 (2026-09-08) for every code
        # below, the first-generation US-* switches included. US-L2-*-PoE and
        # USW-Enterprise-*-PoE are Vintage on help.ui.com: still supported,
        # not EOL.
        "latest": "7.5.15",
        "source": "https://community.ui.com/releases/UniFi-Switch-7-5-15/bf576b40-c001-4224-b8c0-8c95baec920d",
        "models": {
            "US16P150": ("US-16-150W", "S216150"),
            "US24": ("US-24", "US-24-G1"),
            "US24P250": ("US-24-250W", "S224250"),
            "US24P500": ("US-24-500W", "S224500"),
            "US24PL2": ("US-L2-24-PoE",),
            "US24PRO": ("USW-Pro-24-PoE", "USLP24P"),
            "US24PRO2": ("USW-Pro-24",),
            "US48": ("US-48", "US-48-G1"),
            "US48P500": ("US-48-500W", "S248500"),
            "US48P750": ("US-48-750W", "S248750"),
            "US48PL2": ("US-L2-48-PoE",),
            "US48PRO": ("USW-Pro-48-PoE", "USLP48P"),
            "US48PRO2": ("USW-Pro-48",),
            "US624P": ("USW-Enterprise-24-PoE",),
            "US648P": ("USW-Enterprise-48-PoE",),
            "US68P": ("USW-Enterprise-8-PoE",),
            "US6XG150": ("US-XG-6PoE",),
            "US8": ("US-8",),
            "US8P150": ("US-8-150W", "USC8P150", "S28150"),
            "US8P60": ("US-8-60W", "USC8P60"),
            "USAGGPRO": ("USW-Pro-Aggregation", "USW-Aggregation-Pro"),
            "USC8": ("US-8",),
            "USC8P450": ("USW-Industrial",),
            "USF5P": ("USW-Flex", "USW-5-Flex"),
            "USFXG": ("USW-Flex-XG",),
            "USL16LP": ("USW-Lite-16-PoE",),
            "USL16LPB": ("USW-Lite-16-PoE",),
            "USL16P": ("USW-16-PoE",),
            "USL16PB": ("USW-16-PoE",),
            "USL24": ("USW-24", "USW-24-G2"),
            "USL24B": ("USW-24",),
            "USL24P": ("USW-24-PoE",),
            "USL24PB": ("USW-24-PoE",),
            "USL48": ("USW-48", "USW-48-G2"),
            "USL48B": ("USW-48",),
            "USL48P": ("USW-48-PoE",),
            "USL48PB": ("USW-48-PoE",),
            "USL8A": ("USW-Aggregation",),
            "USL8LP": ("USW-Lite-8-PoE",),
            "USL8LPB": ("USW-Lite-8-PoE",),
            "USL8MP": ("USW-Mission-Critical",),
            "USLP8P": ("USW-Pro-8-PoE",),
            "USPM16": ("USW-Pro-Max-16",),
            "USPM16P": ("USW-Pro-Max-16-PoE",),
            "USPM24": ("USW-Pro-Max-24",),
            "USPM24P": ("USW-Pro-Max-24-PoE",),
            "USPM48": ("USW-Pro-Max-48",),
            "USPM48P": ("USW-Pro-Max-48-PoE",),
            "USWED42": ("USW-Pro-XG-48-PoE", "USWPXG48P"),
            "USWED43": ("USW-Pro-XG-48", "USWPXG48"),
            "USWED44": ("USW-Pro-XG-24-PoE", "USWPXG24P"),
            "USWED45": ("USW-Pro-XG-24", "USWPXG24"),
            "USWED72": ("USW-Pro-HD-24-PoE", "USPH24P"),
            "USWED73": ("USW-Pro-HD-24", "USPH24"),
            "USWED76": ("USW-Pro-XG-8-PoE", "USPXG8P"),
            "USWED77": ("USW-Pro-XG-10-PoE", "USPXG10P"),
            "USWF001": ("EAV-XG-24-PoE", "EAV-24-PoE", "EAV24P"),
            "USWF002": ("EAV-Fiber", "EAVAGG"),
            "USWF003": ("USW-Pro-XG-Aggregation", "USWPXGAGG"),
            "USWF067": ("ECS-24-PoE", "EAS24P", "ECS24P"),
            "USWF069": ("ECS-48-PoE", "EAS48P", "ECS48P"),
            "USXG": ("US-16-XG",),
            "USXG24": ("USW-EnterpriseXG-24", "US-24-XG"),
        },
    },
    {
        # Official 2026-09-03; the feed has 7.4.119 for these four.
        "latest": "7.4.119",
        "source": "https://community.ui.com/releases/Enterprise-Campus-24S-48S-PoE-7-4-119/c8b55335-528c-4a51-baa9-57aab79cf624",
        "models": {
            "USWF004": ("ECS-24S-PoE", "EAS24SP", "ECS24SP"),
            "USWF005": ("ECS-24S", "EAS24S", "ECS24S"),
            "USWF006": ("ECS-48S-PoE", "EAS48SP", "ECS48SP"),
            "USWF007": ("ECS-48S", "EAS48S", "ECS48S"),
        },
    },
    {
        # Feed, release channel: 4.0.1 (2026-09-11).
        "latest": "4.0.1",
        "source": _FEED + "USWF066",
        "models": {
            "USWF066": ("ECS-Aggregation", "ECSAGG"),
            "USWF07D": ("ECS-Core", "ECSCORE"),
        },
    },
    {
        # Official 2026-01-15; the feed has 7.3.109 (2026-02-10).
        "latest": "7.3.109",
        "source": "https://community.ui.com/releases/UniFi-Switch-WAN-7-3-109/4b641591-e974-47f1-bbb5-667944ee42de",
        "models": {
            "USWED74": ("USW-WAN", "WRS3F"),
            "USWED75": ("USW-WAN-RJ45", "WRS3"),
        },
    },
    {
        # Flex Mini has its own line. Feed, release channel: 2.1.6 (2025-08-25).
        "latest": "2.1.6",
        "source": _FEED + "USMINI",
        "models": {
            "USMINI": ("USW-Flex-Mini", "USW-Mini"),
            "USMINI2": ("USW-Flex-Mini",),
        },
    },
    {
        # Ultra and Flex 2.5G share a line. Feed, release channel: 2.1.8
        # (2025-04-30).
        "latest": "2.1.8",
        "source": _FEED + "USM8P",
        "models": {
            "USM8P": ("USW-Ultra",),
            "USM8P210": ("USW-Ultra-210W",),
            "USM8P60": ("USW-Ultra-60W",),
            "USWED35": ("USW-Flex-2.5G-5", "USM25G5"),
            "USWED36": ("USW-Flex-2.5G-8", "USM25G8"),
            "USWED37": ("USW-Flex-2.5G-8-POE", "USM25G8P"),
        },
    },
    # ── Gateways ──────────────────────────────────────────────────
    {
        # UniFi OS, Official 2026-09-09. The feed (product unifi-dream) has
        # 5.1.33 (2026-09-10) for every code below. A controller reports the
        # UniFi OS version as these gateways' firmware.
        "latest": "5.1.33",
        "source": "https://community.ui.com/releases/UniFi-OS-Dream-Machines-5-1-33/bdb30bcf-c8b9-4713-8fc7-2405d9de1f8d",
        "models": {
            "UDM": ("UDM",),
            "UDMPRO": ("UDM-Pro", "UDMP"),
            "UDMPROSE": ("UDM-SE", "UDM-PRO-SE", "UDMSE"),
            "UDMPROMAX": ("UDM-Pro-Max",),
            "UDR": ("UDR",),
            "UDW": ("UDW",),
            "UCGMAX": ("UCG-Max",),
            "UDRULT": ("UCG-Ultra", "UDR-Pro", "UDR-Ultra"),
            "UDMENT": ("EFG",),
            "UDMEA4C": ("UDM-Beast",),
            "UCGF": ("UCG-Fiber", "UDMA6A8"),
            "UCGA6AD": ("UCG-Industrial", "UDMA6AD"),
            "UDR5G": ("UDR-5G-Max", "UDMA6B9"),
            "UDR7": ("UDR7", "UDMA67A"),
            "EFGCORE": ("EF-Core", "UDMEA4B", "EFG-Core"),
        },
    },
    {
        # UniFi Express. Feed (unifi-dream and unifi-firmware): 4.0.21
        # (2026-09-18).
        "latest": "4.0.21",
        "source": _FEED + "UX",
        "models": {
            "UX": ("UX", "UEX"),
        },
    },
    {
        # UniFi Express 7. Feed, release channel: 5.2.10 (2026-09-15).
        "latest": "5.2.10",
        "source": _FEED + "UDMA69B",
        "models": {
            "UDMA69B": ("UX7", "UX-Max", "UXMAX"),
        },
    },
    {
        # UniFi Gateways, Official (rolled out in stages); the feed has 5.1.26
        # (2026-08-04) for every code below. UXG-Pro (UXGPRO) stopped at 1.13.8 in 2022 under its old
        # code; its firmware continues under UXGPROV2, whose builds are tagged
        # for the same board ("UXGPRO.al324.v5.1.26..."), so 5.1.26 is newest
        # for that hardware too and a UXG-Pro still on 1.x is behind.
        "latest": "5.1.26",
        "source": "https://community.ui.com/releases/UniFi-Gateways-5-1-26/d0483619-94ae-4f3c-b338-18afbfc906ed",
        "models": {
            "UXG": ("UXG-Lite",),
            "UXGB": ("UXG-Max",),
            "UXGENT": ("UXG-Enterprise",),
            "UXGA6AA": ("UXG-Fiber",),
            "UXGPRO": ("UXG-Pro", "UXG-PRO"),
            "UXGPROV2": ("UXG-Pro",),
        },
    },
    {
        # Legacy on help.ui.com: USG, USG-Pro, USG-XG-8. Last firmware in the
        # feed: 4.4.57 (2023-01-23).
        "latest": "4.4.57",
        "eol": True,
        "source": _EOL_LIST,
        "models": {
            "UGW3": ("USG-3P", "USG", "UGWHD4"),
            "UGW4": ("USG-PRO-4", "USG-Pro", "UGW8"),
            "UGWXG": ("USG-XG-8",),
        },
    },
)

# Controller model code -> {"latest", "eol", "name", "source"}.
FIRMWARE_DB: dict[str, dict] = {
    code: {
        "latest": family["latest"],
        "eol": family.get("eol", False),
        "name": names[0],
        "source": family["source"],
    }
    for family in _FAMILIES
    for code, names in family["models"].items()
}


def _index() -> tuple[dict[str, str], dict[str, list[str]]]:
    """Lower-cased code or name -> code, and the names left out as ambiguous.

    A name maps to a code only if every code going by that name gets the same
    verdict. U6-Mesh, for one, is both U6M (6.8.2) and UAM6 (6.7.57): judging
    a device that says only "U6-Mesh" against either could call it behind when
    it is not, so that name resolves to nothing and the device reads "unknown".
    """
    by_name: dict[str, set[str]] = {}
    for family in _FAMILIES:
        for code, names in family["models"].items():
            for name in names:
                by_name.setdefault(name.lower(), set()).add(code)
    index: dict[str, str] = {}
    ambiguous: dict[str, list[str]] = {}
    for name, codes in by_name.items():
        verdicts = {(FIRMWARE_DB[c]["latest"], FIRMWARE_DB[c]["eol"]) for c in codes}
        if len(verdicts) == 1:
            index[name] = min(codes)
        else:
            ambiguous[name] = sorted(codes)
    # A code is always itself, whatever names collide with it.
    index.update({code.lower(): code for code in FIRMWARE_DB})
    return index, ambiguous


_INDEX, AMBIGUOUS_NAMES = _index()


def normalize_model(raw_model: str) -> str:
    """The controller model code for a model code or product name.

    Exact (case-insensitive) matches only. Prefix matching used to send
    "USW-Flex-2.5G-5" to USW-Flex and judge a 2.x switch against 7.x firmware;
    a name the table does not know is returned as given and reads "unknown".
    """
    raw = (raw_model or "").strip()
    return _INDEX.get(raw.lower(), raw)


def _today() -> date:
    """The clock every verdict reads unless given a day (tests freeze it here)."""
    return date.today()


def db_age_days(today: date | None = None) -> int | None:
    """Age of the firmware table in days, or None if LAST_UPDATED is unparseable."""
    try:
        updated = date.fromisoformat(LAST_UPDATED)
    except ValueError:
        return None
    return ((today or _today()) - updated).days


def is_stale(today: date | None = None) -> bool:
    """True when the table is past its freshness window — fail closed.

    Counts as stale, not fresh: an unparseable/absent LAST_UPDATED, and a
    NEGATIVE age. A negative age means the clock reads earlier than LAST_UPDATED
    — a future-dated table (a manual-update typo) or a clock running behind (dead
    RTC, restored snapshot, NTP not yet synced). Trusting it would let an ancient
    or misdated table masquerade as current, exactly the fail-open SR-007 forbids
    (SR-007 review)."""
    age = db_age_days(today)
    return age is None or age < 0 or age > FRESHNESS_DAYS


def check_firmware(model: str, current_firmware: str, today: date | None = None) -> dict:
    """Check if firmware is up to date.

    Returns:
        {
            "model": product name (or the model as given when unknown),
            "current": current firmware version,
            "latest": latest known version (or None),
            "up_to_date": True/False/None,      # None = could not confirm
            "eol": True/False,
            "severity": "ok" / "warning" / "critical" / "unknown",
            "source": SOURCE,
            "as_of": LAST_UPDATED,
            "stale": True/False,                # table past its freshness window
            "reason": one of REASONS,           # present when severity == "unknown"
        }

    The reason is a code, not a sentence: ``model_unknown``,
    ``version_unparsed`` or ``table_stale`` (the table's date is ``as_of``).
    It was a Norwegian sentence, which reached English readers through
    /api/unifi/firmware-check and the network audit's stored results. The
    codes are the ones firmware_inventory and the FortiOS life cycle
    (fortigate_audit.firmware_lifecycle) already use, so whoever shows one
    words it in the reader's language.

    Fail-closed on staleness: from a stale table it will report "behind"/"EOL"
    (valid lower bounds) but never "up to date" — an up-to-date verdict becomes
    "unknown" because the recorded "latest" may itself be out of date.
    """
    normalized = normalize_model(model)
    stale = is_stale(today)
    result: dict = {
        "model": normalized or model,
        "current": current_firmware,
        "latest": None,
        "up_to_date": None,
        "eol": False,
        "severity": "unknown",
        "source": SOURCE,
        "as_of": LAST_UPDATED,
        "stale": stale,
    }

    db_entry = FIRMWARE_DB.get(normalized)
    if not db_entry:
        result["reason"] = "model_unknown"
        return result

    result["model"] = db_entry["name"]
    result["latest"] = db_entry["latest"]
    result["eol"] = db_entry["eol"]

    # EOL is durable: a model that reached end-of-life stays EOL regardless of
    # how fresh the table is, so this verdict is safe even when stale.
    if result["eol"]:
        result["severity"] = "critical"
        result["up_to_date"] = False
        return result

    # Extract version numbers for comparison
    cur_ver = _extract_version(current_firmware)
    lat_ver = _extract_version(db_entry["latest"])

    if not cur_ver or not lat_ver:
        result["reason"] = "version_unparsed"
        return result

    if cur_ver >= lat_ver:
        if stale:
            # The device matches or exceeds our recorded latest, but the table
            # is stale — a newer release may exist, so we cannot confirm this is
            # current. Fail closed to unknown rather than claim "ok" (SR-007).
            result["up_to_date"] = None
            result["severity"] = "unknown"
            result["reason"] = "table_stale"
        else:
            result["up_to_date"] = True
            result["severity"] = "ok"
    else:
        result["up_to_date"] = False
        # Check how far behind
        if cur_ver[0] < lat_ver[0]:  # Major version behind
            result["severity"] = "critical"
        else:
            result["severity"] = "warning"

    return result


_VERSION = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")


def _extract_version(fw_string: str | None) -> tuple | None:
    """Extract numeric version tuple from firmware string.

    Handles formats like:
        "6.6.77"
        "BZ.qca956x.v6.2.91.13247.220325.0116"
        "v4.4.57"
    """
    if not fw_string:
        return None
    m = _VERSION.search(fw_string)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None

"""Reports must name things, not print ids.

Two places printed raw Graph identifiers that mean nothing to a reader:
the Secure Score improvement table showed control ids (scid_2509), and the
licence inventory showed SKU part numbers (SPE_E3, O365_BUSINESS_PREMIUM —
which is Business *Standard*, not Premium). Both now carry the human name.
"""

from __future__ import annotations

from app.reports.generator import (
    _parse_licenses,
    _parse_secure_score,
    _sku_friendly,
)

# ── Secure Score: the improvement table names the action ─────────────────────

_SECURE_SCORE_TXT = """\
================================================================================
  SECURE SCORE
================================================================================
  Score         : 554.0 / 1162.0  (47.6%)
  As of         : 2026-08-18T06:21:00Z

  Top 20 Improvement Actions (by points still available):
  Control                                                                Score%    Left  Category
  ----------------------------------------------------------------------------
  Ensure multifactor authentication is enabled for all users              0.0%     9.0  Identity
  Ensure Safe Attachments is enabled                                     50.0%     4.5  Apps
================================================================================
"""


def test_secure_score_improvements_carry_the_human_title():
    parsed = _parse_secure_score(_SECURE_SCORE_TXT)
    assert parsed["has_data"] and parsed["pct"] == 47.6
    names = [i["name"] for i in parsed["improvements"]]
    assert "Ensure multifactor authentication is enabled for all users" in names
    assert "Ensure Safe Attachments is enabled" in names
    # never the raw id
    assert not any(n.startswith("scid_") for n in names)


def test_a_row_that_kept_its_id_still_parses():
    # If the profiles (and so the title) could not be read, the collector falls
    # back to the id — the report must still list it rather than drop the row.
    txt = _SECURE_SCORE_TXT.replace(
        "Ensure multifactor authentication is enabled for all users", "scid_2509"
    )
    names = [i["name"] for i in _parse_secure_score(txt)["improvements"]]
    assert "scid_2509" in names


# ── Licences: the SKU carries its product name ───────────────────────────────

def test_known_skus_map_to_their_product_name():
    assert _sku_friendly("SPE_E3") == "Microsoft 365 E3"
    assert _sku_friendly("SPB") == "Microsoft 365 Business Premium"
    # the classic trap: this SKU is Business *Standard*, not Premium
    assert _sku_friendly("O365_BUSINESS_PREMIUM") == "Microsoft 365 Business Standard"


def test_an_unknown_sku_falls_back_to_the_part_number():
    assert _sku_friendly("SOME_NEW_SKU_2027") == "SOME_NEW_SKU_2027"
    assert _sku_friendly("") == ""


_LICENSES_TXT = """\
======================================================================
  LICENSE INVENTORY
======================================================================
  SKU / Part Number                        Used   Total    Pct  Status
  ------------------------------------------------------------------
  SPE_E3                                     10     15      67%
  O365_BUSINESS_PREMIUM                       8      8     100%
======================================================================
"""


def test_parsed_licences_carry_a_friendly_name_beside_the_part():
    lic = _parse_licenses(_LICENSES_TXT)
    by_part = {row["part"]: row for row in lic}
    assert by_part["SPE_E3"]["name"] == "Microsoft 365 E3"
    assert by_part["O365_BUSINESS_PREMIUM"]["name"] == "Microsoft 365 Business Standard"
    # the raw part number is still there for matching against Graph
    assert set(by_part) == {"SPE_E3", "O365_BUSINESS_PREMIUM"}

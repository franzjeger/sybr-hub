"""PIM must distinguish "no P2 license" from "missing permission".

Before this fix the PIM section printed one blurb listing three possible causes
of "no data" — no Entra ID P2, a missing app permission, PIM not configured —
so a Business Premium tenant (which has no P2 and cannot use PIM at all) read
the same as a P2 tenant whose app was under-permissioned. It now checks the
tenant's licence and says which it is (M365 report review, F7).
"""

from __future__ import annotations

from app.core.encryption import encrypted_read_text
from app.modules.m365_audit.sections.pim import PIMSection


class FakePimGraph:
    def __init__(self, skus=None, raise_skus=False):
        self.skus = skus or []
        self.raise_skus = raise_skus
        self.calls: list[str] = []

    async def get_all(self, path, **kw):
        self.calls.append(path)
        if path == "subscribedSkus":
            if self.raise_skus:
                raise RuntimeError("403 Forbidden")
            return list(self.skus)
        return []   # no eligible / active role data

    async def get(self, path, **kw):
        return {}


def _p2_sku(status="Success"):
    return [{"servicePlans": [{"servicePlanName": "AAD_PREMIUM_P2", "provisioningStatus": status}]}]


def _no_p2_sku():
    return [{"servicePlans": [{"servicePlanName": "SHAREPOINTSTANDARD", "provisioningStatus": "Success"}]}]


def _out(tmp_path):
    return encrypted_read_text(tmp_path / "32_pim_roles.txt")


async def test_no_p2_reads_as_not_applicable(tmp_path):
    result = await PIMSection(tmp_path, FakePimGraph(skus=_no_p2_sku())).collect()
    out = _out(tmp_path)
    assert "Not applicable" in out
    assert "no Microsoft Entra ID P2" in out
    assert "missing" not in out.lower(), "no-P2 must not be blamed on a missing permission"
    # It is a licensing fact, not a critical finding — info level, not a warning.
    assert "info" in result.warn_levels, result.warn_levels
    assert any("no Entra ID P2" in w for w in result.warns), result.warns


async def test_p2_present_but_no_data_points_at_the_permission(tmp_path):
    await PIMSection(tmp_path, FakePimGraph(skus=_p2_sku())).collect()
    out = _out(tmp_path)
    assert "licensed" in out
    assert "RoleManagement.Read.Directory" in out
    assert "Not applicable" not in out


async def test_unreadable_license_keeps_the_ambiguous_wording(tmp_path):
    await PIMSection(tmp_path, FakePimGraph(raise_skus=True)).collect()
    out = _out(tmp_path)
    # Could not determine the licence — fall back to listing the possibilities
    # rather than guessing.
    assert "Possible reasons" in out


async def test_a_disabled_p2_plan_is_not_counted_as_licensed(tmp_path):
    await PIMSection(tmp_path, FakePimGraph(skus=_p2_sku(status="Disabled"))).collect()
    out = _out(tmp_path)
    assert "Not applicable" in out

"""Regression tests for Azure VM backup coverage.

Coverage is a cross-reference between two independently-collected files:
``30_azure_vms*`` for the VM list and ``52_azure_backup*`` for protected items.
``_parse_backup_coverage`` ran the cross-reference unconditionally, so when the
backup half was missing or errored, ``backed_up_names`` was empty and every VM
fell into ``vms_not_backed_up``.

Two consumers then stated it as fact: a **high**-priority recommendation
listing each VM by name, and a red panel in the report headed "VMs without
backup". Telling a customer their servers are unprotected is about the most
consequential false finding this report can make — and it needed nothing more
than one collector section failing.

An empty *successful* read is a different thing entirely and still a finding.
"""

from __future__ import annotations

import pytest

from app.reports.generator import _build_recommendations, _parse_backup_coverage

VMS = (
    "AZURE VIRTUAL MACHINES\n"
    "=======================\n"
    "VM Name        Size          Location    Status\n"
    "vm-dc-01       Standard_D2   westeurope  running\n"
    "vm-app-01      Standard_D4   westeurope  running\n"
)

BACKUP_BOTH = (
    "Vault: rsv-prod\n"
    "Name           Type          Status\n"
    "vm-dc-01       AzureVM       Protected\n"
    "vm-app-01      AzureVM       Protected\n"
)

BACKUP_PARTIAL = (
    "Vault: rsv-prod\n"
    "Name           Type          Status\n"
    "vm-dc-01       AzureVM       Protected\n"
)


# ── The parser ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "backup_files",
    [
        {},                                                  # section never ran
        {"52_azure_backup.txt": ""},                         # ran, wrote nothing
        {"52_azure_backup.txt": "   \n"},
        {"52_azure_backup.txt": "Error: insufficient privileges"},
    ],
    ids=["absent", "empty", "whitespace", "error"],
)
def test_unread_backup_data_does_not_mark_every_vm_unprotected(backup_files):
    result = _parse_backup_coverage({"30_azure_vms.txt": VMS, **backup_files})

    assert result["vms_not_backed_up"] == [], (
        "every VM was listed as unprotected on the strength of a file we "
        "never read"
    )
    assert result["vms_backed_up"] == 0
    assert result["vms_total"] == 2, "the VM list itself was readable"
    assert result["coverage_known"] is False


def test_successfully_read_backup_data_still_finds_gaps():
    result = _parse_backup_coverage(
        {"30_azure_vms.txt": VMS, "52_azure_backup.txt": BACKUP_PARTIAL}
    )

    assert result["coverage_known"] is True
    assert result["vms_not_backed_up"] == ["vm-app-01"]
    assert result["vms_backed_up"] == 1
    assert result["backup_pct"] == 50.0


def test_full_coverage_reports_no_gaps():
    result = _parse_backup_coverage(
        {"30_azure_vms.txt": VMS, "52_azure_backup.txt": BACKUP_BOTH}
    )

    assert result["coverage_known"] is True
    assert result["vms_not_backed_up"] == []
    assert result["backup_pct"] == 100.0


def test_a_vault_with_no_protected_items_is_a_real_finding():
    """"We read the vault and nothing is in it" is not the same as not reading it."""
    result = _parse_backup_coverage({
        "30_azure_vms.txt": VMS,
        "52_azure_backup.txt": "Vault: rsv-prod\nNO PROTECTED ITEMS\n",
    })

    assert sorted(result["vms_not_backed_up"]) == ["vm-app-01", "vm-dc-01"]
    assert result["coverage_known"] is True


def test_no_vms_means_nothing_to_cross_reference():
    result = _parse_backup_coverage({"52_azure_backup.txt": BACKUP_BOTH})
    assert result["coverage_known"] is False
    assert result["vms_not_backed_up"] == []


def test_backup_pct_is_not_fabricated_when_coverage_is_unknown():
    result = _parse_backup_coverage({"30_azure_vms.txt": VMS})
    assert result["backup_pct"] == 0.0
    assert result["coverage_known"] is False


# ── The recommendation ────────────────────────────────────────────────────────


def _backup_rec(backup_coverage: dict):
    recs = _build_recommendations(
        mfa={"has_data": True, "pct": 100.0, "no_mfa": 0},
        spf_dmarc=[],
        secure_score={"has_data": True, "pct": 90.0, "improvements": []},
        ext_fwd="",
        risky_users="",
        licenses=[],
        backup_coverage=backup_coverage,
    )
    return next((r for r in recs if "backup" in r.get("title", "").lower()), None)


def test_no_backup_recommendation_when_vault_data_was_never_read():
    cov = _parse_backup_coverage({"30_azure_vms.txt": VMS})
    assert _backup_rec(cov) is None


def test_backup_recommendation_still_fires_on_a_real_gap():
    cov = _parse_backup_coverage(
        {"30_azure_vms.txt": VMS, "52_azure_backup.txt": BACKUP_PARTIAL}
    )
    rec = _backup_rec(cov)
    assert rec is not None
    assert rec["priority"] == "high"
    assert rec["sub_items"] == ["vm-app-01"]


def test_a_stale_coverage_dict_without_the_flag_is_treated_as_unknown():
    """Defensive: a dict from an older code path must not resurrect the claim."""
    assert _backup_rec({"vms_total": 2, "vms_not_backed_up": ["vm-dc-01"]}) is None

"""Exchange Online, from the files the Exchange collector actually writes.

The section takes its data from the PowerShell helper as a dict, so these tests
hand ExchangeSection that dict in the shape exo_collector.ps1 emits it and read
the run back as the report does (tests/collector_rig.py). Sensitivity labels
come from Graph, through a real GraphClient over the rig's fake transport.
"""

from __future__ import annotations

import pytest

from app.modules.m365_audit.sections.exchange import ExchangeSection
from app.reports.compliance import _build_compliance_map
from app.reports.parsers import _parse_exchange_overview, _parse_purview
from app.reports.parsers.tenant import _parse_shared_mailbox_upns
from tests.collector_rig import FakeGraph, run_sections

LABELS_PATH = "beta/security/dataSecurityAndGovernance/sensitivityLabels"


async def _collect(
    tmp_path, exo: dict, *, domains=("acme.example",), labels=None, sidecars=True
) -> tuple[dict, ExchangeSection]:
    """Run the whole section on one helper dict and read the run back."""
    async with FakeGraph({LABELS_PATH: labels if labels is not None else []}) as fake:
        section = ExchangeSection(tmp_path, exo, list(domains), graph=fake.client)
        files = await run_sections(section, sidecars=sidecars)
    return files, section


# ── Mailboxes ─────────────────────────────────────────────────────────────────


def _mailbox(name: str, address: str, kind: str = "UserMailbox", **extra) -> dict:
    """One mailbox as the helper's mailbox block writes it."""
    return {
        "DisplayName": name,
        "PrimarySmtpAddress": address,
        "RecipientType": kind,
        "ArchiveStatus": "None",
        "ForwardingAddress": None,
        "ForwardingSmtp": None,
        "DeliverAndForward": False,
        "TotalItemSize": "1.2 GB (1,288,490,189 bytes)",
        **extra,
    }


async def test_a_shared_mailbox_is_found_when_the_helper_sends_no_upn(tmp_path):
    """Helpers from before UserPrincipalName was added send only the SMTP address.

    The UPN column was then blank on every run, so licence optimisation never
    recognised a shared mailbox and offered its licence as an inactive user's.
    """
    exo = {
        "mailboxes": [
            _mailbox("Kari Nordmann", "kari@acme.example"),
            _mailbox("Postmottak", "post@acme.example", "SharedMailbox"),
            _mailbox("Møterom 1", "rom1@acme.example", "RoomMailbox"),
        ]
    }
    files, _ = await _collect(tmp_path, exo)

    shared = _parse_shared_mailbox_upns(files["20_exchange_mailboxes.txt"])
    assert shared == {"post@acme.example", "rom1@acme.example"}


# ── Connectors ────────────────────────────────────────────────────────────────


async def test_a_tenant_without_connectors_has_none(tmp_path):
    """The helper writes {"inbound": null, "outbound": null} for a tenant with none.

    That dict was written as one record, "inbound: N/A / outbound: N/A", and
    counted as one connector on the customer report.
    """
    files, _ = await _collect(tmp_path, {"connectors": {"inbound": None, "outbound": None}})

    assert _parse_exchange_overview(files)["connectors"] == 0


async def test_every_inbound_and_outbound_connector_counts(tmp_path):
    """One inbound (a single object, as ConvertTo-Json writes one) and two outbound."""
    exo = {
        "connectors": {
            "inbound": {"Name": "Fra skanner", "Enabled": True, "Type": "OnPremises"},
            "outbound": [
                {"Name": "Til partner", "Enabled": True, "Type": "Partner"},
                {"Name": "Til arkiv", "Enabled": False, "Type": "Partner"},
            ],
        }
    }
    files, _ = await _collect(tmp_path, exo)

    assert _parse_exchange_overview(files)["connectors"] == 3
    text = files["22_exchange_connectors.txt"]
    assert "Name: Fra skanner" in text and "Direction: Inbound" in text
    assert "Name: Til arkiv" in text and "Direction: Outbound" in text


# ── Mailbox forwarding ────────────────────────────────────────────────────────

# 51 characters, in a verified domain. Cut to the 45-character column it ends
# "@subsidiary.acme.e", which no tenant has verified.
LONG_INTERNAL = "smtp:kari.nordmann.regnskap@subsidiary.acme.example"
assert len(LONG_INTERNAL) > 45


def _forward(name: str, target: str, *, keep_copy: bool = False) -> dict:
    """One mailbox as the helper's forwarding block writes it."""
    local = name.split()[0].lower()
    return {
        "DisplayName": name,
        "PrimarySmtpAddress": f"{local}@acme.example",
        "ForwardingAddress": None,
        "ForwardingSmtp": target,
        "DeliverAndForward": keep_copy,
    }


async def test_a_long_address_in_a_verified_domain_is_not_external(tmp_path):
    exo = {
        "forwarding": [
            _forward("Kari Nordmann", LONG_INTERNAL, keep_copy=True),
            _forward("Ola Nordmann", "smtp:ola@mail.example"),
        ]
    }
    files, section = await _collect(
        tmp_path, exo, domains=("acme.example", "subsidiary.acme.example")
    )

    warn = files["28b_exchange_external_forwarding_WARN.txt"]
    assert "Ola Nordmann" in warn
    assert "Kari Nordmann" not in warn, "forwarding inside the tenant is not external"
    assert any("1 mailbox(es) forwarding to external" in w for w in section.result.warns)


async def test_the_external_column_says_whether_the_target_is_external(tmp_path):
    """It showed DeliverToMailboxAndForward under the heading External."""
    exo = {
        "forwarding": [
            _forward("Kari Nordmann", "smtp:kari@acme.example", keep_copy=True),
            _forward("Ola Nordmann", "smtp:ola@mail.example", keep_copy=False),
        ]
    }
    files, _ = await _collect(tmp_path, exo)

    rows = {
        line.split()[0]: line.split()[-1]
        for line in files["28_exchange_mailbox_forwarding.txt"].splitlines()
        if "Nordmann" in line
    }
    assert rows == {"Kari": "No", "Ola": "Yes"}


# ── Defender for Office 365: Safe Links / Safe Attachments ────────────────────


def _controls(files: dict, **context) -> dict[str, dict]:
    rows = _build_compliance_map({"file_contents": files, **context})
    return {r["cis_id"]: r for r in rows}


async def test_a_tenant_with_only_the_built_in_policy_keeps_its_defender_file(tmp_path):
    """ConvertTo-Json writes a single result as an object, not a one-item list.

    A tenant whose only Safe Links policy is the Built-In Protection Policy
    therefore sent a dict, the collector iterated its keys, and the whole file
    was lost: CIS 4.5 and 4.6 read "cannot verify" for a protected tenant.
    """
    exo = {
        "defender_policies": {
            "safe_links": {"Name": "Built-In Protection Policy", "IsEnabled": True},
            "safe_attachments": {"Name": "Built-In Protection Policy", "Action": "Block"},
        }
    }
    files, section = await _collect(tmp_path, exo)

    assert not any("Defender" in w for w in section.result.warns), section.result.warns
    controls = _controls(files)
    assert controls["4.5"]["status"] == "pass"
    assert controls["4.6"]["status"] == "pass"


# ── A read the helper reports as failed ───────────────────────────────────────
#
# Each block of exo_collector.ps1 records its failure under its own *_error key
# and leaves the data out. Written as a section with "(0 entries)", that was a
# reading of a tenant with none.

FAILED_READS = [
    ("mailboxes_error", ["20_exchange_mailboxes.txt", "20_exchange_mailboxes_count.txt"]),
    ("transport_rules_error", ["21_exchange_transport_rules.txt"]),
    ("connectors_error", ["22_exchange_connectors.txt"]),
    ("dkim_error", ["25_exchange_dkim.txt"]),
    ("defender_policies_error", ["27_exchange_defender_policies.txt"]),
    ("quarantine_policies_error", ["27b_exchange_quarantine_policies.txt"]),
    ("org_config_error", ["27c_exchange_org_config.txt"]),
    ("admin_audit_log_config_error", ["27d_exchange_admin_audit_log_config.txt"]),
    ("forwarding_error", ["28_exchange_mailbox_forwarding.txt"]),
    ("inbox_rules_error", ["29_exchange_inbox_rules_external_fwd.txt"]),
    ("dlp_error", ["19d_purview_dlp_policies.txt", "19e_purview_retention_policies.txt"]),
]


@pytest.mark.parametrize(("error_key", "names"), FAILED_READS, ids=[k for k, _ in FAILED_READS])
async def test_a_failed_read_is_written_as_an_error_not_as_none(tmp_path, error_key, names):
    files, _ = await _collect(tmp_path, {error_key: "The operation could not be performed."})

    for name in names:
        assert name in files, f"{name} is written, so the report can say why it is empty"
        assert files[name] == "", f"{name} must read as not collected, as an error stub does"


async def test_a_compliance_session_that_did_not_connect_is_not_a_tenant_without_dlp(tmp_path):
    """The helper connects to Security & Compliance once for DLP and retention."""
    exo = {
        "dlp_error": "Connect-IPPSSession: the role assignment is missing.",
        "dlp_policies": [],
        "retention_policies": [],
    }
    files, _ = await _collect(tmp_path, exo)

    controls = _controls(files, purview=_parse_purview(files))
    assert controls["3.1.1"]["status"] == "info", controls["3.1.1"]
    assert controls["7.2.2"]["status"] == "info", controls["7.2.2"]


async def test_missing_defender_cmdlets_are_not_a_tenant_without_safe_links(tmp_path):
    exo = {"defender_policies_error": "The term 'Get-SafeLinksPolicy' is not recognized."}
    files, _ = await _collect(tmp_path, exo)

    controls = _controls(files)
    assert controls["4.5"]["status"] == "info", controls["4.5"]
    assert controls["4.6"]["status"] == "info", controls["4.6"]


async def test_a_forwarding_scan_that_failed_does_not_pass(tmp_path):
    exo = {"forwarding_error": "Get-Mailbox failed.", "inbox_rules_error": "Get-Mailbox failed."}
    files, _ = await _collect(tmp_path, exo)

    assert _controls(files)["4.4"]["status"] == "info"

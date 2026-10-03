"""Exchange Online, from the files the Exchange collector actually writes.

The section takes its data from the PowerShell helper as a dict, so these tests
hand ExchangeSection that dict in the shape exo_collector.ps1 emits it and read
the run back as the report does (tests/collector_rig.py). Sensitivity labels
come from Graph, through a real GraphClient over the rig's fake transport.
"""

from __future__ import annotations

from app.modules.m365_audit.sections.exchange import ExchangeSection
from app.reports.parsers import _parse_exchange_overview
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

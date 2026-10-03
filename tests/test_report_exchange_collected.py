"""Exchange Online, from the files the Exchange collector actually writes.

The section takes its data from the PowerShell helper as a dict, so these tests
hand ExchangeSection that dict in the shape exo_collector.ps1 emits it and read
the run back as the report does (tests/collector_rig.py). Sensitivity labels
come from Graph, through a real GraphClient over the rig's fake transport.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.modules.m365_audit.sections.exchange import ExchangeSection
from app.modules.m365_audit.sections.users_mfa import UsersSection
from app.reports.compliance import _build_compliance_map
from app.reports.parsers import (
    _analyze_license_optimization,
    _parse_exchange_overview,
    _parse_purview,
)
from app.reports.parsers.tenant import _parse_shared_mailbox_upns, _shared_mailbox_upns
from app.reports.recommendations import _build_recommendations
from app.reports.risk import _compute_risk
from tests.collector_rig import FakeGraph, refused, run_sections

LABELS_PATH = "beta/security/dataSecurityAndGovernance/sensitivityLabels"


def _recent() -> str:
    return (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")


async def _collect(
    tmp_path, exo: dict, *, domains=("acme.example",), labels=None, sidecars=True
) -> tuple[dict, ExchangeSection]:
    """Run the whole section on one helper dict and read the run back."""
    async with FakeGraph({LABELS_PATH: labels if labels is not None else []}) as fake:
        section = ExchangeSection(tmp_path, exo, list(domains), graph=fake.client)
        files = await run_sections(section, sidecars=sidecars)
    return files, section


def _controls(files: dict, **context) -> dict[str, dict]:
    """The CIS rows the run's files produce, by id."""
    rows = _build_compliance_map({"file_contents": files, **context})
    return {r["cis_id"]: r for r in rows}


def _text_only(files: dict) -> dict:
    """The same run as one recorded before the collectors wrote sidecars."""
    return {k: v for k, v in files.items() if not k.endswith(".json")}


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


MAILBOXES = [
    _mailbox("Kari Nordmann", "kari@acme.example", UserPrincipalName="kari@acme.example"),
    _mailbox("Ola Nordmann", "ola@acme.example", UserPrincipalName="ola@acme.example"),
    _mailbox("Postmottak", "post@acme.example", "SharedMailbox"),
    _mailbox("Møterom 1", "rom1@acme.example", "RoomMailbox"),
]


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_mailbox_counts_survive_the_round_trip(tmp_path, sidecars):
    files, _ = await _collect(tmp_path, {"mailboxes": MAILBOXES}, sidecars=sidecars)
    assert ("20_exchange_mailboxes_count.json" in files) is sidecars

    overview = _parse_exchange_overview(files)

    assert overview["mailbox_total"] == 4
    assert overview["mailbox_user"] == 2
    assert overview["mailbox_shared"] == 1
    assert _shared_mailbox_upns(files) == {"post@acme.example", "rom1@acme.example"}


async def test_the_mailbox_counts_come_from_the_sidecar(tmp_path):
    files, _ = await _collect(tmp_path, {"mailboxes": MAILBOXES})
    files["20_exchange_mailboxes_count.txt"] = ""  # only the sidecar can answer now

    assert _parse_exchange_overview(files)["mailbox_total"] == 4


async def test_a_long_shared_mailbox_address_is_kept_whole(tmp_path):
    """The table cuts the UPN at 45 characters; the sidecar does not."""
    long_upn = "fakturamottak.regnskapsavdelingen@acme-holding.example"
    assert len(long_upn) > 45
    exo = {"mailboxes": [_mailbox("Faktura", long_upn, "SharedMailbox")]}

    files, _ = await _collect(tmp_path, exo)
    assert long_upn in _shared_mailbox_upns(files)

    text_only = _text_only(files)
    assert long_upn not in _shared_mailbox_upns(text_only)


async def test_a_licensed_shared_mailbox_is_not_offered_as_an_inactive_user(tmp_path):
    """Licence optimisation matches the stale accounts against the shared mailboxes.

    The table reader takes the first column holding an "@" as the UPN, so a
    display name with an "@" in it stood in for the address, the shared mailbox
    went unrecognised, and its licence was offered as an inactive user's.
    """
    users = [
        {
            "id": f"u{i}",
            "displayName": name,
            "userPrincipalName": upn,
            "accountEnabled": True,
            "userType": "Member",
            "assignedLicenses": [{"skuId": "sku-1"}],
            "signInActivity": signin,
        }
        for i, (name, upn, signin) in enumerate(
            [
                ("Kari Nordmann", "kari@acme.example", {"lastSignInDateTime": _recent()}),
                ("Support @ Acme", "support@acme.example", None),  # never signs in
            ]
        )
    ]
    exo = {"mailboxes": [_mailbox("Support @ Acme", "support@acme.example", "SharedMailbox")]}
    async with FakeGraph({"users": users}) as fake:
        await UsersSection(tmp_path, fake.client).collect()
    files, _ = await _collect(tmp_path, exo)

    kinds = {
        s["type"] for s in _analyze_license_optimization([], files)["optimization_suggestions"]
    }
    assert "shared_mailbox_licensed" in kinds
    assert "unused" not in kinds, "a shared mailbox is not an inactive user"


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


# ── Transport rules, connectors, anti-phishing and anti-spam ──────────────────

TRANSPORT_RULES = [
    {
        "Name": "Ekstern advarsel",
        "State": "Enabled",
        "Priority": 0,
        # Get-TransportRule's Description wraps over several lines.
        "Description": (
            "If the message:\n\tIs received from 'Outside the organization'\n"
            "Take the following actions:\n\tPrepend the subject with '[EKSTERN] '"
        ),
    },
    {"Name": "Skanner-unntak", "State": "Disabled", "Priority": 1, "Description": "Bypass"},
]
CONNECTORS = {
    "inbound": {"Name": "Fra skanner", "Enabled": True, "Type": "OnPremises", "RequireTls": True},
    "outbound": [
        {
            "Name": "Til partner",
            "Enabled": True,
            "Type": "Partner",
            "TlsSettings": "DomainValidation",
        },
        {"Name": "Til arkiv", "Enabled": False, "Type": "Partner", "TlsSettings": ""},
    ],
}
ANTI_PHISH = [
    {
        "Name": "Office365 AntiPhish Default",
        "IsDefault": True,
        "EnableTargetedUserProtection": False,
        "EnableSpoofIntelligence": True,
        "EnableFirstContactSafetyTips": False,
    },
    {
        "Name": "Ledelse",
        "IsDefault": False,
        "EnableTargetedUserProtection": True,
        "EnableSpoofIntelligence": True,
        "EnableFirstContactSafetyTips": True,
    },
]
ANTI_SPAM = [
    {
        "Name": "Default",
        "SpamAction": "MoveToJmf",
        "HighConfidenceSpamAction": "Quarantine",
        "BulkSpamAction": "MoveToJmf",
    }
]


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_rules_connectors_and_policies_survive_the_round_trip(tmp_path, sidecars):
    exo = {
        "transport_rules": TRANSPORT_RULES,
        "connectors": CONNECTORS,
        "anti_phish": ANTI_PHISH,
        "anti_spam": ANTI_SPAM,
    }
    files, _ = await _collect(tmp_path, exo, sidecars=sidecars)
    assert ("21_exchange_transport_rules.json" in files) is sidecars

    overview = _parse_exchange_overview(files)
    assert overview["transport_rules"] == 2
    assert overview["connectors"] == 3
    assert overview["antiphish_policies"] == ["Office365 AntiPhish Default", "Ledelse"]
    assert overview["antispam_policies"] == ["Default"]

    controls = _controls(files)
    assert controls["4.2"]["status"] == controls["4.3"]["status"] == "pass"
    assert controls["4.2"]["detail"].startswith("2 anti-phishing")
    assert controls["4.3"]["detail"].startswith("1 anti-spam")


async def test_a_value_that_reads_like_a_count_does_not_change_the_count(tmp_path):
    """A second "(n policies)" in the file leaves the text counter two banners.

    It then counts lines instead, so a rule described "(replaces 2 policies)"
    and a policy named "Ledelse (5 mailboxes)" turned two records into many.
    The sidecar carries the collector's own count.
    """
    rules = [
        {
            "Name": "Arkivkopi",
            "State": "Enabled",
            "Priority": 0,
            "Description": "(replaces 2 policies)",
        },
        {"Name": "Skanner-unntak", "State": "Enabled", "Priority": 1, "Description": "Bypass"},
    ]
    exo = {
        "transport_rules": rules,
        "connectors": {"inbound": None, "outbound": [{"Name": "Partner (3 results)"}]},
        "anti_phish": [ANTI_PHISH[0], {**ANTI_PHISH[1], "Name": "Ledelse (5 mailboxes)"}],
        "anti_spam": [{**ANTI_SPAM[0], "Name": "Streng (2 policies)"}],
    }
    files, _ = await _collect(tmp_path, exo)

    overview = _parse_exchange_overview(files)
    assert (overview["transport_rules"], overview["connectors"]) == (2, 1)
    assert _controls(files)["4.2"]["detail"].startswith("2 anti-phishing")
    assert _controls(files)["4.3"]["detail"].startswith("1 anti-spam")

    text_only = _text_only(files)
    overview = _parse_exchange_overview(text_only)
    assert overview["transport_rules"] != 2 and overview["connectors"] != 1, "the text cannot say"
    assert not _controls(text_only)["4.2"]["detail"].startswith("2 ")
    assert not _controls(text_only)["4.3"]["detail"].startswith("1 ")


async def test_the_policy_names_come_from_the_sidecar(tmp_path):
    files, _ = await _collect(tmp_path, {"anti_spam": ANTI_SPAM})
    files["24_exchange_antispam.txt"] = ""  # only the sidecar can answer now

    assert _parse_exchange_overview(files)["antispam_policies"] == ["Default"]


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


FORWARDING = [
    _forward("Kari Nordmann", "smtp:kari@acme.example", keep_copy=True),
    _forward("Ola Nordmann", "smtp:ola@mail.example"),
    # "NO " opens a line the text counter takes for furniture ("No data ...").
    _forward("No Reply", "smtp:noreply@mail.example"),
]


def _forwarding_findings(files: dict) -> tuple[list[str], int]:
    """The forwarding recommendation's rows, and what forwarding cost the score."""
    ext_fwd = files.get("28b_exchange_external_forwarding_WARN.txt", "")
    recs = _build_recommendations({}, [], {}, ext_fwd, "", [], file_contents=files)
    rows = next((r["sub_items"] for r in recs if r["finding_id"] == "finding-fwd"), [])
    mfa = {"has_data": True, "pct": 100, "no_mfa": 0}  # without MFA there is no score
    clean = _compute_risk({}, mfa, [], [], "", "", "")["score"]
    score = _compute_risk({}, mfa, [], [], ext_fwd, "", "", file_contents=files)["score"]
    return rows, clean - score


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_forwarding_findings_survive_the_round_trip(tmp_path, sidecars):
    files, _ = await _collect(tmp_path, {"forwarding": FORWARDING[:2]}, sidecars=sidecars)
    assert ("28b_exchange_external_forwarding_WARN.json" in files) is sidecars

    overview = _parse_exchange_overview(files)
    assert overview["forwarding_count"] == 2
    assert overview["external_forwarding"] is True
    rows, cost = _forwarding_findings(files)
    assert rows == ["Ola Nordmann → ola@mail.example"]
    assert cost == 5


async def test_a_mailbox_called_no_reply_still_counts_as_forwarding(tmp_path):
    files, _ = await _collect(tmp_path, {"forwarding": FORWARDING})

    assert _parse_exchange_overview(files)["forwarding_count"] == 3
    assert _parse_exchange_overview(_text_only(files))["forwarding_count"] == 2, "the text drops it"


async def test_the_forwarding_findings_come_from_the_sidecar(tmp_path):
    """Where the text and the sidecar disagree, the recommendation and score follow the sidecar."""
    files, _ = await _collect(tmp_path, {"forwarding": FORWARDING[:2]})
    files["28b_exchange_external_forwarding_WARN.txt"] += "".join(
        f"  Lagt til {n}  →  smtp:x{n}@mail.example\n" for n in range(4)
    )

    rows, cost = _forwarding_findings(files)
    assert rows == ["Ola Nordmann → ola@mail.example"]
    assert cost == 5, "one mailbox, not five"


# ── Inbox rules ───────────────────────────────────────────────────────────────


def _inbox_rule(mailbox: str, rule: str, *targets: str) -> dict:
    """One rule as the helper's inbox-rule block writes it."""
    return {"Mailbox": mailbox, "Rule": rule, "Enabled": True, "Targets": list(targets)}


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_inbox_rule_counts_survive_the_round_trip(tmp_path, sidecars):
    rules = [
        _inbox_rule("kari@acme.example", "Til Gmail", '"kari" [SMTP:kari@mail.example]'),
        _inbox_rule("ola@acme.example", "Kopi", '"ola" [SMTP:ola@mail.example]'),
    ]
    files, _ = await _collect(tmp_path, {"inbox_rules_external": rules}, sidecars=sidecars)
    assert ("29_exchange_inbox_rules_external_fwd_WARN.json" in files) is sidecars

    assert _parse_exchange_overview(files)["inbox_rules_external"] == 2
    assert _controls(files)["4.4"]["status"] == "warn"


async def test_no_inbox_rules_is_counted_as_none_from_the_sidecar(tmp_path):
    files, _ = await _collect(tmp_path, {"inbox_rules_external": []})

    assert files["29_exchange_inbox_rules_external_fwd.json"]
    assert _parse_exchange_overview(files)["inbox_rules_external"] == 0


async def test_a_rule_name_that_reads_like_a_count_does_not_change_the_count(tmp_path):
    rules = [
        _inbox_rule("kari@acme.example", "Videresend (3 results)", "kari@mail.example"),
        _inbox_rule("ola@acme.example", "Kopi", "ola@mail.example"),
    ]
    files, _ = await _collect(tmp_path, {"inbox_rules_external": rules})

    assert _parse_exchange_overview(files)["inbox_rules_external"] == 2
    assert _parse_exchange_overview(_text_only(files))["inbox_rules_external"] != 2


# ── Defender for Office 365: Safe Links / Safe Attachments ────────────────────


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


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
@pytest.mark.parametrize(
    ("safe_links", "expected"),
    [
        (
            [
                {"Name": "Built-In Protection Policy", "IsEnabled": True},
                {"Name": "Ledelse", "IsEnabled": False},
            ],
            ("pass", "1 aktiv(e) Safe Links"),
        ),
        ([{"Name": "Ledelse", "IsEnabled": False}], ("fail", "Safe Links-policy(er) finnes")),
    ],
    ids=["one on, one off", "present but off"],
)
async def test_safe_links_state_survives_the_round_trip(tmp_path, sidecars, safe_links, expected):
    exo = {
        "defender_policies": {
            "safe_links": safe_links,
            "safe_attachments": [{"Name": "Built-In Protection Policy", "Action": "Block"}],
        }
    }
    files, _ = await _collect(tmp_path, exo, sidecars=sidecars)
    assert ("27_exchange_defender_policies.json" in files) is sidecars

    controls = _controls(files)
    assert controls["4.5"]["status"] == expected[0]
    assert controls["4.5"]["detail"].startswith(expected[1])
    assert controls["4.6"]["status"] == "pass"


async def test_a_policy_of_the_other_type_named_safe_links_is_not_a_safe_links_policy(tmp_path):
    """The text reader calls Safe Links present when "safe links" appears anywhere.

    A Safe Attachments policy named "Safe Links og vedlegg" then made a tenant
    with no Safe Links policy fail for having one switched off, where the
    sidecar says there is none.
    """
    exo = {
        "defender_policies": {
            "safe_links": None,
            "safe_attachments": {"Name": "Safe Links og vedlegg", "Action": "Block"},
        }
    }
    files, _ = await _collect(tmp_path, exo)

    row = _controls(files)["4.5"]
    assert (row["status"], row["detail"]) == ("warn", "Ingen Safe Links-policyer funnet")
    assert _controls(_text_only(files))["4.5"]["status"] == "fail", "the text cannot tell"


# ── Organization config (CIS 4.1) and Unified Audit Log ingestion (CIS 9.1) ──

ORG_CONFIG = {
    "OAuth2ClientProfileEnabled": True,
    "MapiHttpEnabled": True,
    "DefaultAuthenticationPolicy": None,
    "SmtpClientAuthenticationDisabled": True,
    "ActivityBasedAuthenticationTimeoutEnabled": True,
    "ActivityBasedAuthenticationTimeoutInterval": "06:00:00",
}


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
@pytest.mark.parametrize(
    ("value", "mailbox_audit", "unified_audit_log"),
    [(True, "fail", "pass"), (False, "pass", "fail"), (None, "info", "info")],
    ids=["on", "off", "not returned"],
)
async def test_the_audit_settings_survive_the_round_trip(
    tmp_path, sidecars, value, mailbox_audit, unified_audit_log
):
    # AuditDisabled=True is the bad value; ingestion enabled=True the good one.
    exo = {
        "org_config": {**ORG_CONFIG, "AuditDisabled": value},
        "admin_audit_log_config": {"UnifiedAuditLogIngestionEnabled": value},
    }
    files, _ = await _collect(tmp_path, exo, sidecars=sidecars)
    assert ("27c_exchange_org_config.json" in files) is sidecars

    controls = _controls(files)
    assert controls["4.1"]["status"] == mailbox_audit
    assert controls["9.1"]["status"] == unified_audit_log


async def test_the_audit_settings_come_from_the_sidecar(tmp_path):
    exo = {
        "org_config": {**ORG_CONFIG, "AuditDisabled": False},
        "admin_audit_log_config": {"UnifiedAuditLogIngestionEnabled": True},
    }
    files, _ = await _collect(tmp_path, exo)
    # Text the reader cannot read: only the sidecar can answer now.
    files["27c_exchange_org_config.txt"] = "EXCHANGE ORG CONFIG\n"
    files["27d_exchange_admin_audit_log_config.txt"] = "EXCHANGE ADMIN AUDIT LOG CONFIG\n"

    controls = _controls(files)
    assert controls["4.1"]["status"] == "pass"
    assert controls["9.1"]["status"] == "pass"


async def test_a_setting_the_helper_sent_as_a_word_is_typed_in_the_sidecar(tmp_path):
    exo = {
        "org_config": {**ORG_CONFIG, "AuditDisabled": "False"},
        "admin_audit_log_config": {"UnifiedAuditLogIngestionEnabled": "True"},
    }
    files, _ = await _collect(tmp_path, exo)

    assert '"AuditDisabled": false' in files["27c_exchange_org_config.json"]
    assert (
        '"UnifiedAuditLogIngestionEnabled": true'
        in files["27d_exchange_admin_audit_log_config.json"]
    )
    controls = _controls(files)
    assert (controls["4.1"]["status"], controls["9.1"]["status"]) == ("pass", "pass")


# ── Purview: sensitivity labels (Graph), DLP and retention (the helper) ──────

PARENT = "00000000-0000-0000-0000-00000000000a"


def _label(name: str, priority: int, *, active: bool = True, parent: str | None = None) -> dict:
    """One label as Graph's sensitivityLabels collection returns it."""
    label = {"id": f"label-{priority}", "name": name, "priority": priority, "isActive": active}
    if parent:
        label["parent"] = {"id": parent}
    return label


LABELS = [
    _label("Offentlig", 0),
    _label("Intern", 1),
    _label("Konfidensiell", 2, parent=PARENT),
    _label("Utgått", 3, active=False),
]
DLP = [
    {"Name": "Kundedata", "Mode": "Enable", "Workloads": "Exchange,SharePoint", "Priority": 0},
    {
        "Name": "Fødselsnummer",
        "Mode": "TestWithNotifications",
        "Workloads": "Exchange",
        "Priority": 1,
    },
]
RETENTION = [{"Name": "Sju år", "Enabled": True, "Workloads": "Exchange,SharePoint,OneDrive"}]


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_purview_survives_the_round_trip(tmp_path, sidecars):
    exo = {"dlp_policies": DLP, "retention_policies": RETENTION}
    files, _ = await _collect(tmp_path, exo, labels=LABELS, sidecars=sidecars)
    assert ("19c_purview_sensitivity_labels.json" in files) is sidecars

    purview = _parse_purview(files)
    assert purview["sensitivity_labels"] == [
        {"name": "Offentlig", "priority": 0, "active": True},
        {"name": "Intern", "priority": 1, "active": True},
        {"name": "Konfidensiell", "priority": 2, "active": True},
        {"name": "Utgått", "priority": 3, "active": False},
    ]
    assert [p["name"] for p in purview["dlp_policies"]] == ["Kundedata", "Fødselsnummer"]
    assert [p["name"] for p in purview["retention_policies"]] == ["Sju år"]

    controls = _controls(files, purview=purview)
    assert controls["3.1.1"]["detail"] == "2 DLP-policyer konfigurert"
    assert controls["3.2.1"]["detail"] == "4 sensitivitetsetiketter publisert"
    assert controls["7.2.2"]["detail"] == "1 oppbevaringspolicyer"


async def test_every_label_is_counted_under_its_whole_name(tmp_path):
    """The text cuts names at 45 characters and skips lines that read like headings."""
    long_name = "Strengt fortrolig - kun ledergruppen og styret i konsernet"
    assert len(long_name) > 45
    labels = [_label(long_name, 0), _label("No restrictions", 1), _label("Purview test", 2)]
    files, _ = await _collect(tmp_path, {}, labels=labels)

    purview = _parse_purview(files)
    assert [label["name"] for label in purview["sensitivity_labels"]] == [
        long_name,
        "No restrictions",
        "Purview test",
    ]
    assert _parse_purview(_text_only(files))["sensitivity_label_count"] == 1, "the text loses two"


async def test_the_policy_names_come_from_the_purview_sidecars(tmp_path):
    files, _ = await _collect(tmp_path, {"dlp_policies": DLP, "retention_policies": RETENTION})
    for name in ("19d_purview_dlp_policies.txt", "19e_purview_retention_policies.txt"):
        files[name] = files[name].replace("Name: ", "Name: Endret ")  # the text now disagrees

    purview = _parse_purview(files)
    assert [p["name"] for p in purview["dlp_policies"]] == ["Kundedata", "Fødselsnummer"]
    assert [p["name"] for p in purview["retention_policies"]] == ["Sju år"]


async def test_a_refused_label_read_writes_no_sidecar(tmp_path):
    files, _ = await _collect(tmp_path, {}, labels=refused())

    assert files["19c_purview_sensitivity_labels.txt"] == "", "an error stub, blanked"
    assert "19c_purview_sensitivity_labels.json" not in files
    purview = _parse_purview(files)
    assert purview["sensitivity_label_count"] == 0
    assert _controls(files, purview=purview)["3.2.1"]["status"] == "info"


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
        sidecar = name[:-4] + ".json"
        assert sidecar not in files, f"no {sidecar}: a missing sidecar never means empty"


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

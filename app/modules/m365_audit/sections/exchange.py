"""Section 20-29 — Exchange Online (data sourced from EXO PowerShell helper),
plus the Purview trio 19c/19d/19e.

19d and 19e come from the EXO helper. 19c (sensitivity labels) comes from
Graph, and is collected here so that one section owns all three Purview
outputs rather than splitting them across two.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.modules.base import BaseSection, SectionResult, SectionStatus
from app.modules.m365_audit.graph_client import GraphClient


def _fmt_val(val: Any, indent: int = 4) -> str:
    """Recursively format a value for human-readable output."""
    pad = " " * indent
    if val is None:
        return "N/A"
    if isinstance(val, bool):
        return "Yes" if val else "No"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, str):
        return val or "(empty)"
    if isinstance(val, list):
        if not val:
            return "(none)"
        if all(isinstance(i, str) and len(i) < 60 for i in val):
            joined = ", ".join(str(i) for i in val)
            if len(joined) < 100:
                return joined
        return "\n" + "\n".join(f"{pad}- {_fmt_val(i, indent + 2)}" for i in val)
    if isinstance(val, dict):
        inner = "\n".join(f"{pad}{k}: {_fmt_val(v, indent + 2)}" for k, v in val.items())
        return "\n" + inner
    return str(val)


def _records(val: Any) -> list[dict]:
    """A list the helper nests inside another key, as a list of dicts.

    ConvertTo-Json writes a pipeline that yielded one result as that object,
    not a one-item list, and one that yielded nothing as null. Iterating the
    single object walked its keys instead of its one record.
    """
    if isinstance(val, list):
        return [v for v in val if isinstance(v, dict)]
    return [val] if isinstance(val, dict) else []


def _flag(val: Any) -> bool | None:
    """A yes/no setting as a boolean, or None when its value says neither.

    The same four words the report's text reader accepts, so a setting reads
    the same from the sidecar as from the text.
    """
    if isinstance(val, bool):
        return val
    word = str(val).strip().lower() if isinstance(val, str) else ""
    return {"true": True, "yes": True, "false": False, "no": False}.get(word)


# ── Where forwarding goes ─────────────────────────────────────────────────────
#
# Three answers, never two: a target inside the tenant, one outside it, and one
# the run cannot place. "Cannot place" is never rounded to either side: called
# external, a rule forwarding to a colleague was a critical finding; called
# internal, a rule forwarding out of the tenant would pass CIS 4.4.

INTERNAL, EXTERNAL, UNVERIFIED = "internal", "external", "unverified"

# Recipient types that are the tenant's own: mail to one stays in Exchange
# Online. A group counts as one, whatever its members.
_INTERNAL_RECIPIENT_TYPES = frozenset(
    t.lower()
    for t in (
        "UserMailbox",
        "SharedMailbox",
        "RoomMailbox",
        "EquipmentMailbox",
        "SchedulingMailbox",
        "LinkedMailbox",
        "TeamMailbox",
        "GroupMailbox",
        "DiscoveryMailbox",
        "MailUniversalDistributionGroup",
        "MailUniversalSecurityGroup",
        "MailNonUniversalGroup",
        "DynamicDistributionGroup",
        "RoomList",
        "PublicFolder",
    )
)
# Recipients that stand for an address somewhere else: mail to one goes to its
# ExternalEmailAddress, and that address decides.
_ADDRESS_ELSEWHERE_TYPES = frozenset(("mailcontact", "mailuser", "guestmailuser"))

# The address in an inbox-rule target: '"Kari" [SMTP:kari@example.com]' is a
# one-off address, '"Kari" [EX:/o=ExchangeLabs/...]' a directory recipient.
_RULE_TARGET = re.compile(r"\[(?P<kind>[A-Za-z0-9]+):(?P<value>[^\]]*)\]\s*$")


def _bare_address(address: str) -> str:
    """An address without its "smtp:" prefix or angle brackets."""
    addr = address.strip().strip("<>").strip()
    return addr[5:] if addr.lower().startswith("smtp:") else addr


def _address_scope(address: str, domains: list[str]) -> str:
    """Internal, external or unverified for one SMTP address, on its whole domain.

    Unverified when it is not an address at all, or when the run has no
    verified domains to hold it against: without them every address read as
    external.
    """
    local, at, domain = _bare_address(address).rpartition("@")
    domain = domain.strip().lower()
    if not (at and local and domain) or not domains:
        return UNVERIFIED
    return INTERNAL if domain in {d.lower() for d in domains} else EXTERNAL


def _recipient_scope(info: Any, domains: list[str]) -> tuple[str, str]:
    """(scope, address) for a directory recipient the helper looked up.

    ``info`` is what exo_collector.ps1's Resolve-RecipientInfo returned for it,
    or None when the helper could not look it up (or predates the lookup).
    """
    if not isinstance(info, dict):
        return UNVERIFIED, ""
    kind = str(info.get("RecipientTypeDetails") or "").strip().lower()
    smtp = _bare_address(str(info.get("PrimarySmtpAddress") or ""))
    if kind in _INTERNAL_RECIPIENT_TYPES:
        return INTERNAL, smtp
    elsewhere = _bare_address(str(info.get("ExternalEmailAddress") or ""))
    if kind in _ADDRESS_ELSEWHERE_TYPES and elsewhere:
        return _address_scope(elsewhere, domains), elsewhere
    return UNVERIFIED, smtp


def _rule_target(target: Any, recipients: dict[str, dict], domains: list[str]) -> dict:
    """{"target", "address", "scope"} for one inbox-rule target as Exchange wrote it."""
    text = str(target or "").strip()
    match = _RULE_TARGET.search(text)
    if match and match["kind"].upper() == "SMTP":
        address = _bare_address(match["value"])
        scope = _address_scope(address, domains)
    elif match and match["kind"].upper() == "EX":
        scope, address = _recipient_scope(recipients.get(text), domains)
    elif not match and "@" in text and not any(c.isspace() for c in text):
        address = _bare_address(text)
        scope = _address_scope(address, domains)
    else:
        scope, address = UNVERIFIED, ""
    return {"target": text, "address": address, "scope": scope}


def _overall_scope(scopes: list[str]) -> str:
    """External if any target is, else unverified if any is, else internal."""
    if EXTERNAL in scopes:
        return EXTERNAL
    if UNVERIFIED in scopes or not scopes:
        return UNVERIFIED
    return INTERNAL


def _policy_state(policies: list[dict], kind: str) -> dict[str, int]:
    """How many Defender policies of one PolicyType there are, and how many are on.

    "Enabled" is judged on the value as the text writes it, the way the
    report's text reader judges it, so the sidecar and the text cannot differ.
    """
    found = [p for p in policies if kind in str(p.get("PolicyType") or "").lower().replace(" ", "")]
    on = [p for p in found if _fmt_val(p.get("Enabled")).strip().lower() in ("true", "yes", "1")]
    return {"total": len(found), "enabled": len(on)}


def _section_block(title: str, items: list[dict], key_fields: list[str] | None = None) -> str:
    """Format a list of dicts as a readable block."""
    lines = [
        "=" * 80,
        f"  {title}  ({len(items)} entries)",
        "=" * 80,
    ]
    if not items:
        lines += ["  (none)", ""]
        return "\n".join(lines)

    for i, item in enumerate(items, 1):
        lines.append(f"\n  [{i}]")
        if key_fields:
            # Show key fields first, then the rest
            shown = set()
            for k in key_fields:
                if k in item:
                    lines.append(f"    {k}: {_fmt_val(item[k])}")
                    shown.add(k)
            for k, v in item.items():
                if k not in shown:
                    lines.append(f"    {k}: {_fmt_val(v)}")
        else:
            for k, v in item.items():
                lines.append(f"    {k}: {_fmt_val(v)}")
    lines += ["", "=" * 80, ""]
    return "\n".join(lines)


class ExchangeSection(BaseSection):
    name = "Exchange Online"

    def __init__(
        self,
        out_dir: Path,
        exo_data: dict,
        verified_domains: list[str],
        progress_cb=None,
        *,
        graph: GraphClient,
    ):
        # graph is keyword-only on purpose. Inserting it as a fourth positional
        # would have silently swallowed the progress_cb the one caller passes
        # there, which is the failure identity_security.py:30 documents. A
        # missing graph has to be a TypeError, not a section that runs blind.
        super().__init__(out_dir, progress_cb)
        self.exo_data = exo_data
        self.verified_domains = verified_domains
        self.graph = graph

    def _isolated(self, label: str, fn) -> None:
        """Run one sub-collection so its failure degrades that item, not the
        whole section. A late save that raised used to flip Exchange to FAILED
        even though the mailbox/transport/antiphish data was already written and
        rendered — a "✗ Failed" badge over complete data (review, F3)."""
        try:
            fn()
        except Exception as ex:
            self._warn(f"Exchange: {label} could not be collected: {ex}", level="info")

    async def collect(self) -> SectionResult:
        self._report(SectionStatus.RUNNING)
        try:
            # Sensitivity labels come from Graph, not from the EXO helper, so
            # they are collected before the helper's error is considered. Put
            # below the guard they would vanish whenever PowerShell failed to
            # connect, which is a routine outcome, and the report would then
            # attest "no labels" on evidence it never gathered.
            try:
                await self._collect_sensitivity_labels()
            except Exception as ex:
                self._warn(
                    f"Exchange: sensitivity labels could not be collected: {ex}", level="info"
                )

            # Check for error from PS helper
            if "error" in self.exo_data:
                err_msg = self.exo_data["error"]
                self._save(
                    "EXCHANGE_ERROR.txt",
                    f"Exchange Online data collection failed:\n{err_msg}\n",
                )
                self._report(SectionStatus.SKIPPED, err_msg)
                return self.result

            # Each sub-collection is isolated: one failing save must not discard
            # the whole section's already-written data as "Failed" (F3).
            for label, fn in (
                ("mailboxes", self._save_mailboxes),
                ("transport rules", self._save_transport_rules),
                ("connectors", self._save_connectors),
                ("anti-phishing", self._save_anti_phish),
                ("anti-spam", self._save_anti_spam),
                ("DKIM", self._save_dkim),
                ("Defender policies", self._save_defender_policies),
                ("quarantine policies", self._save_quarantine_policies),
                ("org config", self._save_org_config),
                ("admin audit log config", self._save_admin_audit_log_config),
                ("forwarding", self._save_forwarding),
                ("inbox rules", self._save_inbox_rules),
                ("DLP", self._save_dlp),
                ("retention", self._save_retention),
                ("mailbox delegations", self._save_mailbox_delegations),
            ):
                self._isolated(label, fn)

            self._report(SectionStatus.DONE)
        except Exception as e:
            self._report(SectionStatus.FAILED, str(e))
        return self.result

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get(self, key: str) -> list[dict]:
        val = self.exo_data.get(key, [])
        if isinstance(val, list):
            return val
        if isinstance(val, dict):
            return [val]
        return []

    def _get_single(self, key: str) -> dict:
        val = self.exo_data.get(key, {})
        if isinstance(val, list) and val:
            return val[0]
        if isinstance(val, dict):
            return val
        return {}

    def _read_failed(self, error_key: str, found: Any, what: str, *filenames: str) -> bool:
        """Write the helper's error in place of an empty result, and say so.

        Each block of the helper records its failure under its own *_error key
        and leaves its data out (see _save_anti_phish). Written as a section
        with no entries, a failed read was a reading of "none": a tenant whose
        compliance session did not connect had no DLP or retention policies,
        one without the Defender cmdlets had no Safe Links policy, and a failed
        forwarding scan passed CIS 4.4. The "Error:" stub is what the report
        reads as not collected.
        """
        error = self.exo_data.get(error_key)
        if not error or found:
            return False
        for filename in filenames:
            self._save(filename, f"Error: could not collect {what} — {error}\n")
        return True

    # ── Mailboxes ─────────────────────────────────────────────────────────────

    def _save_mailboxes(self) -> None:
        mailboxes = self._get("mailboxes")
        if self._read_failed(
            "mailboxes_error",
            mailboxes,
            "mailboxes",
            "20_exchange_mailboxes.txt",
            "20_exchange_mailboxes_count.txt",
        ):
            return
        total = len(mailboxes)
        shared = sum(
            1
            for m in mailboxes
            if (m.get("RecipientTypeDetails") or m.get("RecipientType", "")) == "SharedMailbox"
        )
        room = sum(
            1
            for m in mailboxes
            if (m.get("RecipientTypeDetails") or m.get("RecipientType", "")) == "RoomMailbox"
        )
        # The helper collects equipment mailboxes as well, and "user" used to be
        # whatever was neither shared nor a room, so every projector and pool
        # car was a user mailbox on the report.
        equipment = sum(
            1
            for m in mailboxes
            if (m.get("RecipientTypeDetails") or m.get("RecipientType", "")) == "EquipmentMailbox"
        )
        user_mb = total - shared - room - equipment

        lines = [
            "=" * 100,
            f"  EXCHANGE MAILBOXES  ({total} total)",
            "=" * 100,
            f"  {'Display Name':<40} {'UPN':<45} {'Type':<20} {'Quota'}",
            "  " + "-" * 96,
        ]
        rows: list[dict] = []
        for m in mailboxes:
            row = {
                "display_name": m.get("DisplayName"),
                # The helper did not send UserPrincipalName until it was added
                # beside PrimarySmtpAddress, so this column was blank in every
                # run, and licence optimisation, which looks for the shared and
                # room mailboxes here, never found one.
                "upn": m.get("UserPrincipalName") or m.get("PrimarySmtpAddress"),
                "primary_smtp_address": m.get("PrimarySmtpAddress"),
                "type": m.get("RecipientTypeDetails") or m.get("RecipientType"),
                "quota": m.get("TotalItemSize") or m.get("ProhibitSendReceiveQuota"),
            }
            rows.append(row)
            name = str(row["display_name"] or "")[:40]
            upn = str(row["upn"] or "")[:45]
            mtype = str(row["type"] or "")[:20]
            quota = str(row["quota"] or "N/A")[:20]
            lines.append(f"  {name:<40} {upn:<45} {mtype:<20} {quota}")
        lines += ["=" * 100, ""]
        self._save("20_exchange_mailboxes.txt", "\n".join(lines))
        self._save_sidecar("20_exchange_mailboxes.txt", {"count": total, "mailboxes": rows})

        count_lines = [
            "=" * 40,
            "  EXCHANGE MAILBOX COUNT",
            "=" * 40,
            f"  Total     : {total}",
            f"  User      : {user_mb}",
            f"  Shared    : {shared}",
            f"  Room      : {room}",
            f"  Equipment : {equipment}",
            "=" * 40,
            "",
        ]
        self._save("20_exchange_mailboxes_count.txt", "\n".join(count_lines))
        self._save_sidecar(
            "20_exchange_mailboxes_count.txt",
            {
                "total": total,
                "user": user_mb,
                "shared": shared,
                "room": room,
                "equipment": equipment,
            },
        )

    # ── Transport Rules ───────────────────────────────────────────────────────

    def _save_transport_rules(self) -> None:
        rules = self._get("transport_rules")
        if self._read_failed(
            "transport_rules_error", rules, "transport rules", "21_exchange_transport_rules.txt"
        ):
            return
        content = _section_block(
            "EXCHANGE TRANSPORT RULES",
            rules,
            key_fields=["Name", "State", "Priority", "Description"],
        )
        self._save("21_exchange_transport_rules.txt", content)
        self._save_sidecar("21_exchange_transport_rules.txt", {"count": len(rules), "rules": rules})

    # ── Connectors ────────────────────────────────────────────────────────────

    def _connectors(self) -> list[dict]:
        """One dict per connector, inbound and outbound alike.

        The helper returns {"inbound": ..., "outbound": ...}, and each side is a
        list, a single object (ConvertTo-Json unwraps a one-item pipeline) or
        null. _get() wrapped that whole dict as one record, so the report
        counted one connector for a tenant with none and one for a tenant with
        five. A list, or a dict without those two keys, is already one record
        per connector and is kept as it is.
        """
        raw = self.exo_data.get("connectors")
        if not isinstance(raw, dict) or not raw.keys() & {"inbound", "outbound"}:
            return self._get("connectors")
        return [
            {"Name": c.get("Name"), "Direction": direction.capitalize(), **c}
            for direction in ("inbound", "outbound")
            for c in _records(raw.get(direction))
        ]

    def _save_connectors(self) -> None:
        connectors = self._connectors()
        if self._read_failed(
            "connectors_error", connectors, "connectors", "22_exchange_connectors.txt"
        ):
            return
        content = _section_block(
            "EXCHANGE CONNECTORS",
            connectors,
            key_fields=["Name", "ConnectorType", "ConnectorSource", "Enabled", "SmartHosts"],
        )
        self._save("22_exchange_connectors.txt", content)
        self._save_sidecar(
            "22_exchange_connectors.txt", {"count": len(connectors), "connectors": connectors}
        )

    # ── Anti-Phish ────────────────────────────────────────────────────────────

    def _save_anti_phish(self) -> None:
        policies = self._get("anti_phish")
        # The cmdlet runs with -ErrorAction SilentlyContinue and records its
        # failure in a separate key, so an empty list means either "no
        # policies" or "the read failed" — and nothing here used to tell them
        # apart. EOP ships an undeletable default anti-phish policy, so zero
        # rows from a connected session is the second case, and the compliance
        # control now grades a zero as a failure. Write the error through so
        # it can say "could not verify" instead of accusing the tenant.
        error = self.exo_data.get("anti_phish_error")
        if error and not policies:
            self._save(
                "23_exchange_antiphish.txt",
                f"Error: could not collect anti-phishing policies — {error}\n",
            )
            return
        content = _section_block(
            "EXCHANGE ANTI-PHISHING POLICIES",
            policies,
            key_fields=["Name", "Enabled", "PhishThresholdLevel", "EnableMailboxIntelligence"],
        )
        self._save("23_exchange_antiphish.txt", content)
        self._save_sidecar(
            "23_exchange_antiphish.txt", {"count": len(policies), "policies": policies}
        )

    # ── Anti-Spam ─────────────────────────────────────────────────────────────

    def _save_anti_spam(self) -> None:
        policies = self._get("anti_spam")
        error = self.exo_data.get("anti_spam_error")  # see _save_anti_phish
        if error and not policies:
            self._save(
                "24_exchange_antispam.txt",
                f"Error: could not collect anti-spam policies — {error}\n",
            )
            return
        content = _section_block(
            "EXCHANGE ANTI-SPAM POLICIES",
            policies,
            key_fields=["Name", "SpamAction", "BulkSpamAction", "PhishSpamAction"],
        )
        self._save("24_exchange_antispam.txt", content)
        self._save_sidecar(
            "24_exchange_antispam.txt", {"count": len(policies), "policies": policies}
        )

    # ── DKIM ──────────────────────────────────────────────────────────────────

    def _save_dkim(self) -> None:
        configs = self._get("dkim")
        if self._read_failed("dkim_error", configs, "DKIM signing configs", "25_exchange_dkim.txt"):
            return
        lines = [
            "=" * 80,
            f"  EXCHANGE DKIM SIGNING CONFIGS  ({len(configs)} total)",
            "=" * 80,
            f"  {'Domain':<45} {'Enabled':>8} {'Status':<20} {'Selector'}",
            "  " + "-" * 76,
        ]
        rows: list[dict] = []
        for d in configs:
            row = {
                "domain": str(d.get("Domain") or ""),
                # Only a real yes is signing: "False" as a word was truthy and
                # printed "Yes".
                "enabled": _flag(d.get("Enabled")) is True,
                "status": d.get("Status"),
                "selector": d.get("Selector1CNAME") or d.get("Selector"),
            }
            rows.append(row)
            domain = row["domain"][:45]
            enabled = "Yes" if row["enabled"] else "No"
            status = str(row["status"] or "")[:20]
            selector = str(row["selector"] or "N/A")[:30]
            lines.append(f"  {domain:<45} {enabled:>8} {status:<20} {selector}")
        lines += ["=" * 80, ""]
        self._save("25_exchange_dkim.txt", "\n".join(lines))
        # CIS 5.2.3 reads whether Exchange signs for each mail domain from here,
        # with each domain whole: the table cuts it to 45 characters.
        self._save_sidecar("25_exchange_dkim.txt", {"count": len(rows), "configs": rows})

    # ── Defender Policies ─────────────────────────────────────────────────────

    def _save_defender_policies(self) -> None:
        # The collector returns {safe_links: [...], safe_attachments: [...]} —
        # a dict of two lists, each policy carrying IsEnabled / Enable+Action
        # rather than the Name/PolicyType/Enabled the report parser reads.
        # _get() would wrap that whole dict as a single unparseable "policy",
        # so the report saw no Safe Links / Safe Attachments at all — including
        # the tenant Built-In Protection Policy — and reported them "not found".
        # Flatten to one block per policy in the shape the parser expects.
        raw = self.exo_data.get("defender_policies", {}) or {}
        policies: list[dict] = []
        if isinstance(raw, list):
            policies = raw
        elif isinstance(raw, dict):
            # _records: a tenant whose only policy is the Built-In Protection
            # Policy gets it as one object, and iterating that object's keys
            # lost the whole file.
            for p in _records(raw.get("safe_links")):
                policies.append(
                    {
                        "Name": p.get("Name"),
                        "PolicyType": "SafeLinksPolicy",
                        # Get-SafeLinksPolicy exposes IsEnabled.
                        "Enabled": bool(p.get("IsEnabled")),
                    }
                )
            for p in _records(raw.get("safe_attachments")):
                action = str(p.get("Action") or "").strip().lower()
                # Safe Attachments protects when Enable is true OR the action is
                # a protective mode. The Built-In Protection Policy reports
                # Action=Block (Enable may be unset) and is protection all the
                # same, so counting only Enable would miss it.
                enabled = bool(p.get("Enable")) or action in ("block", "replace", "dynamicdelivery")
                policies.append(
                    {
                        "Name": p.get("Name"),
                        "PolicyType": "SafeAttachmentsPolicy",
                        "Enabled": enabled,
                        "Action": p.get("Action"),
                    }
                )
        if self._read_failed(
            "defender_policies_error",
            policies,
            "Defender for Office 365 policies",
            "27_exchange_defender_policies.txt",
        ):
            return
        content = _section_block(
            "MICROSOFT DEFENDER FOR OFFICE 365 POLICIES",
            policies,
            key_fields=["Name", "PolicyType", "Enabled"],
        )
        self._save("27_exchange_defender_policies.txt", content)
        self._save_sidecar(
            "27_exchange_defender_policies.txt",
            {
                "count": len(policies),
                "policies": policies,
                "safe_links": _policy_state(policies, "safelinks"),
                "safe_attachments": _policy_state(policies, "safeattach"),
            },
        )

    # ── Quarantine Policies ───────────────────────────────────────────────────

    def _save_quarantine_policies(self) -> None:
        policies = self._get("quarantine_policies")
        if self._read_failed(
            "quarantine_policies_error",
            policies,
            "quarantine policies",
            "27b_exchange_quarantine_policies.txt",
        ):
            return
        content = _section_block(
            "EXCHANGE QUARANTINE POLICIES",
            policies,
            key_fields=["Name", "EndUserQuarantinePermissionsValue", "ESNEnabled"],
        )
        self._save("27b_exchange_quarantine_policies.txt", content)

    # ── Org Config ────────────────────────────────────────────────────────────

    def _save_org_config(self) -> None:
        cfg = self._get_single("org_config")
        if self._read_failed(
            "org_config_error", cfg, "the organization config", "27c_exchange_org_config.txt"
        ):
            return
        lines = ["=" * 80, "  EXCHANGE ORG CONFIG", "=" * 80]
        for k, v in cfg.items():
            lines.append(f"  {k}: {_fmt_val(v)}")
        lines += ["=" * 80, ""]
        self._save("27c_exchange_org_config.txt", "\n".join(lines))
        # Every setting as the helper gave it, with the one CIS 4.1 reads as a
        # boolean, or null when the helper's value says neither.
        self._save_sidecar(
            "27c_exchange_org_config.txt",
            {**cfg, "AuditDisabled": _flag(cfg.get("AuditDisabled"))},
        )

    # ── Admin Audit Log Config (CIS 9.1) ──────────────────────────────────────

    def _save_admin_audit_log_config(self) -> None:
        # UnifiedAuditLogIngestionEnabled is the Exchange/Purview toggle CIS 9.1
        # is about — kept in its own file (not folded into org config) so the
        # control has one unambiguous source. Emit the label unconditionally:
        # a missing/null value renders as "N/A" via _fmt_val, which the report
        # reads as "not collected" (cannot-verify), so "collected: False" (a
        # real fail) stays distinct from "not collected" (fail-closed to info).
        cfg = self._get_single("admin_audit_log_config")
        if self._read_failed(
            "admin_audit_log_config_error",
            cfg,
            "the admin audit log config",
            "27d_exchange_admin_audit_log_config.txt",
        ):
            return
        lines = ["=" * 80, "  EXCHANGE ADMIN AUDIT LOG CONFIG", "=" * 80]
        val = cfg.get("UnifiedAuditLogIngestionEnabled")
        lines.append(f"  UnifiedAuditLogIngestionEnabled: {_fmt_val(val)}")
        lines += ["=" * 80, ""]
        self._save("27d_exchange_admin_audit_log_config.txt", "\n".join(lines))
        # null is "not collected", as N/A is in the text: cannot verify, never a fail.
        self._save_sidecar(
            "27d_exchange_admin_audit_log_config.txt",
            {"UnifiedAuditLogIngestionEnabled": _flag(val)},
        )

    # ── Mailbox Forwarding ────────────────────────────────────────────────────

    def _forwarding_targets(self, fwd: dict) -> list[tuple[str, str]]:
        """(label, scope) for each forwarding target a mailbox has set.

        ForwardingSmtpAddress is an address, decided on its whole domain. It
        used to be decided on the 45-character column, which turned a long
        address in a verified domain into one ending "@subsidiary.acme.e",
        unverified, so external: a critical finding for forwarding that never
        left the tenant.

        ForwardingAddress is a recipient identity, not an address, so the
        domain test on it always failed and every one was external forwarding,
        a mailbox forwarding to a colleague included. It is decided on what
        the helper resolved it to (ForwardingRecipient), and is unverified
        when the helper could not, or predates the lookup.

        Both are kept when both are set: Exchange forwards to the recipient,
        but an external address left beside it is not cleared, and is reported.
        """
        targets: list[tuple[str, str]] = []
        smtp = str(fwd.get("ForwardingSmtp") or fwd.get("ForwardingSmtpAddress") or "").strip()
        if smtp:
            targets.append((smtp, _address_scope(smtp, self.verified_domains)))
        identity = str(fwd.get("ForwardingAddress") or "").strip()
        if identity:
            scope, address = _recipient_scope(fwd.get("ForwardingRecipient"), self.verified_domains)
            label = f"{identity} ({address})" if address and address != identity else identity
            targets.append((label, scope))
        return targets

    def _save_forwarding(self) -> None:
        fwd_list = self._get("forwarding")
        if self._read_failed(
            "forwarding_error", fwd_list, "mailbox forwarding", "28_exchange_mailbox_forwarding.txt"
        ):
            return
        lines = [
            "=" * 100,
            f"  MAILBOX FORWARDING  ({len(fwd_list)} entries)",
            "=" * 100,
            f"  {'Mailbox':<45} {'Forward To':<45} {'External':>10}",
            "  " + "-" * 96,
        ]
        external_fwd: list[tuple[str, str]] = []
        unverified = 0
        rows: list[dict] = []
        for fwd in fwd_list:
            mbx = str(
                fwd.get("DisplayName")
                or fwd.get("Name")
                or fwd.get("PrimarySmtpAddress")
                or fwd.get("Mailbox")
                or ""
            )
            targets = self._forwarding_targets(fwd)
            scope = _overall_scope([s for _, s in targets])
            fwd_to = ", ".join(label for label, _ in targets)
            if scope == EXTERNAL:
                outside = ", ".join(label for label, s in targets if s == EXTERNAL)
                external_fwd.append((mbx or "?", outside))
            elif scope == UNVERIFIED:
                unverified += 1
            # The column is headed External and used to show
            # DeliverToMailboxAndForward, so an address outside the tenant
            # that keeps no copy read "External: No".
            is_ext = {EXTERNAL: "Yes", INTERNAL: "No"}.get(scope, "Unverified")
            lines.append(f"  {mbx[:45]:<45} {fwd_to[:45]:<45} {is_ext:>10}")
            rows.append(
                {
                    "mailbox": mbx,
                    "primary_smtp_address": fwd.get("PrimarySmtpAddress"),
                    "forward_to": fwd_to,
                    "forwarding_address": fwd.get("ForwardingAddress"),
                    "forwarding_recipient": fwd.get("ForwardingRecipient"),
                    "forwarding_smtp_address": (
                        fwd.get("ForwardingSmtp") or fwd.get("ForwardingSmtpAddress")
                    ),
                    "deliver_and_forward": bool(
                        fwd.get("DeliverAndForward") or fwd.get("DeliverToMailboxAndForward")
                    ),
                    "external": scope == EXTERNAL,
                    "scope": scope,
                }
            )

        lines += ["=" * 100, ""]
        self._save("28_exchange_mailbox_forwarding.txt", "\n".join(lines))
        self._save_sidecar(
            "28_exchange_mailbox_forwarding.txt",
            {
                "count": len(rows),
                "external_count": len(external_fwd),
                "unverified_count": unverified,
                "forwarding": rows,
            },
        )
        if unverified:
            self._warn(
                f"{unverified} mailbox(es) forward to a recipient the audit could not "
                "place inside or outside the tenant",
                level="info",
            )

        if external_fwd:
            self._warn(
                f"{len(external_fwd)} mailbox(es) forwarding to external addresses",
                level="critical",
            )
            ext_lines = [
                "=" * 100,
                f"  EXTERNAL MAILBOX FORWARDING WARNING  ({len(external_fwd)} mailboxes)",
                "=" * 100,
            ]
            ext_rows: list[dict] = []
            for mbx_name, fwd_target in external_fwd:
                ext_lines.append(f"  {mbx_name}  →  {fwd_target}")
                ext_rows.append({"mailbox": mbx_name, "forward_to": fwd_target})
            ext_lines += ["=" * 100, ""]
            self._save("28b_exchange_external_forwarding_WARN.txt", "\n".join(ext_lines))
            self._save_sidecar(
                "28b_exchange_external_forwarding_WARN.txt",
                {"count": len(ext_rows), "forwarding": ext_rows},
            )

    # ── Inbox Rules ───────────────────────────────────────────────────────────

    def _inbox_rule(self, rule: dict) -> dict:
        """One forwarding rule with each target placed inside or outside the tenant.

        The helper sends every rule that forwards or redirects, to anyone. All
        of them used to go into the WARN file as external forwarding, so a
        rule forwarding to a colleague was a critical warning and a CIS 4.4
        warn. A target is now decided on its own: an SMTP address on its whole
        domain against the verified domains, a directory recipient ([EX:...])
        on what the helper found it to be, and anything else is unverified.
        """
        recipients = {
            str(r.get("Target") or "").strip(): r for r in _records(rule.get("TargetRecipients"))
        }
        raw = rule.get("Targets")
        targets = [
            _rule_target(t, recipients, self.verified_domains)
            for t in (raw if isinstance(raw, list) else [raw])
            if t not in (None, "")
        ]
        return {
            "mailbox": rule.get("Mailbox"),
            "rule": rule.get("Rule") or rule.get("Name"),
            "enabled": rule.get("Enabled"),
            "targets": targets,
            "scope": _overall_scope([t["scope"] for t in targets]),
        }

    @staticmethod
    def _inbox_rule_block(title: str, rules: list[dict]) -> str:
        """The rules as the text evidence shows them, one target per line."""
        return _section_block(
            title,
            [
                {
                    "Mailbox": r["mailbox"],
                    "Rule": r["rule"],
                    "Enabled": r["enabled"],
                    "Scope": r["scope"].capitalize(),
                    "Targets": [f"{t['target']} ({t['scope']})" for t in r["targets"]],
                }
                for r in rules
            ],
            key_fields=["Mailbox", "Rule", "Enabled", "Scope", "Targets"],
        )

    def _save_inbox_rules(self) -> None:
        rules = self._get("inbox_rules_external")
        if self._read_failed(
            "inbox_rules_error",
            rules,
            "inbox rules",
            "29_exchange_inbox_rules_external_fwd.txt",
        ):
            return
        placed = [self._inbox_rule(r) for r in rules]
        external = [r for r in placed if r["scope"] == EXTERNAL]
        unverified = [r for r in placed if r["scope"] == UNVERIFIED]

        # Every forwarding rule and where it goes: the scan ran, and this is
        # what it found. Only the external ones are a finding, in the WARN file.
        plain = "29_exchange_inbox_rules_external_fwd.txt"
        self._save(plain, self._inbox_rule_block("INBOX RULES THAT FORWARD OR REDIRECT", placed))
        self._save_sidecar(
            plain,
            {
                "count": len(placed),
                "external_count": len(external),
                "unverified_count": len(unverified),
                "rules": placed,
            },
        )
        if external:
            warn = "29_exchange_inbox_rules_external_fwd_WARN.txt"
            self._save(
                warn, self._inbox_rule_block("INBOX RULES WITH EXTERNAL FORWARDING", external)
            )
            self._save_sidecar(warn, {"count": len(external), "rules": external})
            self._warn(
                f"{len(external)} inbox rule(s) forwarding to external addresses found",
                level="critical",
            )
        if unverified:
            self._warn(
                f"{len(unverified)} inbox rule(s) forward to a recipient the audit could "
                "not place inside or outside the tenant",
                level="info",
            )

    # ── Sensitivity Labels (Graph, not EXO) ───────────────────────────────────

    async def _collect_sensitivity_labels(self) -> None:
        try:
            labels = await self.graph.get_all(
                "security/dataSecurityAndGovernance/sensitivityLabels",
                beta=True,
                params={"$top": "999"},
            )
        except Exception as ex:
            # Keep the "Error:" shape the reader blanks on — a 404 body must
            # not reach the customer report — but say what the status means.
            # A missing permission is refused with 401 or 403; Not Found says
            # the path is not a resource on this endpoint version, so sending
            # a technician to check consent wastes the trip. Whether the fix
            # is tenant-side provisioning or a moved beta path has to be
            # settled against Graph's reference, not guessed here.
            hint = ""
            if "InsufficientGraphPermissions" in str(ex) or "403" in str(ex):
                hint = (
                    "  This endpoint needs SensitivityLabels.Read.All. "
                    "InformationProtectionPolicy.Read.All\n"
                    "  does not cover it — the two are separate app roles.\n"
                )
            elif "404" in str(ex) or "Not Found" in str(ex):
                hint = (
                    "  Not a consent problem: a missing permission is refused with "
                    "401 or 403.\n  Not Found means the path is not a resource on "
                    "this endpoint version.\n"
                )
            self._save("19c_purview_sensitivity_labels.txt", f"Error: {ex}\n{hint}")
            self._warn(f"Sensitivity labels fetch failed: {ex}")
            return

        lines = [
            "=" * 90,
            f"  PURVIEW SENSITIVITY LABELS  ({len(labels)} total)",
            "=" * 90,
            f"  {'Label Name':<45} {'Priority':>9} {'Enabled':>8} {'Parent ID'}",
            "  " + "-" * 86,
        ]
        rows: list[dict] = []
        for lbl in labels:
            row = {
                "id": lbl.get("id"),
                "name": lbl.get("name"),
                "priority": lbl.get("priority", 0),
                "active": bool(lbl.get("isActive")),
                # "or {}": a parent Graph sends as null must not cost the list.
                "parent_id": (lbl.get("parent") or {}).get("id"),
            }
            rows.append(row)
            name = (row["name"] or "")[:45]
            priority = row["priority"]
            enabled = "Yes" if row["active"] else "No"
            parent = row["parent_id"] or "(top-level)"
            lines.append(f"  {name:<45} {priority:>9} {enabled:>8}  {parent}")
        lines += ["=" * 90, ""]
        self._save("19c_purview_sensitivity_labels.txt", "\n".join(lines))
        self._save_sidecar(
            "19c_purview_sensitivity_labels.txt", {"count": len(rows), "labels": rows}
        )

    # ── DLP Policies ──────────────────────────────────────────────────────────

    def _save_dlp(self) -> None:
        policies = self._get("dlp_policies")
        # One key for both: the helper connects to Security & Compliance once
        # for DLP and retention, and records a failed connection as dlp_error.
        if self._read_failed("dlp_error", policies, "DLP policies", "19d_purview_dlp_policies.txt"):
            return
        content = _section_block(
            "PURVIEW DLP POLICIES",
            policies,
            key_fields=["Name", "Mode", "Priority", "Workload"],
        )
        self._save("19d_purview_dlp_policies.txt", content)
        self._save_sidecar(
            "19d_purview_dlp_policies.txt", {"count": len(policies), "policies": policies}
        )

    # ── Retention Policies ────────────────────────────────────────────────────

    def _save_retention(self) -> None:
        policies = self._get("retention_policies")
        if self._read_failed(
            "dlp_error", policies, "retention policies", "19e_purview_retention_policies.txt"
        ):
            return
        content = _section_block(
            "PURVIEW RETENTION POLICIES",
            policies,
            key_fields=["Name", "Enabled", "RetentionRuleTypes"],
        )
        self._save("19e_purview_retention_policies.txt", content)
        self._save_sidecar(
            "19e_purview_retention_policies.txt", {"count": len(policies), "policies": policies}
        )

    # ── Mailbox Delegations ──────────────────────────────────────────────────

    def _save_mailbox_delegations(self) -> None:
        delegations = self._get("mailbox_delegations")
        error = self.exo_data.get("mailbox_delegation_error")

        if error and not delegations:
            self._save(
                "29b_exchange_mailbox_delegations.txt",
                f"Error collecting mailbox delegations: {error}\n",
            )
            return

        lines = [
            "=" * 110,
            f"  MAILBOX DELEGATIONS (SendAs / FullAccess)  ({len(delegations)} entries)",
            "=" * 110,
            f"  {'Mailbox':<45} {'Type':<15} {'Delegate'}",
            "  " + "-" * 106,
        ]

        full_access = []
        send_as = []
        for d in delegations:
            mailbox = str(d.get("Mailbox") or "")[:45]
            ptype = str(d.get("Type") or "")[:15]
            delegate = str(d.get("Delegate") or "")
            lines.append(f"  {mailbox:<45} {ptype:<15} {delegate}")
            if ptype == "FullAccess":
                full_access.append(d)
            elif ptype == "SendAs":
                send_as.append(d)

        lines += [
            "",
            f"  Summary: {len(full_access)} FullAccess, {len(send_as)} SendAs delegation(s)",
            "=" * 110,
            "",
        ]
        self._save("29b_exchange_mailbox_delegations.txt", "\n".join(lines))

        if delegations:
            self._warn(
                f"{len(delegations)} mailbox delegation(s) found "
                f"({len(full_access)} FullAccess, {len(send_as)} SendAs)"
            )

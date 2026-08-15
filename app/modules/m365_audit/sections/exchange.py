"""Section 20–29 — Exchange Online (data sourced from EXO PowerShell helper),
plus the Purview trio 19c/19d/19e.

19d and 19e come from the EXO helper. 19c (sensitivity labels) comes from
Graph, and is collected here so that one section owns all three Purview
outputs rather than splitting them across two.
"""

from __future__ import annotations

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
        items = [_fmt_val(i, indent) for i in val]
        if all(isinstance(i, str) and len(i) < 60 for i in val):
            joined = ", ".join(str(i) for i in val)
            if len(joined) < 100:
                return joined
        return "\n" + "\n".join(f"{pad}- {_fmt_val(i, indent+2)}" for i in val)
    if isinstance(val, dict):
        inner = "\n".join(
            f"{pad}{k}: {_fmt_val(v, indent+2)}" for k, v in val.items()
        )
        return "\n" + inner
    return str(val)


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
        self.exo_data        = exo_data
        self.verified_domains = verified_domains
        self.graph           = graph

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
                self._warn(f"Exchange: sensitivity labels could not be collected: {ex}", level="info")

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

    # ── Mailboxes ─────────────────────────────────────────────────────────────

    def _save_mailboxes(self) -> None:
        mailboxes = self._get("mailboxes")
        total    = len(mailboxes)
        shared   = sum(1 for m in mailboxes if (m.get("RecipientTypeDetails") or m.get("RecipientType", "")) == "SharedMailbox")
        room     = sum(1 for m in mailboxes if (m.get("RecipientTypeDetails") or m.get("RecipientType", "")) == "RoomMailbox")
        user_mb  = total - shared - room

        lines = [
            "=" * 100,
            f"  EXCHANGE MAILBOXES  ({total} total)",
            "=" * 100,
            f"  {'Display Name':<40} {'UPN':<45} {'Type':<20} {'Quota'}",
            "  " + "-" * 96,
        ]
        for m in mailboxes:
            name   = str(m.get("DisplayName") or "")[:40]
            upn    = str(m.get("UserPrincipalName") or "")[:45]
            mtype  = str(m.get("RecipientTypeDetails") or m.get("RecipientType") or "")[:20]
            quota  = str(m.get("TotalItemSize") or m.get("ProhibitSendReceiveQuota") or "N/A")[:20]
            lines.append(f"  {name:<40} {upn:<45} {mtype:<20} {quota}")
        lines += ["=" * 100, ""]
        self._save("20_exchange_mailboxes.txt", "\n".join(lines))

        count_lines = [
            "=" * 40,
            "  EXCHANGE MAILBOX COUNT",
            "=" * 40,
            f"  Total     : {total}",
            f"  User      : {user_mb}",
            f"  Shared    : {shared}",
            f"  Room      : {room}",
            "=" * 40,
            "",
        ]
        self._save("20_exchange_mailboxes_count.txt", "\n".join(count_lines))

    # ── Transport Rules ───────────────────────────────────────────────────────

    def _save_transport_rules(self) -> None:
        rules = self._get("transport_rules")
        content = _section_block(
            "EXCHANGE TRANSPORT RULES",
            rules,
            key_fields=["Name", "State", "Priority", "Description"],
        )
        self._save("21_exchange_transport_rules.txt", content)

    # ── Connectors ────────────────────────────────────────────────────────────

    def _save_connectors(self) -> None:
        connectors = self._get("connectors")
        content = _section_block(
            "EXCHANGE CONNECTORS",
            connectors,
            key_fields=["Name", "ConnectorType", "ConnectorSource", "Enabled", "SmartHosts"],
        )
        self._save("22_exchange_connectors.txt", content)

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
            self._save("23_exchange_antiphish.txt",
                       f"Error: could not collect anti-phishing policies — {error}\n")
            return
        content  = _section_block(
            "EXCHANGE ANTI-PHISHING POLICIES",
            policies,
            key_fields=["Name", "Enabled", "PhishThresholdLevel", "EnableMailboxIntelligence"],
        )
        self._save("23_exchange_antiphish.txt", content)

    # ── Anti-Spam ─────────────────────────────────────────────────────────────

    def _save_anti_spam(self) -> None:
        policies = self._get("anti_spam")
        error = self.exo_data.get("anti_spam_error")  # see _save_anti_phish
        if error and not policies:
            self._save("24_exchange_antispam.txt",
                       f"Error: could not collect anti-spam policies — {error}\n")
            return
        content  = _section_block(
            "EXCHANGE ANTI-SPAM POLICIES",
            policies,
            key_fields=["Name", "SpamAction", "BulkSpamAction", "PhishSpamAction"],
        )
        self._save("24_exchange_antispam.txt", content)

    # ── DKIM ──────────────────────────────────────────────────────────────────

    def _save_dkim(self) -> None:
        configs  = self._get("dkim")
        lines = [
            "=" * 80,
            f"  EXCHANGE DKIM SIGNING CONFIGS  ({len(configs)} total)",
            "=" * 80,
            f"  {'Domain':<45} {'Enabled':>8} {'Status':<20} {'Selector'}",
            "  " + "-" * 76,
        ]
        for d in configs:
            domain   = str(d.get("Domain") or "")[:45]
            enabled  = "Yes" if d.get("Enabled") else "No"
            status   = str(d.get("Status") or "")[:20]
            selector = str(d.get("Selector1CNAME") or d.get("Selector") or "N/A")[:30]
            lines.append(f"  {domain:<45} {enabled:>8} {status:<20} {selector}")
        lines += ["=" * 80, ""]
        self._save("25_exchange_dkim.txt", "\n".join(lines))

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
            for p in (raw.get("safe_links") or []):
                policies.append({
                    "Name": p.get("Name"),
                    "PolicyType": "SafeLinksPolicy",
                    # Get-SafeLinksPolicy exposes IsEnabled.
                    "Enabled": bool(p.get("IsEnabled")),
                })
            for p in (raw.get("safe_attachments") or []):
                action = str(p.get("Action") or "").strip().lower()
                # Safe Attachments protects when Enable is true OR the action is
                # a protective mode. The Built-In Protection Policy reports
                # Action=Block (Enable may be unset) and is protection all the
                # same, so counting only Enable would miss it.
                enabled = bool(p.get("Enable")) or action in (
                    "block", "replace", "dynamicdelivery")
                policies.append({
                    "Name": p.get("Name"),
                    "PolicyType": "SafeAttachmentsPolicy",
                    "Enabled": enabled,
                    "Action": p.get("Action"),
                })
        content  = _section_block(
            "MICROSOFT DEFENDER FOR OFFICE 365 POLICIES",
            policies,
            key_fields=["Name", "PolicyType", "Enabled"],
        )
        self._save("27_exchange_defender_policies.txt", content)

    # ── Quarantine Policies ───────────────────────────────────────────────────

    def _save_quarantine_policies(self) -> None:
        policies = self._get("quarantine_policies")
        content  = _section_block(
            "EXCHANGE QUARANTINE POLICIES",
            policies,
            key_fields=["Name", "EndUserQuarantinePermissionsValue", "ESNEnabled"],
        )
        self._save("27b_exchange_quarantine_policies.txt", content)

    # ── Org Config ────────────────────────────────────────────────────────────

    def _save_org_config(self) -> None:
        cfg = self._get_single("org_config")
        lines = ["=" * 80, "  EXCHANGE ORG CONFIG", "=" * 80]
        for k, v in cfg.items():
            lines.append(f"  {k}: {_fmt_val(v)}")
        lines += ["=" * 80, ""]
        self._save("27c_exchange_org_config.txt", "\n".join(lines))

    # ── Mailbox Forwarding ────────────────────────────────────────────────────

    def _save_forwarding(self) -> None:
        fwd_list = self._get("forwarding")
        lines = [
            "=" * 100,
            f"  MAILBOX FORWARDING  ({len(fwd_list)} entries)",
            "=" * 100,
            f"  {'Mailbox':<45} {'Forward To':<45} {'External':>9}",
            "  " + "-" * 96,
        ]
        external_fwd: list[dict] = []
        for fwd in fwd_list:
            mbx      = str(fwd.get("DisplayName") or fwd.get("Name") or fwd.get("PrimarySmtpAddress") or fwd.get("Mailbox") or "")[:45]
            fwd_to   = str(
                fwd.get("ForwardingSmtp")
                or fwd.get("ForwardingSmtpAddress")
                or fwd.get("ForwardingAddress")
                or ""
            )[:45]
            is_ext   = "Yes" if fwd.get("DeliverAndForward") or fwd.get("DeliverToMailboxAndForward") else "No"
            lines.append(f"  {mbx:<45} {fwd_to:<45} {is_ext:>9}")

            # Detect external (not in verified domains)
            domain_part = fwd_to.split("@")[-1].lower().rstrip(">")
            if domain_part and not any(
                d.lower() == domain_part for d in self.verified_domains
            ):
                external_fwd.append(fwd)

        lines += ["=" * 100, ""]
        self._save("28_exchange_mailbox_forwarding.txt", "\n".join(lines))

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
            for fwd in external_fwd:
                mbx_name = fwd.get('DisplayName') or fwd.get('Name') or fwd.get('PrimarySmtpAddress') or fwd.get('Mailbox') or '?'
                fwd_target = fwd.get('ForwardingSmtp') or fwd.get('ForwardingSmtpAddress') or fwd.get('ForwardingAddress') or '?'
                ext_lines.append(f"  {mbx_name}  →  {fwd_target}")
            ext_lines += ["=" * 100, ""]
            self._save("28b_exchange_external_forwarding_WARN.txt", "\n".join(ext_lines))

    # ── Inbox Rules ───────────────────────────────────────────────────────────

    def _save_inbox_rules(self) -> None:
        rules    = self._get("inbox_rules_external")
        filename = (
            "29_exchange_inbox_rules_external_fwd_WARN.txt"
            if rules
            else "29_exchange_inbox_rules_external_fwd.txt"
        )
        content = _section_block(
            "INBOX RULES WITH EXTERNAL FORWARDING",
            rules,
            key_fields=["Name", "Mailbox", "ForwardTo", "RedirectTo", "Enabled"],
        )
        self._save(filename, content)
        if rules:
            self._warn(
                f"{len(rules)} inbox rule(s) forwarding to external addresses found",
                level="critical",
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
            self._save(
                "19c_purview_sensitivity_labels.txt", f"Error: {ex}\n{hint}"
            )
            self._warn(f"Sensitivity labels fetch failed: {ex}")
            return

        lines = [
            "=" * 90,
            f"  PURVIEW SENSITIVITY LABELS  ({len(labels)} total)",
            "=" * 90,
            f"  {'Label Name':<45} {'Priority':>9} {'Enabled':>8} {'Parent ID'}",
            "  " + "-" * 86,
        ]
        for lbl in labels:
            name     = (lbl.get("name") or "")[:45]
            priority = lbl.get("priority", 0)
            enabled  = "Yes" if lbl.get("isActive") else "No"
            parent   = lbl.get("parent", {}).get("id") or "(top-level)"
            lines.append(f"  {name:<45} {priority:>9} {enabled:>8}  {parent}")
        lines += ["=" * 90, ""]
        self._save("19c_purview_sensitivity_labels.txt", "\n".join(lines))

    # ── DLP Policies ──────────────────────────────────────────────────────────

    def _save_dlp(self) -> None:
        policies = self._get("dlp_policies")
        content  = _section_block(
            "PURVIEW DLP POLICIES",
            policies,
            key_fields=["Name", "Mode", "Priority", "Workload"],
        )
        self._save("19d_purview_dlp_policies.txt", content)

    # ── Retention Policies ────────────────────────────────────────────────────

    def _save_retention(self) -> None:
        policies = self._get("retention_policies")
        content  = _section_block(
            "PURVIEW RETENTION POLICIES",
            policies,
            key_fields=["Name", "Enabled", "RetentionRuleTypes"],
        )
        self._save("19e_purview_retention_policies.txt", content)

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
            mailbox  = str(d.get("Mailbox") or "")[:45]
            ptype    = str(d.get("Type") or "")[:15]
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

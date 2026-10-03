"""Synthetic inputs for the compliance characterisation snapshot.

The suite's own contexts reach most verdicts; these fill in the rest: empty
and missing sections, refusals and error stubs per collector file, licence
gates, threshold edges and the odd shapes each control has a branch for.
Names are what a failing replay prints, so they say what the input is.
"""

from __future__ import annotations

from collections.abc import Iterator

_RULE = "=" * 70 + "\n"
_ERROR = "Error: HTTP 429 Too Many Requests\n"
_REFUSED = (
    _RULE + "  SECTION  (not available)\n" + _RULE + "  Requires Microsoft Entra ID P2 and the\n"
    "  IdentityRiskyUser.Read.All permission.\n"
)
_PARSED = (
    "mfa",
    "ca",
    "secure_score",
    "admin_roles",
    "sharepoint",
    "intune",
    "oauth",
    "purview",
)

_LICENCES = {
    "unknown (no inventory)": [],
    "P2 owned, none assigned": [{"part": "AAD_PREMIUM_P2", "used": 0}],
    "Entra P1 only": [{"part": "AAD_PREMIUM", "used": 5}],
    "Entra P2": [{"part": "AAD_PREMIUM_P2", "used": 5}],
    "Business Premium": [{"part": "SPB", "used": 5}],
    "E5": [{"part": "SPE_E5", "used": 5}],
    "unrecognised SKU": [{"part": "SOMETHING_NEW", "used": 5}],
}


def _f(name: str, text: str, **extra) -> dict:
    return {"file_contents": {name: text}, **extra}


def _banner(title: str, n: int | None, rows: str = "") -> str:
    count = f"  ({n} total)" if n is not None else ""
    return _RULE + f"  {title}{count}\n" + _RULE + rows


def edge_contexts() -> Iterator[tuple[str, object]]:
    yield "edge: empty context", {}
    yield "edge: empty file_contents", {"file_contents": {}}
    yield (
        "edge: every section empty",
        {
            "licenses": [],
            "mfa": {},
            "ca": {},
            "secure_score": {},
            "admin_roles": {},
            "spf_dmarc": [],
            "sharepoint": {},
            "intune": {},
            "file_contents": {},
            "oauth": {},
            "purview": {},
            "risky_users": "",
        },
    )
    yield (
        "edge: every parsed section has_data false",
        {
            **{k: {"has_data": False} for k in _PARSED},
            "file_contents": {},
        },
    )
    yield "edge: risky_users not a string", {"risky_users": ["x@acme.example"]}
    yield "edge: purview None", {"purview": None, "file_contents": {}}
    # Sections present but None. The map reads them with .get(key, {}), so
    # most of these raise; the snapshot pins which do and with what.
    for key in (
        "licenses",
        "mfa",
        "ca",
        "secure_score",
        "admin_roles",
        "spf_dmarc",
        "sharepoint",
        "intune",
        "file_contents",
        "oauth",
        "risky_users",
    ):
        yield f"edge: {key} is None", {key: None}


def base_sweeps(bases: dict[str, dict]) -> Iterator[tuple[str, object]]:
    for base_name, base in bases.items():
        fc = base["file_contents"]
        for key in (*_PARSED, "spf_dmarc", "licenses", "risky_users"):
            yield (
                f"gap: {base_name} / {key} removed",
                {k: v for k, v in base.items() if k != key},
            )
            empty = {"spf_dmarc": [], "licenses": [], "risky_users": ""}.get(key, {})
            yield f"gap: {base_name} / {key} empty", {**base, key: empty}
            if key in _PARSED:
                yield (
                    f"gap: {base_name} / {key} has_data false",
                    {**base, key: {**base.get(key, {}), "has_data": False}},
                )
        yield f"gap: {base_name} / risky_users refused", {**base, "risky_users": _REFUSED}
        yield (
            f"gap: {base_name} / intune refused",
            {
                **base,
                "intune": {
                    **base.get("intune", {}),
                    "unavailable": True,
                    "unavailable_reason": "DeviceManagementManagedDevices.Read.All mangler",
                },
            },
        )
        for name in sorted(fc):
            others = {k: v for k, v in fc.items() if k != name}
            yield f"file: {base_name} / {name} removed", {**base, "file_contents": others}
            for label, text in (("blank", ""), ("error stub", _ERROR), ("refused", _REFUSED)):
                yield (
                    f"file: {base_name} / {name} {label}",
                    {**base, "file_contents": {**fc, name: text}},
                )
        for label, licences in _LICENCES.items():
            yield f"licence: {base_name} / {label}", {**base, "licenses": licences}


def targeted_contexts() -> Iterator[tuple[str, object]]:
    # 1.1.1 MFA, around the 95% line and at zero.
    for pct in (100, 95, 94.9, 50.5, 0.1, 0, 0.0):
        yield f"1.1.1 mfa pct={pct}", {"mfa": {"has_data": True, "pct": pct, "no_mfa": 3}}
    yield "1.1.1 mfa has_data without pct", {"mfa": {"has_data": True}}

    # 1.1.2 phishing-resistant methods.
    am = "09b_auth_methods_policy.txt"
    head = "AUTHENTICATION METHODS POLICY\n=============================\nMethod      State\n"
    yield "1.1.2 error without colon", _f(am, "Error fetching policy (403)\n")
    yield "1.1.2 whitespace only", _f(am, "   \n")
    yield "1.1.2 fido2 enabled", _f(am, head + "Fido2       enabled\n")
    yield (
        "1.1.2 hello and x509 enabled",
        _f(
            am,
            head + "Windows Hello For Business   Enabled\nX509Certificate   ENABLED\n"
            "------\nsingle-column-line\n",
        ),
    )
    yield (
        "1.1.2 nothing phishing-resistant",
        _f(am, head + "Fido2       disabled\nSms         enabled\n"),
    )
    yield "1.1.2 header only", _f(am, head)

    # 1.1.3 Global Admin count, every band.
    for ga in (0, 1, 2, 4, 5, 9):
        yield (
            f"1.1.3 global admins={ga}",
            {"admin_roles": {"has_data": True, "global_admin_count": ga}},
        )
    yield "1.1.3 has_data without count", {"admin_roles": {"has_data": True}}

    # 1.1.4 / 5.1.1 / 1.1.7 Conditional Access.
    for label, ca in (
        (
            "enabled, blocks legacy",
            {
                "has_data": True,
                "enabled": 3,
                "has_client_app_data": True,
                "blocks_legacy_auth": True,
            },
        ),
        (
            "enabled, legacy open",
            {
                "has_data": True,
                "enabled": 2,
                "has_client_app_data": True,
                "blocks_legacy_auth": False,
            },
        ),
        ("none enabled", {"has_data": True, "enabled": 0, "has_client_app_data": True}),
        ("no client-app data", {"has_data": True, "enabled": 1}),
        ("no data", {"has_data": False, "enabled": 4}),
    ):
        yield f"ca {label}", {"ca": ca}
        for sd in ("True", "False", "Unknown"):
            text = _RULE + f"  Security Defaults Enabled : {sd}\n"
            yield (
                f"1.1.7 security defaults {sd} / ca {label}",
                {
                    "ca": ca,
                    **_f("31b_smart_lockout.txt", text),
                },
            )
    yield "1.1.7 no security defaults line", _f("31b_smart_lockout.txt", _RULE + "  Other : x\n")

    # 1.1.5 PIM and 1.1.8 access reviews, against each licence state.
    pim = "07b_pim_eligible_assignments.txt"
    rev = "07d_access_reviews.txt"
    for lic_name, lic in _LICENCES.items():
        for n in (0, 3, None):
            yield (
                f"1.1.5 pim count={n} / {lic_name}",
                {
                    "licenses": lic,
                    **_f(pim, _banner("PIM ELIGIBLE ROLE ASSIGNMENTS", n, "Role   User\n")),
                },
            )
            yield (
                f"1.1.8 reviews count={n} / {lic_name}",
                {
                    "licenses": lic,
                    **_f(rev, _banner("ACCESS REVIEW DEFINITIONS", n)),
                },
            )
    yield "1.1.5 error stub", _f(pim, _ERROR)
    yield "1.1.8 error stub", _f(rev, _ERROR)

    # 1.1.6 emergency access.
    em = "07c_emergency_access_check.txt"
    for label, text in (
        ("skipped", "Global admins unavailable; skipping check\n"),
        ("no summary line", _RULE + "  bg@acme.example  NO  Yes\n"),
        ("exclusions unknown", "SUMMARY: break_glass_candidates=1 ca_exclusions_known=no\n"),
        ("two candidates", "SUMMARY: break_glass_candidates=2 ca_exclusions_known=yes\n"),
        (
            "zero, admin excluded",
            "SUMMARY: break_glass_candidates=0 ca_exclusions_known=yes ca_excluded_admins=2\n",
        ),
        (
            "zero, none excluded",
            "SUMMARY: break_glass_candidates=0 ca_exclusions_known=yes ca_excluded_admins=0\n",
        ),
        ("zero, older evidence", "SUMMARY: break_glass_candidates=0 ca_exclusions_known=yes\n"),
        ("error stub", _ERROR),
    ):
        yield f"1.1.6 {label}", _f(em, text)

    # 1.2.1 banned passwords, with and without Entra P1.
    pw = "31_password_protection.txt"
    for label, text in (
        ("enabled yes", "Custom Banned Passwords Enabled : yes\n"),
        ("list configured", "Custom Banned Passwords : Configured\n"),
        ("list not configured", "Custom Banned Passwords : Not configured\n"),
        ("disabled", "Custom Banned Passwords Enabled : False\n"),
        ("not measured", "Directory settings were not measured. This is not a finding.\n"),
        ("no colon", "Custom Banned Passwords Enabled True\n"),
    ):
        for lic_name in ("unknown (no inventory)", "Entra P1 only", "P2 owned, none assigned"):
            yield (
                f"1.2.1 {label} / {lic_name}",
                {
                    "licenses": _LICENCES[lic_name],
                    **_f(pw, "PASSWORD PROTECTION\n" + text),
                },
            )

    # 1.4 Secure Score bands.
    for pct in (100, 75, 74.6, 50, 49.5, 0):
        yield f"1.4 secure score {pct}", {"secure_score": {"has_data": True, "pct": pct}}

    # 2.1 OAuth, either side of the five-app line.
    for n in (5, 6):
        yield (
            f"2.1 high-privilege apps={n}",
            {
                "oauth": {
                    "total_grants": 40,
                    "unique_apps": 12,
                    "app_registrations": 3,
                    "high_privilege_apps": [f"app{i}" for i in range(n)],
                }
            },
        )

    # 2.1.2 credential expiry.
    warn = "17c_app_credential_expiry_WARN.txt"
    regs = "17_app_registrations.txt"
    ran = {regs: _banner("APP REGISTRATIONS", 2, "  app-a\n  app-b\n")}
    for label, text in (
        ("expired", "3 expired, 2 expiring within 30 days."),
        ("expiring only", "0 expired, 2 expiring within 30 days."),
        ("all zero", "0 Expired , 0 Expiring within 30 days."),
        ("no summary", "WARNING: credentials need attention"),
    ):
        yield f"2.1.2 warn {label}", {"file_contents": {warn: text, **ran}}
    yield "2.1.2 no warn, registrations ran", {"file_contents": dict(ran)}

    # 3.1.1 / 3.2.1 / 7.2.2 Purview counts in each shape the parser emits.
    for label, value in (("list", ["a", "b"]), ("int", 3), ("zero", 0), ("str", "3")):
        yield (
            f"purview {label}",
            {
                "purview": {
                    "dlp_policies": value,
                    "sensitivity_labels": value,
                    "retention_policies": value,
                },
                "file_contents": {},
            },
        )
    dlp = "19d_purview_dlp_policies.txt"
    yield "3.1.1 text says enabled and enforce", _f(dlp, "Policy A  Enabled  Enforce\n")
    yield (
        "purview sections ran empty",
        {
            "purview": {"dlp_policies": 0},
            "file_contents": {
                "19d_purview_dlp_policies.txt": _banner("DLP POLICIES", 0, "  (none)\n"),
                "19c_purview_sensitivity_labels.txt": _banner("LABELS", 0, "  (none)\n"),
                "19e_purview_retention_policies.txt": _banner("RETENTION", 0, "  (none)\n"),
            },
        },
    )

    # 4.1 mailbox audit.
    org = "27c_exchange_org_config.txt"
    for label, text in (
        ("false", "AuditDisabled: False\n"),
        ("true;", "AuditDisabled : True;\n"),
        ("yes", "  AuditDisabled: Yes\n"),
        ("odd value then real", "AuditDisabled: maybe\nAuditDisabled: no\n"),
        ("no audit line", "EXCHANGE ORG CONFIG\nSomething: True\n"),
    ):
        yield f"4.1 {label}", _f(org, text)

    # 4.2 / 4.3 Exchange policy files, populated and empty.
    for name in ("23_exchange_antiphish.txt", "24_exchange_antispam.txt"):
        yield f"{name} empty section", _f(name, _banner("POLICIES", 0, "  (none)\n"))
        yield (
            f"{name} two policies",
            _f(name, _banner("POLICIES", 2, "\n  [1]\n    Name: A\n\n  [2]\n    Name: B\n")),
        )

    # 4.4 forwarding.
    yield "4.4 external forwarding warn", _f("28b_exchange_external_forwarding_WARN.txt", "x@a")
    yield (
        "4.4 inbox rule warn",
        _f("29_exchange_inbox_rules_external_fwd_WARN.txt", "rule -> x@ext.example"),
    )
    yield "4.4 only inbox-rule check ran", _f("29_exchange_inbox_rules_external_fwd.txt", "none\n")

    # 4.5 / 4.6 Defender for Office, across licence states.
    dp = "27_exchange_defender_policies.txt"
    for label, text in (
        (
            "both enabled",
            "Name: SL\nPolicyType: SafeLinksPolicy\nEnabled: True\n\n"
            "Name: SA\nPolicyType: Safe Attachments\nEnabled: yes\n",
        ),
        (
            "both disabled",
            "Name: SL\nPolicyType: SafeLinksPolicy\nEnabled: False\n\n"
            "Name: SA\nPolicyType: SafeAttachmentPolicy\nEnabled: False\n",
        ),
        ("named only", "Safe Links policy\nSafe Attachments policy\n"),
        ("no policies", _banner("DEFENDER POLICIES", 0, "  (none)\n")),
    ):
        for lic_name in ("unknown (no inventory)", "Entra P2", "Business Premium"):
            yield (
                f"4.5/4.6 {label} / {lic_name}",
                {
                    "licenses": _LICENCES[lic_name],
                    **_f(dp, text),
                },
            )

    # 1.1.9 cross-tenant access.
    xt = "18c_cross_tenant_access_policy.txt"
    for label, text in (
        ("direct connect allowed", "  B2B Direct Connect In : Allowed\n"),
        ("system default", "  B2B Direct Connect In : blocked\n  System Default : True\n"),
        ("configured", "=== x: y\n  B2B Direct Connect In : blocked\n  System Default : false\n"),
        ("no direct connect line", "  System Default : true\n"),
        ("error stub", _ERROR),
    ):
        yield f"1.1.9 {label}", _f(xt, text)

    # 7.2.4 anonymous links and how complete the scan was.
    od = "25_onedrive_sharing.txt"

    def onedrive(anyone, scope="complete", refused=0, discovery=0, folders=0, scanned=7):
        lines = [f"  Drives scanned : {scanned}"]
        if anyone is not None:
            lines.append(f"  'Anyone' links : {anyone}")
        if scope is not None:
            lines.append(f"  Scan scope : {scope}")
        lines += [
            f"  Drives refused : {refused}",
            f"  Discovery failures : {discovery}",
            f"  Folder failures : {folders}",
        ]
        return "\n".join(lines) + "\n"

    for label, text in (
        ("no anyone line", onedrive(None)),
        ("zero, complete", onedrive(0)),
        ("zero, complete (budget ok)", onedrive(0, scope="complete (all drives)")),
        ("zero, refused drives", onedrive(0, refused=2)),
        ("zero, discovery failures", onedrive(0, discovery=1)),
        ("zero, folder failures", onedrive(0, folders=4)),
        ("zero, budget hit", onedrive(0, scope="partial (request budget)")),
        ("zero, every gap", onedrive(0, scope="partial", refused=1, discovery=1, folders=1)),
        ("zero, scope unknown", onedrive(0, scope=None)),
        ("three found, partial", onedrive("3", scope="partial", refused=1)),
        ("1,204 found", onedrive("1,204")),
    ):
        yield f"7.2.4 {label}", _f(od, text)

    # 7.2.3 / 7.2.1 SharePoint.
    for label, sp in (
        ("legacy on", {"has_data": True, "legacy_auth_known": True, "legacy_auth": True}),
        ("legacy off", {"has_data": True, "legacy_auth_known": True, "legacy_auth": False}),
        ("legacy unknown", {"has_data": True, "legacy_auth": True}),
        ("sharing ok", {"has_data": True, "sharing_level": "ok", "sharing_label": "Kun interne"}),
        ("sharing ok, no label", {"has_data": True, "sharing_level": "ok"}),
        ("sharing unknown", {"has_data": True, "sharing_level": "unknown"}),
        (
            "anyone links",
            {
                "has_data": True,
                "sharing_level": "warning",
                "sharing": "External User And Guest Sharing",
                "sharing_label": "Alle med lenken",
            },
        ),
        (
            "anyone links, no label",
            {
                "has_data": True,
                "sharing_level": "warning",
                "sharing": "ExternalUserAndGuestSharing",
            },
        ),
        (
            "guests only",
            {"has_data": True, "sharing_level": "warning", "sharing": "ExternalUserSharingOnly"},
        ),
        ("sharing None", {"has_data": True, "sharing_level": "warning", "sharing": None}),
    ):
        yield f"sharepoint {label}", {"sharepoint": sp}

    # 5.2.x per domain.
    domains = [
        {"domain": "acme.example", "spf": "OK (v=spf1 -all)", "dmarc": "OK (p=reject)"},
        {"domain": "tenant.onmicrosoft.com", "spf": "MISSING", "dmarc": "MISSING"},
        {"domain": "Tenant.Mail.OnMicrosoft.com", "spf": "MISSING"},
        {"domain": "q.example", "spf": "ERROR (SERVFAIL)", "dmarc": "p=quarantine"},
        {"domain": "n.example", "spf": "", "dmarc": "OK", "dmarc_record": "v=DMARC1; p=none"},
        {"domain": "n2.example", "spf": "MISSING", "dmarc": "p=none"},
        {"domain": "r.example", "spf": "MISSING", "dmarc": "", "dmarc_record": "(none)"},
        {"domain": "e.example", "dmarc": "ERROR (timeout)", "dmarc_record": "(none)"},
        {"domain": "f.example", "dmarc": "WEAK", "dmarc_record": "v=DMARC1; p=foo"},
        {"domain": "s.example", "dkim": "Enabled (M365 signing)"},
        {"domain": "t.example", "dkim": "OK"},
        {"domain": "u.example", "dkim": "Disabled", "dkim1": "", "dkim2": ""},
        {"domain": "v.example", "dkim1": "CNAME selector1 -> x", "dkim2": ""},
        {"domain": "w.example", "dkim1": "", "dkim2": "CNAME s2 -> y"},
        {"domain": "x.example", "dkim1": "v=DKIM1; k=rsa; p=AAA", "dkim2": ""},
        {"domain": "y.example", "dkim1": "", "dkim2": "v=DKIM1; k=rsa; p=BBB"},
        {"domain": "z.example", "dkim1": "ERROR (DoH)", "dkim2": "v=DKIM1; k=rsa; p=C"},
        {"domain": "za.example", "dkim1": "ERROR (DoH)", "dkim2": "ERROR (DoH)"},
        {"domain": "zb.example", "dkim1": "TXT present, no key", "dkim2": ""},
        {"domain": "zc.example", "dkim": ""},
        {"domain": "zd.example"},
        {},
    ]
    yield "5.2 domains", {"spf_dmarc": domains}
    for d in domains:
        yield f"5.2 single domain {d.get('domain', '(no domain)')}", {"spf_dmarc": [d]}

    # 6.1.1 Intune: policies, devices, refusals and Entra-only devices.
    cp = "11_intune_compliance_policies.txt"
    policies = _banner("INTUNE COMPLIANCE POLICIES", None, "  Policy A\n  Policy B\n")
    for label, intune, text in (
        ("refused, no policies", {"unavailable": True}, None),
        ("refused, reason", {"unavailable": True, "unavailable_reason": "403 fra Graph"}, None),
        ("refused, policies readable", {"unavailable": True}, policies),
        ("entra devices only", {"has_data": False, "entra_total": 25}, None),
        ("nothing at all", {"has_data": True, "total": 0}, None),
        ("devices, policy file refused", {"has_data": True, "total": 10}, _REFUSED),
        (
            "devices, policy file empty section",
            {"has_data": True, "total": 10},
            _banner("INTUNE COMPLIANCE POLICIES", 0, "  (none)\n"),
        ),
        ("policies, no devices", {"has_data": True, "total": 0}, policies),
        ("policies, 90%", {"has_data": True, "total": 10, "compliance_pct": 90}, policies),
        (
            "policies, 89.9%",
            {"has_data": True, "total": 10, "compliance_pct": 89.9, "noncompliant": 1},
            policies,
        ),
        ("policies, no pct", {"has_data": True, "total": 10}, policies),
    ):
        ctx = {"intune": intune}
        if text is not None:
            ctx["file_contents"] = {cp: text}
        yield f"6.1.1 {label}", ctx

    # 8.1.1 Teams external access.
    te = "16c_teams_external_access.txt"

    def teams(collab="N/A", direct="N/A", partners=""):
        return (
            _RULE + "  Default Inbound Settings:\n"
            f"    B2B Collaboration  : {collab}\n"
            f"    B2B Direct Connect : {direct}\n" + partners
        )

    for label, text in (
        ("collab open, direct blocked", teams("allowed", "blocked")),
        ("collab open only", teams(collab="AllUsers")),
        ("direct open only", teams(direct="allowed")),
        ("both restricted", teams("Restricted to listed", "Denied")),
        ("both disabled", teams("disabled", "none")),
        ("partners, blocked", teams(partners="  Partner Configurations (2):\n  blocked\n")),
        ("partners, disabled", teams(partners="  Partner Configurations (1):\n  Disabled\n")),
        (
            "partners, allowed for all",
            teams(partners="  Partner Configurations (1):\n  Allowed for all\n"),
        ),
        ("partners, everyone", teams(partners="  Partner Configurations (1):\n  Everyone\n")),
        (
            "partners, no restrictions",
            teams(partners="  Partner Configurations (1):\n  No restrictions\n"),
        ),
        ("partners, other", teams(partners="  Partner Configurations (3):\n  scoped\n")),
    ):
        yield f"8.1.1 {label}", _f(te, text)

    # 8.1.2 guest access.
    gu = "30b_teams_guest_access.txt"
    for label, invites, role in (
        ("member role", "Admins and Guest Inviters", "Same as member users"),
        ("everyone invites", "Everyone (most open)", "Restricted access"),
        ("members invite", "Admins, Guest Inviters and Members", "Limited access"),
        ("admins only", "Admins and Guest Inviters", "Restricted access"),
        ("no role", "None", "N/A"),
    ):
        text = f"  Allow Invites From       : {invites}\n  Guest User Role          : {role}\n"
        yield f"8.1.2 {label}", _f(gu, text)

    # 9.1 unified audit log.
    ual = "27d_exchange_admin_audit_log_config.txt"
    for label, text in (
        ("true", "UnifiedAuditLogIngestionEnabled: True\n"),
        ("no", "UnifiedAuditLogIngestionEnabled : No;\n"),
        (
            "odd value stops the scan",
            "UnifiedAuditLogIngestionEnabled: maybe\nUnifiedAuditLogIngestionEnabled: True\n",
        ),
        ("no ingestion line", "AdminAuditLogEnabled: True\n"),
    ):
        yield f"9.1 {label}", _f(ual, text)

    # 9.2 Defender alerts.
    yield (
        "9.2 two open alerts",
        _f(
            "19b_defender_active_alerts.txt",
            "DEFENDER ALERTS\n===\nTitle   Severity   Status\n---\n"
            "Alert one   high   new\nAlert two   low   new\n",
        ),
    )
    yield "9.2 count file only", _f("19b_defender_alert_count.txt", "Active alerts: 0\n")

    # 9.3 risky users.
    header = "  RISKY USERS  (3 total)\n" + _RULE + "  UPN   Risk Level   State\n  ---\n"
    for label, rows in (
        ("high and low", "  a@acme.example   high   atRisk\n  b@acme.example   low   atRisk\n"),
        ("medium", "  c@acme.example   Medium   atRisk\n"),
        ("low only", "  d@acme.example   low   atRisk\n  e@acme.example   low   dismissed\n"),
        ("rows without upn", "  service-principal   high   atRisk\n  short   row\n"),
        ("none", ""),
    ):
        yield f"9.3 {label}", {"risky_users": header + rows, "file_contents": {}}
    yield "9.3 error stub", {"risky_users": _ERROR}


def synthetic_contexts(bases: dict[str, dict]) -> Iterator[tuple[str, object]]:
    yield from edge_contexts()
    yield from base_sweeps(bases)
    yield from targeted_contexts()

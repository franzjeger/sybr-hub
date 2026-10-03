"""Synthetic inputs for the recommendations characterisation snapshot.

The suite's own calls reach the common findings; these fill in the rest:
missing, None and malformed arguments (two at a time too, to pin which one
the builder trips over first), a tenant where every finding fires with each
argument, field and collector file taken away or spoiled in turn, threshold
edges, and the odd shapes each finding has a branch for. Names are what a
failing replay prints, so they say what the input is.
"""

from __future__ import annotations

from collections.abc import Iterator

_RULE = "=" * 70 + "\n"
_ERROR = "Error: HTTP 429 Too Many Requests\n"
_REFUSED = (
    _RULE + "  SECTION  (not available)\n" + _RULE + "  Requires Microsoft Entra ID P2 and the\n"
    "  IdentityRiskyUser.Read.All permission.\n"
)

# Arguments with no default: leaving one out is a TypeError, pinned once each.
_REQUIRED = ("mfa", "spf_dmarc", "secure_score", "ext_fwd", "risky_users", "licenses")
_OPTIONAL = (
    "admin_roles",
    "intune",
    "sharepoint",
    "oauth",
    "azure",
    "file_contents",
    "backup_coverage",
    "signin_risk",
    "network",
)
_EMPTY = {"spf_dmarc": [], "licenses": [], "ext_fwd": "", "risky_users": ""}

QUIET = {
    "mfa": {},
    "spf_dmarc": [],
    "secure_score": {},
    "ext_fwd": "",
    "risky_users": "",
    "licenses": [],
}


def _call(**args) -> dict:
    return {**QUIET, **args}


# ── A tenant where every finding fires ────────────────────────────────────────

_MFA_USERS = [
    # Excluded from CA and a Global Admin: the dedicated critical.
    {
        "name": "Ola Admin",
        "upn": "Ola@Acme.example",
        "ca_excluded": True,
        "has_mfa": True,
        "methods": "Phone (SMS/Call)",
    },
    # Excluded, no name, no method, being brute-forced.
    {"name": "", "upn": " kari@acme.example ", "ca_excluded": True, "has_mfa": False},
    # Excluded, both reasons.
    {
        "name": "Bo",
        "upn": "bo@acme.example",
        "ca_excluded": True,
        "has_mfa": True,
        "methods": "Email OTP",
    },
    # Excluded but neither an admin nor attacked: stays in the general count.
    {
        "name": "Per",
        "upn": "per@acme.example",
        "ca_excluded": True,
        "has_mfa": True,
        "methods": "Authenticator App",
    },
    {"name": "Tom", "upn": "", "ca_excluded": True},
    {
        "name": "Lise",
        "upn": "lise@acme.example",
        "has_mfa": True,
        "methods": "Authenticator App, FIDO2 Key",
    },
    {
        "name": "Nils",
        "upn": "nils@acme.example",
        "has_mfa": True,
        "methods": "Phone (SMS/Call), Something New",
    },
    {"name": "Siv", "upn": "siv@acme.example", "has_mfa": True, "methods": "Email OTP, , "},
    {"name": "Ulf", "upn": "ulf@acme.example", "has_mfa": False, "methods": None},
]

_MFA_JSON = (
    '{"users": ['
    '{"display_name": "Ola Admin", "upn": "ola@acme.example", "mfa_registered": true,'
    ' "ca_covered": false, "ca_excluded": true},'
    '{"display_name": "Per", "upn": "per@acme.example", "mfa_registered": true,'
    ' "ca_covered": true, "ca_excluded": true},'
    '{"display_name": "Ulf", "upn": "ulf@acme.example", "mfa_registered": false,'
    ' "ca_covered": false, "ca_excluded": false},'
    '{"display_name": "Vera", "upn": "vera@acme.example", "mfa_registered": false,'
    ' "ca_covered": true, "ca_excluded": false},'
    '{"display_name": "Geir", "upn": "geir@acme.example", "mfa_registered": null,'
    ' "ca_covered": false},'
    '{"display_name": "Anne", "mfa_registered": false},'
    '{"upn": "lise@acme.example", "mfa_registered": true, "ca_covered": false}'
    "]}"
)

_AUTH_POLICY = (
    _RULE
    + "  AUTHENTICATION METHODS POLICY\n"
    + _RULE
    + "  Method                                   State\n"
    "  " + "-" * 66 + "\n"
    "  sms                                      disabled\n"
    "  voice                                    Disabled\n"
    "  email                                    DISABLED\n"
    "  microsoftAuthenticator                   enabled\n"
    "  fido2                                    enabled\n"
    "  orphan\n" + _RULE
)

_RISKY = (
    _RULE + "  RISKY USERS  (5 total)\n" + _RULE + "  UPN                 Risk Level   State\n"
    "  ---\n"
    "\n"
    "  a@acme.example      high         atRisk\n"
    "  b@acme.example      medium       remediated\n"
    "  c@acme.example      low          Confirmed Safe\n"
    "  d@acme.example      high         dismissed\n"
    "  e@acme.example      low          safe\n"
    "  f@acme.example      none\n"
    "  g@acme.example      medium       atRisk\n"
)

_FORWARDING = (
    "  EXTERNAL FORWARDING\n"
    "  Ola Admin  →  smtp:ola@ext.example\n"
    "  Per  →  SMTP:per@ext.example\n"
    "  shared  →  x@ext.example\n"
)

_STALE = (
    _RULE
    + "  STALE ACCOUNTS\n"
    + _RULE
    + "  4 enabled account(s) with licenses have not signed in for 90 days\n"
)
_CREDS = (
    _RULE
    + "  APP CREDENTIAL EXPIRY  WARNING\n"
    + _RULE
    + "  2 expired, 3 expiring within 30 days.\n"
)
_NSG = (
    _RULE + "  RISKY NSG INBOUND RULES\n" + _RULE + "\n"
    "  ⚠ NSG 'web' rule 'rdp' (priority 100): allows inbound from * to port(s) 3389\n"
    "  NSG 'db' rule 'sql' (priority 110): allows inbound from Internet to port(s) 1433\n"
    "  ⚠ rule without the word\n"
    "  NSGs listed above\n"
)

_EVIDENCE = (
    "03b_stale_accounts.txt",
    "04b_mfa_ca_analysis.txt",
    "05_signin_activity.txt",
    "05b_signin_failures.txt",
    "07_admin_roles.txt",
    "09_secure_score.txt",
    "10_intune_devices.txt",
    "10_intune_devices_count.txt",
    "15_entra_devices_count.txt",
    "15b_sharepoint_settings.txt",
    "17_app_registrations.txt",
    "17b_oauth_consent_grants.txt",
    "17c_app_credential_expiry.txt",
    "18_risky_users.txt",
    "18d_risk_detections.txt",
    "26_email_dns_spf_dmarc.txt",
    "28_exchange_mailbox_forwarding.txt",
    "28b_exchange_external_forwarding_WARN.txt",
)

_FILES = {
    "04_mfa_methods.txt": "x\n",
    "04_mfa_methods.json": _MFA_JSON,
    "09b_auth_methods_policy.txt": _AUTH_POLICY,
    "03c_stale_accounts_WARN.txt": _STALE,
    "17c_app_credential_expiry_WARN.txt": _CREDS,
    "sub-a_32b_azure_nsg_risky_rules_WARN.txt": _NSG,
    "sub-b_32b_azure_nsg_risky_rules_WARN.txt": "  NSG 'b' rule 'ssh': port 22\n",
    "32b_azure_nsg_risky_rules.txt": "not a WARN file\n",
    "unrelated_WARN.txt": "  NSG 'z' rule\n",
    **{name: "x\n" for name in _EVIDENCE},
}

_ADVISOR = [
    {"category": "Security", "impact": "High", "count": 1, "description": "Enable MFA"},
    {
        "category": "Security",
        "impact": "Medium",
        "count": 3,
        "subscription": "Prod",
        "description": "Patch VMs",
    },
    {"category": "HighAvailability", "impact": "Low", "count": 1, "description": "Zones"},
    {"category": "HighAvailability", "impact": "Low", "count": 2, "description": "Backup"},
    {
        "category": "HighAvailability",
        "impact": "Medium",
        "count": 1,
        "subscription": "Dev",
        "description": "Replicas",
    },
    {"category": "Cost", "impact": "High", "count": 4, "description": "Right-size"},
    {"category": "Performance", "impact": "High", "count": 1, "description": "Cache"},
    {"category": "OperationalExcellence", "impact": "High", "count": 1, "description": "Tags"},
    {"category": "Unheard", "impact": "High", "count": 1, "description": "New kind"},
    # Two low-impact items: below the line, no finding for this category.
    {"category": "Quiet", "impact": "Low", "count": 1, "description": "a"},
    {"category": "Quiet", "impact": "Medium", "count": 1, "description": "b"},
]

_FORTIGATE = {
    "admins": [
        {"name": "admin", "profile": "super_admin", "two_factor": False, "trusthost": False},
        {"name": "ops", "profile": "prof", "two_factor": True, "trusthost": True},
        {"two_factor": False},
    ],
    "policy_warnings": [
        "Policy 3 is allow-all (any/any/ALL)",
        "Policy 7 has logging disabled",
        "Policy 9 ALLOW-ALL without Logging",
        "Policy 12 uses a weak profile",
    ],
}

_UNIFI = {
    "mode": "controller",
    "default_creds_count": 2,
    "eol_count": 1,
    "outdated_firmware_count": 2,
    "devices": [
        {
            "label": "Core switch",
            "host": "10.0.0.2",
            "default_credentials": True,
            "firmware": "6.5.1",
            "fw_check": {"model": "US-24", "eol": True, "up_to_date": False, "latest": "7.0"},
            "is_default_config": True,
        },
        {
            "host": "10.0.0.3",
            "default_credentials": True,
            "firmware": "6.0",
            "fw_check": {"model": "UAP", "up_to_date": False, "latest": "6.6"},
        },
        {"label": "Fresh AP", "fw_check": {"up_to_date": True}, "is_default_config": True},
        {"label": "Unknown fw"},
    ],
    "wlans": [
        {"name": "Guest", "security_label": "Open", "enabled": True},
        {"name": "Lobby", "security_label": "Open", "enabled": False},
        {"name": "Staff", "security_label": "WPA2", "enabled": True},
        {"name": "Legacy", "security": "open", "enabled": True},
        {"security_label": "Open", "enabled": True},
    ],
}

LOADED = {
    "mfa": {
        "has_data": True,
        "no_mfa": 7,
        "mfa_registered": 6,
        "ca_covered": 2,
        "no_mfa_registered": 2,
        "registered_but_excluded": 5,
        "users": _MFA_USERS,
    },
    "spf_dmarc": [
        {"domain": "acme.example", "spf": "MISSING", "dmarc": "MISSING"},
        {"domain": "acme.onmicrosoft.com", "spf": "MISSING", "dmarc": "MISSING"},
        {"domain": "b.example", "spf": "CRITICAL (+all)", "dmarc": "WEAK (p=none)"},
        {"domain": "c.example", "spf": "WEAK (~all)", "dmarc": "OK (p=reject)"},
        {"domain": "d.example", "spf": "OK (-all)", "dmarc": "OK"},
    ],
    "secure_score": {
        "pct": 42.4,
        "current": 33.6,
        "max": 79.2,
        "improvements": [
            {"name": "Require MFA for admins", "category": "Identity"},
            {"name": "Turn on audit logging"},
        ],
    },
    "ext_fwd": _FORWARDING,
    "risky_users": _RISKY,
    "licenses": [{"part": "SPB", "used": 5, "total": 5}],
    "admin_roles": {
        "global_admin_count": 6,
        "global_admin_users": [
            {"email": " ola@acme.example"},
            {"email": "BO@acme.example"},
            {"email": None},
            {},
        ],
    },
    "intune": {
        "noncompliant": 7,
        "compliance_pct": 30.0,
        "entra_unmanaged": 6,
        "entra_total": 10,
    },
    "sharepoint": {"has_data": True, "sharing_level": "warning", "legacy_auth": True},
    "oauth": {"high_privilege_apps": ["Mail.ReadWrite app", "Directory.ReadWrite.All app"]},
    "azure": {
        "advisor_summary": _ADVISOR,
        "orphaned": 2,
        "orphaned_details": [
            {"type": "Disk", "status": "Unattached", "detail": "disk-1 (128 GB)"},
            {"type": "Public IP", "status": "Unassociated", "detail": "pip-2"},
        ],
    },
    "file_contents": _FILES,
    "backup_coverage": {"coverage_known": True, "vms_not_backed_up": ["vm-a", "vm-b"]},
    "signin_risk": {
        "brute_force_suspects": ["KARI@acme.example", None, "bo@acme.example"],
        "stale_credential_users": ["printer@acme.example"],
    },
    "network": {
        "unreadable": ["fortigate_audit.json"],
        "has_data": True,
        "fortigate": _FORTIGATE,
        "unifi": _UNIFI,
    },
}


# ── Inputs ────────────────────────────────────────────────────────────────────


def edge_contexts() -> Iterator[tuple[str, dict]]:
    yield "edge: nothing to report", dict(QUIET)
    yield "edge: every optional section empty", _call(**{k: {} for k in _OPTIONAL})
    yield "edge: every optional section None", _call(**dict.fromkeys(_OPTIONAL))
    for key in _REQUIRED:
        yield f"edge: {key} missing", {k: v for k, v in QUIET.items() if k != key}
    # None, a list where a dict belongs and the reverse, and a bare string:
    # the snapshot pins which of these raise and with what.
    for key in (*_REQUIRED, *_OPTIONAL):
        yield f"edge: {key} is None", _call(**{key: None})
        for label, value in (("a list", ["x"]), ("a string", "x"), ("a dict", {"x": 1})):
            yield f"edge: {key} is {label}", _call(**{key: value})
    for label, value in (("None", None), ("a list", ["x"]), ("a string", "x"), ("7", 7)):
        yield f"edge: every argument {label}", dict.fromkeys((*_REQUIRED, *_OPTIONAL), value)


def order_contexts() -> Iterator[tuple[str, dict]]:
    # Two unreadable arguments, an int and a float: the type in the message
    # says which one the builder reached first.
    keys = (*_REQUIRED, *_OPTIONAL)
    for i, first in enumerate(keys):
        for second in keys[i + 1 :]:
            yield f"order: {first} is 7, {second} is 7.5", {**LOADED, first: 7, second: 7.5}


def loaded_sweeps() -> Iterator[tuple[str, dict]]:
    yield "loaded: every finding fires", dict(LOADED)
    for key in (*_REQUIRED, *_OPTIONAL):
        if key in _OPTIONAL:
            yield f"loaded: {key} left out", {k: v for k, v in LOADED.items() if k != key}
        yield f"loaded: {key} None", {**LOADED, key: None}
        yield f"loaded: {key} empty", {**LOADED, key: _EMPTY.get(key, {})}
        value = LOADED[key]
        if isinstance(value, dict):
            for field in value:
                rest = {k: v for k, v in value.items() if k != field}
                yield f"loaded: {key} without {field}", {**LOADED, key: rest}
            if "has_data" in value:
                yield (
                    f"loaded: {key} has_data false",
                    {**LOADED, key: {**value, "has_data": False}},
                )
    for name in sorted(_FILES):
        others = {k: v for k, v in _FILES.items() if k != name}
        yield f"file: {name} removed", {**LOADED, "file_contents": others}
        yield f"file: {name} whitespace", {**LOADED, "file_contents": {**_FILES, name: " \n\t"}}
        if name in _EVIDENCE:
            continue  # only cited: any text that is not blank reads the same
        for label, text in (("blank", ""), ("error stub", _ERROR), ("refused", _REFUSED)):
            yield f"file: {name} {label}", {**LOADED, "file_contents": {**_FILES, name: text}}


def _mfa_cases() -> Iterator[tuple[str, dict]]:
    users = LOADED["mfa"]["users"]
    admins = LOADED["admin_roles"]
    risk = LOADED["signin_risk"]
    base = {"has_data": True, "no_mfa": 3, "mfa_registered": 4, "ca_covered": 1}
    for no_mfa in (0, 1, 3, 4, 5):
        yield (
            f"mfa: no_mfa={no_mfa}, three high-risk accounts",
            _call(
                mfa={**LOADED["mfa"], "no_mfa": no_mfa},
                admin_roles=admins,
                signin_risk=risk,
                file_contents=_FILES,
            ),
        )
    yield "mfa: summary only", _call(mfa=base)
    yield "mfa: has_data without counts", _call(mfa={"has_data": True})
    yield "mfa: count but no data", _call(mfa={"no_mfa": 3})
    yield (
        "mfa: excluded users, no admin or sign-in data",
        _call(mfa={**base, "users": users}),
    )
    yield (
        "mfa: excluded users, admins only",
        _call(mfa={**base, "users": users}, admin_roles=admins),
    )
    yield (
        "mfa: excluded users, brute force only",
        _call(mfa={**base, "users": users}, signin_risk=risk),
    )
    yield (
        "mfa: admin list without users",
        _call(mfa={**base, "users": users}, admin_roles={"global_admin_count": 2}),
    )
    yield (
        "mfa: high-risk counts exceed the breakdown",
        _call(
            mfa={**base, "no_mfa": 9, "users": users, "no_mfa_registered": 0},
            admin_roles=admins,
            signin_risk=risk,
        ),
    )
    table = (
        "  Display Name | UPN | MFA:NO | CA:NO | CA_EXCL:NO\n"
        "  Kari | kari@acme.example | MFA:NO | CA:YES | EXCL:NO\n"
        "  Ola | ola@acme.example | MFA:YES | CA:YES | CA_EXCL:YES\n"
        "  Anne | anne@acme.example | MFA:NO | CA:NO | CA_EXCL:NO\n"
    )
    yield (
        "mfa: table fallback when the sidecar is unreadable",
        _call(
            mfa={**base, "users": users},
            admin_roles=admins,
            file_contents={"04_mfa_methods.json": "{not json", "04_mfa_methods.txt": table},
        ),
    )
    many = ",".join(
        f'{{"display_name": "U{i}", "upn": "u{i}@acme.example", "mfa_registered": false}}'
        for i in range(60)
    )
    yield (
        "mfa: sixty not enforced, capped at fifty",
        _call(
            mfa={**base, "no_mfa": 60},
            file_contents={"04_mfa_methods.json": '{"users": [' + many + "]}"},
        ),
    )
    many_excluded = [
        {"name": f"A{i}", "upn": f"a{i}@acme.example", "ca_excluded": True} for i in range(55)
    ]
    yield (
        "mfa: fifty-five excluded admins, capped at fifty",
        _call(
            mfa={**base, "users": many_excluded},
            admin_roles={"global_admin_users": [{"email": u["upn"]} for u in many_excluded]},
        ),
    )


def _auth_lockout_cases() -> Iterator[tuple[str, dict]]:
    head = _RULE + "  Method      State\n  ------\n"
    users = [
        {"name": "A", "upn": "a@acme.example", "methods": "Phone (SMS/Call)"},
        {"name": "B", "upn": "b@acme.example", "methods": "Authenticator App"},
        {"upn": "c@acme.example", "methods": "Temp Access Pass, Certificate"},
        {"name": "D", "methods": "OATH TOTP"},
        {"name": "E", "upn": "e@acme.example", "methods": ""},
    ]
    for label, policy in (
        ("sms only disabled", head + "  sms   disabled\n"),
        ("sms and voice disabled", head + "  sms   disabled\n  voice   disabled\n"),
        (
            "everything disabled",
            head
            + "".join(
                f"  {m}   disabled\n"
                for m in (
                    "sms",
                    "voice",
                    "microsoftAuthenticator",
                    "temporaryAccessPass",
                    "x509Certificate",
                    "softwareOath",
                )
            ),
        ),
        ("nothing disabled", head + "  sms   enabled\n"),
        ("error stub", _ERROR),
    ):
        yield (
            f"lockout: {label}",
            _call(
                mfa={"users": users},
                file_contents={"09b_auth_methods_policy.txt": policy},
            ),
        )
    yield (
        "lockout: policy but no users",
        _call(mfa={"users": []}, file_contents={"09b_auth_methods_policy.txt": head}),
    )
    many = [{"name": f"U{i}", "upn": f"u{i}@x.example", "methods": "Email OTP"} for i in range(55)]
    yield (
        "lockout: fifty-five locked out, capped at fifty",
        _call(
            mfa={"users": many},
            file_contents={"09b_auth_methods_policy.txt": head + "  email  disabled\n"},
        ),
    )


def _mail_cases() -> Iterator[tuple[str, dict]]:
    for label, record in (
        ("no domain", {"spf": "MISSING", "dmarc": "MISSING"}),
        ("empty domain", {"domain": "", "spf": "OK", "dmarc": "OK"}),
        ("domain only", {"domain": "e.example"}),
        ("dmarc missing", {"domain": "f.example", "dmarc": "MISSING"}),
        ("dmarc weak", {"domain": "f.example", "dmarc": "WEAK"}),
        ("dmarc ok", {"domain": "f.example", "dmarc": "OK (p=reject)"}),
        ("spf missing", {"domain": "f.example", "spf": "MISSING"}),
        ("spf critical", {"domain": "f.example", "spf": "CRITICAL"}),
        ("spf weak", {"domain": "f.example", "spf": "WEAK"}),
        ("spf ok", {"domain": "f.example", "spf": "OK"}),
        ("microsoft domain", {"domain": "x.mail.onmicrosoft.com", "spf": "MISSING"}),
    ):
        yield f"mail: {label}", _call(spf_dmarc=[record])
    # The same domain twice: the id has nothing left to tell them apart.
    twice = [{"domain": "g.example", "spf": "MISSING", "dmarc": "MISSING"}] * 2
    yield "mail: one domain listed twice", _call(spf_dmarc=twice)

    for label, text in (
        ("whitespace only", " \n "),
        ("no arrow lines", "  EXTERNAL FORWARDING\n  (rows could not be parsed)\n"),
        ("one mailbox", "  Ola → smtp:ola@ext.example\n"),
        ("arrow in target", "a → b → c\n"),
    ):
        yield f"forwarding: {label}", _call(ext_fwd=text)


def _risky_cases() -> Iterator[tuple[str, dict]]:
    head = _RULE + "  RISKY USERS  (2 total)\n" + _RULE + "  UPN      Risk Level   State\n  ---\n"
    for label, text in (
        ("none at risk", "No risky users found.\n"),
        ("error stub", _ERROR),
        ("refused", _REFUSED),
        ("header only", head),
        ("only handled rows", head + "  a@x.example   high   remediated\n"),
        ("short rows", head + "  a@x.example   high\n  lone\n"),
        ("one at risk", head + "  a@x.example   high   atRisk\n"),
        ("single spaces", head + "  a@x.example high atRisk\n"),
        ("dash row", head + "- a@x.example   high   atRisk\n"),
    ):
        yield f"risky: {label}", _call(risky_users=text)


def _score_cases() -> Iterator[tuple[str, dict]]:
    imps = [{"name": "Do the thing", "category": "Apps"}]
    for pct in (80, 79.9, 50, 49.9, 0):
        yield f"secure score: {pct}%", _call(secure_score={"pct": pct, "improvements": imps})
    yield "secure score: low, no improvements", _call(secure_score={"pct": 20, "improvements": []})
    yield "secure score: improvements, no pct", _call(secure_score={"improvements": imps})
    yield (
        "secure score: with current and max",
        _call(secure_score={"pct": 60, "current": 30.4, "max": 50, "improvements": imps}),
    )


def _admin_and_device_cases() -> Iterator[tuple[str, dict]]:
    for ga in (4, 5):
        yield f"global admins: {ga}", _call(admin_roles={"global_admin_count": ga})
    for label, intune in (
        ("all compliant", {"noncompliant": 0, "compliance_pct": 100}),
        ("one noncompliant at 50%", {"noncompliant": 1, "compliance_pct": 50}),
        ("one noncompliant at 49.9%", {"noncompliant": 1, "compliance_pct": 49.9}),
        ("noncompliant, no pct", {"noncompliant": 2}),
        ("unmanaged half", {"entra_unmanaged": 5, "entra_total": 10}),
        ("unmanaged under half", {"entra_unmanaged": 4, "entra_total": 10}),
        ("unmanaged, no total", {"entra_unmanaged": 4, "entra_total": 0}),
        ("total, none unmanaged", {"entra_unmanaged": 0, "entra_total": 10}),
    ):
        yield f"intune: {label}", _call(intune=intune)
    for label, sp in (
        ("warning without data", {"has_data": False, "sharing_level": "warning"}),
        ("sharing ok", {"has_data": True, "sharing_level": "ok", "legacy_auth": False}),
        ("legacy only", {"has_data": True, "legacy_auth": True}),
        ("sharing only", {"has_data": True, "sharing_level": "warning"}),
    ):
        yield f"sharepoint: {label}", _call(sharepoint=sp)
    yield "oauth: no high-privilege apps", _call(oauth={"high_privilege_apps": []})
    yield "oauth: one app", _call(oauth={"high_privilege_apps": ["App"]})


def _azure_cases() -> Iterator[tuple[str, dict]]:
    for label, item in (
        ("count one, no subscription", {"count": 1}),
        ("count two", {"count": 2}),
        ("subscription only", {"count": 1, "subscription": "Prod"}),
        ("count and subscription", {"count": 5, "subscription": "Prod"}),
        ("empty subscription", {"count": 1, "subscription": ""}),
    ):
        advice = {"category": "Security", "impact": "High", "description": "Do it", **item}
        yield f"advisor: {label}", _call(azure={"advisor_summary": [advice]})
    three_low = [
        {"category": "Cost", "impact": "Low", "count": 1, "description": f"d{i}"} for i in range(3)
    ]
    yield "advisor: three low-impact items", _call(azure={"advisor_summary": three_low})
    yield "advisor: two low-impact items", _call(azure={"advisor_summary": three_low[:2]})
    yield (
        "advisor: an unknown category named like a known label",
        _call(
            azure={
                "advisor_summary": [
                    {"category": "Security", "impact": "High", "count": 1, "description": "a"},
                    {"category": "Sikkerhet", "impact": "High", "count": 1, "description": "b"},
                    {"category": "", "impact": "High", "count": 1, "description": "c"},
                ]
            }
        ),
    )
    yield "orphaned: count without details", _call(azure={"orphaned": 3})
    yield "orphaned: zero", _call(azure={"orphaned": 0, "orphaned_details": []})

    stale = "03c_stale_accounts_WARN.txt"
    for label, text in (
        ("summary line", "  3 enabled account(s) with licenses have not signed in\n"),
        ("licensed stale", "  5 licensed accounts are stale\n"),
        ("n stale", "  2 STALE accounts\n"),
        ("zero", "  0 enabled account(s) with licenses have not signed in\n"),
        ("no count", "  STALE ACCOUNTS\n"),
    ):
        yield f"stale accounts: {label}", _call(file_contents={stale: text})

    cred = "17c_app_credential_expiry_WARN.txt"
    rows = (
        _RULE + "  WARNING: credentials\n" + _RULE + "  App Name    Expires    Status\n  ---\n"
        "\n"
        "  app-a   2026-01-01   EXPIRED\n"
        "  app-b   2026-11-01   critical\n"
        "  app-c   2027-01-01   OK\n"
    )
    for label, text in (
        ("summary", "  1 expired, 0 expiring within 30 days.\n"),
        ("summary, expiring only", "  0 Expired , 4 EXPIRING within 30 days.\n"),
        ("summary, nothing", "  0 expired, 0 expiring within 30 days.\n"),
        ("per-row status", rows),
        ("per-row, critical only", rows.replace("EXPIRED", "OK")),
        ("per-row, nothing", "  app-c   2027-01-01   OK\n"),
    ):
        yield f"credential expiry: {label}", _call(file_contents={cred: text})

    for label, backup in (
        ("coverage unknown", {"coverage_known": False, "vms_not_backed_up": ["vm-a"]}),
        ("all backed up", {"coverage_known": True, "vms_not_backed_up": []}),
        ("one missing", {"coverage_known": True, "vms_not_backed_up": ["vm-a"]}),
    ):
        yield f"backup: {label}", _call(backup_coverage=backup)
    yield (
        "sign-in: nothing suspicious",
        _call(signin_risk={"brute_force_suspects": [], "stale_credential_users": []}),
    )


def _network_cases() -> Iterator[tuple[str, dict]]:
    fg, uf = _FORTIGATE, _UNIFI
    yield (
        "network: two unreadable files",
        _call(network={"unreadable": ["fortigate.json", "unifi.json"]}),
    )
    yield (
        "network: unreadable, no data",
        _call(network={"unreadable": ["a.json"], "has_data": False, "fortigate": fg}),
    )
    yield "network: has_data, no devices", _call(network={"has_data": True})
    for label, value in (
        ("error", {"error": "timeout"}),
        ("empty", {}),
        ("healthy", {"admins": [{"name": "a", "two_factor": True, "trusthost": True}]}),
        ("admins only", {"admins": fg["admins"]}),
        ("warnings only", {"policy_warnings": fg["policy_warnings"]}),
    ):
        yield f"fortigate: {label}", _call(network={"has_data": True, "fortigate": value})
    for label, value in (
        ("error", {"error": "login failed"}),
        ("empty", {}),
        ("standalone mode", {**uf, "mode": "standalone"}),
        (
            "counts without devices",
            {"default_creds_count": 1, "eol_count": 1, "outdated_firmware_count": 1},
        ),
        ("devices without counts", {"devices": uf["devices"]}),
        ("controller, no open wlans", {"mode": "controller", "wlans": uf["wlans"][1:3]}),
        ("controller, no wlans", {"mode": "controller"}),
    ):
        yield f"unifi: {label}", _call(network={"has_data": True, "unifi": value})


def targeted_contexts() -> Iterator[tuple[str, dict]]:
    yield from _mfa_cases()
    yield from _auth_lockout_cases()
    yield from _mail_cases()
    yield from _risky_cases()
    yield from _score_cases()
    yield from _admin_and_device_cases()
    yield from _azure_cases()
    yield from _network_cases()


def synthetic_contexts() -> Iterator[tuple[str, dict]]:
    yield from edge_contexts()
    yield from order_contexts()
    yield from loaded_sweeps()
    yield from targeted_contexts()

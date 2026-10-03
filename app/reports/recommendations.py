"""Prioritised recommendations, and their text in the reader's language.

Every finding the report recommends action on is one rule in ``_RULES``: a
small named function that reads the audit and yields the recommendations it
raises, none, one, or one per subject (a domain, an Advisor category, an
unreadable file). The rules are grouped by domain below; the table lists them
in report order.

``_build_recommendations`` walks the table, sorts what comes out by priority
(a stable sort, so table order breaks ties), numbers it, and gives each
recommendation a language-independent id and the recipe for its own text,
which ``relocalise_recommendations`` rebuilds for a reader in another
language months later.

A rule writes its recommendation out in full, the collector files it was
formed from included: a citation in the same dict as the verdict cannot drift
away from the code that produced it. Only files this run collected are cited,
so a citation always points at something the reader can open.
"""

import logging
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from app.reports.evidence import _evidence_unavailable
from app.reports.i18n import T
from app.reports.parsers import (
    _is_audit_relevant_domain,
    _mfa_user_records,
    _risky_users_from_sidecar,
)
from app.reports.parsers.collaboration import _app_credential_counts
from app.reports.parsers.common import _find_azure_files, _sidecar
from app.reports.parsers.email import _external_forwarding_items
from app.reports.risk import _is_open_wlan

logger = logging.getLogger(__name__)


def relocalise_recommendations(metrics: dict, lang: str) -> dict:
    """Rebuild each recommendation's text in the reader's language.

    A recommendation is written once, when the audit runs, and read for months
    afterwards — so the language it was collected in is not the language the
    reader wants. Runs from before this carry no recipe; their stored text is
    kept as it is, which is the honest answer rather than a blank line.
    """
    from app.reports.i18n import T

    recs = metrics.get("recommendations")
    if not isinstance(recs, list):
        return metrics
    t = T(lang)
    rebuilt = []
    for rec in recs:
        if not isinstance(rec, dict):
            continue
        out = dict(rec)
        for field in ("title", "detail"):
            key = rec.get(f"{field}_key")
            if key:
                try:
                    out[field] = str(t(key, **(rec.get(f"{field}_params") or {})))
                except (KeyError, IndexError):
                    # A stored param set that no longer matches its template.
                    # The stored sentence is stale in one language; a crash
                    # would lose the whole dashboard.
                    logger.warning("Could not re-render recommendation %r", key)
        rebuilt.append(out)
    return {**metrics, "recommendations": rebuilt}


def _build_finding_rec_map(recs: list[dict]) -> dict[str, list[int]]:
    """Build a mapping from finding_id → list of recommendation indices (1-based)."""
    result: dict[str, list[int]] = {}
    for rec in recs:
        fid = rec.get("finding_id", "")
        if fid:
            result.setdefault(fid, []).append(rec.get("rec_index", 0))
    return result


# Registered-method labels (04_mfa_methods) → the authentication-methods policy
# IDs (09b) that make them usable. A phone can be used via SMS or Voice, so it is
# only unusable when BOTH are disabled.
#
# The keys MUST be the exact display labels the collector emits, i.e. the values
# of users_mfa._METHOD_LABELS — a mismatch makes _auth_method_lockout_users treat
# the method as an unrecognised (assumed-usable) label and silently drop the
# lockout warning for anyone whose only method is that one. tests/test_recommendation_identity.py
# cross-checks the two maps so they cannot drift again (M365 review follow-up).
_METHOD_LABEL_TO_POLICY: dict[str, set[str]] = {
    "Authenticator App": {"microsoftAuthenticator"},
    "Phone (SMS/Call)": {"sms", "voice"},
    "FIDO2 Key": {"fido2"},
    "OATH TOTP": {"softwareOath"},
    "Windows Hello": {"windowsHelloForBusiness"},
    "Temp Access Pass": {"temporaryAccessPass"},
    "Email OTP": {"email"},
    "Certificate": {"x509Certificate"},
}


def _disabled_auth_methods(policy_text: str, sidecar: dict | None = None) -> set[str]:
    """Method IDs the authentication-methods policy (09b) reports as disabled.

    From 09b_auth_methods_policy.json when the run has it.
    """
    if sidecar is not None:
        return {
            m.get("method") or ""
            for m in sidecar.get("methods") or []
            if str(m.get("state") or "").lower() == "disabled"
        }
    disabled: set[str] = set()
    for line in policy_text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1].lower() == "disabled":
            disabled.add(parts[0])
    return disabled


def _auth_method_lockout_users(
    mfa: dict, policy_text: str, sidecar: dict | None = None
) -> list[str]:
    """Users whose EVERY registered method is disabled in the policy.

    Enforcing MFA would lock these accounts out — the report never compared the
    two files, so the discrepancy went unflagged (M365 review, F5). Conservative:
    an unrecognised method label is assumed usable, so this only fires when a
    user has methods and none of them can be used.
    """
    disabled = _disabled_auth_methods(policy_text, sidecar)
    if not disabled:
        return []
    locked_out: list[str] = []
    for u in mfa.get("users") or []:
        methods = [m.strip() for m in (u.get("methods") or "").split(",") if m.strip()]
        if not methods:
            continue
        usable = False
        for label in methods:
            ids = _METHOD_LABEL_TO_POLICY.get(label)
            if ids is None or any(pid not in disabled for pid in ids):
                usable = True
                break
        if not usable:
            locked_out.append(f"{u.get('name', '')} ({u.get('upn', '')})")
    return locked_out


# ── Engine ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Audit:
    """The builder's arguments, as the rules read them."""

    t: T
    mfa: dict
    spf_dmarc: list[dict]
    secure_score: dict
    ext_fwd: str
    risky_users: str
    admin_roles: dict | None
    intune: dict | None
    sharepoint: dict | None
    oauth: dict | None
    azure: dict | None
    file_contents: dict | None
    backup_coverage: dict | None
    signin_risk: dict | None
    network: dict | None

    @property
    def fc(self) -> dict:
        return self.file_contents or {}

    def ev(self, *names: str) -> list[str]:
        """The files among *names* this run collected, for a recommendation to cite."""
        have = self.fc
        return [n for n in names if have.get(n, "").strip()]


# A rule reads the audit and yields the recommendations it raises.
_Rule = Callable[[_Audit], Iterator[dict]]

_PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _build_recommendations(
    mfa: dict,
    spf_dmarc: list[dict],
    secure_score: dict,
    ext_fwd: str,
    risky_users: str,
    licenses: list[dict],
    admin_roles: dict | None = None,
    intune: dict | None = None,
    sharepoint: dict | None = None,
    oauth: dict | None = None,
    azure: dict | None = None,
    file_contents: dict | None = None,
    backup_coverage: dict | None = None,
    signin_risk: dict | None = None,
    network: dict | None = None,
    lang: str = "no",
) -> list[dict]:
    """The audit's recommendations, most urgent first, each with a stable id.

    *licenses* is taken and not read. Licence utilisation ("near capacity") is
    a commercial note, not a security finding: raised here it outranked real
    security findings (SharePoint external sharing) as a "medium", and the
    licence table's "near limit" badge and the License Optimization section
    already show it.
    """
    audit = _Audit(
        t=T(lang),
        mfa=mfa,
        spf_dmarc=spf_dmarc,
        secure_score=secure_score,
        ext_fwd=ext_fwd,
        risky_users=risky_users,
        admin_roles=admin_roles,
        intune=intune,
        sharepoint=sharepoint,
        oauth=oauth,
        azure=azure,
        file_contents=file_contents,
        backup_coverage=backup_coverage,
        signin_risk=signin_risk,
        network=network,
    )
    recs = [rec for rule in _RULES for rec in rule(audit)]
    recs.sort(key=lambda r: _PRIORITY_ORDER.get(r["priority"], 9))
    for i, rec in enumerate(recs):
        rec["rec_index"] = i + 1
    return _label_recommendations(recs)


# ── Identity and access ───────────────────────────────────────────────────────


def _mfa(audit: _Audit) -> Iterator[dict]:
    # A Conditional-Access exclusion removes MFA enforcement, and an excluded
    # account that is also a Global Admin or under brute force is the most
    # exposed account in the tenant, reachable with a password alone. It gets
    # its own critical, worked out first so the general MFA finding does not
    # count it again: one account surfacing as two criticals is the double
    # count the review flagged (M365 review, F2).
    high_risk, high_risk_upns = _high_risk_exclusions(audit)
    if audit.mfa.get("has_data"):
        yield from _mfa_not_enforced(audit, high_risk_upns)
    if high_risk:
        t = audit.t
        yield {
            "priority": "critical",
            "evidence": audit.ev("04b_mfa_ca_analysis.txt", "07_admin_roles.txt"),
            "finding_id": "finding-mfa-excluded",
            "title": t("rec_mfa_excluded_title", count=len(high_risk)),
            "detail": t.rec_mfa_excluded_detail,
            "effort": t.rec_effort_immediate,
            "sub_items": high_risk[:50],
            "doc_url": "https://learn.microsoft.com/en-us/entra/identity/conditional-access/concept-conditional-access-users-groups",
        }


# The width 07_admin_roles.txt cuts each UPN to (groups_roles.AdminRolesSection).
_ADMIN_UPN_WIDTH = 45


def _high_risk_exclusions(audit: _Audit) -> tuple[list[str], set[str]]:
    """CA-excluded accounts that are a Global Admin or a brute-force target.

    Returns a sub-item line for each, naming why, and their UPNs.
    """
    t = audit.t
    excluded_users = [u for u in (audit.mfa.get("users") or []) if u.get("ca_excluded")]
    high_risk: list[str] = []
    high_risk_upns: set[str] = set()
    if not excluded_users:
        return high_risk, high_risk_upns
    ga_emails = {
        (g.get("email") or "").strip().lower()
        for g in (audit.admin_roles or {}).get("global_admin_users", [])
    }
    # A run from before 07_admin_roles.json has the admins' UPNs from the
    # table, cut to its column, while the MFA records carry them whole: match
    # a cut one on the part the table kept.
    ga_cut = {e for e in ga_emails if len(e) == _ADMIN_UPN_WIDTH}
    bf_emails = {
        (u or "").strip().lower() for u in (audit.signin_risk or {}).get("brute_force_suspects", [])
    }
    for u in excluded_users:
        upn = (u.get("upn") or "").strip().lower()
        reasons = []
        if upn and (upn in ga_emails or upn[:_ADMIN_UPN_WIDTH] in ga_cut):
            reasons.append(t.rec_mfa_excluded_ga)
        if upn and upn in bf_emails:
            reasons.append(t.rec_mfa_excluded_bruteforce)
        if reasons:
            label = u.get("name") or u.get("upn") or ""
            high_risk.append(f"{label} ({u.get('upn', '')}): {', '.join(reasons)}")
            high_risk_upns.add(upn)
    return high_risk, high_risk_upns


def _mfa_not_enforced(audit: _Audit, high_risk_upns: set[str]) -> Iterator[dict]:
    """Users without enforced MFA, less the accounts finding-mfa-excluded owns."""
    mfa, t, fc = audit.mfa, audit.t, audit.fc
    records = _mfa_user_records(fc.get("04_mfa_methods.json", ""), fc.get("04_mfa_methods.txt", ""))
    not_enforced = [
        f"{r.get('display_name', '')} ({r.get('upn', '')})"
        for r in records
        if _mfa_not_enforced_for(r) and (r.get("upn") or "").strip().lower() not in high_risk_upns
    ]
    # The summary's count less the high-risk accounts, so no account is
    # counted by both criticals; nothing at all when every not-enforced
    # account is already raised there (M365 review, F2).
    adjusted_no_mfa = max(0, mfa.get("no_mfa", 0) - len(high_risk_upns))
    if adjusted_no_mfa > 0:
        detail = _mfa_breakdown(audit, high_risk_upns)
        yield {
            "priority": "critical",
            "evidence": audit.ev("04_mfa_methods.txt", "04b_mfa_ca_analysis.txt"),
            "finding_id": "finding-mfa",
            "title": t("rec_mfa_title", count=adjusted_no_mfa),
            "detail": detail,
            "effort": t.rec_effort_low,
            "sub_items": not_enforced[:50],
            "doc_url": "https://learn.microsoft.com/en-us/entra/identity/authentication/concept-mfa-howitworks",
        }


def _mfa_not_enforced_for(record: dict):
    """Truthy for a user known not to be MFA-enforced.

    No method registered and no CA coverage, or CA-excluded: the exclusion
    means MFA is not enforced even with a method registered.
    """
    unprotected = record.get("mfa_registered") is False and not record.get("ca_covered")
    return unprotected or record.get("ca_excluded")


def _mfa_breakdown(audit: _Audit, high_risk_upns: set[str]) -> str:
    """The detail line's partition, less the high-risk accounts.

    The title and the sub-items already leave out the accounts
    finding-mfa-excluded owns, and so must this, or the card's own numbers
    stop adding up. Each high-risk account is CA-excluded, so it sits in
    exactly one bucket: registered_but_excluded with a method, else
    no_mfa_registered. Taking it from that bucket keeps
    no_mfa_registered + registered_but_excluded equal to the title's count.
    """
    mfa = audit.mfa
    hr_registered = sum(
        1
        for u in (mfa.get("users") or [])
        if (u.get("upn") or "").strip().lower() in high_risk_upns and u.get("has_mfa")
    )
    hr_no_method = len(high_risk_upns) - hr_registered
    return audit.t(
        "rec_mfa_detail",
        registered=mfa.get("mfa_registered", 0),
        ca_covered=mfa.get("ca_covered", 0),
        no_mfa_registered=max(0, mfa.get("no_mfa_registered", 0) - hr_no_method),
        registered_but_excluded=max(0, mfa.get("registered_but_excluded", 0) - hr_registered),
    )


_HANDLED_RISK_STATES = ("remediated", "dismissed", "confirmedsafe", "safe")


def _risky_users(audit: _Audit) -> Iterator[dict]:
    text, t = audit.risky_users, audit.t
    users = _risky_users_from_sidecar(audit.fc)
    if users is None and (not text or "No risky" in text or _evidence_unavailable(text)):
        return
    risky_items = _users_at_risk(t, text, users)
    # A header with no rows (the audit ran, nobody matches) is not a finding:
    # an empty "Risky users detected" would be a false positive.
    if risky_items:
        title_suffix = t("rec_risky_users_suffix", count=len(risky_items))
        yield {
            "priority": "high",
            "evidence": audit.ev("18_risky_users.txt", "18d_risk_detections.txt"),
            "finding_id": "finding-risky",
            "title": t("rec_risky_users_title", suffix=title_suffix),
            "detail": t.rec_risky_users_detail,
            "effort": t.rec_effort_low,
            "sub_items": risky_items,
            "doc_url": "https://learn.microsoft.com/en-us/entra/id-protection/howto-identity-protection-investigate-risk",
        }


def _users_at_risk(t: T, text: str, users: list[dict] | None = None) -> list[str]:
    """A line per user still at risk, from the columnar risky-users report.

    A remediated or dismissed account is no longer a live risk; listing it told
    the customer to investigate something already handled (accuracy sweep).
    ``users`` are the rows from 18_risky_users.json; the text is read without it.
    """
    if users is not None:
        return [
            t("rec_risky_user_line", upn=u["upn"], level=u["level"], state=u["state"])
            for u in users
            if u["state"].lower().replace(" ", "") not in _HANDLED_RISK_STATES
        ]
    items = []
    for line in text.splitlines():
        line = line.strip()
        if (
            not line
            or line.startswith("=")
            or line.startswith("-")
            or "UPN" in line
            or "RISKY" in line
        ):
            continue
        cols = re.split(r"\s{2,}", line)
        if len(cols) < 3:
            continue
        upn, level, state = cols[0].strip(), cols[1].strip(), cols[2].strip()
        if state.lower().replace(" ", "") in _HANDLED_RISK_STATES:
            continue
        items.append(t("rec_risky_user_line", upn=upn, level=level, state=state))
    return items


def _global_admins(audit: _Audit) -> Iterator[dict]:
    admin_roles, t = audit.admin_roles, audit.t
    if admin_roles and admin_roles.get("global_admin_count", 0) > 4:
        yield {
            "priority": "high",
            "evidence": audit.ev("07_admin_roles.txt"),
            "finding_id": "finding-ga",
            "title": t("rec_ga_title", count=admin_roles["global_admin_count"]),
            "detail": t.rec_ga_detail,
            "effort": t.rec_effort_medium,
            "doc_url": "https://learn.microsoft.com/en-us/entra/identity/role-based-access-control/best-practices",
        }


def _auth_method_lockout(audit: _Audit) -> Iterator[dict]:
    # A user's registered methods may all be disabled in the
    # authentication-methods policy, so enforcing MFA would lock them out. The
    # report never compared the two files (M365 review, F5).
    t = audit.t
    policy = audit.fc.get("09b_auth_methods_policy.txt", "")
    sidecar = _sidecar(audit.fc, "09b_auth_methods_policy.txt")
    if not ((policy or sidecar is not None) and audit.mfa.get("users")):
        return
    locked_out = _auth_method_lockout_users(audit.mfa, policy, sidecar)
    if locked_out:
        yield {
            "priority": "high",
            "evidence": audit.ev("09b_auth_methods_policy.txt", "04_mfa_methods.txt"),
            "finding_id": "finding-auth-method-lockout",
            "title": t("rec_auth_lockout_title", count=len(locked_out)),
            "detail": t.rec_auth_lockout_detail,
            "effort": t.rec_effort_medium,
            "sub_items": locked_out[:50],
            "doc_url": "https://learn.microsoft.com/en-us/entra/identity/authentication/concept-authentication-methods-manage",
        }


def _oauth(audit: _Audit) -> Iterator[dict]:
    oauth, t = audit.oauth, audit.t
    if oauth and oauth.get("high_privilege_apps"):
        apps = oauth["high_privilege_apps"]
        yield {
            "priority": "medium",
            "evidence": audit.ev("17b_oauth_consent_grants.txt", "17_app_registrations.txt"),
            "finding_id": "finding-oauth",
            "title": t("rec_oauth_title", count=len(apps)),
            "detail": t.rec_oauth_detail,
            "effort": t.rec_effort_medium,
            "sub_items": apps,
            "doc_url": "https://learn.microsoft.com/en-us/entra/identity/enterprise-apps/manage-application-permissions",
        }


# The collector's summary line reads "N enabled account(s) with licenses have
# not signed in for ...". The older patterns ("N licensed ... stale", "N stale")
# matched neither it nor the banner, so the count was always 0 and the finding
# never fired (accuracy sweep); they stay as fallbacks, tried in order.
_STALE_COUNT = (
    re.compile(r"(\d+)\s+enabled account\(s\) with licenses", re.IGNORECASE),
    re.compile(r"(\d+)\s+licensed.*stale", re.IGNORECASE),
    re.compile(r"(\d+)\s+stale", re.IGNORECASE),
)


def _stale_accounts(audit: _Audit) -> Iterator[dict]:
    t = audit.t
    text = audit.fc.get("03c_stale_accounts_WARN.txt", "")
    sidecar = _sidecar(audit.fc, "03c_stale_accounts_WARN.txt")
    if sidecar is None and not (text and text.strip()):
        return
    count = int(sidecar.get("count") or 0) if sidecar is not None else _stale_account_count(text)
    if count > 0:
        yield {
            "priority": "medium",
            "finding_id": "finding-stale",
            "evidence": audit.ev("03c_stale_accounts_WARN.txt", "03b_stale_accounts.txt"),
            "title": t("rec_stale_title", count=count),
            "detail": t.rec_stale_detail,
            "effort": t.rec_effort_low,
        }


def _stale_account_count(text: str) -> int:
    for pattern in _STALE_COUNT:
        m = pattern.search(text)
        if m:
            return int(m.group(1))
    return 0


# The summary line the collector writes at the top of the WARN file.
_CREDENTIAL_SUMMARY = re.compile(r"(\d+)\s+expired\s*,\s*(\d+)\s+expiring", re.IGNORECASE)


def _credential_expiry(audit: _Audit) -> Iterator[dict]:
    t = audit.t
    text = audit.fc.get("17c_app_credential_expiry_WARN.txt", "")
    # The 17c sidecar's counts first, where the run has them.
    counts = _app_credential_counts(audit.fc)
    if counts is None and not (text and text.strip()):
        return
    expired_count, critical_count = counts or _credential_counts(text)
    total = expired_count + critical_count
    if total > 0:
        yield {
            "priority": "high" if expired_count > 0 else "medium",
            "finding_id": "finding-cred-expiry",
            "evidence": audit.ev(
                "17c_app_credential_expiry_WARN.txt", "17c_app_credential_expiry.txt"
            ),
            "title": t("rec_cred_expiry_title", count=total),
            "detail": t("rec_cred_expiry_detail", expired=expired_count, critical=critical_count),
            "effort": t.rec_effort_low,
        }


def _credential_counts(text: str) -> tuple[int, int]:
    """(expired, expiring soon) app credentials, from the WARN file.

    From the summary line ("X expired, Y expiring within Z days."). Counting
    substrings across the whole file instead double-counted the header word
    "EXPIRED", the summary itself and each row's "Status: EXPIRED", inflating
    the total by about 3 every time the finding fired.
    """
    m = _CREDENTIAL_SUMMARY.search(text)
    if m:
        return int(m.group(1)), int(m.group(2))
    # Without it, the Status that ends each data row: less precise than the
    # summary, better than counting substrings.
    expired_count = critical_count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if (
            not stripped
            or stripped.startswith("=")
            or stripped.startswith("-")
            or "WARNING" in stripped
            or "App Name" in stripped
        ):
            continue
        status = stripped.split()[-1].upper()
        if status == "EXPIRED":
            expired_count += 1
        elif status == "CRITICAL":
            critical_count += 1
    return expired_count, critical_count


def _brute_force(audit: _Audit) -> Iterator[dict]:
    signin_risk, t = audit.signin_risk, audit.t
    if signin_risk and signin_risk.get("brute_force_suspects"):
        suspects = signin_risk["brute_force_suspects"]
        yield {
            "priority": "high",
            "finding_id": "finding-brute-force",
            "evidence": audit.ev("05b_signin_failures.txt", "05_signin_activity.txt"),
            "title": t("rec_brute_force_title", count=len(suspects)),
            "detail": t.rec_brute_force_detail,
            "effort": t.rec_effort_immediate,
            "sub_items": suspects,
        }


def _stale_credentials(audit: _Audit) -> Iterator[dict]:
    # Many failures interleaved with successful sign-ins: a device retrying an
    # old password, not an attack, so low priority and not worded as one.
    signin_risk, t = audit.signin_risk, audit.t
    if signin_risk and signin_risk.get("stale_credential_users"):
        stale = signin_risk["stale_credential_users"]
        yield {
            "priority": "low",
            "finding_id": "finding-stale-credential",
            "evidence": audit.ev("05_signin_activity.txt", "05b_signin_failures.txt"),
            "title": t("rec_stale_cred_title", count=len(stale)),
            "detail": t.rec_stale_cred_detail,
            "effort": t.rec_effort_low,
            "sub_items": stale,
        }


# ── Mail ──────────────────────────────────────────────────────────────────────
#
# One finding per offending domain, never only the first: the domain is part of
# the id, and stopping at the first hid every other domain's gap (accuracy
# sweep).


def _dmarc(audit: _Audit) -> Iterator[dict]:
    t = audit.t
    for d in audit.spf_dmarc:
        # A record without a domain names nothing to fix; d["domain"] below
        # used to raise on it and take the whole report down.
        if not d.get("domain") or not _is_audit_relevant_domain(d["domain"]):
            continue
        if "MISSING" in d.get("dmarc", "") or "WEAK" in d.get("dmarc", ""):
            yield {
                "priority": "high",
                "finding_id": "finding-email",
                "evidence": audit.ev("26_email_dns_spf_dmarc.txt"),
                "title": t("rec_dmarc_title", domain=d["domain"]),
                "detail": t.rec_dmarc_detail,
                "effort": t.rec_effort_low,
                "doc_url": "https://learn.microsoft.com/en-us/microsoft-365/security/office-365-security/email-authentication-dmarc-configure",
            }


def _spf(audit: _Audit) -> Iterator[dict]:
    # A WEAK SPF (~all softfail) counts too, matching the grade, which
    # penalised it while raising no recommendation.
    t = audit.t
    for d in audit.spf_dmarc:
        if not d.get("domain") or not _is_audit_relevant_domain(d["domain"]):
            continue
        if (
            "MISSING" in d.get("spf", "")
            or "CRITICAL" in d.get("spf", "")
            or "WEAK" in d.get("spf", "")
        ):
            yield {
                "priority": "high",
                "finding_id": "finding-email",
                "evidence": audit.ev("26_email_dns_spf_dmarc.txt"),
                "title": t("rec_spf_title", domain=d["domain"]),
                "detail": t.rec_spf_detail,
                "effort": t.rec_effort_low,
                "doc_url": "https://learn.microsoft.com/en-us/microsoft-365/security/office-365-security/email-authentication-spf-configure",
            }


def _external_forwarding(audit: _Audit) -> Iterator[dict]:
    text, t = audit.ext_fwd, audit.t
    if not (text and text.strip()):
        return
    fwd_items = _external_forwarding_items(audit.fc)
    if fwd_items is None:
        fwd_items = _forwarding_rules(text)
    fwd_count = len(fwd_items) if fwd_items else t.rec_ext_fwd_unknown_count
    yield {
        "priority": "critical",
        "evidence": audit.ev(
            "28b_exchange_external_forwarding_WARN.txt",
            "28_exchange_mailbox_forwarding.txt",
        ),
        "finding_id": "finding-fwd",
        "title": t("rec_ext_fwd_title", count=fwd_count),
        "detail": t.rec_ext_fwd_detail,
        "effort": t.rec_effort_immediate,
        "sub_items": fwd_items,
        "doc_url": "https://learn.microsoft.com/en-us/microsoft-365/security/office-365-security/outbound-spam-policies-external-email-forwarding",
    }


def _forwarding_rules(text: str) -> list[str]:
    """ "mailbox → target" for each "  UserName  →  smtp:external@example.com" line."""
    items = []
    for line in text.splitlines():
        line = line.strip()
        if "→" in line:
            parts = line.split("→", 1)
            mailbox = parts[0].strip()
            target = parts[1].strip().replace("smtp:", "").replace("SMTP:", "")
            items.append(f"{mailbox} → {target}")
    return items


# ── Devices and data ──────────────────────────────────────────────────────────


def _secure_score(audit: _Audit) -> Iterator[dict]:
    ss, t = audit.secure_score, audit.t
    if not (ss.get("pct", 100) < 80 and ss.get("improvements")):
        return
    prio = "high" if ss["pct"] < 50 else "medium"
    improvements = ss["improvements"]
    yield {
        "priority": prio,
        "evidence": audit.ev("09_secure_score.txt"),
        "finding_id": "finding-securescore",
        "title": t("rec_secure_score_title", pct=ss["pct"], count=len(improvements)),
        "detail": t(
            "rec_secure_score_detail",
            pct=ss["pct"],
            current=ss.get("current", 0),
            max=ss.get("max", 0),
        ),
        "effort": t.rec_effort_medium,
        "sub_items": [f"{imp['name']} ({imp.get('category', '')})" for imp in improvements],
        "doc_url": "https://learn.microsoft.com/en-us/microsoft-365/security/defender/microsoft-secure-score",
    }


def _intune_noncompliant(audit: _Audit) -> Iterator[dict]:
    intune, t = audit.intune, audit.t
    if intune and intune.get("noncompliant", 0) > 0:
        # An unknown share is neither "high" by being under 50 nor "only 0%":
        # the two defaults used to say opposite things about the same gap.
        pct = intune.get("compliance_pct")
        prio = "high" if pct is not None and pct < 50 else "medium"
        detail = t("rec_intune_detail", pct=pct) if pct is not None else t.rec_intune_detail_no_pct
        yield {
            "priority": prio,
            "evidence": audit.ev("10_intune_devices_count.txt", "10_intune_devices.txt"),
            "finding_id": "finding-intune",
            "title": t("rec_intune_title", count=intune["noncompliant"]),
            "detail": detail,
            "effort": t.rec_effort_medium,
            "doc_url": "https://learn.microsoft.com/en-us/mem/intune/protect/device-compliance-get-started",
        }


def _entra_unmanaged(audit: _Audit) -> Iterator[dict]:
    # Entra-registered endpoints Intune does not manage, raised whatever the
    # compliance percentage, which only speaks to enrolled devices. The gap
    # used to show only when there were no Intune devices at all (M365 review,
    # F10b).
    intune, t = audit.intune, audit.t
    if not (intune and intune.get("entra_unmanaged", 0) > 0 and intune.get("entra_total", 0) > 0):
        return
    entra_unmanaged = intune["entra_unmanaged"]
    entra_total = intune["entra_total"]
    prio = "high" if entra_unmanaged / entra_total >= 0.5 else "medium"
    yield {
        "priority": prio,
        "evidence": audit.ev("15_entra_devices_count.txt", "10_intune_devices_count.txt"),
        "finding_id": "finding-entra-unmanaged",
        "title": t("rec_entra_unmanaged_title", count=entra_unmanaged),
        "detail": t("rec_entra_unmanaged_detail", unmanaged=entra_unmanaged, total=entra_total),
        "effort": t.rec_effort_medium,
        "doc_url": "https://learn.microsoft.com/en-us/mem/intune/enrollment/device-enrollment",
    }


def _sharepoint_read(audit: _Audit) -> dict | None:
    """The SharePoint settings, when the audit reached them.

    The parser defaults sharing_level to "warning" for an absent or
    unrecognised "Sharing Capability", so without this gate an audit that never
    reached the admin settings raised "external sharing is at its most
    permissive level" against every tenant. _compute_risk gates the same way.
    """
    sharepoint = audit.sharepoint
    return sharepoint if sharepoint and sharepoint.get("has_data") else None


def _sharepoint_sharing(audit: _Audit) -> Iterator[dict]:
    sharepoint, t = _sharepoint_read(audit), audit.t
    if sharepoint and sharepoint.get("sharing_level") == "warning":
        yield {
            "priority": "medium",
            "evidence": audit.ev("15b_sharepoint_settings.txt"),
            "finding_id": "finding-sp",
            "title": t.rec_sp_sharing_title,
            "detail": t.rec_sp_sharing_detail,
            "effort": t.rec_effort_low,
            "doc_url": "https://learn.microsoft.com/en-us/sharepoint/turn-external-sharing-on-or-off",
        }


def _sharepoint_legacy_auth(audit: _Audit) -> Iterator[dict]:
    sharepoint, t = _sharepoint_read(audit), audit.t
    if sharepoint and sharepoint.get("legacy_auth"):
        yield {
            "priority": "medium",
            "finding_id": "finding-sp-legacy",
            "evidence": audit.ev("15b_sharepoint_settings.txt"),
            "title": t.rec_sp_legacy_title,
            "detail": t.rec_sp_legacy_detail,
            "effort": t.rec_effort_low,
            "doc_url": "https://learn.microsoft.com/en-us/entra/identity/conditional-access/overview",
        }


# ── Azure ─────────────────────────────────────────────────────────────────────


def _nsg(audit: _Audit) -> Iterator[dict]:
    # Rule by rule, from each subscription's NSG sidecar, or from its WARN
    # file when the run is from before the sidecar.
    fc, t = audit.fc, audit.t
    nsg_warns = [k for k in fc if "nsg_risky" in k.lower() and "WARN" in k]
    nsg_sub_items, replaced = _risky_nsg_rules_from_sidecars(fc)
    nsg_sub_items += [
        rule for k in nsg_warns if k not in replaced for rule in _risky_nsg_rules(fc[k])
    ]
    if not nsg_warns and not nsg_sub_items:
        return
    yield {
        "priority": "critical",
        "finding_id": "finding-nsg",
        "evidence": sorted(nsg_warns),
        "title": t("rec_nsg_title", count=len(nsg_sub_items)),
        "detail": t.rec_nsg_detail,
        "effort": t.rec_effort_medium,
        "sub_items": nsg_sub_items,
    }


def _risky_nsg_rules_from_sidecars(fc: dict) -> tuple[list[str], set[str]]:
    """The risky inbound rules in each 32_azure_nsgs sidecar, and the WARN
    files they stand in for, which are then not read a second time."""
    rules: list[str] = []
    replaced: set[str] = set()
    for fname, _content, sub in _find_azure_files(fc, "32_azure_nsgs"):
        nsgs = _sidecar(fc, fname)
        if nsgs is None:
            continue
        rules += [rule.get("detail") or "" for rule in nsgs.get("risky_rules") or []]
        replaced.add(f"32b_azure_nsg_risky_rules_WARN{'_' + sub if sub else ''}.txt")
    return rules, replaced


def _risky_nsg_rules(text: str) -> list[str]:
    rules = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("NSG ") or (line.startswith("\u26a0") and "NSG" in line):
            rules.append(line.lstrip("\u26a0 ").strip())
    return rules


_ADVISOR_PRIORITY = {
    "Security": "high",
    "HighAvailability": "high",
    "Cost": "medium",
    "Performance": "medium",
    "OperationalExcellence": "low",
}
# Category label i18n keys. A category not named here is shown as Azure names it.
_ADVISOR_LABELS = {
    "Security": "rec_advisor_cat_security",
    "HighAvailability": "rec_advisor_cat_ha",
    "Cost": "rec_advisor_cat_cost",
    "Performance": "rec_advisor_cat_performance",
    "OperationalExcellence": "rec_advisor_cat_ops",
}


def _advisor(audit: _Audit) -> Iterator[dict]:
    # One finding per category, with the specific actions under it.
    azure, t = audit.azure, audit.t
    if not (azure and azure.get("advisor_summary")):
        return
    by_cat: dict[str, list] = {}
    for ad in azure["advisor_summary"]:
        by_cat.setdefault(ad["category"], []).append(ad)
    for cat, items in by_cat.items():
        high_impact = [i for i in items if i["impact"] == "High"]
        # Worth a finding with one high-impact item, or three of any.
        if not high_impact and len(items) < 3:
            continue
        label_key = _ADVISOR_LABELS.get(cat)
        cat_label = getattr(t, label_key) if label_key else cat
        sub_items = [_advisor_line(item) for item in items]
        yield {
            "priority": _ADVISOR_PRIORITY.get(cat, "medium"),
            "title": t("rec_advisor_title", category=cat_label, count=len(items)),
            "detail": t("rec_advisor_detail", high_count=len(high_impact)),
            "effort": t.rec_effort_medium,
            "sub_items": sub_items,
        }


def _advisor_line(item: dict) -> str:
    """ "[High] description (x3, Prod)": count and subscription share one bracket."""
    notes = [f"x{item['count']}"] if item["count"] > 1 else []
    if item.get("subscription"):
        notes.append(item["subscription"])
    note = f" ({', '.join(notes)})" if notes else ""
    return f"[{item['impact']}] {item['description']}{note}"


def _orphaned(audit: _Audit) -> Iterator[dict]:
    azure, t = audit.azure, audit.t
    if azure and azure.get("orphaned", 0) > 0:
        orphan_details = azure.get("orphaned_details", [])
        yield {
            "priority": "low",
            "title": t("rec_orphaned_title", count=azure["orphaned"]),
            "detail": t.rec_orphaned_detail,
            "effort": t.rec_effort_low,
            "sub_items": [f"{o['type']} ({o['status']}): {o['detail']}" for o in orphan_details],
        }


def _backup(audit: _Audit) -> Iterator[dict]:
    coverage, t = audit.backup_coverage, audit.t
    if coverage and coverage.get("coverage_known") and coverage.get("vms_not_backed_up"):
        not_backed = coverage["vms_not_backed_up"]
        yield {
            "priority": "high",
            "title": t("rec_backup_title", count=len(not_backed)),
            "detail": t.rec_backup_detail,
            "effort": t.rec_effort_low,
            "sub_items": not_backed,
        }


# ── Network (FortiGate and UniFi) ─────────────────────────────────────────────


def _network_unreadable(audit: _Audit) -> Iterator[dict]:
    # A file that would not parse leaves the network findings silent, and
    # silence there reads as "nothing found on the network", the opposite of
    # what happened. Say so in the report, not only in a log the customer
    # never sees.
    t = audit.t
    for unreadable in (audit.network or {}).get("unreadable", []):
        yield {
            "priority": "high",
            "title": t("rec_network_audit_unreadable_title", file=unreadable),
            "detail": t.rec_network_audit_unreadable_detail,
            "effort": t.rec_effort_immediate,
            # The file that would not parse is both the provenance and the
            # whole finding, so naming it is not a formality here.
            "evidence": [unreadable],
        }


def _network_device(audit: _Audit, kind: str) -> dict | None:
    """The network audit's reading of "fortigate" or "unifi", unless absent or failed.

    The reading is json.loads of a file on disk, so it can predate a field or
    be a partial write: the rules read it with .get, never [], or a missing
    label would cost the whole report.
    """
    network = audit.network
    if not (network and network.get("has_data")):
        return None
    device = network.get(kind)
    return device if device and "error" not in device else None


def _fg_admins_without_2fa(audit: _Audit) -> Iterator[dict]:
    fg, t = _network_device(audit, "fortigate"), audit.t
    if not fg:
        return
    admins = [a for a in fg.get("admins", []) if not a.get("two_factor")]
    if admins:
        yield {
            "priority": "critical",
            "finding_id": "finding-fg-admin-2fa",
            "title": t("rec_fg_admin_no_2fa_title", count=len(admins)),
            "detail": t.rec_fg_admin_no_2fa_detail,
            "effort": t.rec_effort_low,
            "sub_items": [f"{a.get('name', '?')} ({a.get('profile', '?')})" for a in admins],
        }


def _fg_allow_all(audit: _Audit) -> Iterator[dict]:
    fg, t = _network_device(audit, "fortigate"), audit.t
    if not fg:
        return
    allow_all = [w for w in fg.get("policy_warnings", []) if "allow-all" in w.lower()]
    if allow_all:
        yield {
            "priority": "critical",
            "finding_id": "finding-fg-allow-all",
            "title": t("rec_fg_allow_all_title", count=len(allow_all)),
            "detail": t.rec_fg_allow_all_detail,
            "effort": t.rec_effort_medium,
            "sub_items": allow_all,
        }


def _fg_no_logging(audit: _Audit) -> Iterator[dict]:
    fg, t = _network_device(audit, "fortigate"), audit.t
    if not fg:
        return
    no_log = [w for w in fg.get("policy_warnings", []) if "logging" in w.lower()]
    if no_log:
        yield {
            "priority": "high",
            "finding_id": "finding-fg-no-logging",
            "title": t("rec_fg_no_logging_title", count=len(no_log)),
            "detail": t.rec_fg_no_logging_detail,
            "effort": t.rec_effort_low,
            "sub_items": no_log,
        }


def _fg_admins_without_trusted_host(audit: _Audit) -> Iterator[dict]:
    fg, t = _network_device(audit, "fortigate"), audit.t
    if not fg:
        return
    admins = [a for a in fg.get("admins", []) if not a.get("trusthost")]
    if admins:
        yield {
            "priority": "high",
            "finding_id": "finding-fg-no-trusthost",
            "title": t("rec_fg_no_trusthost_title", count=len(admins)),
            "detail": t.rec_fg_no_trusthost_detail,
            "effort": t.rec_effort_low,
            "sub_items": [a.get("name", "?") for a in admins],
        }


def _device_label(device: dict) -> str:
    return device.get("label", device.get("host", ""))


def _uf_default_credentials(audit: _Audit) -> Iterator[dict]:
    uf, t = _network_device(audit, "unifi"), audit.t
    if not uf:
        return
    default_creds = uf.get("default_creds_count", 0)
    if default_creds:
        devices = [_device_label(d) for d in uf.get("devices", []) if d.get("default_credentials")]
        yield {
            "priority": "critical",
            "finding_id": "finding-uf-default-creds",
            "title": t("rec_uf_default_creds_title", count=default_creds),
            "detail": t.rec_uf_default_creds_detail,
            "effort": t.rec_effort_immediate,
            "sub_items": devices,
        }


def _uf_end_of_life(audit: _Audit) -> Iterator[dict]:
    uf, t = _network_device(audit, "unifi"), audit.t
    if not uf:
        return
    eol_count = uf.get("eol_count", 0)
    if eol_count:
        devices = [
            f"{_device_label(d)} ({d.get('fw_check', {}).get('model', '')})"
            for d in uf.get("devices", [])
            if d.get("fw_check", {}).get("eol")
        ]
        yield {
            "priority": "critical",
            "finding_id": "finding-uf-eol",
            "title": t("rec_uf_eol_title", count=eol_count),
            "detail": t.rec_uf_eol_detail,
            "effort": t.rec_effort_medium,
            "sub_items": devices,
        }


def _uf_outdated_firmware(audit: _Audit) -> Iterator[dict]:
    uf, t = _network_device(audit, "unifi"), audit.t
    if not uf:
        return
    outdated = uf.get("outdated_firmware_count", 0)
    if outdated:
        devices = [
            f"{_device_label(d)}: {d.get('firmware', '')} → {d.get('fw_check', {}).get('latest', '')}"
            for d in uf.get("devices", [])
            if d.get("fw_check", {}).get("up_to_date") is False
            and not d.get("fw_check", {}).get("eol")
        ]
        yield {
            "priority": "high",
            "finding_id": "finding-uf-outdated-fw",
            "title": t("rec_uf_outdated_fw_title", count=outdated),
            "detail": t.rec_uf_outdated_fw_detail,
            "effort": t.rec_effort_low,
            "sub_items": devices,
        }


def _uf_factory_default(audit: _Audit) -> Iterator[dict]:
    uf, t = _network_device(audit, "unifi"), audit.t
    if not uf:
        return
    factory_devs = [d for d in uf.get("devices", []) if d.get("is_default_config")]
    if factory_devs:
        yield {
            "priority": "high",
            "finding_id": "finding-uf-factory-default",
            "title": t("rec_uf_factory_default_title", count=len(factory_devs)),
            "detail": t.rec_uf_factory_default_detail,
            "effort": t.rec_effort_medium,
            "sub_items": [_device_label(d) for d in factory_devs],
        }


def _uf_open_wifi(audit: _Audit) -> Iterator[dict]:
    # The WLAN list is the controller's; a standalone device has none.
    uf, t = _network_device(audit, "unifi"), audit.t
    if not uf or uf.get("mode") != "controller":
        return
    open_wlans = [
        w.get("name", "") for w in uf.get("wlans", []) if _is_open_wlan(w) and w.get("enabled")
    ]
    if open_wlans:
        yield {
            "priority": "critical",
            "finding_id": "finding-uf-open-wifi",
            "title": t.rec_uf_open_wifi_title,
            "detail": t.rec_uf_open_wifi_detail,
            "effort": t.rec_effort_low,
            "sub_items": open_wlans,
        }


# ── The table ─────────────────────────────────────────────────────────────────
#
# In report order: the sort is by priority only, so within one priority this
# order is the order the reader sees.

_RULES: tuple[_Rule, ...] = (
    _mfa,
    _dmarc,
    _spf,
    _external_forwarding,
    _risky_users,
    _secure_score,
    _global_admins,
    _intune_noncompliant,
    _entra_unmanaged,
    _auth_method_lockout,
    _sharepoint_sharing,
    _sharepoint_legacy_auth,
    _oauth,
    _nsg,
    _advisor,
    _orphaned,
    _stale_accounts,
    _credential_expiry,
    _backup,
    _brute_force,
    _stale_credentials,
    _network_unreadable,
    _fg_admins_without_2fa,
    _fg_allow_all,
    _fg_no_logging,
    _fg_admins_without_trusted_host,
    _uf_default_credentials,
    _uf_end_of_life,
    _uf_outdated_firmware,
    _uf_factory_default,
    _uf_open_wifi,
)


# ── Identity of a recommendation ──────────────────────────────────────────────

# Params that name *which* thing a recommendation is about, as opposed to how
# much of it there is. "kunde-a.example" identifies a finding; "3 mailboxes" is how
# big it is this week. Only the former may enter the id, or marking an item done
# would come undone the moment the count moved.
_REC_IDENTITY_PARAMS = ("domain", "part", "category", "sku", "name")


def _label_recommendations(recs: list[dict]) -> list[dict]:
    """Give each recommendation a stable id and the recipe for its own text.

    The id is language-independent so remediation state survives a language
    change — it used to be keyed on the rendered title, which meant an operator
    who marked something done in Norwegian would find it open again in English.

    The key and params come off the Localised strings the builder already
    produced, so there is nothing to keep in step by hand.
    """
    from app.reports.i18n import Localised

    seen: dict[str, int] = {}
    for rec in recs:
        for field in ("title", "detail"):
            value = rec.get(field)
            if isinstance(value, Localised):
                rec[f"{field}_key"] = value.key
                rec[f"{field}_params"] = dict(value.params)

        base = rec.get("title_key") or rec.get("finding_id") or "rec"
        params = rec.get("title_params") or {}
        rec_id = ":".join(
            [base]
            + [str(params[k]) for k in _REC_IDENTITY_PARAMS if params.get(k) not in (None, "")]
        )
        # Two recommendations from one key with nothing to tell them apart is a
        # bug in the builder, but a silently shared id would merge their
        # remediation state, so they are separated and the collision logged.
        seen[rec_id] = seen.get(rec_id, 0) + 1
        if seen[rec_id] > 1:
            logger.warning("Recommendation id %r is not unique - disambiguating", rec_id)
            rec_id = f"{rec_id}#{seen[rec_id]}"
        rec["rec_id"] = rec_id
    return recs

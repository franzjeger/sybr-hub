"""The audit must use the data it already collected, not report it as unknown.

F8 — the break-glass check reported Global Admins' CA-exclusion status as
"unknown, cannot confirm" even when the Conditional Access data contained the
exclusions: the collector simply never passed the exclusion set to the check.
And it printed raw GUIDs instead of the UPN.

F3 — the Exchange section wrapped every sub-save in one try/except, so a single
late save that raised flipped the whole section to FAILED while its already-
written mailbox/transport/anti-phish data was still rendered — a "✗ Failed"
badge over complete data.
"""

from __future__ import annotations

from app.core.encryption import encrypted_read_text
from app.modules.base import SectionStatus
from app.modules.m365_audit.sections.exchange import ExchangeSection
from app.modules.m365_audit.sections.identity_security import IdentitySecuritySection

# ── F8: break-glass correlation ──────────────────────────────────────────────

class _Graph:
    def __init__(self, methods_by_uid=None):
        self.methods_by_uid = methods_by_uid or {}

    async def get(self, path, **kw):
        if "/authentication/methods" in path:
            uid = path.split("/")[1]
            return {"value": self.methods_by_uid.get(uid, [])}
        return {}

    async def get_all(self, path, **kw):
        return []


class _CA:
    def __init__(self, policies):
        self.policies = policies


_APP_METHOD = [{"@odata.type": "#microsoft.graph.microsoftAuthenticatorAuthenticationMethod"}]


def _bg(tmp_path, *, admins, exclusions, users, ca_policies, methods=None):
    sec = IdentitySecuritySection(
        tmp_path, _Graph(methods),
        global_admin_ids=list(admins),
        ca_exclusions=set(exclusions),
        users_ref=list(users),
        ca_section=_CA(ca_policies),
    )
    return sec


def _out(tmp_path):
    return encrypted_read_text(tmp_path / "07c_emergency_access_check.txt")


async def test_an_excluded_admin_is_confirmed_not_unknown(tmp_path):
    sec = _bg(
        tmp_path,
        admins=["admin-guid"],
        exclusions={"admin-guid"},
        users=[{"id": "admin-guid", "userPrincipalName": "sybr_admin@acme.no"}],
        ca_policies=[{"id": "p1"}],
        methods={"admin-guid": _APP_METHOD},
    )
    await sec._collect_break_glass()
    out = _out(tmp_path)
    assert "sybr_admin@acme.no" in out, "the GUID should be resolved to a UPN"
    assert "admin-guid" not in out, "the raw GUID should not be shown when a UPN exists"
    assert "confirmed break-glass candidate" in out
    assert "cannot confirm" not in out, "we had the exclusion data — do not say unknown"


async def test_a_non_excluded_admin_reads_no_when_ca_was_collected(tmp_path):
    # Empty exclusion set + CA policies present = "nobody is excluded", a clean
    # answer, not absence of data.
    sec = _bg(
        tmp_path,
        admins=["a1"],
        exclusions=set(),
        users=[{"id": "a1", "userPrincipalName": "ok@acme.no"}],
        ca_policies=[{"id": "p1"}],
        methods={"a1": _APP_METHOD},
    )
    await sec._collect_break_glass()
    out = _out(tmp_path)
    assert "ok@acme.no" in out
    assert "cannot confirm" not in out


async def test_no_ca_policies_collected_still_says_cannot_confirm(tmp_path):
    sec = _bg(
        tmp_path,
        admins=["a1"],
        exclusions=set(),
        users=[{"id": "a1", "userPrincipalName": "ok@acme.no"}],
        ca_policies=[],   # CA was not collected
        methods={"a1": _APP_METHOD},
    )
    await sec._collect_break_glass()
    assert "cannot confirm" in _out(tmp_path)


async def test_summary_line_counts_only_ca_excluded_candidates(tmp_path):
    # A break-glass account is a Global Admin intentionally excluded from CA. The
    # machine-readable summary must count those, not "every admin row" — the
    # report keys CIS 1.1.6 on this line, and counting rows made every tenant PASS.
    sec = _bg(
        tmp_path,
        admins=["a1", "a2"],
        exclusions={"a1"},                       # only a1 is a real candidate
        users=[{"id": "a1", "userPrincipalName": "bg@acme.no"},
               {"id": "a2", "userPrincipalName": "ok@acme.no"}],
        ca_policies=[{"id": "p1"}],
        methods={"a1": [], "a2": _APP_METHOD},
    )
    await sec._collect_break_glass()
    out = _out(tmp_path)
    assert "break_glass_candidates=1" in out
    assert "ca_exclusions_known=yes" in out


def _signed_in(days_ago: int) -> dict:
    """A user whose last sign-in was ``days_ago`` days back."""
    from datetime import UTC, datetime, timedelta
    ts = (datetime.now(UTC) - timedelta(days=days_ago)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    return {"signInActivity": {"lastSignInDateTime": ts}}


async def test_an_actively_used_excluded_admin_is_not_a_break_glass_candidate(tmp_path):
    # A Global Admin excluded from CA who has signed in this month is an
    # everyday account bypassing MFA — a risk, not the emergency-access posture
    # CIS 1.1.6 checks for. Counting it is what let a daily-use admin PASS
    # 1.1.6 as a "break-glass account" while the same report flagged it as a
    # high-risk account to remove from the exclusion.
    sec = _bg(
        tmp_path,
        admins=["a1"],
        exclusions={"a1"},
        users=[{"id": "a1", "userPrincipalName": "sybr_admin@acme.no",
                **_signed_in(2)}],
        ca_policies=[{"id": "p1"}],
        methods={"a1": _APP_METHOD},
    )
    await sec._collect_break_glass()
    out = _out(tmp_path)
    assert "break_glass_candidates=0" in out, (
        "a recently-used excluded admin is a risk, not a break-glass account"
    )
    assert "actively-used admin bypassing MFA" in out
    assert "confirmed break-glass candidate" not in out


async def test_a_rarely_used_excluded_admin_still_counts(tmp_path):
    # The opposite: an excluded admin whose last sign-in is long gone is the
    # genuine break-glass account — it survives an MFA/CA outage and is not
    # part of daily operations. It must still be counted.
    sec = _bg(
        tmp_path,
        admins=["a1"],
        exclusions={"a1"},
        users=[{"id": "a1", "userPrincipalName": "breakglass@acme.no",
                **_signed_in(120)}],
        ca_policies=[{"id": "p1"}],
        methods={"a1": _APP_METHOD},
    )
    await sec._collect_break_glass()
    out = _out(tmp_path)
    assert "break_glass_candidates=1" in out
    assert "confirmed break-glass candidate" in out


async def test_an_excluded_admin_with_no_sign_in_data_still_counts(tmp_path):
    # signInActivity is null on tenants without P1/P2. Absence of recency data
    # is "no evidence of recent use", not proof of recent use — the account
    # must still qualify as a candidate, exactly as before this check existed.
    sec = _bg(
        tmp_path,
        admins=["a1"],
        exclusions={"a1"},
        users=[{"id": "a1", "userPrincipalName": "bg@acme.no"}],
        ca_policies=[{"id": "p1"}],
        methods={"a1": _APP_METHOD},
    )
    await sec._collect_break_glass()
    out = _out(tmp_path)
    assert "break_glass_candidates=1" in out
    assert "confirmed break-glass candidate" in out


async def test_ca_known_is_false_when_the_mfa_analysis_never_ran(tmp_path):
    # CA policies WERE collected, but the MFA section (which derives and populates
    # the exclusion set) never ran, so ca_exclusions is a stale empty set. Reading
    # that empty set as "nobody is excluded" would report a genuinely-excluded
    # admin as clean. It must fail closed to "cannot confirm" / unknown.
    sec = IdentitySecuritySection(
        tmp_path, _Graph({"a1": _APP_METHOD}),
        global_admin_ids=["a1"],
        ca_exclusions=set(),                     # never populated
        users_ref=[{"id": "a1", "userPrincipalName": "ok@acme.no"}],
        ca_section=_CA([{"id": "p1"}]),          # CA policies present
        mfa_analysis_ran=lambda: False,          # but the MFA analysis did not run
    )
    await sec._collect_break_glass()
    out = _out(tmp_path)
    assert "cannot confirm" in out, "an uncomputed exclusion set is unknown, not clean"
    assert "ca_exclusions_known=no" in out


# ── F3: Exchange sub-collection isolation ────────────────────────────────────

class _ExGraph:
    async def get(self, *a, **k):
        return {}

    async def get_all(self, *a, **k):
        return []


async def test_a_late_exchange_save_failure_does_not_fail_the_whole_section(tmp_path):
    sec = ExchangeSection(tmp_path, exo_data={"mailboxes": []}, verified_domains=[], graph=_ExGraph())
    # A late sub-collection raises; the early ones (mailboxes, transport, ...)
    # have already written their data.
    def boom():
        raise RuntimeError("EXO cmdlet timed out")
    sec._save_retention = boom

    result = await sec.collect()

    assert result.status == SectionStatus.DONE, "one failed save must not fail the section"
    assert any("retention" in w for w in result.warns), result.warns

"""A directory audit log is dumped in full but never read for patterns.

The same operation failing repeatedly from one actor across the window is a
finding in its own right — a stuck integration, a misconfigured app, or a
technician's own tool failing against the tenant (e.g. repeated
delegated-permission-grant failures = the audit tool failing OAuth consent).
The report used to dump 800 rows and flag none of it (M365 review, F12).
"""

from __future__ import annotations

from app.core.encryption import encrypted_read_text
from app.modules.m365_audit.sections.identity_security import IdentitySecuritySection


class _Graph:
    async def get(self, *a, **k):
        return {}

    async def get_all(self, *a, **k):
        return []


def _fail(activity, actor):
    return {"activityDisplayName": activity, "result": "failure",
            "initiatedBy": {"user": {"userPrincipalName": actor}}}


def _ok(activity, actor):
    return {"activityDisplayName": activity, "result": "success",
            "initiatedBy": {"user": {"userPrincipalName": actor}}}


def test_a_repeated_failure_from_one_actor_is_flagged(tmp_path):
    sec = IdentitySecuritySection(tmp_path, _Graph())
    audits = [_fail("Add delegated permission grant", "tech@sybr.no") for _ in range(6)]
    sec._analyse_audit_failures(audits)

    assert any("failed repeatedly" in w for w in sec.result.warns), sec.result.warns
    out = encrypted_read_text(tmp_path / "19b_entra_audit_log_failures_WARN.txt")
    assert "Add delegated permission grant" in out
    assert "tech@sybr.no" in out


def test_failures_below_the_threshold_are_not_flagged(tmp_path):
    sec = IdentitySecuritySection(tmp_path, _Graph())
    audits = [_fail("X", "a@x.no") for _ in range(4)] + [_ok("Y", "b@x.no") for _ in range(20)]
    sec._analyse_audit_failures(audits)
    assert not any("failed repeatedly" in w for w in sec.result.warns), sec.result.warns


def test_failures_scattered_across_actors_do_not_aggregate(tmp_path):
    # Six failures, but each a different (activity, actor) pair — no single
    # repeated pattern, so nothing is flagged.
    sec = IdentitySecuritySection(tmp_path, _Graph())
    audits = [_fail(f"Op{i}", f"user{i}@x.no") for i in range(6)]
    sec._analyse_audit_failures(audits)
    assert not any("failed repeatedly" in w for w in sec.result.warns), sec.result.warns


def test_successes_are_never_flagged(tmp_path):
    sec = IdentitySecuritySection(tmp_path, _Graph())
    audits = [_ok("Add delegated permission grant", "tech@sybr.no") for _ in range(20)]
    sec._analyse_audit_failures(audits)
    assert not any("failed repeatedly" in w for w in sec.result.warns), sec.result.warns

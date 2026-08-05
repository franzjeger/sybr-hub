"""MFA coverage: the number the whole report leans on.

The collector renders a fixed-width table and truncates the display name to
exactly the column width before padding it to that same width. At 35
characters the padding vanishes, so one space separates name from UPN — and
the reader split on runs of two-or-more spaces, merging them and shifting
every later field left by one. The MFA column was then read out of the CA
column.

It propagates: the 35-point risk weight, CIS 1.1.1, the executive summary,
audit_metrics.mfa_coverage_pct, the IT Glue asset, the audit email and the
scheduler's threshold alert all come from this one figure.
"""

from __future__ import annotations

import json

from app.reports.generator import _mfa_user_records, _parse_mfa

HEADER = (
    "=" * 130 + "\n"
    "  MFA METHOD REPORT\n"
    + "=" * 130 + "\n"
    f"  {'Display Name':<35} {'UPN':<45} {'MFA':>5} {'CA':>4} {'CA EXCL':>8}  Methods\n"
    "  " + "-" * 126
)


def _row(name: str, upn: str, mfa: str, ca: str, excl: str, methods: str) -> str:
    """Render exactly as app/modules/m365_audit/sections/users_mfa.py does."""
    return f"  {name[:35]:<35} {upn[:45]:<45} {mfa:>5} {ca:>4} {excl:>8}  {methods}"


def _table(*rows: str) -> str:
    return HEADER + "\n" + "\n".join(rows) + "\n" + "=" * 130


def test_a_long_name_does_not_flip_a_protected_user_to_unprotected():
    """Three users, all with MFA registered. Two have names at the width."""
    table = _table(
        _row("Ola Nordmann", "ola@example.no", "YES", "NO", "NO", "microsoftAuthenticator"),
        _row("Kristoffer Andreas Wilhelmsen Bergstrom", "kaw@example.no", "YES", "NO", "NO", "fido2"),
        _row("Anne-Marie Sophie Johansen Lindqvist", "ams@example.no", "YES", "NO", "NO", "sms"),
    )
    out = _parse_mfa(table, "", [])
    assert out["total"] == 3
    assert out["mfa_registered"] == 3, "every one of these has MFA registered"
    assert out["no_mfa"] == 0
    assert out["pct"] == 100.0


def test_the_most_dangerous_state_is_not_reported_as_covered():
    """No MFA method AND excluded from the CA MFA policy — the worst combination
    a tenant can be in, and the one the shift used to hide."""
    table = _table(
        _row("Kristoffer Andreas Wilhelmsen Bergstrom", "kaw@example.no", "NO", "YES", "YES", "(none)"),
    )
    out = _parse_mfa(table, "", [])
    assert out["total"] == 1
    assert out["mfa_registered"] == 0
    assert out["no_mfa"] == 1
    assert out["pct"] == 0.0, "reporting this user as covered is the bug"


def test_a_doubled_space_in_a_name_shifts_the_other_way():
    table = _table(
        _row("Ola  Nordmann", "ola@example.no", "NO", "NO", "NO", "(none)"),
    )
    out = _parse_mfa(table, "", [])
    assert out["total"] == 1
    assert out["mfa_registered"] == 0


def test_an_unknown_lookup_is_not_counted_as_missing_mfa():
    """'?' means the lookup failed. Bucketing it with the failures turns a
    throttled run into a page of false findings."""
    table = _table(
        _row("Ola Nordmann", "ola@example.no", "YES", "NO", "NO", "microsoftAuthenticator"),
        _row("Kari Nordmann", "kari@example.no", "?", "NO", "NO", "(lookup failed)"),
    )
    recs = _mfa_user_records("", table)
    assert [r["mfa_registered"] for r in recs] == [True, None]


def test_the_sidecar_wins_over_the_table():
    """The collector now writes both; the figures must come from the JSON."""
    sidecar = json.dumps({"users": [
        {"display_name": "Ola Nordmann", "upn": "ola@example.no",
         "mfa_registered": True, "ca_covered": False, "ca_excluded": False, "methods": ["fido2"]},
        {"display_name": "Kari Nordmann", "upn": "kari@example.no",
         "mfa_registered": False, "ca_covered": True, "ca_excluded": False, "methods": []},
    ]})
    out = _parse_mfa("", "", [], sidecar)
    assert out["total"] == 2
    assert out["mfa_registered"] == 1
    assert out["ca_covered"] == 1


def test_a_corrupt_sidecar_falls_back_to_the_table():
    table = _table(_row("Ola Nordmann", "ola@example.no", "YES", "NO", "NO", "fido2"))
    out = _parse_mfa(table, "", [], "{not json")
    assert out["total"] == 1 and out["mfa_registered"] == 1


def test_the_pipe_format_still_parses():
    text = "Ola Nordmann | ola@example.no | MFA:YES | CA:NO | CA_EXCL:NO"
    out = _parse_mfa(text, "", [])
    assert out["total"] == 1 and out["mfa_registered"] == 1


def test_the_collector_and_the_reader_agree_on_the_layout():
    """Guards the column offsets against a change to the collector's f-string."""
    from app.reports.generator import _MFA_COLS

    line = _row("X" * 35, "y" * 45, "YES", "NO", "YES", "fido2")
    assert line[slice(*_MFA_COLS["display_name"])].strip() == "X" * 35
    assert line[slice(*_MFA_COLS["upn"])].strip() == "y" * 45
    assert line[slice(*_MFA_COLS["mfa"])].strip() == "YES"
    assert line[slice(*_MFA_COLS["ca"])].strip() == "NO"
    assert line[slice(*_MFA_COLS["ca_excl"])].strip() == "YES"


def test_coverage_cannot_exceed_a_hundred_percent():
    """The dashboard read "Avg MFA 102%", which is not a coverage figure.

    A user whose method lookup returned nothing was counted as unknown and
    removed from the denominator. If a Conditional Access policy covered that
    same user they were also counted as effectively covered — so they stayed
    in the numerator. One such user in a fifty-user tenant is 102%.

    The two sets have to be the same set. A CA policy enforcing MFA settles a
    user's protection whichever way the method lookup went, so such a user is
    determined, not unknown.
    """
    rows = [_row(f"User {i}", f"u{i}@x.no", "YES", "NO", "NO", "app") for i in range(49)]
    # the method lookup failed for this one, but CA covers them
    rows.append(_row("Ghost", "ghost@x.no", "?", "YES", "NO", ""))
    result = _parse_mfa(HEADER + "\n" + "\n".join(rows), "", [])

    assert result["pct"] <= 100, f"coverage read {result['pct']}%"
    assert result["covered"] <= result["measured"], (
        "the numerator counts users the denominator does not"
    )
    assert result["unknown"] == 0, "CA coverage settles this user's state"
    assert result["pct"] == 100.0
    assert result["no_mfa"] == 0


def test_a_user_with_no_signal_at_all_is_still_unknown():
    """The counterpart: nothing determined means nothing determined."""
    rows = [_row(f"User {i}", f"u{i}@x.no", "YES", "NO", "NO", "app") for i in range(9)]
    rows.append(_row("Ghost", "ghost@x.no", "?", "NO", "NO", ""))
    result = _parse_mfa(HEADER + "\n" + "\n".join(rows), "", [])

    assert result["unknown"] == 1
    assert result["measured"] == 9
    assert result["covered"] == 9
    assert result["pct"] == 100.0


def test_registration_and_enforcement_are_reported_apart():
    """99.5% coverage printed above "42 users have no MFA methods".

    Coverage counts a user as protected when an enabled CA policy forces MFA
    at sign-in, registered method or not. That is a defensible claim about the
    account — it cannot be reached with a password alone — but it is not what
    "MFA coverage" sounds like, and on the tenant this was written against 47
    of the 185 covered users had never registered anything. Both figures are
    now named, so the headline and the warning stop contradicting each other.
    """
    rows = [_row(f"Reg {i}", f"r{i}@x.no", "YES", "YES", "NO", "app") for i in range(6)]
    rows += [_row(f"CA {i}", f"c{i}@x.no", "NO", "YES", "NO", "") for i in range(4)]
    result = _parse_mfa(HEADER + "\n" + "\n".join(rows), "", [])

    assert result["measured"] == 10
    assert result["covered"] == 10
    assert result["pct"] == 100.0, "enforcement really does cover all ten"

    assert result["mfa_registered"] == 6
    assert result["registered_pct"] == 60.0, "and only six of them have a method"
    assert result["enforced_only"] == 4


def test_the_two_figures_agree_when_everyone_has_registered():
    rows = [_row(f"Reg {i}", f"r{i}@x.no", "YES", "YES", "NO", "app") for i in range(5)]
    result = _parse_mfa(HEADER + "\n" + "\n".join(rows), "", [])
    assert result["pct"] == 100.0
    assert result["registered_pct"] == 100.0
    assert result["enforced_only"] == 0

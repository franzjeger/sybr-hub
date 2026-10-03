"""Rows that start with "No" or "Note" are data unless they are the collectors' prose."""

from __future__ import annotations

import pytest

from app.reports.parsers.common import _count_data_lines, _is_furniture


@pytest.mark.parametrize(
    "line",
    [
        "No jailbroken devices",
        "No external forwarding",
        "Notes",
        "No Code Lab",
        "No one (most restrictive)",
        "No Reply  noreply@acme.example  ext@mail.example",
    ],
)
def test_a_row_named_no_or_note_is_data(line):
    assert not _is_furniture(line)


@pytest.mark.parametrize(
    "line",
    [
        "No Recovery Services vaults found.",
        "No secure score data available.",
        "No credentials found on any app registration.",
        "No external sharing or anonymous links detected.",
        "No subscription_id configured",
        "No organization data returned",
        "NOTE: Dynamic group — 0 members resolved; rule shown above.",
        "Note: This endpoint requires SecurityAlert.Read.All permissions.",
        "Note that the endpoint also requires Microsoft Entra ID P2.",
    ],
)
def test_the_collectors_prose_is_still_furniture(line):
    assert _is_furniture(line)


def test_a_table_of_policies_named_no_counts_every_row():
    frame = "=" * 40
    text = (
        f"{frame}\n  INTUNE COMPLIANCE POLICIES  (2 policies)\n{frame}\n\n"
        f"Name                      Platform\n{'-' * 40}\n"
        "No jailbroken devices     Windows\n"
        "No removable media        Windows\n"
    )
    assert _count_data_lines(text) == 2

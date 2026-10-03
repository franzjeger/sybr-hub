"""The password rules, and the one that used to be unreachable.

``validate_password`` applies its checks in order: length, then letter, digit
and special character, then the common-password blocklist. The blocklist ran
last and held only 8-9 character classics, so every entry was rejected by an
earlier rule and the list could never decide anything. It looked like a
control and was decoration.
"""

from __future__ import annotations

import pytest

from app.core.auth import _COMMON_PASSWORDS, ENV_DISABLE_HIBP, validate_password


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Keep the breached-password lookup out of the unit tests.

    validate_password reaches api.pwnedpasswords.com for anything that clears
    the local rules. These tests are about the local rules.
    """
    monkeypatch.setenv(ENV_DISABLE_HIBP, "1")


def _rejected_by_an_earlier_rule(candidate: str) -> str | None:
    """Re-run the rules that precede the blocklist, in order."""
    import re

    if len(candidate) < 10:
        return "too short"
    if len(candidate) > 128:
        return "too long"
    if not re.search(r"[a-zA-Z]", candidate):
        return "no letter"
    if not re.search(r"[0-9]", candidate):
        return "no digit"
    if not re.search(r"[^a-zA-Z0-9]", candidate):
        return "no special character"
    return None


def test_every_blocklist_entry_is_actually_reachable():
    """An entry an earlier rule already rejects never decides anything."""
    unreachable = {
        entry: reason
        for entry in _COMMON_PASSWORDS
        if (reason := _rejected_by_an_earlier_rule(entry)) is not None
    }
    assert not unreachable, (
        "these blocklist entries can never be reached — an earlier rule "
        f"rejects them first: {unreachable}"
    )


def test_the_blocklist_is_not_empty():
    assert _COMMON_PASSWORDS


@pytest.mark.parametrize("candidate", sorted(_COMMON_PASSWORDS))
async def test_each_blocklisted_password_is_refused(candidate):
    assert await validate_password(candidate) is not None


async def test_the_blocklist_is_case_insensitive():
    """The check lowercases, so capitalising must not walk around it."""
    entry = next(iter(sorted(_COMMON_PASSWORDS)))
    assert await validate_password(entry.upper()) is not None
    assert await validate_password(entry.capitalize()) is not None


@pytest.mark.parametrize(
    ("candidate", "why"),
    [
        ("kort1!", "under ten characters"),
        ("abcdefghij!", "no digit"),
        ("abcdefgh12", "no special character"),
        ("1234567890!", "no letter"),
        ("a1!" + "x" * 130, "over 128 characters"),
    ],
)
async def test_the_shape_rules_still_reject(candidate, why):
    assert await validate_password(candidate) is not None, why


async def test_a_strong_password_is_accepted():
    assert await validate_password("Fjord-Kompani-2026!") is None


@pytest.mark.parametrize(
    ("candidate", "accepted"),
    [("Abcde123!x", True), ("Abcd123!x", False)],
)
async def test_the_length_floor_is_ten_not_nine(candidate, accepted):
    """Boundary, carried over from the file this replaced."""
    assert (await validate_password(candidate) is None) is accepted

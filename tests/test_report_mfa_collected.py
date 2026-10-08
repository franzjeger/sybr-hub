"""MFA coverage, from the files the Users, Conditional Access and MFA collectors write.

The headline MFA figure is a cross-reference too: who has a method registered
(one Graph call per user), who a Conditional Access policy enforcing MFA
reaches, and who it excludes. The collectors write the result twice, as the
fixed-width 04_mfa_methods.txt for a person and as 04_mfa_methods.json for
the report. Both are read here exactly as a run leaves them, through a real
GraphClient answering from tests/collector_rig.py, and both must give the same
figures: the table is the fallback for runs from before the sidecar existed.
"""

from __future__ import annotations

import pytest

from app.modules.m365_audit.sections.conditional_access import ConditionalAccessSection
from app.modules.m365_audit.sections.users_mfa import MFASection, UsersSection
from app.reports.parsers import _parse_mfa, _parse_user_counts
from tests.collector_rig import FakeGraph, refused, run_sections

# Exactly the width of the table's name column. At this length the padding
# disappears and a reader that splits on runs of spaces merges name and UPN.
FULL_WIDTH_NAME = "Anne-Marie Christoffersen Haugsland"
assert len(FULL_WIDTH_NAME) == 35


def _user(uid: str, name: str, *, enabled: bool = True, guest: bool = False) -> dict:
    return {
        "id": uid,
        "displayName": name,
        "userPrincipalName": f"{uid}@acme.example",
        "accountEnabled": enabled,
        "userType": "Guest" if guest else "Member",
        "onPremisesSyncEnabled": False,
        "assignedLicenses": [{"skuId": "sku-1"}],
        "signInActivity": {"lastSignInDateTime": "2026-10-01T08:00:00Z"},
    }


def _methods(*odata_types: str) -> dict:
    return {"value": [{"@odata.type": f"#microsoft.graph.{t}"} for t in odata_types]}


USERS = [
    _user("kari", "Kari Nordmann"),  # authenticator, in the MFA policy's group
    _user("annemarie", FULL_WIDTH_NAME),  # FIDO2 key, no policy
    _user("ola", "Ola Nordmann"),  # password only, no policy
    _user("per", "Per Hansen"),  # method lookup refused
    _user("breakglass", "Break Glass"),  # authenticator, excluded from the policy
    _user("gjest", "Gjest Bruker", guest=True),
    _user("sluttet", "Sluttet Ansatt", enabled=False),
]

MFA_POLICY = {
    "id": "policy-1",
    "displayName": "Krev MFA",
    "state": "enabled",
    "conditions": {
        "users": {
            "includeUsers": [],
            "includeGroups": ["group-mfa"],
            "excludeUsers": ["breakglass"],
            "excludeGroups": [],
        },
        "applications": {"includeApplications": ["All"]},
        "clientAppTypes": ["all"],
    },
    "grantControls": {"operator": "OR", "builtInControls": ["mfa"]},
}

ROUTES = {
    "users": USERS,
    "users/kari/authentication/methods": _methods(
        "passwordAuthenticationMethod", "microsoftAuthenticatorAuthenticationMethod"
    ),
    "users/annemarie/authentication/methods": _methods("fido2AuthenticationMethod"),
    "users/ola/authentication/methods": _methods("passwordAuthenticationMethod"),
    "users/per/authentication/methods": refused(),
    "users/breakglass/authentication/methods": _methods(
        "microsoftAuthenticatorAuthenticationMethod"
    ),
    "identity/conditionalAccess/policies": [MFA_POLICY],
    "identity/conditionalAccess/namedLocations": [],
    "groups/group-mfa": {"id": "group-mfa", "displayName": "MFA-brukere", "groupTypes": []},
    "groups/group-mfa/members": [{"id": "kari"}, {"id": "breakglass"}],
}


async def _collect(tmp_path, *, sidecars: bool) -> tuple[dict, FakeGraph]:
    async with FakeGraph(ROUTES, page_size=2) as fake:
        users = UsersSection(tmp_path, fake.client)
        ca = ConditionalAccessSection(tmp_path, fake.client)
        mfa = MFASection(tmp_path, fake.client, users.users, ca_section=ca)
        files = await run_sections(users, ca, mfa, sidecars=sidecars)
    return files, fake


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_mfa_coverage_survives_the_round_trip(tmp_path, sidecars):
    files, _ = await _collect(tmp_path, sidecars=sidecars)
    assert ("04_mfa_methods.json" in files) is sidecars

    mfa = _parse_mfa(
        files["04_mfa_methods.txt"],
        files["04b_mfa_ca_analysis.txt"],
        [],
        files.get("04_mfa_methods.json", ""),
    )

    # The five enabled members are measured; guests and disabled accounts are not.
    assert mfa["total"] == 5
    assert mfa["unknown"] == 1, "a refused lookup is unknown, not 'no MFA'"
    assert mfa["measured"] == 4
    assert mfa["covered"] == 2
    assert mfa["pct"] == 50.0
    assert mfa["mfa_registered"] == 3
    assert mfa["registered_pct"] == 75.0
    assert mfa["ca_covered"] == 2
    assert mfa["ca_excluded"] == 1
    # The two ways of not being covered, kept apart for the recommendation.
    assert mfa["no_mfa"] == 2
    assert mfa["no_mfa_registered"] == 1, "Ola: nothing registered"
    assert mfa["registered_but_excluded"] == 1, "Break Glass: registered, but excluded"

    by_name = {u["name"]: u for u in mfa["users"]}
    assert by_name[FULL_WIDTH_NAME]["upn"] == "annemarie@acme.example"
    assert by_name[FULL_WIDTH_NAME]["protected"] is True
    assert by_name["Per Hansen"]["unknown"] is True
    assert by_name["Break Glass"]["protected"] is False


async def test_the_user_counts_come_from_every_page(tmp_path):
    """Seven users in pages of two: the count is only right if all four pages were read."""
    files, fake = await _collect(tmp_path, sidecars=True)

    assert len(fake.requested("users")) == 4
    assert fake.unrouted == [], "every call the sections made was answered"

    counts = _parse_user_counts(files["03_users_count.txt"])
    assert counts["total"] == 7
    assert counts["enabled"] == 6
    assert counts["disabled"] == 1
    assert counts["guests"] == 1


# ── A registered method is a code, worded by the report ───────────────────────
#
# The collector wrote its own English label for each method ("Authenticator
# App", "Phone (SMS/Call)"), and the technical report listed them as they
# stood under a Norwegian heading (TODO C15).


async def test_the_methods_are_stored_as_graphs_own_types(tmp_path):
    """The sidecar's (the table's methods column is not read back)."""
    files, _ = await _collect(tmp_path, sidecars=True)

    mfa = _parse_mfa(
        files["04_mfa_methods.txt"],
        files["04b_mfa_ca_analysis.txt"],
        [],
        files.get("04_mfa_methods.json", ""),
    )
    by_name = {u["name"]: u for u in mfa["users"]}
    assert by_name["Kari Nordmann"]["methods"] == "microsoftAuthenticator"
    assert by_name[FULL_WIDTH_NAME]["methods"] == "fido2"


@pytest.mark.parametrize(
    ("lang", "expected"),
    [
        ("no", "Authenticator-app, FIDO2-sikkerhetsnøkkel, Midlertidig tilgangspass, ukjentMetode"),
        ("en", "Authenticator app, FIDO2 security key, Temporary Access Pass, ukjentMetode"),
    ],
)
def test_the_report_words_new_codes_and_old_labels_alike(lang, expected):
    from app.reports.i18n import T
    from app.reports.parsers.identity import mfa_methods_text

    # A new run's codes, an old run's label, and a type nobody has a word for.
    methods = "microsoftAuthenticator, FIDO2 Key, temporaryAccessPass, ukjentMetode"
    assert mfa_methods_text(methods, T(lang)) == expected

"""GDAP import enriches the customer that is already there, or creates one.

Partner Center knows a customer by tenant id and company name. A customer
imported from IT Glue has a name and an org id and nothing else — no tenant id
at all. The import matched on tenant id alone, so every tenant looked new and
importing would have created a second record for each of 272 customers, with
the IT Glue org id on one and the tenant id on the other.

Name is the only thing the two systems share. It is enough to *propose* a link;
it is not enough to write one unattended, because a tenant id on the wrong
company hands one customer's Conditional Access to another.
"""

from __future__ import annotations

from app.core.name_match import match_by_name, normalise_org_name, score_name_match


def _cands(*names):
    return [(n, {"_id": n.lower().replace(" ", "-"), "CustomerName": n}) for n in names]


def test_an_exact_company_name_is_a_confident_proposal():
    payload, score, confidence = match_by_name("Acme AS", _cands("Acme AS", "Beta AS"))
    assert confidence == "high"
    assert score == 1.0
    assert payload["CustomerName"] == "Acme AS"


def test_the_legal_suffix_does_not_have_to_agree():
    # Partner Center returns "Acme", IT Glue holds "Acme AS". Same company.
    _, _, confidence = match_by_name("Acme", _cands("Acme AS"))
    assert confidence == "high"


def test_two_plausible_customers_are_ambiguous_not_a_guess():
    _, _, confidence = match_by_name(
        "Nordic Konsult", _cands("Nordic Konsult Oslo", "Nordic Konsult Bergen")
    )
    assert confidence == "ambiguous"


def test_an_unknown_company_proposes_nobody():
    payload, _, confidence = match_by_name("Helt Ukjent Bedrift", _cands("Acme AS"))
    assert confidence == "none"
    assert payload is None


def test_no_local_customers_is_not_an_error():
    # The state right after a clean install, before any import.
    payload, score, confidence = match_by_name("Acme AS", [])
    assert (payload, score, confidence) == (None, 0.0, "none")


def test_a_blank_company_name_proposes_nobody():
    _, _, confidence = match_by_name("   ", _cands("Acme AS"))
    assert confidence == "none"


def test_containment_still_respects_word_boundaries():
    # The Star Bil / Star Bilskade lesson, which this module now owns for
    # every caller rather than for UniFi alone.
    assert score_name_match(
        normalise_org_name("Star Bilskade Agder AS"), normalise_org_name("Star Bil AS")
    ) < 0.75

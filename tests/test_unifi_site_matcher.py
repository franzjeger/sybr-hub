"""Matching cloud sites to customers, and admitting when it cannot.

An IT Glue import creates customers with a name and nothing else; the cloud
lists sites with a name and nothing else. The join is by name, which means the
interesting cases are not the ones that match — they are the ones where two
customers look equally plausible, and where nothing matches at all.

Scoring follows the Uniweb matcher already in the tree so this codebase has one
notion of "matched" rather than two that disagree.
"""

from __future__ import annotations

from app.services.unifi_api import (
    match_sites_to_customers,
    normalise_org_name,
    score_name_match,
    summarise_site_matches,
)


def _cust(name, cid=None):
    return {"_id": cid or name.lower().replace(" ", "-"), "CustomerName": name}


def _site(name, site_id="s1"):
    return {"site_id": site_id, "host_id": "h1", "name": name}


def test_a_legal_suffix_is_not_part_of_the_name():
    # "Acme AS" and "Acme" are one company. Leaving the suffix in drags an
    # otherwise exact match below the threshold.
    assert normalise_org_name("Acme AS") == "acme"
    assert normalise_org_name("Acme Konsult A/S") == "acme konsult"
    assert normalise_org_name("Acme Ltd.") == "acme"


def test_punctuation_and_case_do_not_change_identity():
    assert normalise_org_name("A-Tre, Konsult AS") == normalise_org_name("a tre konsult")


def test_a_name_that_is_only_a_suffix_normalises_to_nothing():
    assert normalise_org_name("AS") == ""
    assert normalise_org_name("") == ""
    assert normalise_org_name(None) == ""


def test_the_score_follows_the_uniweb_scale():
    assert score_name_match("acme", "acme") == 1.0
    assert score_name_match("acme", "acme konsult") == 0.85
    assert 0 < score_name_match("acme", "beta industri") < 0.75
    assert score_name_match("", "acme") == 0.0


def test_an_exact_name_matches_with_high_confidence():
    [p] = match_sites_to_customers([_site("Acme AS")], [_cust("Acme")])
    assert p["confidence"] == "high"
    assert p["customer_name"] == "Acme"
    assert p["score"] == 1.0


def test_two_equally_plausible_customers_are_ambiguous_not_a_guess():
    # Picking the higher score here would be a coin flip written into a
    # customer record. The operator decides.
    proposals = match_sites_to_customers(
        [_site("Nordic Konsult")],
        [_cust("Nordic Konsult Oslo"), _cust("Nordic Konsult Bergen")],
    )
    assert proposals[0]["confidence"] == "ambiguous"


def test_a_site_with_no_plausible_customer_still_appears():
    # Hiding it would make the list look complete when it is not — the site
    # belongs to a customer nobody imported.
    [p] = match_sites_to_customers([_site("Helt Ukjent Bedrift")], [_cust("Acme")])
    assert p["confidence"] == "none"
    assert p["customer_id"] == ""
    assert p["site_name"] == "Helt Ukjent Bedrift"


def test_no_customers_at_all_is_not_an_error():
    # The state right after a clean install: sites exist, customers do not.
    [p] = match_sites_to_customers([_site("Acme")], [])
    assert p["confidence"] == "none"
    assert p["score"] == 0.0


def test_ambiguous_sorts_first_because_it_needs_a_person():
    proposals = match_sites_to_customers(
        [_site("Acme", "s1"), _site("Nordic Konsult", "s2"), _site("Ukjent", "s3")],
        [_cust("Acme"), _cust("Nordic Konsult Oslo"), _cust("Nordic Konsult Bergen")],
    )
    assert proposals[0]["confidence"] == "ambiguous"
    assert proposals[-1]["confidence"] == "none"


def test_the_summary_counts_only_unambiguous_matches_as_applicable():
    proposals = match_sites_to_customers(
        [_site("Acme", "s1"), _site("Nordic Konsult", "s2"), _site("Ukjent", "s3")],
        [_cust("Acme"), _cust("Nordic Konsult Oslo"), _cust("Nordic Konsult Bergen")],
    )
    summary = summarise_site_matches(proposals)
    assert summary["total"] == 3
    assert summary["auto_applicable"] == 1
    assert summary["needs_review"] >= 1


def test_a_customer_with_a_blank_name_is_not_a_candidate():
    [p] = match_sites_to_customers([_site("Acme")], [{"_id": "x", "CustomerName": "  "}])
    assert p["confidence"] == "none"

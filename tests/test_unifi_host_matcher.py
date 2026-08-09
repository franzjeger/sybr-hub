"""Matching consoles to customers, and admitting when it cannot.

An IT Glue import creates customers with a name and nothing else. The cloud's
*site* names carry no identity — 29 of 30 are literally "default" and the rest
are opaque ids — so matching on them proposed nothing for 76 of 77. The console
name is what a technician typed at adoption, and it is hyphenated rather than
spaced, which is why normalise_org_name turns a hyphen into a space.

The interesting cases are not the ones that match. They are the ones where two
customers look equally plausible, and where nothing matches at all.

Scoring follows the Uniweb matcher already in the tree so this codebase has one
notion of "matched" rather than two that disagree.
"""

from __future__ import annotations

from app.services.unifi_api import (
    match_hosts_to_customers,
    normalise_org_name,
    score_name_match,
    summarise_host_matches,
)


def _cust(name, cid=None):
    return {"_id": cid or name.lower().replace(" ", "-"), "CustomerName": name}


def _host(name, host_id="h1"):
    return {"host_id": host_id, "name": name}


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
    [p] = match_hosts_to_customers([_host("Acme AS")], [_cust("Acme")])
    assert p["confidence"] == "high"
    assert p["customer_name"] == "Acme"
    assert p["score"] == 1.0


def test_two_equally_plausible_customers_are_ambiguous_not_a_guess():
    # Picking the higher score here would be a coin flip written into a
    # customer record. The operator decides.
    proposals = match_hosts_to_customers(
        [_host("Nordic Konsult")],
        [_cust("Nordic Konsult Oslo"), _cust("Nordic Konsult Bergen")],
    )
    assert proposals[0]["confidence"] == "ambiguous"


def test_a_site_with_no_plausible_customer_still_appears():
    # Hiding it would make the list look complete when it is not — the site
    # belongs to a customer nobody imported.
    [p] = match_hosts_to_customers([_host("Helt Ukjent Bedrift")], [_cust("Acme")])
    assert p["confidence"] == "none"
    assert p["customer_id"] == ""
    assert p["host_name"] == "Helt Ukjent Bedrift"


def test_no_customers_at_all_is_not_an_error():
    # The state right after a clean install: sites exist, customers do not.
    [p] = match_hosts_to_customers([_host("Acme")], [])
    assert p["confidence"] == "none"
    assert p["score"] == 0.0


def test_ambiguous_sorts_first_because_it_needs_a_person():
    proposals = match_hosts_to_customers(
        [_host("Acme", "h1"), _host("Nordic Konsult", "h2"), _host("Ukjent", "h3")],
        [_cust("Acme"), _cust("Nordic Konsult Oslo"), _cust("Nordic Konsult Bergen")],
    )
    assert proposals[0]["confidence"] == "ambiguous"
    assert proposals[-1]["confidence"] == "none"


def test_the_summary_counts_only_unambiguous_matches_as_applicable():
    proposals = match_hosts_to_customers(
        [_host("Acme", "h1"), _host("Nordic Konsult", "h2"), _host("Ukjent", "h3")],
        [_cust("Acme"), _cust("Nordic Konsult Oslo"), _cust("Nordic Konsult Bergen")],
    )
    summary = summarise_host_matches(proposals)
    assert summary["total"] == 3
    assert summary["auto_applicable"] == 1
    assert summary["needs_review"] >= 1


def test_a_customer_with_a_blank_name_is_not_a_candidate():
    [p] = match_hosts_to_customers([_host("Acme")], [{"_id": "x", "CustomerName": "  "}])
    assert p["confidence"] == "none"


def test_a_hyphenated_console_name_matches_a_spaced_customer_name():
    # The regression that made this branch necessary: consoles are adopted as
    # "A-Tre-Konsult-AS" while the customer is "A-Tre Konsult AS".
    [p] = match_hosts_to_customers(
        [_host("A-Tre-Konsult-AS")], [_cust("A-Tre Konsult AS")]
    )
    assert p["confidence"] == "high"
    assert p["score"] == 1.0


def test_a_site_style_default_name_matches_nothing():
    # What the old matcher was fed for 29 of 30 consoles.
    [p] = match_hosts_to_customers([_host("default")], [_cust("Acme")])
    assert p["confidence"] == "none"


# ── Containment must respect word boundaries ─────────────────────────────────

def test_containment_does_not_fire_inside_a_word():
    # Star Bil AS and Star Bilskade AS are different companies. Raw substring
    # containment scored them 0.85 — "confident" — because *bil* begins
    # *bilskade*, and the resulting link would have been silently wrong.
    score = score_name_match(
        normalise_org_name("Star-Bilskade-AS-Avd-Skien"),
        normalise_org_name("STAR BIL AS"),
    )
    assert score < 0.75


def test_containment_still_fires_on_whole_words():
    assert score_name_match(
        normalise_org_name("Unifi-OS-Sybr-AS"), normalise_org_name("Sybr AS")
    ) == 0.85


def test_an_infrastructure_hostname_is_not_a_customer():
    # "unifi.sybr.no" collapses to one word, so "sybr" is inside it but not a
    # word of it. It is a DNS name, not a company.
    assert score_name_match(
        normalise_org_name("unifi.sybr.no"), normalise_org_name("Sybr AS")
    ) < 0.75


# ── One customer cannot own two consoles by accident ─────────────────────────

def test_a_customer_wanted_by_two_consoles_is_contested():
    # UniFiHostId holds one value, so accepting both halves would overwrite the
    # first without a word. Neither is auto-applicable.
    proposals = match_hosts_to_customers(
        [_host("Acme-AS", "h1"), _host("Acme-AS-Avdeling", "h2")],
        [_cust("Acme AS")],
    )
    contested = [p for p in proposals if p["customer_id"]]
    assert len(contested) == 2
    assert all(p["contested"] for p in contested)
    assert all(p["confidence"] == "ambiguous" for p in contested)


def test_an_uncontested_match_is_not_flagged():
    [p] = match_hosts_to_customers([_host("Acme-AS")], [_cust("Acme AS")])
    assert p["contested"] is False
    assert p["confidence"] == "high"


# ── Re-running does not re-propose what is already linked ────────────────────

def test_a_linked_customer_is_not_offered_again():
    customers = [{"_id": "c1", "CustomerName": "Acme AS", "UniFiHostId": "h9"}]
    [p] = match_hosts_to_customers([_host("Acme-AS")], customers)
    assert p["confidence"] == "none"
    assert p["customer_id"] == ""


def test_include_linked_reconsiders_everything():
    customers = [{"_id": "c1", "CustomerName": "Acme AS", "UniFiHostId": "h9"}]
    [p] = match_hosts_to_customers([_host("Acme-AS")], customers, include_linked=True)
    assert p["confidence"] == "high"


def test_a_blank_host_id_does_not_count_as_linked():
    customers = [{"_id": "c1", "CustomerName": "Acme AS", "UniFiHostId": "   "}]
    [p] = match_hosts_to_customers([_host("Acme-AS")], customers)
    assert p["confidence"] == "high"

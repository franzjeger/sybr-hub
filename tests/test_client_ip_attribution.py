"""Who a request is attributed to, when a proxy is in front of the process.

Two things read ``client_ip``: the rate limiter picks its bucket with it, and
the login log records it. Both are only as good as the answer, and the answer
is an attacker-supplied header unless the count from the right is exact — so
these tests pin the arithmetic rather than the shape of the code.

The deployment they describe is the shipped one: ``scripts/install-cachyos.sh``
runs ``tailscale serve --https 443 http://127.0.0.1:8099``, so every request
arrives from loopback and every request carries an X-Forwarded-For.
"""

from __future__ import annotations

import pytest
from starlette.datastructures import Headers

from app.web.transport import ENV_TRUSTED_PROXY_HOPS, client_ip


class _Request:
    """The three attributes ``client_ip`` reads, and nothing else."""

    def __init__(self, peer: str, forwarded: str | None = None):
        self.client = type("C", (), {"host": peer})() if peer else None
        self.headers = Headers({"x-forwarded-for": forwarded} if forwarded else {})


# The real client as the terminator appends it, behind whatever the caller
# chose to put in the header first.
SPOOFED = "203.0.113.66"
REAL = "100.64.0.9"


def test_a_spoofed_leading_entry_never_wins():
    """The regression. A terminator appends, so the client is on the right.

    Reading the left-hand entry let a caller pick its own rate-limit bucket by
    rotating the header, and write its own address into the login log.
    """
    request = _Request("127.0.0.1", f"{SPOOFED}, {REAL}")
    assert client_ip(request) == REAL


def test_a_rotating_header_cannot_split_the_rate_limit_bucket():
    keys = {
        client_ip(_Request("127.0.0.1", f"{spoof}, {REAL}"))
        for spoof in ("1.1.1.1", "2.2.2.2", "3.3.3.3")
    }
    assert keys == {REAL}, "each forged value bought its own bucket"


def test_a_terminator_that_replaces_the_header_still_resolves():
    """Not every proxy appends; a single-entry header is the client itself."""
    assert client_ip(_Request("127.0.0.1", REAL)) == REAL


def test_extra_trusted_hops_move_one_entry_further_left(monkeypatch):
    monkeypatch.setenv(ENV_TRUSTED_PROXY_HOPS, "1")
    request = _Request("127.0.0.1", f"{SPOOFED}, {REAL}, 10.0.0.2")
    assert client_ip(request) == REAL


@pytest.mark.parametrize("value", ["", "not-a-number", "-3"])
def test_a_broken_hop_count_falls_back_to_the_safe_default(monkeypatch, value):
    """Wrong configuration must not re-open the hole it was added to close."""
    monkeypatch.setenv(ENV_TRUSTED_PROXY_HOPS, value)
    assert client_ip(_Request("127.0.0.1", f"{SPOOFED}, {REAL}")) == REAL


def test_a_hop_count_longer_than_the_header_does_not_index_past_the_front(monkeypatch):
    monkeypatch.setenv(ENV_TRUSTED_PROXY_HOPS, "9")
    assert client_ip(_Request("127.0.0.1", f"{SPOOFED}, {REAL}")) == SPOOFED


def test_the_header_is_ignored_from_a_non_loopback_peer():
    """Nothing trustworthy wrote it, so the socket is the only fact available."""
    assert client_ip(_Request("198.51.100.7", f"{SPOOFED}, {REAL}")) == "198.51.100.7"


def test_no_header_means_the_direct_peer():
    assert client_ip(_Request("127.0.0.1")) == "127.0.0.1"


def test_a_blank_header_does_not_become_the_bucket_key():
    assert client_ip(_Request("127.0.0.1", " , ")) == "127.0.0.1"


def test_a_request_without_a_client_is_attributed_to_nothing_reusable():
    assert client_ip(_Request("", f"{SPOOFED}, {REAL}")) == ""

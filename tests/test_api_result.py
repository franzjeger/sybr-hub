"""The container that lets a failed read stop looking like an empty one.

``ApiList`` and ``ApiDict`` exist so the thirty-odd call sites that iterate,
``len``, index or ``.get`` a device-client result keep working unchanged, while
the handful that publish a customer-facing number can ask ``read_failed(x)`` and
say "unavailable" instead of "0". These pin both halves: the container is
transparent to the old consumers, and ``.error`` survives for the new ones.
"""

from __future__ import annotations

from app.modules.api_result import ApiDict, ApiList, read_error, read_failed

# ── It really is the empty value it replaces ─────────────────────────────────

def test_an_apilist_is_a_list():
    x = ApiList([1, 2, 3])
    assert isinstance(x, list)
    assert x == [1, 2, 3]
    assert len(x) == 3
    assert [n * 2 for n in x] == [2, 4, 6]
    assert x[0] == 1


def test_a_failed_apilist_is_empty_not_a_sentinel():
    """The bug this replaces: FortiGate's {"error":...} had len 1 and crashed
    iteration. An empty ApiList has len 0 and iterates to nothing."""
    x = ApiList(error="HTTP 403")
    assert isinstance(x, list)
    assert len(x) == 0
    assert list(x) == []
    assert [n for n in x] == []


def test_an_apidict_is_a_dict():
    x = ApiDict({"cpu": 12})
    assert isinstance(x, dict)
    assert x["cpu"] == 12
    assert x.get("cpu") == 12
    assert x.get("missing", "default") == "default"


def test_a_failed_apidict_returns_defaults_like_the_old_sentinel():
    """A consumer that only does .get(field, default) is unaffected — exactly
    the property that lets the fix be applied without touching every caller."""
    x = ApiDict(error="timeout")
    assert x.get("cpu", 0) == 0
    assert x.get("hostname", "") == ""
    assert "cpu" not in x


# ── The error survives ───────────────────────────────────────────────────────

def test_read_failed_distinguishes_refused_from_empty():
    assert read_failed(ApiList(error="refused")) is True
    assert read_failed(ApiList([])) is False
    assert read_failed(ApiDict(error="refused")) is True
    assert read_failed(ApiDict({})) is False


def test_read_failed_is_false_for_a_genuinely_empty_read():
    """The other half. A controller with no devices is not an error, and must
    not be flagged unavailable — that would be a refusal-is-not-a-zero bug in
    the opposite direction."""
    assert read_failed(ApiList([])) is False
    assert read_error(ApiList([])) is None


def test_read_failed_tolerates_plain_containers():
    """So a caller can guard a value whose origin it is unsure of."""
    assert read_failed([]) is False
    assert read_failed({}) is False
    assert read_failed(["a", "b"]) is False
    assert read_failed(None) is False


def test_read_error_returns_the_reason():
    assert read_error(ApiList(error="HTTP 403")) == "HTTP 403"
    assert read_error(ApiDict(error="timeout")) == "timeout"
    assert read_error(ApiList([1])) is None


def test_the_error_is_never_a_partial_result():
    """A half-read that looked whole would be a subtler version of the same
    lie. A failed container is always empty."""
    assert list(ApiList([1, 2, 3, 4]).__class__(error="x")) == []
    assert dict(ApiDict({"a": 1}).__class__(error="x")) == {}

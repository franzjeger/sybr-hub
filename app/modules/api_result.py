"""A read that failed is not an empty read.

Both device-audit clients — FortiGate and UniFi — sit at the far end of a VPN
tunnel to a customer site, and both used to answer a failed read with a sentinel
the caller could not tell apart from a genuine empty result. UniFi returned
``[]``; FortiGate returned ``{"error": ...}``. So a controller that answered 403
became "0 devices", a firewall the audit could not reach became "0 policies,
score 100", and a CIS check whose evidence could not be read was silently
skipped. The report said the network was clean because nobody could look.

This is the defect the architecture doc names — "a refusal is not a zero" — the
same one the M365 audit pipeline was rebuilt around. It lived on in the two
device clients because the fix there was per-section, and these clients feed
dozens of call sites.

The mechanism here is a container that *is* the empty value it replaces, so the
thirty-odd call sites that iterate it, ``len()`` it, or index it keep working
unchanged — but carries ``.error`` so the handful of sites that publish a number
a customer reads can ask "was this measured, or refused?" and say so.

    devices = await client.get_devices(site)   # ApiList, maybe empty
    if read_failed(devices):
        return _unavailable(devices.error)     # not "0 devices"
    ...

The container is empty on failure, never a partial result: a half-read that
looked like a whole one would be a subtler version of the same lie.
"""

from __future__ import annotations

from typing import Any


class ApiList(list):
    """A list that remembers whether the read that produced it failed.

    Subclasses ``list`` so every existing consumer — iteration, ``len``,
    indexing, ``isinstance(x, list)`` — behaves exactly as before. On a failed
    read it is empty and ``.error`` is the reason; on a good read ``.error`` is
    ``None`` and the contents are real.
    """

    error: str | None

    def __init__(self, iterable: Any = (), *, error: str | None = None) -> None:
        super().__init__(iterable)
        self.error = error

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        if self.error is not None:
            return f"ApiList(<unavailable: {self.error}>)"
        return f"ApiList({list(self)!r})"


class ApiDict(dict):
    """A dict counterpart, for the endpoints that return a single object.

    ``.get(...)`` on a failed read returns the caller's default, exactly as the
    old ``{"error": ...}`` sentinel did — so a consumer that only reads fields
    is unaffected — while ``.error`` lets a consumer that publishes the value
    distinguish "the field was absent" from "the object could not be read".
    """

    error: str | None

    def __init__(self, mapping: Any = None, *, error: str | None = None) -> None:
        super().__init__(mapping or {})
        self.error = error

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        if self.error is not None:
            return f"ApiDict(<unavailable: {self.error}>)"
        return f"ApiDict({dict(self)!r})"


def read_failed(value: Any) -> bool:
    """Whether *value* came from a read that failed.

    Tolerant of plain lists and dicts — anything without an ``error`` attribute
    is treated as a successful read — so a caller can guard a value whose origin
    it is not certain of without a type check first.
    """
    return getattr(value, "error", None) is not None


def read_error(value: Any) -> str | None:
    """The failure reason carried by *value*, or ``None`` if it read cleanly."""
    return getattr(value, "error", None)

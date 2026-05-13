"""RMM link-builder — STUB.

Workshop intent: don't reimplement remote control. The MSP already
pays for an RMM with WebRemote (Datto RMM, NinjaOne, Atera, etc.).
Sybr HUB just builds deep-links so technicians can jump from
"customer X has 3 non-compliant devices" → the RMM session in one
click.

This stub establishes the URL-builder interface. Concrete RMM
back-ends (datto, ninja, atera, …) implement ``build_webremote_url``.
"""

from __future__ import annotations

from typing import Protocol


class RMMProvider(Protocol):
    """Minimal interface a Sybr-HUB-compatible RMM driver must satisfy."""

    name: str
    """Human-readable RMM name shown in the UI (e.g. 'Datto RMM')."""

    def build_webremote_url(self, device_identifier: str) -> str:
        """Return a deep-link URL that opens a remote session to the
        given device. ``device_identifier`` is whatever the customer
        record uses to identify it (hostname / serial / UUID / RMM
        device-id) — drivers decide how to map.

        Drivers MUST NOT make a network call here — this is a pure
        URL builder. Drivers MUST raise ``ValueError`` if they can't
        produce a deterministic URL for the given identifier.
        """
        ...


def get_provider(name: str) -> RMMProvider:
    """Return the configured RMM provider driver by name. Raises
    KeyError if no driver matches."""
    raise NotImplementedError(
        "rmm.get_provider: implement when the first RMM driver lands. "
        "Workshop direction: start with Datto RMM (most common in our "
        "customer base) before adding others."
    )

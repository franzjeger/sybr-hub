"""Request models for the remote-session endpoints: the remote browser and RDP
over Guacamole.

The handlers keep every check that carries a message — the browser target
policy, "URL er påkrevd", the RDP port range, whose password may be sent — and
the models make sure what reaches those checks has the right shape.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class BrowserTarget(BaseModel):
    """Where the remote browser should go. Optional when starting a session."""

    model_config = ConfigDict(extra="forbid")

    url: str | None = None


class RdpStartRequest(BaseModel):
    """Open an RDP session through Guacamole to a registered host.

    The address always comes from the host record. A missing or zero port
    means 3389, as ``int(body.get("port") or 3389)`` did.
    """

    model_config = ConfigDict(extra="forbid")

    host_id: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None


class RdpClipboard(BaseModel):
    """Text to put on the RDP session's clipboard. Empty keeps its answer."""

    model_config = ConfigDict(extra="forbid")

    text: str = ""

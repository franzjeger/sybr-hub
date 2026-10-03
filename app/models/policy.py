"""Request models for the Conditional Access deploy, adoption and restore routes.

These routes write into a customer's Microsoft tenant. The handlers keep every
rail they had — the template renderer refusing unfilled placeholders, the
break-glass group check, the plan fingerprint, adoption validation against
both sides — and the models make sure what reaches those rails has the shape
they expect. Absent and null lists or maps mean empty, as ``body.get(k) or
[]`` did.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PolicyTemplateRequest(BaseModel):
    """A template and the values that fill its placeholders.

    A missing template keeps the handler's "No template named"; a missing
    value keeps the renderer's message naming the placeholder.
    """

    model_config = ConfigDict(extra="forbid")

    template: str = ""
    values: dict[str, str] | None = None


class PolicyPlanRequest(PolicyTemplateRequest):
    """…plus which of the template's policies (by displayName) to include, all
    when empty, and which live policies (by id) the plan may delete."""

    select: list[str] | None = None
    delete: list[str] | None = None


class PolicyApplyRequest(PolicyPlanRequest):
    """…plus the fingerprint of the plan that was reviewed."""

    fingerprint: str = ""


class PolicyEnableRequest(BaseModel):
    """One report-only policy, by id, to enforce."""

    model_config = ConfigDict(extra="forbid")

    policy_id: str = ""


class AdoptionSetRequest(PolicyTemplateRequest):
    """Which existing policy each policy of the standard takes over.

    ``{standard policy name: live policy id}``; an empty or null id means "not
    adopted" and is dropped, as before.
    """

    mapping: dict[str, str | None] | None = None


class RestorePlanRequest(BaseModel):
    """A restore source (``kind`` and ``ref`` from the sources list), and which
    policies created since then the plan may delete."""

    model_config = ConfigDict(extra="forbid")

    kind: str = ""
    ref: str = ""
    delete: list[str] | None = None


class RestoreApplyRequest(RestorePlanRequest):
    fingerprint: str = ""

"""Request models for the settings endpoints.

These routes read ``await request.json()`` and index straight into the result.
That is fine right up to the moment somebody sends a JSON list, at which point
``body.get(...)`` raises ``AttributeError`` and the caller gets an unexplained
500 — and, in the scheduler's case, the whole unvalidated body had already
been written into persisted settings on the way past.

The models below are deliberately narrow. ``extra="forbid"`` matters more than
the field types: the failure that motivated this was not a wrong value, it was
an arbitrary object being stored under a key the scheduler later reads.

Only the highest-risk bodies are modelled. There are around a hundred other
raw-JSON sites in the route layer, and converting them wholesale in one change
would be a large diff with no way to review the behaviour of any single
endpoint. These are the ones that persist what they are given.
"""

from __future__ import annotations

from typing import Union

from pydantic import BaseModel, ConfigDict, Field

# The alert thresholds use `False` to mean "this alert is off" and an integer
# to mean "alert past this value". That is the shape `core/scheduler.py`
# already reads, so the model describes it rather than tidying it into
# something the consumer would not understand.
Threshold = Union[bool, int]


class AlertOn(BaseModel):
    """Which scheduler outcomes raise a webhook alert."""

    model_config = ConfigDict(extra="forbid")

    audit_completed: bool = True
    risk_score_drop: Threshold = 5
    new_risky_users: bool = True
    expired_credentials: bool = True
    secure_score_drop: Threshold = 5
    new_nsg_warnings: bool = True
    mfa_below_threshold: Threshold = 80


class SchedulerConfig(BaseModel):
    """The scheduler block of app settings.

    Persisted verbatim, which is why ``extra="forbid"`` is here rather than
    ``ignore``: a typo'd key used to be stored forever and silently do nothing,
    and the operator's evidence that they had configured something was the key
    sitting in the settings file.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    interval_hours: int = Field(default=168, ge=1, le=8760)
    audit_all_customers: bool = True
    webhook_url: str = Field(default="", max_length=2048)
    alert_on: AlertOn = Field(default_factory=AlertOn)


class WebhookTest(BaseModel):
    """A single webhook URL to try."""

    model_config = ConfigDict(extra="forbid")

    webhook_url: str = Field(min_length=1, max_length=2048)


class TaskSchedule(BaseModel):
    """Schedule for one named background task."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    day: str | None = Field(default=None, max_length=16)
    interval_hours: int | None = Field(default=None, ge=1, le=8760)


class LanguageChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: str = Field(default="no", pattern=r"^(no|en)$")

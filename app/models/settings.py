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

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


_WEEKDAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_TASK_TYPES = ("daily", "weekly", "interval")


class TaskSchedule(BaseModel):
    """Schedule for one named background task.

    The scheduler reads `type` to decide whether to run daily, weekly, or on an
    interval; `day` names the weekday for a weekly task; `time` is HH:MM. An
    unvalidated `type`/`day` used to be accepted here and then quietly mis-fire
    in _compute_next_run — a "weekley" typo fell through to the daily branch and
    a bad weekday silently became Sunday (SR-004 config validation)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    type: str | None = None
    time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    day: str | None = None
    interval_hours: int | None = Field(default=None, ge=1, le=8760)

    @field_validator("type")
    @classmethod
    def _valid_type(cls, v: str | None) -> str | None:
        if v is None:
            return v
        low = v.strip().lower()
        if low not in _TASK_TYPES:
            raise ValueError(f"type must be one of {', '.join(_TASK_TYPES)}")
        return low

    @field_validator("day")
    @classmethod
    def _valid_day(cls, v: str | None) -> str | None:
        if v is None:
            return v
        low = v.strip().lower()
        if low not in _WEEKDAY_NAMES:
            raise ValueError("day must be a weekday name (monday..sunday)")
        return low


class LanguageChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: str = Field(default="no", pattern=r"^(no|en)$")


class CreateTicketRequest(BaseModel):
    """One audit finding, on its way to becoming one Autotask ticket.

    ``rec_id`` is in the body rather than the URL because it is built from a
    message key plus the params that identify the finding, and those params
    carry tenant data — a domain, an app registration's name. A path segment
    cannot safely hold one.

    ``title`` and ``queue_id`` are optional overrides for the modal: the
    operator may reword the summary before it lands in a customer's PSA, and
    may route it somewhere other than the configured default queue. Everything
    unset falls back to the finding and the settings.
    """

    model_config = ConfigDict(extra="forbid")

    rec_id: str = Field(min_length=1, max_length=512)
    title: str = Field(default="", max_length=255)
    notes: str = Field(default="", max_length=4000)
    # Autotask priority is a picklist; 1-4 covers a stock install and a wrong
    # number is a 400 from Autotask rather than a wrong ticket.
    priority: int | None = Field(default=None, ge=1, le=4)
    queue_id: int | None = Field(default=None, ge=1)


class CreateRecommendationRequest(BaseModel):
    """One audit finding, on its way to a myITprocess Recommendation.

    Same identity as the ticket request, and deliberately a separate model
    rather than a shared one with optional halves: the two systems take
    different things. Autotask wants a numeric queue and a 1-4 priority;
    myITprocess takes free-text category and priority whose vocabularies this
    codebase has not seen from a live instance, so they are strings with a
    length cap and nothing more specific pretended.
    """

    model_config = ConfigDict(extra="forbid")

    rec_id: str = Field(min_length=1, max_length=512)
    title: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=4000)
    category: str = Field(default="", max_length=100)
    priority: str = Field(default="", max_length=50)

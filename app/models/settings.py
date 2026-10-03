"""Request models for the settings endpoints.

These routes read ``await request.json()`` and index straight into the result.
That is fine right up to the moment somebody sends a JSON list, at which point
``body.get(...)`` raises ``AttributeError`` and the caller gets an unexplained
500 — and, in the scheduler's case, the whole unvalidated body had already
been written into persisted settings on the way past.

The models below are deliberately narrow. ``extra="forbid"`` matters more than
the field types: the failure that motivated this was not a wrong value, it was
an arbitrary object being stored under a key the scheduler later reads.

The scheduler models came first because they persist what they are given. The
rest of the settings router followed, one model per body, with the defaults
the handlers used to pass to ``body.get`` kept as the field defaults so a body
the front-end sends behaves exactly as before.
"""

from __future__ import annotations

from typing import Any, Literal, Union

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
    # Read by audit_scheduler._maybe_create_backup and sent by the Settings
    # form's scheduler block. It was missing here, so with extra="forbid" that
    # form's whole scheduler save was refused with a 422.
    backup_after_audit: bool = False
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


class FindingStatusRequest(BaseModel):
    """What a technician decided about one finding on the customer page."""

    model_config = ConfigDict(extra="forbid")

    rec_id: str = Field(min_length=1, max_length=512)
    status: Literal["open", "in_progress", "done", "ignored"]
    notes: str = Field(default="", max_length=4000)


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


# ── POST /api/settings ───────────────────────────────────────────────────────

# Autotask's ticket defaults arrive as whatever the form field held: a number,
# the text of one, an empty string meaning "clear it", or null. The handler
# turns them into an int and answers a bad one with a message naming the field,
# so the model admits those shapes and leaves the numeric check where the
# message is.
_PicklistValue = Union[int, str, None]


class SettingsUpdate(BaseModel):
    """The app-wide settings form, and every integration card that saves into it.

    A field a card did not send is left alone; the handler reads
    ``model_fields_set`` for that. Only a field sent empty resets its setting.
    (An absent ``audit_dir`` or ``smtp_server`` used to reset it too, so saving
    one integration card cleared another's settings.)
    """

    model_config = ConfigDict(extra="forbid")

    audit_dir: str = ""
    cert_dir: str = ""
    branding: dict[str, Any] | None = None

    itglue_api_key: str = ""
    itglue_region: str = ""
    unifi_site_manager_api_key: str = ""
    unifi_controller_host: str = ""
    unifi_controller_username: str = ""
    unifi_controller_password: str = ""
    also_username: str = ""
    also_password: str = ""
    also_country: str = ""
    autotask_integration_code: str = ""
    autotask_username: str = ""
    autotask_secret: str = ""
    autotask_zone_url: str = ""
    autotask_default_queue_id: _PicklistValue = None
    autotask_default_priority: _PicklistValue = None
    autotask_default_status: _PicklistValue = None
    myitprocess_api_key: str = ""
    myitprocess_base_url: str = ""
    tailscale_api_key: str = ""
    tailscale_tailnet: str = ""
    uniweb_email: str = ""
    uniweb_password: str = ""

    smtp_server: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    email_default_recipient: str = ""
    email_auto_send: bool = False

    # The ALSO and Tailscale cards save by sending the whole GET /api/settings
    # response back with their own fields changed, so every read-only key that
    # response carries arrives too. They are named here, accepted and dropped,
    # rather than ignoring every unknown key — that keeps a misspelt writable
    # key a 422 instead of a setting that silently never saves.
    audit_dir_default: Any = None
    audit_dir_custom: Any = None
    cert_dir_default: Any = None
    cert_dir_custom: Any = None
    itglue_api_key_set: Any = None
    smtp_password_set: Any = None
    unifi_site_manager_api_key_set: Any = None
    fortigate_configured: Any = None
    also_password_set: Any = None
    autotask_integration_code_set: Any = None
    autotask_secret_set: Any = None
    myitprocess_api_key_set: Any = None
    tailscale_api_key_set: Any = None
    uniweb_password_set: Any = None
    gdap_configured: Any = None
    gdap_validated: Any = None
    gdap_validated_at: Any = None
    gdap_validation_error: Any = None
    gdap_partner_tenant_id: Any = None
    gdap_client_id: Any = None
    gdap_client_secret_set: Any = None
    gdap_app_display_name: Any = None
    gdap_setup_date: Any = None
    gdap_last_customer_sync: Any = None
    gdap_customer_count: Any = None


class EncryptionKeyRestore(BaseModel):
    """A master key pasted back from a backup.

    Empty is allowed through so the handler can answer it with its own
    translated message rather than a field error.
    """

    model_config = ConfigDict(extra="forbid")

    key: str = ""


class AlertRuleUpdate(BaseModel):
    """One automatic-alert rule.

    Only the keys sent are applied (``model_dump(exclude_unset=True)``), so the
    defaults below are never written; they exist to make each key optional
    without making it nullable.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    days: int = 0
    threshold: int = 0
    alert_on_changed: bool = False


class AlertConfigUpdate(BaseModel):
    """The automatic-alert settings. Absent keys keep their stored value.

    Same rule as ``AlertRuleUpdate``: only what was sent is applied. The
    notification view's rule switch sends ``rules`` alone, taken from the GET
    response, so every rule name the server knows can arrive; a name it does
    not know is skipped by the handler, as before.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    notify_teams: bool = False
    notify_email: bool = False
    email_recipient: str = ""
    rules: dict[str, AlertRuleUpdate] = Field(default_factory=dict)

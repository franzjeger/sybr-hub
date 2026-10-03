"""Request models for the report, report-archive and e-mail endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EmailTestRequest(BaseModel):
    """SMTP settings from the form, tried without saving them.

    The handler passes the keys that were sent on as the SMTP config, as it
    always did, so ``model_dump(exclude_unset=True)`` is what it reads.
    """

    model_config = ConfigDict(extra="forbid")

    to: str = ""
    smtp_server: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""


class EmailReportRequest(BaseModel):
    """Where to send the selected audit's report; empty means the default."""

    model_config = ConfigDict(extra="forbid")

    to: str = ""


class ReportGenerateRequest(BaseModel):
    """Which report to render from the selected audit run.

    The values are the ones the report screen offers and the generator
    understands; anything else used to reach the generator unchecked.
    """

    model_config = ConfigDict(extra="forbid")

    format: Literal["html", "pdf"] = "html"
    report_type: Literal["tech", "customer"] = "tech"
    lang: Literal["no", "en"] = "no"
    frameworks: Literal["cis", "cis+nist", "cis+iso", "all"] = "all"
    theme: Literal["light", "dark"] = "light"


class ReportArchiveDelete(BaseModel):
    """A run directory, relative to the audit directory. Empty keeps its message."""

    model_config = ConfigDict(extra="forbid")

    path: str = ""


class ReportArchiveCleanup(BaseModel):
    """Delete every run older than this many months.

    At least one: zero or a negative number put the cutoff at or after today,
    which deleted every report there was. The archive view offers 3, 6 and 12.
    """

    model_config = ConfigDict(extra="forbid")

    months: int = Field(default=6, ge=1)


class BatchSummaryRequest(BaseModel):
    """Customers to include in the QBR summary; empty means all with metrics."""

    model_config = ConfigDict(extra="forbid")

    customer_ids: list[str] = []

"""Request models for the AI console endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    message: str = Field(min_length=1, max_length=16000)
    conversation_id: str | None = Field(default=None, max_length=128)
    customer_id: str | None = Field(default=None, max_length=255)
    focus: str = Field(default="general", max_length=100)
    external_processing_consent: bool = False


class ActionDecision(BaseModel):
    approve: bool


class ClaudeSettings(BaseModel):
    """The AI console's mode, model and (in API mode) key.

    The settings card sends all three; in CLI mode the key field is empty and
    is not read. A missing key in API mode keeps the handler's message.
    """

    model_config = ConfigDict(extra="forbid")

    mode: Literal["api", "cli"] = "api"
    model: str = ""
    api_key: str = ""

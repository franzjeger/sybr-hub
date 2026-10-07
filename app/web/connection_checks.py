"""Record connection-test evidence without mistaking an unsaved draft for stored credentials."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from pydantic import BaseModel

from app.core import config
from app.core.integration_health import DEFAULTS, record_check

P = ParamSpec("P")
R = TypeVar("R")
log = logging.getLogger(__name__)
_test_settings: ContextVar[dict[str, Any] | None] = ContextVar(
    "connection_test_settings", default=None
)


def connection_settings() -> dict[str, Any]:
    """The exact stored snapshot used by this check; ordinary reads remain fresh."""
    snapshot = _test_settings.get()
    return snapshot if snapshot is not None else config.load_app_settings()


def connection_check(
    provider: str, fields: dict[str, str]
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    def decorate(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        signature = inspect.signature(fn, eval_str=True)

        @wraps(fn)
        async def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            saved = config.load_app_settings()
            body = signature.bind(*args, **kwargs).arguments.get("body")
            sent = body.model_dump() if isinstance(body, BaseModel) else {}
            if provider == "autotask" and not all(
                sent.get(k) for k in ("integration_code", "username", "secret")
            ):
                sent = {}
            if provider == "myitprocess" and not sent.get("api_key"):
                sent = {}
            if (
                provider == "myitprocess"
                and sent.get("api_key") == "••••••"
                and isinstance(body, BaseModel)
                and "base_url" not in body.model_fields_set
            ):
                sent["base_url"] = saved.get("myitprocess_base_url", "")
            if provider == "itglue" and isinstance(body, BaseModel):
                sent["api_key"] = str(sent.get("api_key", "")).strip()
                if sent["api_key"] in ("", "••••••") and "region" not in body.model_fields_set:
                    sent["region"] = saved.get("itglue_region", "eu")
            matches = all(
                sent.get(field) is None
                or sent.get(field) == "••••••"
                or (field == "api_key" and sent.get(field) == "")
                or sent[field] == saved.get(key, DEFAULTS.get(key, ""))
                for field, key in fields.items()
            )

            def record(ok: bool) -> None:
                if matches:
                    try:
                        record_check(provider, saved, ok)
                    except Exception:
                        # Persistence failure cannot turn a successful vendor check into an error.
                        log.exception("Could not persist %s connection check", provider)

            token = _test_settings.set(saved)
            try:
                try:
                    result = await fn(*args, **kwargs)
                except Exception:
                    record(False)
                    raise
            finally:
                _test_settings.reset(token)
            record(isinstance(result, dict) and result.get("ok") is True)
            return result

        # FastAPI must resolve annotations in the endpoint's own module.
        wrapped.__signature__ = signature  # type: ignore[attr-defined]  # FastAPI inspects this function attribute.
        return wrapped

    return decorate

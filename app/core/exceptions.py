"""Structured exceptions for MSP Toolkit.

Raise these from route handlers and services instead of returning
{"error": str(e)} dicts.  The global exception handler in server.py
converts them to consistent JSON responses.
"""

from __future__ import annotations


class ToolkitError(Exception):
    """Base for all application errors.  Subclass this, never raise it directly."""
    status_code: int = 500
    error_type: str = "internal_error"

    def __init__(self, message: str = "Internal server error", *, detail: str | None = None):
        self.message = message
        self.detail = detail
        super().__init__(message)

    def to_dict(self) -> dict:
        d: dict = {"ok": False, "error": self.message, "error_type": self.error_type}
        if self.detail:
            d["detail"] = self.detail
        return d


class ValidationError(ToolkitError):
    """Bad input from the client (missing field, wrong type, etc.)."""
    status_code = 400
    error_type = "validation_error"

    def __init__(self, message: str = "Invalid request", *, detail: str | None = None):
        super().__init__(message, detail=detail)


class NotFoundError(ToolkitError):
    """Requested resource doesn't exist."""
    status_code = 404
    error_type = "not_found"

    def __init__(self, message: str = "Not found", *, detail: str | None = None):
        super().__init__(message, detail=detail)


class AuthError(ToolkitError):
    """Authentication / authorization failure."""
    status_code = 401
    error_type = "auth_error"

    def __init__(self, message: str = "Unauthorized", *, detail: str | None = None):
        super().__init__(message, detail=detail)


class IntegrationError(ToolkitError):
    """Upstream service failure (FortiGate API down, UniFi unreachable, etc.)."""
    status_code = 502
    error_type = "integration_error"

    def __init__(self, message: str = "Integration error", *, detail: str | None = None):
        super().__init__(message, detail=detail)


class ConflictError(ToolkitError):
    """Resource already exists or state conflict."""
    status_code = 409
    error_type = "conflict"

    def __init__(self, message: str = "Conflict", *, detail: str | None = None):
        super().__init__(message, detail=detail)

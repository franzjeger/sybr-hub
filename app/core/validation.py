"""Input validators for values that reach a shell, a device CLI, or a path.

Everything here raises :class:`~app.core.exceptions.ValidationError` on bad
input, so route handlers get a 400 instead of passing attacker-controlled
text into a config file, a FortiOS CLI session, or a filesystem path.

These are deliberately strict allowlists. The values they guard (connection
names, admin usernames, VDOMs, access profiles) all come from small, known
character sets in practice — rejecting anything unusual costs nothing and
closes the injection surface entirely.
"""

from __future__ import annotations

import ipaddress
import re

from app.core.exceptions import ValidationError

# Conservative identifier: starts alphanumeric, then alphanumerics plus
# `_`, `-`, `.`. No whitespace, quotes, braces, newlines, or path separators.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

# Hostname or IP literal. Permits IPv6 in brackets and dotted/colon forms.
_HOST_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._:\[\]-]*[A-Za-z0-9\]])?$")

# An OpenSSH public key line: "<type> <base64> [comment]".
_SSH_KEY_RE = re.compile(
    r"^(ssh-(?:rsa|dss|ed25519)|ecdsa-sha2-nistp(?:256|384|521)|"
    r"sk-(?:ssh-ed25519|ecdsa-sha2-nistp256)@openssh\.com)\s+"
    r"[A-Za-z0-9+/]+={0,3}(?:\s+[^\r\n]*)?$"
)


def validate_identifier(value: str, field: str, max_length: int = 64) -> str:
    """Return *value* if it is a safe bare identifier, else raise.

    Used for anything interpolated into a device CLI command, a config-file
    key, or a filename component.
    """
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{field} er påkrevd")
    if len(value) > max_length:
        raise ValidationError(f"{field} kan ikke være lengre enn {max_length} tegn")
    if not _IDENTIFIER_RE.match(value):
        raise ValidationError(
            f"Ugyldig {field}: kun bokstaver, tall, '.', '_' og '-' er tillatt"
        )
    return value


def validate_host(value: str, field: str = "host", max_length: int = 255) -> str:
    """Return *value* if it is a plausible hostname or IP literal, else raise."""
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{field} er påkrevd")
    if len(value) > max_length:
        raise ValidationError(f"{field} kan ikke være lengre enn {max_length} tegn")
    if not _HOST_RE.match(value):
        raise ValidationError(f"Ugyldig {field}: '{value}' er ikke et gyldig vertsnavn eller IP")
    return value


def validate_host_list(value: str, field: str = "host") -> str:
    """Validate a comma-separated list of hosts (swanctl ``remote_addrs``)."""
    parts = [p.strip() for p in value.split(",") if p.strip()]
    if not parts:
        raise ValidationError(f"{field} er påkrevd")
    for part in parts:
        validate_host(part, field)
    return ",".join(parts)


def validate_cidr(value: str, field: str = "subnet") -> str:
    """Return the normalised CIDR/IP, or raise if it doesn't parse."""
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} er påkrevd")
    text = value.strip()
    try:
        if "/" in text:
            return str(ipaddress.ip_network(text, strict=False))
        return str(ipaddress.ip_address(text))
    except ValueError as e:
        raise ValidationError(f"Ugyldig {field}: {e}") from e


def validate_cidr_list(value: str, field: str = "subnets", separator: str = ",") -> list[str]:
    """Validate a separator-delimited list of CIDRs. Returns the parsed list.

    Accepts both ``,`` and whitespace as separators, since FortiOS trust-host
    lists use spaces and swanctl traffic selectors use commas.
    """
    if not isinstance(value, str):
        raise ValidationError(f"{field} er påkrevd")
    raw = value.replace(separator, " ").split()
    if not raw:
        raise ValidationError(f"{field} er påkrevd")
    return [validate_cidr(item, field) for item in raw]


def validate_ssh_public_key(value: str, field: str = "public_key") -> str:
    """Return *value* if it looks like a single OpenSSH public key line."""
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} er påkrevd")
    text = value.strip()
    if "\n" in text or "\r" in text:
        raise ValidationError(f"{field} må være én enkelt linje")
    if len(text) > 8192:
        raise ValidationError(f"{field} er for lang")
    if not _SSH_KEY_RE.match(text):
        raise ValidationError(f"Ugyldig {field}: forventet en OpenSSH public key")
    return text


def quote_conf_value(value: str, field: str) -> str:
    """Escape *value* for use inside a double-quoted config string.

    Rejects control characters outright — there is no legitimate reason for a
    PSK or password to contain a newline, and allowing one would let a value
    close its quote and open a new config directive.
    """
    if not isinstance(value, str):
        raise ValidationError(f"{field} må være tekst")
    if any(ch in value for ch in ("\n", "\r", "\x00")):
        raise ValidationError(f"{field} kan ikke inneholde linjeskift")
    return value.replace("\\", "\\\\").replace('"', '\\"')

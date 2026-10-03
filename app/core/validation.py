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

import base64
import ipaddress
import re
import unicodedata

from app.core.exceptions import ValidationError
from app.core.messages import invalid as _invalid

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
        raise _invalid("err_field_required", field=field)
    if len(value) > max_length:
        raise _invalid("err_field_too_long_n", field=field, max_length=max_length)
    if not _IDENTIFIER_RE.fullmatch(value):
        raise _invalid("err_field_identifier", field=field)
    return value


def validate_host(value: str, field: str = "host", max_length: int = 255) -> str:
    """Return *value* if it is a plausible hostname or IP literal, else raise."""
    if not isinstance(value, str) or not value:
        raise _invalid("err_field_required", field=field)
    if len(value) > max_length:
        raise _invalid("err_field_too_long_n", field=field, max_length=max_length)
    if not _HOST_RE.fullmatch(value):
        raise _invalid("err_field_not_host", field=field, text=value)
    return value


def validate_host_list(value: str, field: str = "host") -> str:
    """Validate a comma-separated list of hosts (swanctl ``remote_addrs``)."""
    parts = [p.strip() for p in value.split(",") if p.strip()]
    if not parts:
        raise _invalid("err_field_required", field=field)
    for part in parts:
        validate_host(part, field)
    return ",".join(parts)


def validate_cidr(value: str, field: str = "subnet") -> str:
    """Return the normalised CIDR/IP, or raise if it doesn't parse."""
    if not isinstance(value, str) or not value.strip():
        raise _invalid("err_field_required", field=field)
    text = value.strip()
    # ipaddress accepts an IPv6 scope id ("fe80::1%eth0") holding any text,
    # newlines included, and echoes it back in str().
    if "%" in text or any(ch.isspace() or ord(ch) < 0x20 for ch in text):
        raise _invalid("err_field_not_address", field=field, text=text)
    try:
        if "/" in text:
            return str(ipaddress.ip_network(text, strict=False))
        return str(ipaddress.ip_address(text))
    except ValueError as e:
        raise _invalid("err_field_unparsable", field=field, reason=str(e)) from e


def validate_cidr_list(value: str, field: str = "subnets", separator: str = ",") -> list[str]:
    """Validate a separator-delimited list of CIDRs. Returns the parsed list.

    Accepts both ``,`` and whitespace as separators, since FortiOS trust-host
    lists use spaces and swanctl traffic selectors use commas.
    """
    if not isinstance(value, str):
        raise _invalid("err_field_required", field=field)
    raw = value.replace(separator, " ").split()
    if not raw:
        raise _invalid("err_field_required", field=field)
    return [validate_cidr(item, field) for item in raw]


def validate_ssh_public_key(value: str, field: str = "public_key") -> str:
    """Return *value* if it looks like a single OpenSSH public key line."""
    if not isinstance(value, str) or not value.strip():
        raise _invalid("err_field_required", field=field)
    text = value.strip()
    if "\n" in text or "\r" in text:
        raise _invalid("err_field_single_line", field=field)
    if len(text) > 8192:
        raise _invalid("err_field_too_long", field=field)
    if not _SSH_KEY_RE.match(text):
        raise _invalid("err_field_ssh_key", field=field)
    return text


def quote_conf_value(value: str, field: str) -> str:
    """Escape *value* for use inside a double-quoted config string.

    Rejects control characters outright — there is no legitimate reason for a
    PSK or password to contain a newline, and allowing one would let a value
    close its quote and open a new config directive.
    """
    if not isinstance(value, str):
        raise _invalid("err_field_not_text", field=field)
    if any(ch in value for ch in ("\n", "\r", "\x00")):
        raise _invalid("err_field_line_breaks", field=field)
    return value.replace("\\", "\\\\").replace('"', '\\"')


# ── VPN profile values ───────────────────────────────────────────────────────
#
# These reach configuration files a VPN client parses line by line. wg-quick
# runs PreUp/PostUp hooks through a shell, so a single newline in any stored
# field is command execution on the host. Every validator rejects line breaks
# before anything else and returns the normalised value the caller must use.

_LINE_BREAKS = ("\r", "\n", "\x00")

# One DNS label: alphanumerics and inner hyphens, at most 63 characters.
_HOSTNAME_LABEL_RE = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)$")

# A WireGuard key is 32 bytes of standard base64: 43 characters and one '='.
# The last character before the padding carries only four bits, so it is one
# of sixteen values; anything else is not a key wg would accept.
_WG_KEY_RE = re.compile(r"^[A-Za-z0-9+/]{42}[AEIMQUYcgkosw048]=$")

_PEM_CERT_RE = re.compile(
    r"-----BEGIN CERTIFICATE-----\n((?:[A-Za-z0-9+/=]{1,76}\n)+)-----END CERTIFICATE-----"
)


def reject_line_breaks(value: str, field: str) -> str:
    """Return *value* if it is text without CR, LF or NUL, else raise."""
    if not isinstance(value, str):
        raise _invalid("err_field_not_text", field=field)
    if any(ch in value for ch in _LINE_BREAKS):
        raise _invalid("err_field_line_breaks", field=field)
    return value


def validate_int_range(value: int | str, field: str, minimum: int, maximum: int) -> int:
    """Return *value* as an int within [minimum, maximum], else raise."""
    if isinstance(value, bool):
        raise _invalid("err_field_not_integer", field=field)
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and re.fullmatch(r"[0-9]{1,10}", value):
        number = int(value)
    else:
        raise _invalid("err_field_not_integer", field=field)
    if not minimum <= number <= maximum:
        raise _invalid("err_field_range", field=field, minimum=minimum, maximum=maximum)
    return number


def validate_port(value: int | str, field: str = "port") -> int:
    return validate_int_range(value, field, 1, 65535)


def validate_ip(value: str, field: str = "ip") -> str:
    """Return the normalised IP literal (no scope id), else raise."""
    text = reject_line_breaks(value, field).strip()
    if not text:
        raise _invalid("err_field_required", field=field)
    if "%" in text:
        raise _invalid("err_field_not_ip", field=field, text=text)
    try:
        return str(ipaddress.ip_address(text))
    except ValueError as e:
        raise _invalid("err_field_not_ip", field=field, text=text) from e


def validate_ip_interface(value: str, field: str = "address") -> str:
    """Return an interface address with prefix ("10.0.0.2/24"), else raise.

    Unlike validate_cidr this keeps the host bits: an interface address is not
    a network.
    """
    text = reject_line_breaks(value, field).strip()
    if not text:
        raise _invalid("err_field_required", field=field)
    if "%" in text:
        raise _invalid("err_field_not_address", field=field, text=text)
    try:
        return str(ipaddress.ip_interface(text))
    except ValueError as e:
        raise _invalid("err_field_unparsable", field=field, reason=str(e)) from e


def validate_hostname(value: str, field: str = "host") -> str:
    """Return *value* if it is a DNS name or an IP literal, else raise.

    Stricter than validate_host: no brackets, colons or underscores, and every
    label is checked, so the value is safe as a bare token in a config line.
    """
    text = reject_line_breaks(value, field).strip()
    if not text:
        raise _invalid("err_field_required", field=field)
    try:
        return validate_ip(text, field)
    except ValidationError:
        pass
    name = text[:-1] if text.endswith(".") else text
    if len(name) > 253 or not all(_HOSTNAME_LABEL_RE.fullmatch(lbl) for lbl in name.split(".")):
        raise _invalid("err_field_not_host", field=field, text=text)
    return text


def validate_wireguard_key(value: str, field: str = "key") -> str:
    """Return *value* if it is a base64 WireGuard key (44 characters), else raise."""
    text = reject_line_breaks(value, field)
    if not _WG_KEY_RE.fullmatch(text):
        raise _invalid("err_field_wg_key", field=field)
    return text


def validate_wireguard_endpoint(value: str, field: str = "endpoint") -> str:
    """Return a normalised ``host:port`` or ``[v6]:port``, else raise."""
    text = reject_line_breaks(value, field).strip()
    if not text:
        raise _invalid("err_field_required", field=field)
    if text.startswith("["):
        match = re.fullmatch(r"\[([^\]]+)\]:([0-9]{1,5})", text)
        if not match:
            raise _invalid("err_field_endpoint_v6", field=field)
        host = validate_ip(match.group(1), field)
        if ":" not in host:
            raise _invalid("err_field_brackets", field=field)
        return f"[{host}]:{validate_port(match.group(2), field)}"
    host, sep, port = text.rpartition(":")
    if not sep or not host or ":" in host:
        raise _invalid("err_field_endpoint", field=field)
    return f"{validate_hostname(host, field)}:{validate_port(port, field)}"


def validate_pem_certificates(value: str, field: str = "certificate") -> str:
    """Return one or more PEM certificates, normalised to LF, else raise.

    Only BEGIN/END CERTIFICATE blocks of base64 are accepted. Anything around
    or between them could close the surrounding inline block in an OpenVPN
    config and open a directive of its own.
    """
    if not isinstance(value, str):
        raise _invalid("err_field_not_text", field=field)
    if "\x00" in value:
        raise _invalid("err_field_nul", field=field)
    lines = (line.strip() for line in value.replace("\r\n", "\n").split("\n"))
    text = "\n".join(line for line in lines if line)
    blocks = list(_PEM_CERT_RE.finditer(text))
    rebuilt = "\n".join(m.group(0) for m in blocks)
    if not blocks or rebuilt != text:
        raise _invalid("err_field_pem", field=field)
    for match in blocks:
        try:
            base64.b64decode(match.group(1).replace("\n", ""), validate=True)
        except ValueError as e:
            raise _invalid("err_field_pem_base64", field=field) from e
    return text


# ── End of VPN profile values ────────────────────────────────────────────────


# ── SSH/RDP host records ─────────────────────────────────────────────────────
# Fields of a stored SSH/RDP host. They end up in a generated ~/.ssh/config, in
# xfreerdp arguments and in a .rdp file, all of which are line-oriented: one
# embedded newline is a new directive.

# Unicode categories that are never text a person means to type: controls,
# format characters (bidi overrides, zero-width), surrogates, private use,
# unassigned, and the line/paragraph separators.
_NON_PRINTING_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})

# Letters in any script, digits, and `. _ - @ \ $`: POSIX accounts,
# DOMAIN\user, UPNs and machine accounts. Inner spaces are allowed because
# Windows accounts sometimes have them.
_LOGIN_NAME_RE = re.compile(r"^[\w.@\\$-](?:[\w .@\\$-]*[\w.@\\$-])?$")


def validate_display_text(
    value: str, field: str, *, max_length: int, multiline: bool = False
) -> str:
    """Return *value* if it contains only printable characters, else raise.

    For free text such as a label, group or note. Any script is fine; control
    and format characters are not. ``multiline`` lets newline and tab through
    for fields that really are multi-line, such as notes.
    """
    if not isinstance(value, str):
        raise _invalid("err_field_not_text", field=field)
    if len(value) > max_length:
        raise _invalid("err_field_too_long_n", field=field, max_length=max_length)
    allowed = "\n\r\t" if multiline else ""
    for ch in value:
        if ch not in allowed and unicodedata.category(ch) in _NON_PRINTING_CATEGORIES:
            raise _invalid("err_field_bad_chars", field=field)
    return value


def validate_login_name(value: str, field: str = "username", max_length: int = 128) -> str:
    """Return *value* if it is a plausible SSH/RDP login name, else raise."""
    if not isinstance(value, str) or not value:
        raise _invalid("err_field_required", field=field)
    if len(value) > max_length:
        raise _invalid("err_field_too_long_n", field=field, max_length=max_length)
    if not _LOGIN_NAME_RE.fullmatch(value):
        raise _invalid("err_field_login_name", field=field)
    return value


# ── end SSH/RDP host records ─────────────────────────────────────────────────

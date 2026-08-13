"""Take secrets out of text that is about to be logged or returned.

The rule this exists to enforce: a secret must not be masked *on the branch
somebody remembered*. The FortiGate bootstrap masked its generated API key
before logging it, and then, in the branch where the key could not be parsed,
returned the same terminal output verbatim as ``raw_output``. That branch runs
exactly when the key did not look the way the parser expected — which is the
one case where a key is most likely to still be sitting in the text.

So the masking here is deliberately *not* driven by knowing where the secret
is. Two passes:

**Known strings.** Anything the caller can name — a password it just
generated, a token it just parsed — is replaced wherever it appears. This is
the exact pass and it runs first.

**Shape.** A long unbroken run of secret-shaped characters is replaced too.
This is a heuristic and it will sometimes hit something that is not a secret:
a certificate fingerprint, a long hostname, a base64 blob. That trade is
deliberate. Over-redacting a diagnostic string costs a support round-trip;
under-redacting one puts a live credential in a log file that gets attached to
a ticket.

Not a substitute for not collecting the secret in the first place. Prefer
never putting it in the string.
"""

from __future__ import annotations

import re

MASK = "***REDACTED***"

# 24 or more characters from the alphabet API tokens are drawn from, not broken
# by anything a sentence would contain. FortiOS API keys, Graph client secrets
# and IT Glue keys all sit comfortably above this; a long English word or a
# dotted hostname does not reach it, because `.` and ` ` terminate the run.
#
# `/` and `+` are deliberately *not* in the class, though standard base64 uses
# both. With `/` included, `/home/user/sybr-hub/app/web/` is one 28-character
# run and every file path in a traceback disappears — redaction that destroys
# the diagnostics is redaction somebody switches off. The cost is small: the
# secrets this codebase actually handles are alphanumeric (FortiOS, IT Glue),
# `A-Za-z0-9~._-` (Graph client secrets) or urlsafe base64 (the master key
# backups, JWTs), none of which contain `/`.
#
# Padding is included so a wrapped key is caught whole rather than leaving its
# tail behind.
_SECRET_SHAPED = re.compile(r"[A-Za-z0-9_-]{24,}={0,2}")

# The minimum length worth masking exactly. Below this, a "secret" is either
# absent or so short that replacing every occurrence would shred the text
# around it — an empty factory password being the case that matters, since
# replacing "" would mask between every character.
_MIN_EXACT = 6


def redact(text: str, *known: str | None) -> str:
    """Return *text* with *known* secrets and secret-shaped runs replaced.

    ``known`` may contain None and empty strings so callers can pass optional
    values straight through without guarding each one.
    """
    if not text:
        return text
    out = text
    for secret in known:
        if secret and len(secret) >= _MIN_EXACT:
            out = out.replace(secret, MASK)
    return _SECRET_SHAPED.sub(MASK, out)


def redact_mapping(data: dict, *known: str | None) -> dict:
    """Redact every string value in a flat mapping.

    Used for the diagnostic dicts these device flows return, where the caller
    wants the structure preserved and only the values scrubbed.
    """
    return {
        k: redact(v, *known) if isinstance(v, str) else v
        for k, v in data.items()
    }

"""A bearer token shaped like one a real login issues.

A login creates a session and, having just checked the password, counts as a
step-up for five minutes. Tests that exercise backups, user management or the
encryption key through a token need the same, or the step-up guard answers 403
before the code under test runs.
"""

from __future__ import annotations

import uuid

from app.core import mfa
from app.core.auth import create_access_token, create_refresh_token, create_session


async def signed_in_token(user) -> str:
    session_id = str(uuid.uuid4())
    access = await create_access_token(user, session_id=session_id)
    await create_session(
        user.id, await create_refresh_token(user, session_id), session_id=session_id
    )
    await mfa.mark_recent(session_id)
    return access

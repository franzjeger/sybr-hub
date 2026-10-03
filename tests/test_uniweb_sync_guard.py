"""The Uniweb sync is single-flight, enforced inside _run_sync itself.

The HTTP route checks _sync_status['running'] for a friendly message, but the
scheduled task (scheduler._do_uniweb_sync) calls _run_sync directly and used to
skip the check — so a manual sync running when the 02:00 tick fired started a
second concurrent scrape, spinning up a second headless Chromium and racing on
uniweb_accounts, with whichever finished first clearing `running` while the other
was mid-flight. The guard now lives in _run_sync, so neither path can bypass it.
"""

from __future__ import annotations

from app.web.routes import uniweb as uw


async def test_run_sync_skips_when_a_sync_is_already_running():
    prev = dict(uw._sync_status)
    uw._sync_status["running"] = True
    # Sentinels the normal path would overwrite (it resets accounts_synced to 0
    # and stamps a fresh sync_start_time before doing any work).
    uw._sync_status["accounts_synced"] = 42
    uw._sync_status["sync_start_time"] = "SENTINEL"
    try:
        await uw._run_sync("api@example.com", "pw")
        # Guard returned before the reset block: nothing was touched.
        assert uw._sync_status["accounts_synced"] == 42
        assert uw._sync_status["sync_start_time"] == "SENTINEL"
        assert uw._sync_status["running"] is True
    finally:
        uw._sync_status.clear()
        uw._sync_status.update(prev)

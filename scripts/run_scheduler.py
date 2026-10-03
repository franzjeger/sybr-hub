#!/usr/bin/env python3
"""Optional standby for the Sybr HUB schedule.

The web process (main.py) runs scheduled jobs itself, and nothing else is
needed. This process only matters when the web process is down: it waits on
the same schedule lock (app/services/schedule_owner.py) and takes over while
the lock is free, so jobs keep running across a web restart and never run
twice.
"""

import asyncio
import logging
import os
import signal
import sys

logging.basicConfig(
    level=os.environ.get("SYBR_HUB_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)-8s scheduler | %(name)s | %(message)s",
)
log = logging.getLogger("scheduler.main")


async def main() -> None:
    from app.core.database import close_pool, run_migrations
    from app.core.encryption import verify_master_key_available
    from app.core.system_user import ensure
    from app.services import schedule_owner
    from app.web.routes.frontend import install_log_capture

    install_log_capture()
    verify_master_key_available()
    # Migrations before anything reads a table — this process may start first.
    await run_migrations()
    from app.core import modules

    await modules.initialize()
    await ensure()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    try:
        if await schedule_owner.wait_and_start(stop):
            await stop.wait()
    finally:
        await schedule_owner.stop()
        await close_pool()
        log.info("Scheduler standby stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log.critical("Scheduler crashed: %s", e, exc_info=True)
        sys.exit(1)

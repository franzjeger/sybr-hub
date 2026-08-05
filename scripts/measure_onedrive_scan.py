#!/usr/bin/env python3
"""Measure what the OneDrive sharing scan actually costs against a real tenant.

The three budgets in ``OneDriveSharingSection`` — depth, folders per drive, and
total Graph requests — are currently chosen numbers, not measured ones. No test
can settle them: what they need to be depends on how many site collections and
OneDrives a tenant has and how deep its folder trees run, and on how Microsoft
throttles that particular tenant on that particular day.

This script answers that with one run. It scans with the limits lifted, so it
reports what the tenant *needs* rather than what the current cap allows, and
then says what the defaults would have covered.

    # Cheap: enumerate sites and users only, project the cost, touch no files.
    python scripts/measure_onedrive_scan.py --estimate

    # The real measurement.
    python scripts/measure_onedrive_scan.py

    # Same, but bounded if you would rather not let it run unchecked.
    python scripts/measure_onedrive_scan.py --max-requests 5000

Run it on the machine that holds the customer's credentials, against a tenant
whose owner is content for it to be scanned. It reads only permissions and
folder listings and writes its output under a temporary directory, but it is
still a scan of somebody's files.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# auth.py defines its own AuthError rather than reusing app.core.exceptions —
# catch the one it actually raises.
from app.modules.m365_audit.auth import AuthError, AuthManager
from app.modules.m365_audit.graph_client import GraphClient
from app.modules.m365_audit.sections.onedrive_sharing import (
    OneDriveSharingSection,
)


class CountingGraph:
    """Wraps GraphClient and records what the scan actually asked for.

    Counting inside the section would only count what the section thinks it
    spent. This counts what left the machine, which is the number that matters
    for throttling — including the pages ``get_all`` fetches behind one call.
    """

    def __init__(self, inner: GraphClient):
        self._inner = inner
        self.calls: Counter[str] = Counter()
        self.durations: list[float] = []
        self.errors: Counter[str] = Counter()
        self.slowest: tuple[float, str] = (0.0, "")

    @staticmethod
    def _bucket(path: str) -> str:
        """Group a path by shape so the report reads by phase, not by id."""
        if path == "sites":
            return "site enumeration"
        if path.startswith("sites/") and path.endswith("/drives"):
            return "drives per site"
        if path.startswith("users/") and path.endswith("/drive"):
            return "OneDrive per user"
        if path.endswith("/root/permissions"):
            return "drive root permissions"
        if "/items/" in path and path.endswith("/children"):
            return "folder listing (+permissions)"
        return path

    async def _timed(self, method: str, path: str, **kw):
        bucket = self._bucket(path)
        self.calls[bucket] += 1
        started = time.monotonic()
        try:
            return await getattr(self._inner, method)(path, **kw)
        except Exception as ex:
            self.errors[f"{bucket}: {type(ex).__name__}"] += 1
            raise
        finally:
            elapsed = time.monotonic() - started
            self.durations.append(elapsed)
            if elapsed > self.slowest[0]:
                self.slowest = (elapsed, path)

    async def get(self, path: str, **kw):
        return await self._timed("get", path, **kw)

    async def get_all(self, path: str, **kw):
        return await self._timed("get_all", path, **kw)

    @property
    def total(self) -> int:
        return sum(self.calls.values())


async def _run(args) -> int:
    auth = AuthManager.from_config()
    print(f"Tenant   : {auth.org_domain} ({auth.tenant_id})")

    async with auth as a, GraphClient(a.credential) as raw:
        graph = CountingGraph(raw)

        print("Fetching the user directory (needed to reach each OneDrive)...")
        users = await raw.get_all(
            "users", params={"$select": "id,userPrincipalName", "$top": "999"}
        )
        print(f"           {len(users)} users")

        out_dir = Path(tempfile.mkdtemp(prefix="onedrive-measure-"))
        section = OneDriveSharingSection(
            out_dir, graph, users_ref=users,
            max_depth=args.max_depth,
            max_folders_per_drive=args.max_folders,
            max_requests=args.max_requests,
        )

        if args.estimate:
            print("\nEstimate mode: discovering drives only, not walking them.\n")
            started = time.monotonic()
            drives = await section._discover_drives()
            wall = time.monotonic() - started
            _report_estimate(graph, drives, wall, args)
            return 0

        print(f"\nScanning with depth={args.max_depth}, "
              f"folders/drive={args.max_folders}, budget={args.max_requests}.")
        print("This talks to the tenant. Ctrl-C to stop.\n")
        started = time.monotonic()
        await section.collect()
        wall = time.monotonic() - started

    _report(graph, section, wall, out_dir, args)
    return 0


def _report_estimate(graph, drives, wall, args) -> None:
    print(f"Drives found      : {len(drives)}")
    print(f"Requests to find  : {graph.total}")
    print(f"Wall clock        : {wall:.1f}s")
    print()
    # A drive costs 1 request for its root permissions plus one per folder
    # opened, so the floor is one per drive and the ceiling is the folder cap.
    floor = graph.total + len(drives)
    ceiling = graph.total + len(drives) * (1 + args.max_folders)
    print(f"Full scan would cost between {floor} and {ceiling} requests")
    print("  (floor  = discovery + one root-permissions call per drive)")
    print(f"  (ceiling = every drive hitting the {args.max_folders}-folder cap)")
    print()
    print("Run without --estimate for the real figure; the ceiling is almost")
    print("always far above what a real tenant costs.")


def _report(graph, section, wall, out_dir, args) -> None:
    print("=" * 70)
    print("  MEASUREMENT")
    print("=" * 70)
    print(f"  Wall clock            : {wall:.1f}s")
    print(f"  Graph requests        : {graph.total}")
    if graph.durations:
        avg = sum(graph.durations) / len(graph.durations)
        print(f"  Mean request          : {avg * 1000:.0f}ms")
        print(f"  Slowest               : {graph.slowest[0] * 1000:.0f}ms  "
              f"({graph.slowest[1][:60]})")
    print()
    print("  By phase:")
    for bucket, n in graph.calls.most_common():
        print(f"    {bucket:<32} {n:>6}")
    if graph.errors:
        print()
        print("  Refusals and errors (expected for drives we may not read):")
        for kind, n in graph.errors.most_common():
            print(f"    {kind:<52} {n:>4}")
    print()
    print("  Coverage the section reported:")
    print(f"    drives seen                      {section._drives_seen:>6}")
    print(f"    drives refused                   {section._drives_refused:>6}")
    print(f"    folders examined                 {section._folders_visited:>6}")
    print(f"    items examined                   {section._items_examined:>6}")
    if section._truncated:
        print()
        print("  !! The scan hit a limit. The numbers above are a floor, not the")
        print("     requirement — raise the limit and run again for the real one:")
        for note in dict.fromkeys(section._truncated):
            print(f"       {note}")

    print()
    print("=" * 70)
    print("  SUGGESTED BUDGETS")
    print("=" * 70)
    if section._truncated:
        print("  Inconclusive: the scan was cut short, so its cost is unknown.")
        print("  Re-run with a higher --max-requests / --max-folders / --max-depth.")
    else:
        # Headroom because tenants grow and folder trees are not static. 2x is
        # the usual rule of thumb for a cap you do not want to hit by accident.
        suggested = max(500, int(graph.total * 2))
        print(f"  _MAX_REQUESTS         = {suggested}"
              f"   (2x the {graph.total} this tenant needed)")
        print(f"  _MAX_DEPTH            = {args.max_depth}"
              f"   (unchanged — nothing was cut off at this depth)")
        print(f"  _MAX_FOLDERS_PER_DRIVE= {args.max_folders}"
              f"   (unchanged — no drive reached the cap)")
        print()
        default = OneDriveSharingSection._MAX_REQUESTS
        if graph.total <= default:
            print(f"  The shipped default of {default} would have covered this tenant"
                  f" ({graph.total} used, {default - graph.total} spare).")
        else:
            print(f"  !! The shipped default of {default} would NOT have covered this")
            print(f"     tenant: it needed {graph.total}. Raise it before shipping.")
    print()
    print(f"  Output written to {out_dir}")
    print("  Delete it when you are done — it describes a customer's sharing.")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--estimate", action="store_true",
                   help="discover drives and project the cost; do not walk them")
    p.add_argument("--max-requests", type=int, default=100_000,
                   help="request ceiling (default: effectively unbounded, so the "
                        "run measures the requirement rather than the cap)")
    p.add_argument("--max-depth", type=int, default=OneDriveSharingSection._MAX_DEPTH)
    p.add_argument("--max-folders", type=int,
                   default=OneDriveSharingSection._MAX_FOLDERS_PER_DRIVE)
    args = p.parse_args()

    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        return 130
    except AuthError as e:
        # The common case by far: run from a machine or container that has no
        # customer configured. Say so plainly rather than with a traceback.
        print(f"\nCannot reach a tenant: {e}", file=sys.stderr)
        print("\nThis needs the machine that holds the customer's credentials —",
              file=sys.stderr)
        print("a configured customer and a reachable graph.microsoft.com.",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

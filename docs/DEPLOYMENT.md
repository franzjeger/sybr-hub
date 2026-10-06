# Supported release workflow

The production dependency lock supports Python 3.12–3.14 on Linux. CI installs
and tests the same hash-verified lockfile on every version in that range.
`requirements.txt` declares runtime ranges; `requirements.lock` records the resolved production versions and hashes.
`requirements-dev.txt` adds test/build tools. The experimental TUI is an optional
`.[tui]` install and has its own `sybr-hub-tui` entrypoint.

## Build before touching the running service

1. Use a clean checkout of an exact reviewed commit. Run Python tests, browser
   tests, type checking, dependency audits and the lint budget. See CONTRIBUTING.
2. Build a wheel with `python -m build --wheel`. Verify it with
   `python scripts/check_wheel.py dist/*.whl` and install it in a fresh environment
   using `pip install --require-hashes -r requirements.lock`, then install the
   wheel with `--no-deps`. Preserve the wheel, lockfile and their SHA-256 hashes.
3. For Linux amd64 containers, build the checked-in Dockerfile:

   ```bash
   python -m pip install setuptools-scm==9.2.2
   docker build --build-arg SOURCE_REVISION="$(git rev-parse HEAD)" \
     --build-arg RELEASE_VERSION="$(python -m setuptools_scm)" --tag sybr-hub:reviewed .
   ```

   Use an actual release version when a release is tagged. The GitHub repository
   previously had no release tags; do not infer deployed source from a `v1.1.8`
   label. The image records its source revision. Pin its resulting digest in the
   deployment inventory. The base image and PowerShell archive are pinned; OS
   packages still come from Debian repositories at build time, so retain the
   built image for exact rollback rather than assuming a later rebuild is byte-identical.

The image contains PowerShell and Chromium. Microsoft modules, external VPN
backends, Guacamole and provider credentials remain deployment prerequisites for
the features that use them. The default container grants no host networking
privileges; do not add broad privileges to make a particular VPN backend work.
The container build and provider flows must pass in the deployment environment
before this replaces the older homelab container branch.

## Cutover and rollback

1. Prepare an independent wrapping secret of at least 32 random bytes, outside
   the data volume. Preserve it separately with an exported master key and a
   tested recovery copy. `SYBR_KEY_WRAP_SECRET_FILE` points to that file.
   For Compose bind-mounted secrets, the file must be readable by UID 10001;
   Compose implementations may ignore requested secret uid/mode settings.
2. Complete active audits, setup, policy changes and external ticket operations.
   Stop the old service and take a cold backup of **all** its directories and DB,
   not just its source tree. A DB rollback must be paired with the matching data
   and encryption key. Reconcile uncertain ticket writes before retrying them.
3. Test a restore into an isolated copy first. Do not connect that copy to
   scheduled provider writes. Back up the original data volume before migrations.
4. Set `SYBR_IMAGE` to the tested image and `SYBR_WRAP_SECRET_FILE` to the separate
   secret. `docker compose up -d` starts it with a persistent data volume. The
   provided port binding exposes only host loopback. Configure a trusted TLS
   reverse proxy before remote use; do not expose the container's internal
   cleartext port directly or join untrusted containers to its network.
5. Verify `/api/health` (web/DB liveness), `/api/ready` (DB, which process owns
   the schedule and whether its enabled jobs are alive), login, customer scope, MFA, a read-only collection and a backup
   round-trip. `/api/system/health` gives administrators component diagnostics.
6. If verification fails, stop the new process and restore the old image **and
   matching cold data backup**. Reconcile external side effects separately;
   switching images cannot undo changes already accepted by a provider.

Keep one worker per installation. File operations and AI conversation state
are process-local; multi-worker deployment is unsupported. The web process runs
scheduled jobs itself; `scripts/sybr-hub-scheduler.service` is an optional
standby that takes over only while the web service is down.

The former in-app updater is intentionally disabled: it modified dependencies
in the live interpreter, and a git reset could not undo those changes. The Arch
installer is now for initial installations only and refuses an existing checkout.

## Identity and recovery

Enable local MFA through the avatar menu. Enrollment requires the current
password and confirmation from an authenticator app. Save the displayed recovery
codes separately. Each code is single-use; TOTP steps cannot be replayed. Five
failed attempts temporarily lock MFA verification. A correct password alone
cannot disable an enrolled factor.

Set `SYBR_REQUIRE_MFA=1` to require enrollment for technicians and administrators.
An unenrolled account can still reach its own enrollment screens, but cannot
use customer features. Verify emergency recovery before enforcing this policy.
Use a protected individual emergency administrator with separately stored MFA
recovery codes. Entra/OIDC is not implemented by this change.

For enrolled accounts, key export/import, backup changes, user privilege changes
and terminal handshakes require verification within five minutes. Use
**MFA / verify login** in the avatar menu when prompted. Already-open sockets are
closed when their account, session or customer permissions are revoked.

## CI account prerequisite

The audit found GitHub Actions jobs blocked before they started by account
billing/spending settings. Code changes cannot resolve that condition. Restore
runner availability, execute every job on the release commit and configure
required checks using a plan/ruleset the repository supports. Local checks do
not establish that the hosted matrix or image job has passed.

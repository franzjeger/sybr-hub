# October audit fixes

The October 5 review targets `main` at `203546c`. The remote was fetched before
implementation; that was still its latest commit on October 6. These changes
address GR2-01 through GR2-37. They do not claim to close the separate backlog.

| Finding | Result |
|---|---|
| 01 | Customer listings use an explicit allowlist; device passwords, future secret fields and server paths cannot enter the response. |
| 02 | Report generation defaults to read-only metrics. Web, scheduled, bulk and terminal audit completion persist the measurements. |
| 03 | All three controller paths use `model`, including fixtures with boolean `model_in_lts`. |
| 04 | Current metrics use the same measured-value guard as persistence. Unknown values stay absent from trends and are marked in completion messages. |
| 05 | Default branding preserves theme colours. Custom accents require 4.5:1 contrast against the active card background; button text is checked separately. |
| 06 | Canonical backup paths require technician access, including through `/audit_data`; config listings omit absolute paths. |
| 07 | Scheduler reads return only `webhook_url_set`, including for administrators. Masked form values preserve the saved webhook and still allow testing it. |
| 08 | Installing SSH keys and generating firewall tokens require admin. Activities record the target, outcome and key fingerprint. Technicians cannot bootstrap over a saved admin password. |
| 09 | UniFi paths use `customer_dir_name`; customer imports reject path separators and `..`. |
| 10 | All four Azure collectors propagate failed reads to FAILED. Azure sections, which do not contribute to the risk score, do not create score gaps. |
| 11 | Excel export handles missing percentages and marks them in the selected language. |
| 12 | Scheduled audits wait cancellably for manual audits. Failed or skipped cycle results trigger a webhook. |
| 13 | A forwarding-read error creates an explicit data-quality gap in the risk assessment. |
| 14 | Upgrade instructions explain backup and migration across rewritten history. Obsolete self-update instructions and service comments are removed. |
| 15 | The standby scheduler service has its source import path and bounded restart policy. |
| 16 | Python 3.12 is the production floor. CI installs the hashed runtime lock before development tools and constrains their dependency resolution. |
| 17 | Declared dependency floors include the patched PyJWT and urllib3 versions. Weekly CI scans and npm/Docker Dependabot updates are configured. GitHub vulnerability alerts were enabled. |
| 18 | Confirmations start on Cancel, trap Tab, close on Escape and restore focus. Export controls, archive headers and grade filters are buttons. |
| 19 | Mobile network headers wrap as a row; titles retain their width. Archive tables scroll instead of breaking every heading. |
| 20 | Severity labels and grade tiles use their contrast tokens; legacy grade rules do not override tiles. Hero grades use colours suitable for white text. |
| 21 | Archive deletion accepts only a canonical customer/run directory. Root, customer-only and parent paths are rejected. |
| 22 | Subnet size is checked before enumerating hosts. |
| 23 | Tailscale assignments check ownership from both manual mappings and customer tags, and fail closed if that check cannot run. |
| 24 | Server and browser CSV exports neutralise formula prefixes in text, including imported names, domains, tags and notes. Numeric values remain numeric. |
| 25 | The AI console supplies `customer_id` when backing up a FortiGate. |
| 26 | Bulk audit summaries read grade and score from the nested risk result without inventing zero scores. |
| 27 | Scheduled cycles invoke customer-site collection before auditing. |
| 28 | Report templates no longer request Google Fonts. |
| 29 | CI and documented Docker builds pass the Git-derived release version into the image. |
| 30 | Remaining browser-native confirmations use the shared confirmation dialog. |
| 31 | Firewall activities have translated names and resolve customer IDs for display and filtering. |
| 32 | Undefined colour tokens are replaced with existing design tokens. |
| 33 | Architecture checks include modules and relative imports. The segmentation tester uses the service layer. |
| 34 | Lint budgeting ignores `noqa` suppression. Playwright forbids focused tests in CI. Newly exposed lint findings are corrected. |
| 35 | The missing blame-ignore commit and obsolete repository/privacy/history references are corrected. |
| 36 | Calendar schedules use the configured `timezone` (default Europe/Oslo), including daylight-saving offsets. Interval schedules retain UTC elapsed time. |
| 37 | Initial HTML language reads the same `ui_lang` key as the application. |

Regression coverage is in `tests/test_october_audit_regressions.py`,
`tests/test_firmware_inventory.py`, `tests/test_tailscale_customers.py`,
the scheduler tests and `tests/browser/october-audit.spec.cjs`. Existing
browser tests continue checking navigation, report controls and both themes.
Repeated browser runs also exposed a scope-loading race: customer changes
now invalidate stale responses and clear the old chooser immediately.
Branding requests likewise discard older responses, and theme tokens take
effect immediately while settings are fetched. A browser test deliberately
delays the older response to verify that it cannot overwrite the newer one.

Local verification on October 6, using macOS and Python 3.14:

- The full Python suite completed successfully. One orphan process-group test
  is Linux-only; the terminal pipe test now also runs on macOS.
- The complete Chromium suite passed three consecutive runs, including both
  themes, mobile layouts, keyboard controls and delayed branding responses.
- JavaScript checks, formatting, lint budgeting, type checking and architecture
  checks passed. The architecture gate also rejected deliberately introduced
  absolute and relative HTTP imports in disposable directories.
- The wheel built and passed asset inspection. A fresh environment installed
  the hash-verified runtime lock and the wheel, then passed authentication,
  database, readiness, static-file and native PDF smoke checks.
- Python, npm and vendored dependency scans found no known vulnerabilities;
  vendored hashes matched the recorded manifest.

These checks use synthetic provider responses. They do not replace a live
tenant or appliance check. Docker is unavailable in the local macOS environment;
the deployment image, Linux process-group behaviour and Python 3.12/3.13 runs
are verified by the Linux CI jobs instead. Require these jobs to pass before
deployment. No deployment was made during local verification.
Follow `docs/UPGRADING.md` before updating an installation with the old history.

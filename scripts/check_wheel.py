"""Verify installed assets and entrypoints, not just successful wheel creation."""

import sys
import zipfile
from pathlib import Path


def check(path: Path) -> None:
    with zipfile.ZipFile(path) as wheel:
        names = wheel.namelist()
        required = {
            "main.py",
            "app/web/static/index.html",
            "app/web/static/app.js",
            "app/web/static/ui_i18n.json",
            "app/web/static/vendor/purify.min.js",
            "app/web/static/vendor/cairo-latin.woff2",
            "app/web/static/branding/300 x 86.png",
            "app/web/static/branding/SYBR_3.png",
            "app/web/static/branding/sybr_logo_dark_matched.png",
            "app/web/static/branding/sybr_logo_transparent.png",
            "app/core/_version.py",
            "app/core/mfa.py",
            "app/modules/m365_audit/app_setup.py",
            "app/modules/m365_audit/throttling.py",
            "app/services/notification_text.py",
            "app/policy_catalog/library.json",
            "app/core/policy_library.py",
            "app/core/policy_evidence.py",
            "app/core/integration_health.py",
            "app/web/connection_checks.py",
            "app/web/static/app-forms.js",
            "app/web/static/app-navigation.js",
            "app/web/static/app-audit-presentation.js",
            "app/web/static/app-shell-status.js",
        }
        missing = required - set(names)
        if missing:
            raise SystemExit(f"Missing packaged files: {sorted(missing)}")
        if not any(n.startswith("app/reports/templates/") for n in names):
            raise SystemExit("Report templates are absent")
        entrypoints = next(n for n in names if n.endswith(".dist-info/entry_points.txt"))
        if "sybr-hub = main:run" not in wheel.read(entrypoints).decode():
            raise SystemExit("Web entrypoint is absent")
    print(f"Wheel assets verified: {path.name}")


if __name__ == "__main__":
    for argument in sys.argv[1:]:
        check(Path(argument))

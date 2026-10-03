"""Exercise the installed service with synthetic data in a disposable container.

Requires an empty /var/lib/sybr tmpfs, no network and a separate test wrapping
secret. This is deliberately not a probe that can target a running installation.
"""

import asyncio
import json
import os
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path


def main():
    root = Path("/var/lib/sybr")
    if os.getuid() != 10001 or not root.is_dir() or list(root.iterdir()):
        raise SystemExit("Use the unprivileged image with an EMPTY disposable /var/lib/sybr tmpfs")
    if os.environ.get("SYBR_REQUIRE_MFA") != "1":
        raise SystemExit("The smoke test must exercise enforced MFA")

    import httpx

    from app.core import mfa
    from app.core.database import close_all_pools, init_db

    # The default schedule stays on: /api/ready must pass with it, because
    # that is what a fresh container runs.
    async def seed():
        try:
            await init_db()
        finally:
            await close_all_pools()

    asyncio.run(seed())
    password = "Synthetic-Container-Test123!"
    process = None
    with tempfile.TemporaryFile(mode="w+") as log:

        def start():
            child = subprocess.Popen(["sybr-hub"], stdout=log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 30
            while child.poll() is None and time.monotonic() < deadline:
                try:
                    if httpx.get("http://127.0.0.1:8099/api/ready", timeout=1).status_code == 200:
                        return child
                except httpx.RequestError:
                    pass
                time.sleep(0.1)
            child.terminate()
            child.wait(timeout=15)
            raise AssertionError("Installed service did not become ready")

        try:
            process = start()
            with httpx.Client(base_url="http://127.0.0.1:8099", timeout=30) as client:

                def post(path, body):
                    response = client.post("/api/" + path, json=body)
                    assert response.status_code == 200, (path, response.status_code, response.text)
                    return response.json()

                post(
                    "auth/setup",
                    {
                        "username": "container-smoke",
                        "password": password,
                        "display_name": "Synthetic Smoke",
                    },
                )
                assert client.get("/api/customers").status_code == 403
                secret = post("auth/mfa/enroll", {"password": password})["secret"]
                recovery = post(
                    "auth/mfa/confirm",
                    {
                        "password": password,
                        "otp": mfa.totp(secret, int(time.time() // 30)),
                    },
                )["recovery_codes"]
                assert len(recovery) == 10
                subprocess.run(
                    [
                        "python",
                        "/opt/sybr-ops/grant_write.py",
                        "--user",
                        "container-smoke",
                        "--write",
                    ],
                    check=True,
                    timeout=20,
                    capture_output=True,
                )
                customer = post(
                    "customers/add-manual",
                    {
                        "name": "Synthetic Container Customer",
                        "contact_email": "synthetic@example.invalid",
                    },
                )["customer_id"]
                archive = post(
                    "backup/create",
                    {
                        "dest_path": str(root / "backups"),
                        "backup_password": password,
                    },
                )["path"]
                with zipfile.ZipFile(archive) as backup:
                    manifest = json.loads(backup.read("manifest.json"))
                    assert manifest["format"] == 3
                    assert b"SQLite format 3" not in backup.read("database/msp_toolkit.db")
                    assert b"container-smoke" not in backup.read("activity_log.jsonl")
                assert post("customers/delete", {"customer_id": customer})["archived"]
                restored = post(
                    "backup/restore", {"zip_path": archive, "backup_password": password}
                )
                assert restored["restored_files"]["database"]
                customers = client.get("/api/customers").json()["customers"]
                assert any(c["_id"] == customer for c in customers)
                assert client.get("/api/ready").status_code == 200
                post("auth/logout", {})
                credentials = {"username": "container-smoke", "password": password}
                assert client.post("/api/auth/login", json=credentials).status_code == 401
                post("auth/login", {**credentials, "otp": recovery[0]})
                assert client.get("/api/auth/me").status_code == 200
                process.terminate()
                process.wait(timeout=20)
                process = start()
                assert client.get("/api/auth/me").status_code == 200
                assert client.get("/static/app.js").status_code == 200

            from weasyprint import HTML

            assert HTML(string="<p>Container PDF smoke</p>").write_pdf().startswith(b"%PDF")
            subprocess.run(
                [
                    "pwsh",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "$PSVersionTable.PSVersion.ToString()",
                ],
                check=True,
                capture_output=True,
                timeout=20,
            )
            browser = subprocess.run(
                [
                    "chromium",
                    "--headless",
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--dump-dom",
                    "data:text/html,<p>synthetic-browser-smoke</p>",
                ],
                capture_output=True,
                text=True,
                timeout=20,
                check=True,
            )
            assert "synthetic-browser-smoke" in browser.stdout
            print(
                "PASS: non-root read-only startup, readiness, enforced MFA, customer archive, "
                "encrypted backup/restore, recovery login, restart, static assets, PDF, PowerShell and Chromium"
            )
        except BaseException:
            log.seek(0)
            print(log.read())
            raise
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait(timeout=20)


if __name__ == "__main__":
    main()

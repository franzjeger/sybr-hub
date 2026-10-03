"""Smoke-test an installed wheel in disposable directories, without providers.

Run with the clean environment's Python, from outside the source checkout.
"""

import asyncio
import os
import re
import sys
import tempfile
from pathlib import Path


def main():
    with tempfile.TemporaryDirectory(prefix="sybr-installed-smoke-") as directory:
        root = Path(directory)
        os.environ.update(
            {
                "MSP_DATA_DIR": str(root / "data"),
                "MSP_CONFIG_DIR": str(root / "config"),
                "MSP_AUDIT_DIR": str(root / "audits"),
                "SYBR_KEY_WRAP_SECRET": "isolated-wheel-smoke-independent-secret",
                "SYBR_REQUIRE_MFA": "0",
            }
        )
        os.environ.pop("SYBR_KEY_WRAP_SECRET_FILE", None)
        import keyring

        import app

        if not Path(app.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()):
            raise SystemExit("Smoke test must import the installed package, not the checkout")
        keyring.get_password = lambda *args: None
        keyring.set_password = lambda *args: None
        from app.core import encryption

        encryption._backup_locations = lambda: [root / "key.backup"]

        async def check():
            import httpx

            from app.core.database import close_pool, init_db
            from app.web.server import create_app

            await init_db()
            try:
                # Run the real lifespan with the default schedule left on:
                # /api/ready has to pass the way a fresh install starts.
                app_ = create_app()
                transport = httpx.ASGITransport(app=app_)
                async with (
                    app_.router.lifespan_context(app_),
                    httpx.AsyncClient(
                        transport=transport, base_url="https://wheel.invalid"
                    ) as client,
                ):
                    assert (await client.get("/api/health")).status_code == 200
                    assert (await client.get("/api/ready")).status_code == 200
                    setup = await client.post(
                        "/api/auth/setup",
                        json={
                            "username": "wheel-smoke",
                            "password": "Wheel-Smoke123!",
                            "display_name": "Disposable smoke account",
                        },
                    )
                    assert setup.status_code == 200, setup.text
                    assert (await client.get("/api/auth/me")).status_code == 200
                    shell = await client.get("/")
                    assert shell.status_code == 200
                    # A source checkout used to serve logos that the wheel omitted.
                    # Exercise every logo used by the installed login/header/footer.
                    logos = set(re.findall(r'src="(/branding/[^"]+)"', shell.text))
                    assert logos, "The shell must include its branding images"
                    for url in sorted(logos):
                        logo = await client.get(url)
                        assert logo.status_code == 200, (url, logo.status_code)
                        assert logo.headers["content-type"] == "image/png", url
                        assert logo.content.startswith(b"\x89PNG\r\n\x1a\n"), url
                    script = await client.get("/static/app.js")
                    assert (
                        script.status_code == 200 and "function registerUiHandlers" in script.text
                    )
            finally:
                await close_pool()

        asyncio.run(check())
        from weasyprint import HTML

        assert HTML(string="<p>Installed Sybr HUB PDF smoke</p>").write_pdf().startswith(b"%PDF")
        print(
            f"Installed wheel: auth, database, readiness, static assets, logos and native PDF passed ({app.__file__})"
        )


if __name__ == "__main__":
    main()

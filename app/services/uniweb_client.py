"""Uniweb Tornado Kontrollpanel scraper.

Scrapes customer data from uniweb.no using pychrome (CDP) for read-only
integration. Uses headless Chromium to handle JSF/PrimeFaces.

**This has no API contract.** Uniweb can change its markup without notice and
without a version number, so every selector here is a guess that was true
once. Two consequences shape the code below.

A parse that finds nothing must not answer "nothing is there". Every reader
here used to `return []` on any failure, which turned "the page changed" into
"this customer has no domains" — and a technician acting on that would be
acting on a scrape that never ran. The readers raise UniwebScrapeError now,
and the callers report it as a failure rather than an empty result.

Worse than an exception is a parse that half-works. Partner accounts are
recognised by a JSF component id, and JSF renumbers those whenever a
component is added earlier in the page. If that id changes, no account looks
like a partner, the sub-customers underneath are never visited, and
list_accounts returns a shorter list with no error at all. That one cannot be
detected from the page alone, so it is surfaced instead: the result carries
how many partner rows were recognised, and zero of them on a partner account
is the thing to go and check.
"""

from __future__ import annotations

import json
import logging
import os
import random
import shutil
import subprocess
import time
from typing import Optional

import pychrome

logger = logging.getLogger(__name__)


class UniwebScrapeError(Exception):
    """The page did not look like the one this scraper parses.

    Its own type so a caller cannot mistake it for an empty result — that
    mistake is the reason it exists.
    """

LOGIN_URL = "https://uniweb.no/controlpanel/login/"
PRINCIPAL_URL = "https://uniweb.no/controlpanel/principal/?showExpanded=true"
BASE_URL = "https://uniweb.no/controlpanel"
PAGE_LOAD_WAIT = 2

# A JSF-generated component id. JSF renumbers these when a component is added
# earlier in the page, and nothing announces it — see the module docstring.
_PARTNER_BUTTON_MARKER = "j_idt87"


class UniwebClient:
    """Headless Chromium CDP client for Uniweb scraping (read-only)."""

    def __init__(self):
        self._port: int = 0
        self._process: Optional[subprocess.Popen] = None
        self._browser: Optional[pychrome.Browser] = None
        self._tab: Optional[pychrome.Tab] = None
        self._logged_in = False

    # ── Chromium management ─────────────────────────────────────────────────

    def _start_chromium(self) -> int:
        self._port = random.randint(19000, 19999)
        chrome_bin = (
            shutil.which("chromium")
            or shutil.which("chromium-browser")
            or shutil.which("google-chrome")
            or "/snap/bin/chromium"
        )
        self._process = subprocess.Popen(
            [chrome_bin, "--headless=new", "--no-sandbox", "--disable-gpu",
             "--disable-dev-shm-usage", f"--remote-debugging-port={self._port}",
             "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for attempt in range(20):
            time.sleep(0.5)
            try:
                self._browser = pychrome.Browser(url=f"http://127.0.0.1:{self._port}")
                self._browser.version()
                logger.info("Chromium CDP ready on port %d", self._port)
                return self._port
            except Exception:
                continue
        raise RuntimeError(f"Chromium failed to start on port {self._port}")

    def _open_tab(self):
        self._tab = self._browser.new_tab()
        self._tab.start()
        self._tab.Page.enable()

    def _nav(self, url: str, wait: float = PAGE_LOAD_WAIT):
        logger.debug("Navigating to %s", url)
        self._tab.Page.navigate(url=url)
        # Wait for page load via DOM ready check, fall back to fixed wait
        deadline = time.monotonic() + wait + 3
        time.sleep(0.5)
        while time.monotonic() < deadline:
            state = self._js("document.readyState")
            if state == "complete":
                time.sleep(0.3)  # brief settle for JS frameworks
                return
            time.sleep(0.3)

    def _js(self, expression: str):
        """Run JS and return value."""
        try:
            r = self._tab.Runtime.evaluate(expression=expression)
            if "result" in r and "value" in r["result"]:
                return r["result"]["value"]
        except Exception as e:
            logger.debug("JS eval error: %s", e)
        return None

    def close(self):
        try:
            if self._tab:
                self._tab.stop()
        except Exception:
            pass
        try:
            if self._process:
                self._process.terminate()
                self._process.wait(timeout=5)
        except Exception:
            try:
                self._process.kill()
            except Exception:
                pass
        logger.info("Chromium process terminated")

    # ── Login ───────────────────────────────────────────────────────────────

    def login(self, email: str, password: str) -> bool:
        try:
            self._start_chromium()
            self._open_tab()
        except Exception as e:
            logger.error("Failed to start Chromium: %s", e)
            return False

        try:
            self._nav(LOGIN_URL, wait=4)

            result = self._js(f"""
            (function() {{
                var e = document.getElementById('loginForm:email');
                var p = document.getElementById('loginForm:password');
                var b = document.getElementById('loginForm:loginButton');
                if (!e || !p) return 'no_fields';
                e.value = {json.dumps(email)};
                p.value = {json.dumps(password)};
                if (b) {{ b.click(); return 'clicked'; }}
                return 'no_button';
            }})()
            """)
            logger.info("Login result: %s", result)

            if result != "clicked":
                logger.error("Login form interaction failed: %s", result)
                return False

            time.sleep(3)
            url = self._js("window.location.href") or ""
            if "principal" in url or "home" in url:
                self._logged_in = True
                logger.info("Successfully logged into Uniweb")
                return True

            logger.error("Login failed — URL after login: %s", url)
            return False

        except Exception as e:
            logger.error("Login failed: %s", e, exc_info=True)
            return False

    # ── Account listing ─────────────────────────────────────────────────────

    def list_accounts(self) -> list[dict]:
        """All accounts, including sub-customers under partner accounts.

        Raises UniwebScrapeError when the account table is not on the page.
        An empty list from here means Uniweb showed a table with no rows.
        """
        if not self._logged_in:
            raise UniwebScrapeError("Not logged in to Uniweb.")

        try:
            self._nav(PRINCIPAL_URL, wait=3)

            # The container is reported separately from the rows: a missing
            # table is a changed page, an empty one is an answer.
            raw = self._js("""
            (function() {
                var table = document.querySelector('#accountForm\\\\:grants tbody');
                if (!table) { return JSON.stringify({found: false, accounts: []}); }
                var rows = table.querySelectorAll('tr');
                var accounts = [];
                rows.forEach(function(row, idx) {
                    var cells = row.querySelectorAll('td');
                    if (cells.length >= 2) {
                        var btn = row.querySelector('button');
                        var btnId = btn ? btn.id : '';
                        // Partner accounts have onsuccess with modal, direct have render=@form
                        var isPartner = btnId.indexOf('j_idt87') !== -1;
                        accounts.push({
                            id: cells[0].textContent.trim(),
                            name: cells[1].textContent.trim(),
                            index: idx,
                            is_partner: isPartner,
                            button_id: btnId
                        });
                    }
                });
                return JSON.stringify({found: true, accounts: accounts});
            })()
            """)

            if not raw:
                raise UniwebScrapeError(
                    "The account page returned nothing — Uniweb may have "
                    "changed its markup, or the session was dropped."
                )
            parsed = json.loads(raw)
            if not parsed.get("found"):
                raise UniwebScrapeError(
                    "The account table (#accountForm:grants) is not on the "
                    "page. This is a markup change, not an empty account list."
                )
            accounts = parsed.get("accounts", [])
            partner_rows = sum(1 for a in accounts if a.get("is_partner"))
            logger.info(
                "Found %d direct accounts (%d recognised as partner)",
                len(accounts), partner_rows,
            )
            if accounts and partner_rows == 0:
                # Not proof of anything — a tenant may hold no partner
                # accounts — but if one is expected this is where it went.
                logger.warning(
                    "No account matched the partner marker %r. If partner "
                    "accounts are expected, their sub-customers are being "
                    "skipped silently: JSF renumbers these ids.",
                    _PARTNER_BUTTON_MARKER,
                )
            self.last_partner_rows = partner_rows

            # For partner accounts, get sub-customers
            all_accounts = []
            for acct in accounts:
                if acct.get("is_partner"):
                    subs = self._get_partner_sub_customers(acct)
                    all_accounts.extend(subs)
                else:
                    all_accounts.append(acct)

            logger.info("Total accounts (including sub-customers): %d", len(all_accounts))
            return all_accounts

        except UniwebScrapeError:
            raise
        except Exception as e:
            logger.error("Failed to list accounts: %s", e, exc_info=True)
            raise UniwebScrapeError(f"Could not read the account list: {e}") from e

    def _get_partner_sub_customers(self, partner: dict) -> list[dict]:
        """Click partner account button, extract sub-customers from modal."""
        try:
            # Click the partner button to open modal
            btn_id = partner.get("button_id", "")
            if btn_id:
                self._js(f"document.getElementById({json.dumps(btn_id)}).click();")
            else:
                idx = int(partner.get("index", 0))
                self._js(f"document.querySelectorAll('#accountForm\\\\:grants tbody tr')[{idx}].querySelector('button').click();")
            time.sleep(2)

            # Extract sub-customers from suToPartnerCustomerModal
            raw = self._js(f"""
            (function() {{
                var modal = document.getElementById('suToPartnerCustomerModal');
                if (!modal) return '[]';
                var parentId = {json.dumps(partner["id"])};
                var parentName = {json.dumps(partner["name"])};
                var rows = modal.querySelectorAll('table tbody tr, tr[data-rk]');
                var subs = [];
                rows.forEach(function(row) {{
                    var cells = row.querySelectorAll('td');
                    if (cells.length >= 2) {{
                        subs.push({{
                            id: cells[0].textContent.trim(),
                            name: cells[1].textContent.trim(),
                            is_partner: false,
                            parent_id: parentId,
                            parent_name: parentName
                        }});
                    }}
                }});
                return JSON.stringify(subs);
            }})()
            """)

            subs = json.loads(raw) if raw else []
            logger.info("Partner %s has %d sub-customers", partner["name"], len(subs))

            # Close modal by navigating back
            self._nav(PRINCIPAL_URL, wait=2)

            return subs

        except Exception as e:
            logger.error("Failed to get sub-customers for %s: %s", partner["name"], e)
            return [partner]

    # ── Select account and scrape data ──────────────────────────────────────

    # Track last opened partner modal to avoid redundant navigation
    _last_partner_id: str = ""

    def _ensure_on_principal(self) -> None:
        """Navigate to principal page only if not already there."""
        url = self._js("window.location.href") or ""
        if "principal" in url:
            return
        self._nav(PRINCIPAL_URL)

    def _open_partner_modal(self, parent_id: str, parent_name: str) -> bool:
        """Open the partner sub-customer modal. Reuses if already open for same partner."""
        # Check if modal is already open with content for this partner
        if self._last_partner_id == parent_id:
            has_rows = self._js("""
            (function() {
                var modal = document.getElementById('suToPartnerCustomerModal');
                if (!modal) return false;
                return modal.querySelectorAll('table tbody tr, tr[data-rk]').length > 0;
            })()
            """)
            if has_rows:
                return True

        self._ensure_on_principal()

        # Click partner row to open modal
        partner_clicked = self._js(f"""
        (function() {{
            var targetId = {json.dumps(parent_id)};
            var targetName = {json.dumps(parent_name)};
            var rows = document.querySelectorAll('#accountForm\\\\:grants tbody tr');
            for (var i = 0; i < rows.length; i++) {{
                var cells = rows[i].querySelectorAll('td');
                if (cells.length >= 1 && cells[0].textContent.trim() === targetId) {{
                    var btn = rows[i].querySelector('button');
                    if (btn) {{ btn.click(); return 'clicked_id'; }}
                }}
            }}
            for (var i = 0; i < rows.length; i++) {{
                var cells = rows[i].querySelectorAll('td');
                if (cells.length >= 2 && cells[1].textContent.trim() === targetName) {{
                    var btn = rows[i].querySelector('button');
                    if (btn) {{ btn.click(); return 'clicked_name'; }}
                }}
            }}
            return 'not_found';
        }})()
        """)

        if not partner_clicked or not partner_clicked.startswith("clicked"):
            logger.error("Could not find parent %s in accounts table", parent_id)
            return False

        time.sleep(2)

        # Force modal visible (PrimeFaces often CSS-hides it)
        self._js("""
        (function() {
            var modal = document.getElementById('suToPartnerCustomerModal');
            if (modal) {
                modal.style.display = 'block';
                modal.style.visibility = 'visible';
                modal.style.opacity = '1';
                modal.style.position = 'fixed';
                modal.style.zIndex = '99999';
                modal.style.top = '0';
                modal.style.left = '0';
            }
        })()
        """)
        time.sleep(0.5)

        row_count = self._js("""
        (function() {
            var modal = document.getElementById('suToPartnerCustomerModal');
            if (!modal) return 0;
            return modal.querySelectorAll('table tbody tr, tr[data-rk]').length;
        })()
        """) or 0
        logger.info("Partner modal for %s: %d rows", parent_name, row_count)

        if row_count > 0:
            self._last_partner_id = parent_id
            return True

        # Retry once
        logger.warning("Modal empty, retrying for %s...", parent_name)
        self._nav(PRINCIPAL_URL)
        self._js(f"""
        (function() {{
            var targetId = {json.dumps(parent_id)};
            var rows = document.querySelectorAll('#accountForm\\\\:grants tbody tr');
            for (var i = 0; i < rows.length; i++) {{
                if (rows[i].textContent.indexOf(targetId) !== -1) {{
                    var btn = rows[i].querySelector('button');
                    if (btn) {{ btn.click(); return 'clicked'; }}
                }}
            }}
        }})()
        """)
        time.sleep(3)
        self._last_partner_id = parent_id
        return True

    def _click_sub_customer(self, acct_id: str, acct_name: str) -> bool:
        """Click a sub-customer in the already-open partner modal."""
        clicked = self._js(f"""
        (function() {{
            var targetId = {json.dumps(acct_id)};
            var targetName = {json.dumps(acct_name)};
            var modal = document.getElementById('suToPartnerCustomerModal');
            if (!modal) return 'no_modal';
            var rows = modal.querySelectorAll('table tbody tr, tr[data-rk]');
            for (var i = 0; i < rows.length; i++) {{
                var cells = rows[i].querySelectorAll('td');
                if (cells.length >= 1 && cells[0].textContent.trim() === targetId) {{
                    var btn = rows[i].querySelector('button, a');
                    if (btn) {{ btn.click(); return 'clicked_id'; }}
                    rows[i].click();
                    return 'clicked_row_id';
                }}
            }}
            for (var i = 0; i < rows.length; i++) {{
                var cells = rows[i].querySelectorAll('td');
                if (cells.length >= 2 && cells[1].textContent.trim() === targetName) {{
                    var btn = rows[i].querySelector('button, a');
                    if (btn) {{ btn.click(); return 'clicked_name'; }}
                    rows[i].click();
                    return 'clicked_row_name';
                }}
            }}
            return 'not_found';
        }})()
        """)
        logger.info("Sub-customer click %s: %s", acct_name, clicked[:100] if clicked else "null")
        return bool(clicked) and "not_found" not in clicked

    def select_account(self, account: dict) -> bool:
        """Navigate into a specific customer account."""
        try:
            if account.get("parent_id"):
                parent_id = account["parent_id"]
                parent_name = account.get("parent_name", "")
                acct_id = account["id"]
                acct_name = account["name"]

                logger.info("Selecting sub-customer %s (id=%s) under %s",
                            acct_name, acct_id, parent_name)

                if not self._open_partner_modal(parent_id, parent_name):
                    return False

                if not self._click_sub_customer(acct_id, acct_name):
                    logger.error("Sub-customer %s not found in modal", acct_name)
                    return False

                time.sleep(2)

            else:
                self._ensure_on_principal()
                acct_id = account.get("id", "")
                idx = int(account.get("index", 0))
                click_result = self._js(f"""
                (function() {{
                    var targetId = {json.dumps(acct_id)};
                    var rows = document.querySelectorAll('#accountForm\\\\:grants tbody tr');
                    for (var i = 0; i < rows.length; i++) {{
                        var cells = rows[i].querySelectorAll('td');
                        if (cells.length >= 1 && cells[0].textContent.trim() === targetId) {{
                            var btn = rows[i].querySelector('button');
                            if (btn) {{ btn.click(); return 'clicked_id'; }}
                        }}
                    }}
                    if (rows[{idx}]) {{
                        var btn = rows[{idx}].querySelector('button');
                        if (btn) {{ btn.click(); return 'clicked_idx'; }}
                    }}
                    return 'not_found';
                }})()
                """)
                logger.info("Direct account click for %s: %s", account["name"], click_result)
                time.sleep(2)

            # Verify we're in the account
            url = self._js("window.location.href") or ""
            if "home" in url or "dashboard" in url:
                logger.info("Selected account: %s", account["name"])
                return True

            # Try navigating to home directly
            self._nav(f"{BASE_URL}/home")
            url = self._js("window.location.href") or ""
            if "principal" not in url:
                logger.info("Selected account: %s (via home)", account["name"])
                return True

            logger.error("Failed to enter account %s — URL: %s", account["name"], url)
            return False

        except Exception as e:
            logger.error("Failed to select account %s: %s", account.get("name"), e)
            return False

    def scrape_domain_dns(self, domain: str) -> list[dict]:
        """Scrape DNS records for a single domain from its edit page."""
        try:
            self._nav(f"{BASE_URL}/one/domain/edit/{domain}")

            # Click the "Edit DNS" accordion title
            self._js("""
            (function() {
                var titles = document.querySelectorAll('.accordion-title');
                for (var i = 0; i < titles.length; i++) {
                    if (titles[i].textContent.indexOf('DNS') !== -1) {
                        titles[i].click();
                        return 'clicked';
                    }
                }
                return 'not_found';
            })()
            """)
            time.sleep(1)

            # Extract DNS records from the editor table rows
            raw = self._js("""
            (function() {
                var editor = document.getElementById('acc:dnsRecordEditor');
                if (!editor) return '[]';
                var knownTypes = ['A','AAAA','CNAME','MX','TXT','NS','SRV','SOA','PTR','CAA',
                                  'WEBFORWARD_301','WEBFORWARD_302'];
                var records = [];
                var rows = editor.querySelectorAll('tr');
                rows.forEach(function(row) {
                    var cells = row.querySelectorAll('td, th');
                    if (cells.length < 4) return;
                    var hostname = cells[0].textContent.trim();
                    var ttl = parseInt(cells[1].textContent.trim()) || 0;
                    var type = cells[2].textContent.trim();
                    var value = cells[3].textContent.trim();
                    if (knownTypes.indexOf(type) !== -1 && hostname) {
                        records.push({hostname: hostname, ttl: ttl, type: type, value: value});
                    }
                });
                return JSON.stringify(records);
            })()
            """)

            records = json.loads(raw) if raw else []
            logger.debug("DNS for %s: %d records", domain, len(records))
            return records

        except UniwebScrapeError:
            raise
        except Exception as e:
            logger.warning("Failed to scrape DNS for %s: %s", domain, e)
            raise UniwebScrapeError(
                f"Could not read DNS for {domain} — the page may have changed: {e}"
            ) from e

    def scrape_account_data(self) -> dict:
        """Scrape all data for the currently selected account."""
        # Always scrape domains and subscriptions (present for ~97% of accounts).
        # Only scrape ssl/email/hosting if the sidebar menu links to them,
        # avoiding ~6s of wasted navigation per account for empty sections.
        data = {
            "domains": self._scrape_section("domain"),
            "subscriptions": self._scrape_section("subscriptions"),
            "ssl": [],
            "email": [],
            "hosting": [],
        }

        # Check which optional sections exist via sidebar menu
        available = self._js("""
        (function() {
            var links = document.querySelectorAll('a[href]');
            var found = [];
            links.forEach(function(a) {
                var h = a.getAttribute('href') || '';
                if (h.indexOf('/ssl') !== -1) found.push('ssl');
                if (h.indexOf('/mail') !== -1) found.push('email');
                if (h.indexOf('/webhotel') !== -1) found.push('hosting');
            });
            return found.join(',');
        })()
        """) or ""

        if "ssl" in available:
            data["ssl"] = self._scrape_section("ssl/")
        if "email" in available:
            data["email"] = self._scrape_section("one/mail/")
        if "hosting" in available:
            data["hosting"] = self._scrape_section("webhotel/")

        # Normalise domain entries — Uniweb's domain table often has an empty
        # <th> for the domain-name column, so the scraper stores it under "".
        # Promote that value to the canonical "domain" key.
        for dom in data["domains"]:
            if not dom.get("domain") and "" in dom:
                dom["domain"] = dom.pop("")
            elif not dom.get("domain"):
                # Last resort: use the first string value
                for v in dom.values():
                    if isinstance(v, str) and v and v != "":
                        dom["domain"] = v
                        break

        # Scrape DNS records for each domain
        for dom in data["domains"]:
            domain_name = dom.get("domain", "")
            if domain_name:
                dom["dns"] = self.scrape_domain_dns(domain_name)
            else:
                dom["dns"] = []

        return data

    def _scrape_section(self, path: str) -> list[dict]:
        """Navigate to a section and scrape all table data."""
        try:
            self._nav(f"{BASE_URL}/{path}")

            raw = self._js("""
            (function() {
                var tables = document.querySelectorAll('table');
                var result = [];
                tables.forEach(function(t) {
                    var headers = [];
                    t.querySelectorAll('thead th').forEach(function(h) {
                        headers.push(h.textContent.trim());
                    });
                    if (headers.length === 0) {
                        // Try first row as header
                        var firstRow = t.querySelector('tr');
                        if (firstRow) {
                            firstRow.querySelectorAll('th, td').forEach(function(h) {
                                headers.push(h.textContent.trim());
                            });
                        }
                    }
                    t.querySelectorAll('tbody tr').forEach(function(row) {
                        var cells = row.querySelectorAll('td');
                        if (cells.length === 0) return;
                        var rowData = {};
                        for (var i = 0; i < cells.length; i++) {
                            var key = i < headers.length ? headers[i] : 'col_' + i;
                            rowData[key] = cells[i].textContent.trim();
                        }
                        result.push(rowData);
                    });
                });
                return JSON.stringify(result);
            })()
            """)

            rows = json.loads(raw) if raw else []
            logger.debug("Section %s: %d rows", path, len(rows))
            return rows

        except UniwebScrapeError:
            raise
        except Exception as e:
            logger.warning("Failed to scrape section %s: %s", path, e)
            raise UniwebScrapeError(
                f"Could not read section {path} — the page may have changed: {e}"
            ) from e

    # ── Full sync ───────────────────────────────────────────────────────────

    def sync_all(self) -> list[dict]:
        """Sync all accounts with their data. Returns list of account dicts."""
        accounts = self.list_accounts()
        results = []
        success = 0
        failed = 0

        # Group sub-customers by parent so we can reuse the modal
        # Sort: sub-customers grouped by parent_id first, then direct accounts
        accounts.sort(key=lambda a: (not bool(a.get("parent_id")), a.get("parent_id", ""), a.get("name", "")))

        for i, acct in enumerate(accounts):
            is_sub = bool(acct.get("parent_id"))
            logger.info("[%d/%d] Syncing %s: %s (%s)%s",
                        i + 1, len(accounts),
                        "sub-account" if is_sub else "direct",
                        acct["name"], acct["id"],
                        f" under {acct.get('parent_name', '')}" if is_sub else "")
            try:
                if self.select_account(acct):
                    data = self.scrape_account_data()
                    acct["data"] = data
                    logger.info("  OK — Domains: %d, Subscriptions: %d, SSL: %d",
                                len(data["domains"]), len(data["subscriptions"]),
                                len(data.get("ssl", [])))
                    success += 1
                    # After scraping, go back to principal so modal is available
                    # for next sub-customer under same partner
                    if is_sub:
                        self._ensure_on_principal()
                else:
                    # No data key at all. Filling it with empty lists made
                    # "we could not open this account" render as "this
                    # customer has no domains", which is a claim about them.
                    acct["unavailable"] = "Could not enter the account page."
                    logger.warning("  FAILED — could not enter account, not scraped")
                    failed += 1
            except Exception as e:
                logger.error("  ERROR syncing %s: %s", acct["name"], e)
                acct["unavailable"] = str(e)[:300]
                failed += 1

            results.append(acct)

        logger.info("Sync complete: %d/%d success, %d failed", success, len(accounts), failed)
        return results

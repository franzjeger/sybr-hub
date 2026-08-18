"""The "Renew Credentials" action must actually renew — and leave no junk behind.

Two defects an operator hit on the customer status page:

* The button cleared the stored credentials and stopped there, dropping the
  operator on a status page with no credentials and a "run setup again" note.
  Renewal now clears the old credentials and then runs the same device-code
  sign-in that first-run setup does, so it finishes with fresh, working
  credentials in one action.

* Re-running setup left the previous audit app registration standing in the
  customer tenant. Over many renewals a tenant accumulated a pile of identical,
  privileged "MSP Toolkit Audit" enterprise apps that nobody pruned. The setup
  helper now keeps the one it reuses and deletes the same-named duplicates.

Both live in code pytest cannot execute — browser JS and a PowerShell helper
that signs into a real tenant — so these are source assertions, the same
approach test_graph_permissions.py already takes for the helper's permission
list. They guard against the fix being silently undone.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "app/web/static/app.js").read_text(encoding="utf-8")
PS1 = (ROOT / "app/helpers/setup_helper.ps1").read_text(encoding="utf-8")


def test_renew_runs_setup_after_clearing_credentials():
    """renewCreds must clear the old credentials AND start the sign-in.

    Clearing without starting setup is the exact bug: the credentials were gone
    and nothing re-issued them, so the button "did nothing" the operator could
    use.
    """
    m = re.search(r"function renewCreds\(\)\s*\{(.*?)\n\}", APP_JS, re.S)
    assert m, "renewCreds not found"
    body = m.group(1)
    assert "/api/customer/renew" in body, "renew no longer clears the old credentials"
    assert "startSetup()" in body, (
        "renew clears the credentials but never re-runs setup — the operator is "
        "left with none, which is the bug being fixed"
    )


def test_the_setup_helper_prunes_duplicate_audit_apps():
    """The helper keeps the app it reuses and deletes the other same-named ones.

    Without this every renewal left the previous 'MSP Toolkit Audit' app
    standing in the customer tenant — a privileged sign-in nobody prunes.
    """
    # You cannot dedup what you never queried: the app-by-name lookup must fetch
    # every match, not cap at one.
    app_query = re.search(
        r"gget 'applications' \"`\$filter=displayName eq '\$appName'([^\"]*)\"", PS1
    )
    assert app_query, "app-by-displayName lookup not found"
    assert "top=1" not in app_query.group(1), (
        "the app lookup still caps at one result, so duplicates are never seen"
    )

    assert "function gdelete" in PS1, "no delete helper — nothing can be pruned"
    # The prune must exclude the app it just settled on, or it could delete the
    # live one.
    assert re.search(r"\$_\.id -ne \$appObjectId", PS1), (
        "the prune does not exclude the app being kept"
    )
    assert re.search(r'gdelete "applications/\$\(\$d\.id\)"', PS1), (
        "duplicates are not deleted by their object id"
    )

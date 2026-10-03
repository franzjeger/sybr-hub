# Contributing to Sybr HUB

## Scope check first

Before opening a PR for a new feature, check [`ROADMAP.md`](ROADMAP.md).
The project is opinionated about what it does and doesn't do — see
the "Out of scope" section. If you're not sure, open an issue first.

## Setting up

```bash
git clone https://github.com/franzjeger/sybr-hub
cd sybr-hub
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
npm ci --ignore-scripts
npx playwright install chromium
```

## Tests

The audit-correctness work that produced the validated audit layer is locked
in by the full regression suite. Do not merge a PR that breaks it, and add new
tests for any new behaviour. Avoid hard-coding the current test count in docs;
it changes with every useful fix.

```bash
python -m pytest -q
npm run check
npm run vendor
npm test
python scripts/audit_vendor.py
mypy
python scripts/check_architecture.py
python -m build --wheel
```

If you're changing parser logic or compliance verdicts: every change
needs a regression test that locks the new behaviour in, ideally
with a comment explaining what the test prevents from coming back.
See `tests/test_parsers.py` for the convention.

`app/reports/compliance.py` is pinned by a characterisation snapshot
(`tests/compliance_characterisation.json`). A refactor must leave it passing
unchanged. When you mean to change a verdict or its wording, recompute it with
`python -m tests.compliance_characterisation` and say in the commit what
changed in it, ideally after comparing old and new context by context.

`npm run check` is more than a syntax check. It fails on:
- a top-level name declared in two scripts;
- any inline event handler or `javascript:` URL, and any handler name that is
  not registered or never used (controls use `data-click-handler` and
  `registerUiHandlers`; see docs/ARCHITECTURE.md, Front-end structure);
- unescaped data in an `innerHTML` string in the files it enforces;
- an em or en dash in text the scripts build;
- any ESLint error.

A new route that reads a body takes a Pydantic model from `app/models/` with
`extra="forbid"`. A refusal a person reads carries a `message_key` with both
languages in `app/web/i18n.py`, or comes from `app/core/messages.py` below the
web layer. Norwegian text has no em or en dashes.

## Code style

Ruff handles formatting and lint:

```bash
ruff format path/to/changed_file.py
ruff check .
python scripts/lint_budget.py
```

Aim for explicit code over clever code. The audit layer in particular
favours readability — auditors will read these reports and "what does
this verdict actually mean?" needs a clear answer in the source.

## Data quality is non-negotiable

A recurring lesson from the v10.10.2–.12 work is that parsers and
verdicts must distinguish:

- **"audit succeeded with zero records"** (valid measurement, e.g.
  M365-only tenant with no Intune devices)
- **"audit failed / data unavailable"** (data-quality issue)
- **"audit found a problem"** (real finding)

When you write a parser or compliance check, pick the three branches
explicitly. Substring-matching against a banner that's always present
is a bug we've had at least eight times.

## Customer data must never enter the repo

- Commit messages, CHANGELOG entries, examples: use anonymised names
  ("Customer A", "Customer B"). Real names go in customer-facing
  reports, never in source control.
- The `.gitignore` excludes `audit_data/`, `*.pfx`, and Claude Code
  session directories — do not loosen these.
- If you spot a leak (PII, real domain, real tenant id) in any
  tracked file or commit message, open a SECURITY issue before
  opening a PR.

## PR conventions

- Conventional commit style: `fix(area):`, `feat(area):`, `chore:`, `docs:`, `test:`.
- One logical change per commit. We rebase-merge.
- Reference the ROADMAP section your work lands in.
- Include the current full-suite output in the PR description.

Before protecting `main`, configure GitHub to require the stable CI checks
`pytest (3.11)`, `pytest (3.12)`, `pytest (3.13)`, `pytest (3.14)`, `ruff`, and
`pip-audit`, and `browser, types and package`; also require an up-to-date branch, resolved review conversations,
and at least one approval. Repository settings are an external control and
cannot be enforced by workflow YAML alone. The workflow includes a
`merge_group` trigger so those same checks work with GitHub's merge queue.

## Author identity

Commits go in under the contributor's GitHub identity. If you're
contributing on behalf of a company, use a company email; if as an
individual, your personal one is fine. PRs from the upstream
maintainer (SYBR) use `support@sybr.no`.

## Review gates and isolated browser checks

Use a separate mechanical change for repository-wide formatting. The lint budget
must not grow, and newly added modules must be clean. Ruff is pinned to keep the
ratchet stable. Run `python scripts/lint_budget.py --update` only after a decrease.

Browser checks start their own disposable local server with synthetic accounts,
isolated key storage and disabled background integrations. They exercise actual
cookies, HTML parsing, keyboard activation and the authenticated API. To use an
existing Chromium, set `SYBR_TEST_CHROMIUM=/path/to/chromium`. They must never point
to a production instance. Dependency lock regeneration uses Python 3.14:

```bash
pip-compile --generate-hashes --no-emit-index-url -o requirements.lock requirements.txt
pip-audit -r requirements.lock --require-hashes --disable-pip --strict
```

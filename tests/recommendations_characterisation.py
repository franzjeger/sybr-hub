"""Frozen inputs and outputs for the prioritised recommendations.

``_build_recommendations`` feeds the customer report and the customer page,
and its ids key the remediation state an operator has recorded, so a change
to how it is written has to leave what it produces identical, not merely
similar. ``recommendations_characterisation.json`` holds a broad set of
inputs and the exact recommendations the code produced for each, in both
languages; ``test_recommendations_characterisation.py`` replays them.

The inputs are stored rather than rebuilt. Rebuilding them through the parsers
would make the snapshot fail on parser changes that never touched the builder.

They come from two places:

* every call the rest of the suite makes to the builder, recorded by the
  pytest plugin in this module and cut down to the fields the builder reads;
* ``tests/recommendations_cases.py``: gaps, malformed shapes and the
  threshold edges the suite does not reach, so both outcomes of every branch
  in ``app/reports/recommendations.py`` that the builder can reach are
  exercised.

Each replay is compared on the ``json.dumps(..., sort_keys=True)`` text, each
recommendation's key order and value types at every depth (a Localised keeps
the key and parameters it is rebuilt from), the exception raised if any, the
warnings logged, and which output lists and dicts are the caller's own
objects rather than copies.

Rebuild the inputs (rare; the outputs are recomputed from the current code)::

    SYBR_RECS_CAPTURE=/tmp/recs.json python -m pytest -q -p tests.recommendations_characterisation
    python -m tests.recommendations_characterisation --inputs-from /tmp/recs.json

Recompute the outputs for the stored inputs, only when a change in behaviour
is intended::

    python -m tests.recommendations_characterisation
"""

from __future__ import annotations

import functools
import inspect
import json
import logging
import os
import re
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

# The codec and the distinct-item table are the compliance snapshot's: the
# same JSON-safe round trip for Localised values, tuples and collector files.
from tests.compliance_characterisation import (
    _intern,
    _lines,
    _Table,
    clone,
    decode,
    encode,
    encode_context,
)

SNAPSHOT = Path(__file__).with_name("recommendations_characterisation.json")
LANGS = ("no", "en")
_LOGGER = "app.reports.recommendations"


# ── Observation ───────────────────────────────────────────────────────────────


def shape(value):
    """Types and key order at every depth: what json.dumps(sort_keys=True) cannot see.

    A Localised is a str to JSON, but it carries the key and parameters a
    reader in the other language rebuilds it from, so those are part of it.
    Runs of equal list items are stored once with a count.
    """
    from app.reports.i18n import Localised

    if isinstance(value, Localised):
        return {"L": [value.key, shape(value.params)]}
    if type(value) is dict:
        return {"d": [[k, shape(v)] for k, v in value.items()]}
    if type(value) in (list, tuple):
        runs: list[list] = []
        for item in value:
            s = shape(item)
            if runs and runs[-1][0] == s:
                runs[-1][1] += 1
            else:
                runs.append([s, 1])
        return {type(value).__name__: runs}
    return type(value).__name__


def _containers(value, path: str, found: dict[int, str]) -> None:
    if type(value) in (list, dict):
        found.setdefault(id(value), path)
    if type(value) is dict:
        for k, v in value.items():
            _containers(v, f"{path}.{k}" if path else str(k), found)
    elif type(value) in (list, tuple):
        for i, v in enumerate(value):
            _containers(v, f"{path}.{i}" if path else str(i), found)


def aliases(context: dict, recs) -> list[list[str]]:
    """Output lists and dicts that are the caller's own objects, not copies.

    A recommendation hands some input lists straight through as its
    sub_items, so a consumer that edits one edits the audit data too.
    """
    inputs: dict[int, str] = {}
    _containers(context, "", inputs)
    outputs: dict[int, str] = {}
    _containers(recs, "", outputs)
    pairs = [[path, inputs[oid]] for oid, path in outputs.items() if oid in inputs]
    return sorted(pairs)


class _Records(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(f"{record.levelname}: {record.getMessage()}")


def observe(build: Callable, context: dict, lang: str) -> dict:
    """What one call produces, everything a caller could notice."""
    before = json.dumps(encode(context, {}), sort_keys=True, ensure_ascii=False)
    logger = logging.getLogger(_LOGGER)
    records, level = _Records(), logger.level
    logger.addHandler(records)
    logger.setLevel(logging.DEBUG)
    try:
        recs = build(**context, lang=lang)
    except Exception as exc:
        seen: dict = {"raises": f"{type(exc).__name__}: {exc}"}
    else:
        seen = {
            "dump": json.dumps(recs, sort_keys=True, ensure_ascii=False),
            "recs": recs,
            "shapes": [shape(r) for r in recs],
            "aliases": aliases(context, recs),
        }
    finally:
        logger.removeHandler(records)
        logger.setLevel(level)
    seen["logs"] = records.lines
    after = json.dumps(encode(context, {}), sort_keys=True, ensure_ascii=False)
    seen["mutates"] = after != before
    return seen


def comparable(seen: dict) -> dict:
    """An observation without the live objects, as the snapshot holds it."""
    return {k: v for k, v in seen.items() if k != "recs"}


def signature() -> str:
    from app.reports.recommendations import _build_recommendations

    # The generator passes most arguments by position.
    return str(inspect.signature(_build_recommendations))


# ── Snapshot file ─────────────────────────────────────────────────────────────


def load() -> dict:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def stored_contexts(snapshot: dict) -> Iterator[tuple[str, dict, dict]]:
    """(name, decoded arguments, {lang: expected}) for every stored input.

    *expected* has the keys comparable() leaves in an observation.
    """
    texts = snapshot["texts"]
    shapes = snapshot["shapes"]
    table = snapshot["recs"]
    outputs = snapshot["outputs"]
    for entry in snapshot["contexts"]:
        expected = {}
        for lang, out in zip(snapshot["langs"], entry["outputs"], strict=True):
            result = outputs[out]
            want = {"logs": result.get("logs", []), "mutates": result.get("mutates", False)}
            if "raises" in result:
                want["raises"] = result["raises"]
            else:
                refs = result["recs"]
                index = result.get("rec_index", range(1, len(refs) + 1))
                recs = [
                    {**decode(table[i][0], texts), "rec_index": n}
                    for i, n in zip(refs, index, strict=True)
                ]
                want["dump"] = json.dumps(recs, sort_keys=True, ensure_ascii=False)
                want["shapes"] = [shapes[table[i][1]] for i in refs]
                want["aliases"] = result.get("aliases", [])
            expected[lang] = want
        yield entry["name"], decode(entry["context"], texts), expected


def _output(seen: dict, recs: _Table, shapes: _Table, texts: dict[str, int]) -> dict:
    out: dict = {}
    if "raises" in seen:
        out["raises"] = seen["raises"]
    else:
        # rec_index is kept apart, where it is not simply the position: a
        # recommendation that moves up one place is otherwise a new entry.
        plain = json.loads(seen["dump"])
        out["recs"] = [
            recs.add(
                [encode({k: v for k, v in rec.items() if k != "rec_index"}, texts), shapes.add(s)]
            )
            for rec, s in zip(plain, seen["shapes"], strict=True)
        ]
        index = [rec.get("rec_index") for rec in plain]
        if index != list(range(1, len(plain) + 1)):
            out["rec_index"] = index
        if seen["aliases"]:
            out["aliases"] = seen["aliases"]
    # Rare; left out when empty or false to keep the file small.
    if seen["logs"]:
        out["logs"] = seen["logs"]
    if seen["mutates"]:
        out["mutates"] = True
    return out


def _compact(context: dict, texts: dict[str, int]) -> dict:
    """encode_context(), with each file set also stored once and referred to.

    Most synthetic inputs vary one argument of the same tenant, so the rest
    of each is a repeat.
    """
    out = encode_context(context, texts)
    for key, value in out.items():
        as_json = json.dumps(value, ensure_ascii=False)
        if len(as_json) >= 40 and not (isinstance(value, dict) and "$j" in value):
            out[key] = {"$j": _intern(as_json, texts)}
    return out


def write(named_contexts: list[tuple[str, dict]], build: Callable) -> None:
    texts: dict[str, int] = {}
    shapes = _Table()
    recs = _Table()
    outputs = _Table()
    entries = []
    for name, context in named_contexts:
        # Each call gets its own copy: a builder that mutated its input would
        # otherwise leak into the next language.
        refs = [
            outputs.add(_output(observe(build, clone(context), lang), recs, shapes, texts))
            for lang in LANGS
        ]
        entries.append({"name": name, "context": _compact(context, texts), "outputs": refs})
    # Tables, in order: long texts the contexts and recommendations refer to;
    # recommendation key-order and type shapes; distinct recommendations,
    # without rec_index, as [rec, shape]; distinct outputs; and per context
    # one output per language.
    SNAPSHOT.write_text(
        "{\n"
        f'"signature": {json.dumps(signature())},\n'
        f'"langs": {json.dumps(LANGS)},\n'
        f'"texts": {_lines(sorted(texts, key=texts.__getitem__))},\n'
        f'"shapes": {_lines(shapes.items)},\n'
        f'"recs": {_lines(recs.items)},\n'
        f'"outputs": {_lines(outputs.items)},\n'
        f'"contexts": {_lines(entries)}\n'
        "}\n",
        encoding="utf-8",
    )


# ── Capture plugin ────────────────────────────────────────────────────────────
#
# Loaded with ``-p tests.recommendations_characterisation``; inert unless
# SYBR_RECS_CAPTURE names an output file. It patches in pytest_configure,
# after conftest has pointed app's data directories at the sandbox and before
# any test module binds the name.

_capture: dict = {"test": "collection", "calls": [], "texts": {}}


def pytest_configure(config) -> None:
    if not os.environ.get("SYBR_RECS_CAPTURE"):
        return
    import app.reports.generator as generator
    import app.reports.recommendations as recommendations

    original = recommendations._build_recommendations
    params = inspect.signature(original)

    # wraps(): the recorder keeps the builder's name, signature and source.
    @functools.wraps(original)
    def recording(*args, **kwargs):
        bound = params.bind(*args, **kwargs)
        call = dict(bound.arguments)
        lang = call.pop("lang", "no")
        _capture["calls"].append(
            {"test": _capture["test"], "lang": lang, "args": encode(call, _capture["texts"])}
        )
        return original(*args, **kwargs)

    recommendations._build_recommendations = recording
    generator._build_recommendations = recording


def pytest_runtest_setup(item) -> None:
    _capture["test"] = item.nodeid


def pytest_sessionfinish(session) -> None:
    path = os.environ.get("SYBR_RECS_CAPTURE")
    if not path:
        return
    texts = sorted(_capture["texts"], key=_capture["texts"].__getitem__)
    Path(path).write_text(
        json.dumps({"texts": texts, "calls": _capture["calls"]}, ensure_ascii=False),
        encoding="utf-8",
    )


# ── Building the input set ────────────────────────────────────────────────────

# Collector files whose text the builder parses. Any other file it names is
# only cited as evidence, where all that counts is whether it is blank.
_PARSED_FILES = (
    "04_mfa_methods.json",
    "04_mfa_methods.txt",
    "09b_auth_methods_policy.txt",
    "03c_stale_accounts_WARN.txt",
    "17c_app_credential_expiry_WARN.txt",
)


def _named_files() -> set[str]:
    src = (Path(__file__).parents[1] / "app/reports/recommendations.py").read_text(encoding="utf-8")
    return set(re.findall(r"""["']([0-9]{2}[a-z]?_[A-Za-z0-9_]+\.(?:txt|json))["']""", src))


def _is_nsg_warn(name: str) -> bool:
    return "nsg_risky" in name.lower() and "WARN" in name


def _reduce_files(fc: dict, named: set[str]) -> dict:
    out = {}
    for name, text in fc.items():
        if name in _PARSED_FILES or _is_nsg_warn(name):
            out[name] = text
        elif name in named:
            # Cited only: "x" stands in for any text that is not blank.
            out[name] = "x" if isinstance(text, str) and text.strip() else text
    return out


# The fields the builder reads from each argument, as {field: item fields}
# (None: kept as it is). The rest (per-user rows in other sections, device
# inventories) would only bloat the snapshot.
_READ_FIELDS: dict[str, dict[str, tuple[str, ...] | None]] = {
    "mfa": {
        "has_data": None,
        "no_mfa": None,
        "mfa_registered": None,
        "ca_covered": None,
        "no_mfa_registered": None,
        "registered_but_excluded": None,
        "users": ("ca_excluded", "upn", "name", "has_mfa", "methods"),
    },
    "secure_score": {
        "pct": None,
        "current": None,
        "max": None,
        "improvements": ("name", "category"),
    },
    "admin_roles": {"global_admin_count": None, "global_admin_users": ("email",)},
    "intune": {
        "noncompliant": None,
        "compliance_pct": None,
        "entra_unmanaged": None,
        "entra_total": None,
    },
    "sharepoint": {"has_data": None, "sharing_level": None, "legacy_auth": None},
    "oauth": {"high_privilege_apps": None},
    "azure": {
        "advisor_summary": ("category", "impact", "count", "subscription", "description"),
        "orphaned": None,
        "orphaned_details": ("type", "status", "detail"),
    },
    "backup_coverage": {"coverage_known": None, "vms_not_backed_up": None},
    "signin_risk": {"brute_force_suspects": None, "stale_credential_users": None},
    "network": {"unreadable": None, "has_data": None, "fortigate": None, "unifi": None},
}
_READ_ITEM_FIELDS = {"spf_dmarc": ("domain", "spf", "dmarc")}


def _pick_items(value, fields: tuple[str, ...] | None):
    if fields is None or not isinstance(value, list):
        return value
    return [
        {k: v for k, v in item.items() if k in fields} if isinstance(item, dict) else item
        for item in value
    ]


def _reduce(args: dict, named: set[str]) -> dict:
    out = dict(args)
    if isinstance(out.get("file_contents"), dict):
        out["file_contents"] = _reduce_files(out["file_contents"], named)
    if "licenses" in out:
        out["licenses"] = []  # passed, never read
    for key, fields in _READ_FIELDS.items():
        value = out.get(key)
        if isinstance(value, dict):
            out[key] = {k: _pick_items(v, fields[k]) for k, v in value.items() if k in fields}
    for key, fields in _READ_ITEM_FIELDS.items():
        if isinstance(out.get(key), list):
            out[key] = _pick_items(out[key], fields)
    return out


def _same(build: Callable, a: dict, b: dict) -> bool:
    return all(
        comparable(observe(build, clone(a), lang)) == comparable(observe(build, clone(b), lang))
        for lang in LANGS
    )


def _shrink_parsed(build: Callable, args: dict) -> dict:
    """Stand "x" in for each parsed file whose text this input does not need.

    The MFA table, say, is only parsed when its JSON sidecar is unreadable.
    """
    fc = args.get("file_contents")
    if not isinstance(fc, dict):
        return args
    for name, text in fc.items():
        if not isinstance(text, str) or not text.strip() or text == "x":
            continue
        trial = {**args, "file_contents": {**args["file_contents"], name: "x"}}
        if _same(build, args, trial):
            args = trial
    return args


def captured(path: Path, build: Callable) -> list[tuple[str, dict]]:
    """Suite calls, cut down to what the builder reads and deduplicated.

    The cut is verified, not assumed: each reduced input must produce the
    same observation as the one the suite passed, or the full one is kept.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    named = _named_files()
    seen: set[str] = set()
    per_test: dict[str, int] = {}
    out = []
    for call in data["calls"]:
        full = decode(call["args"], data["texts"])
        reduced = _reduce(full, named)
        if not _same(build, full, reduced):
            reduced = full
        reduced = _shrink_parsed(build, reduced)
        key = json.dumps(encode(reduced, {}), sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        n = per_test.get(call["test"], 0)
        per_test[call["test"]] = n + 1
        out.append((f"suite: {call['test']}" + (f" #{n}" if n else ""), reduced))
    return out


def main(argv: list[str]) -> int:
    # Sandbox app's data directories before app is imported, as the suite does.
    import tests.conftest
    from app.reports.recommendations import _build_recommendations

    if "--inputs-from" in argv:
        from tests.recommendations_cases import synthetic_contexts

        suite = captured(Path(argv[argv.index("--inputs-from") + 1]), _build_recommendations)
        named = suite + list(synthetic_contexts())
    else:
        named = [(name, ctx) for name, ctx, _ in stored_contexts(load())]
    names = [n for n, _ in named]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise SystemExit(f"duplicate context names: {dupes}")
    write(named, _build_recommendations)
    print(f"{len(named)} contexts written to {SNAPSHOT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

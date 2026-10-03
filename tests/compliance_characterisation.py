"""Frozen inputs and outputs for the CIS compliance map.

``_build_compliance_map`` feeds the customer-facing report, so a change to how
it is written has to leave what it produces identical, not merely similar.
``compliance_characterisation.json`` holds a broad set of inputs and the exact
rows the code produced for each, in every language and framework selection;
``test_compliance_characterisation.py`` replays them.

The inputs are stored rather than rebuilt. Rebuilding them through the parsers
would make the snapshot fail on parser changes that never touched the map.

They come from two places:

* every context the rest of the suite hands to the map, recorded by the
  pytest plugin in this module;
* ``synthetic_contexts()``: data gaps, refusals, licence gates and failing
  values the suite does not reach, so every verdict branch is exercised.

Rebuild the inputs (rare; the outputs are recomputed from the current code)::

    SYBR_COMPLIANCE_CAPTURE=/tmp/ctx.json python -m pytest -q -p tests.compliance_characterisation
    python -m tests.compliance_characterisation --inputs-from /tmp/ctx.json

Recompute the outputs for the stored inputs, only when a change in behaviour
is intended::

    python -m tests.compliance_characterisation
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

SNAPSHOT = Path(__file__).with_name("compliance_characterisation.json")
LANGS = ("no", "en")
# "unknown" stands for any value the code does not name: it gets the CIS-only
# columns, and the route passes whatever the request body carried.
FRAMEWORKS = ("cis", "cis+nist", "cis+iso", "all", "unknown")
# The only context keys the map reads. Everything else a report context
# carries is irrelevant to it and would only bloat the snapshot.
INPUT_KEYS = (
    "licenses",
    "mfa",
    "ca",
    "secure_score",
    "admin_roles",
    "spf_dmarc",
    "sharepoint",
    "intune",
    "file_contents",
    "oauth",
    "purview",
    "risky_users",
)
_INTERN_MIN = 80


# ── Codec ─────────────────────────────────────────────────────────────────────
#
# JSON alone would flatten a Localised into a plain str and a tuple into a
# list, and the map passes some context values straight through to its rows.
# Long strings and collector file names are interned: the same file appears
# in hundreds of contexts.


def _intern(text: str, texts: dict[str, int]) -> int:
    return texts.setdefault(text, len(texts))


def encode(value, texts: dict[str, int]):
    from app.reports.i18n import Localised

    if isinstance(value, Localised):
        return {"$L": [str(value), value.key, encode(value.params, texts)]}
    if type(value) is str:
        return {"$t": _intern(value, texts)} if len(value) >= _INTERN_MIN else value
    if value is None or type(value) in (bool, int, float):
        return value
    if type(value) is list:
        return [encode(v, texts) for v in value]
    if type(value) is tuple:
        return {"$tuple": [encode(v, texts) for v in value]}
    if type(value) is dict and all(type(k) is str and not k.startswith("$") for k in value):
        return {k: encode(v, texts) for k, v in value.items()}
    # Not a type the map reads; kept as text so the context still round-trips.
    return {"$repr": repr(value)}


def encode_context(context, texts: dict[str, int]):
    """encode(), compacted: hundreds of contexts share the same sections.

    file_contents becomes [name, text] index pairs, and each other section is
    stored once as JSON text and referred to by index.
    """
    if not isinstance(context, dict):
        return encode(context, texts)
    out = {}
    for key, value in context.items():
        fc = value if key == "file_contents" and isinstance(value, dict) else None
        if fc is not None and all(type(k) is str for k in fc):
            out[key] = {
                "$fc": [
                    [
                        _intern(k, texts),
                        _intern(v, texts) if type(v) is str else {"raw": encode(v, texts)},
                    ]
                    for k, v in fc.items()
                ]
            }
            continue
        encoded = encode(value, texts)
        as_json = json.dumps(encoded, ensure_ascii=False)
        out[key] = {"$j": _intern(as_json, texts)} if len(as_json) >= 40 else encoded
    return out


def decode(value, texts: list[str]):
    from app.reports.i18n import Localised

    if isinstance(value, list):
        return [decode(v, texts) for v in value]
    if isinstance(value, dict):
        if len(value) == 1:
            ((tag, payload),) = value.items()
            if tag == "$t":
                return texts[payload]
            if tag == "$L":
                text, key, params = payload
                return Localised(text, key, decode(params, texts))
            if tag == "$tuple":
                return tuple(decode(v, texts) for v in payload)
            if tag == "$repr":
                return payload
            if tag == "$fc":
                return {
                    texts[k]: texts[v] if isinstance(v, int) else decode(v["raw"], texts)
                    for k, v in payload
                }
            if tag == "$j":
                return decode(json.loads(texts[payload]), texts)
        return {k: decode(v, texts) for k, v in value.items()}
    return value


def clone(value):
    """A deep copy through the codec, so it is exactly what a replay sees."""
    texts: dict[str, int] = {}
    encoded = encode(value, texts)
    return decode(encoded, sorted(texts, key=texts.__getitem__))


# ── Observation ───────────────────────────────────────────────────────────────


def row_shape(row: dict) -> list[list[str]]:
    """Key order and value types: what json.dumps(sort_keys=True) cannot see.

    A Localised detail carries the key and parameters a reader in the other
    language rebuilds it from, so those are part of the output too.
    """
    from app.reports.i18n import Localised

    shape = []
    for key, value in row.items():
        if isinstance(value, Localised):
            params = json.dumps(value.params, sort_keys=True, ensure_ascii=False, default=repr)
            tag = f"Localised:{value.key}:{params}"
        else:
            tag = type(value).__name__
        shape.append([key, tag])
    return shape


# CPython words some of its own errors differently between versions: 3.14
# says "argument of type 'int' is not a container or iterable" where 3.11 to
# 3.13 say "... is not iterable". The snapshot pins which error is raised and
# what our code puts in it, not the interpreter's phrasing.
_CPYTHON_WORDING = ((" is not a container or iterable", " is not iterable"),)


def exception_text(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}"
    for newer, older in _CPYTHON_WORDING:
        text = text.replace(newer, older)
    return text


def observe(build: Callable, context, lang: str, frameworks: str) -> dict:
    try:
        rows = build(context, lang=lang, frameworks=frameworks)
    except Exception as exc:
        return {"raises": exception_text(exc)}
    return {
        "dump": json.dumps(rows, sort_keys=True, ensure_ascii=False),
        "rows": rows,
        "shapes": [row_shape(r) for r in rows],
    }


def variant(lang: str, frameworks: str) -> str:
    return f"{lang}|{frameworks}"


# ── Snapshot file ─────────────────────────────────────────────────────────────


def load() -> dict:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def stored_contexts(snapshot: dict) -> Iterator[tuple[str, object, dict]]:
    """(name, decoded context, {variant: expected}) for every stored input.

    *expected* is either {"raises": ...} or {"dump": ..., "shapes": ...}.
    """
    texts = snapshot["texts"]
    shapes = snapshot["shapes"]
    table = snapshot["rows"]
    outputs = snapshot["outputs"]
    variants = [variant(lang, fw) for lang in snapshot["langs"] for fw in snapshot["frameworks"]]
    for entry in snapshot["contexts"]:
        expected = {}
        for key, out in zip(variants, entry["outputs"], strict=True):
            result = outputs[out]
            if isinstance(result, str):
                expected[key] = {"raises": result}
                continue
            rows = [table[i][0] for i in result]
            expected[key] = {
                "dump": json.dumps(rows, sort_keys=True, ensure_ascii=False),
                "shapes": [shapes[table[i][1]] for i in result],
            }
        yield entry["name"], decode(entry["context"], texts), expected


def _lines(items: list) -> str:
    # One item per line keeps the file diffable.
    return "[\n" + ",\n".join(json.dumps(i, ensure_ascii=False) for i in items) + "\n]"


class _Table:
    """Distinct items in first-seen order; the snapshot refers to them by index."""

    def __init__(self) -> None:
        self.index: dict[str, int] = {}
        self.items: list = []

    def add(self, item) -> int:
        key = json.dumps(item, ensure_ascii=False)
        if key not in self.index:
            self.index[key] = len(self.items)
            self.items.append(item)
        return self.index[key]


def write(named_contexts: list[tuple[str, object]], build: Callable) -> None:
    texts: dict[str, int] = {}
    shapes = _Table()
    rows = _Table()
    outputs = _Table()
    entries = []
    for name, context in named_contexts:
        refs = []
        for lang in LANGS:
            for frameworks in FRAMEWORKS:
                # Each call gets its own copy: a map that mutated its input
                # would otherwise leak into the next variant.
                seen = observe(build, clone(context), lang, frameworks)
                if "raises" in seen:
                    refs.append(outputs.add(seen["raises"]))
                    continue
                result = [
                    rows.add([row, shapes.add(shape)])
                    for row, shape in zip(seen["rows"], seen["shapes"], strict=True)
                ]
                refs.append(outputs.add(result))
        entries.append({"name": name, "context": encode_context(context, texts), "outputs": refs})
    # Tables, in order: texts the contexts refer to; row key-order/type shapes;
    # distinct rows as [row, shape]; distinct outputs as row lists (or the
    # exception raised); and per context one output per lang x frameworks.
    SNAPSHOT.write_text(
        "{\n"
        f'"langs": {json.dumps(LANGS)},\n'
        f'"frameworks": {json.dumps(FRAMEWORKS)},\n'
        f'"texts": {_lines(sorted(texts, key=texts.__getitem__))},\n'
        f'"shapes": {_lines(shapes.items)},\n'
        f'"rows": {_lines(rows.items)},\n'
        f'"outputs": {_lines(outputs.items)},\n'
        f'"contexts": {_lines(entries)}\n'
        "}\n",
        encoding="utf-8",
    )


# ── Capture plugin ────────────────────────────────────────────────────────────
#
# Loaded with ``-p tests.compliance_characterisation``; inert unless
# SYBR_COMPLIANCE_CAPTURE names an output file. It patches in pytest_configure,
# after conftest has pointed app's data directories at the sandbox and before
# any test module binds the name.

_capture: dict = {"test": "collection", "calls": [], "texts": {}}


def pytest_configure(config) -> None:
    if not os.environ.get("SYBR_COMPLIANCE_CAPTURE"):
        return
    import app.reports.compliance as compliance
    import app.reports.generator as generator

    original = compliance._build_compliance_map

    def recording(context, lang="no", frameworks="all"):
        subset = {k: context[k] for k in INPUT_KEYS if k in context}
        _capture["calls"].append(
            {
                "test": _capture["test"],
                "lang": lang,
                "frameworks": frameworks,
                "context": encode(subset, _capture["texts"]),
            }
        )
        return original(context, lang, frameworks)

    compliance._build_compliance_map = recording
    generator._build_compliance_map = recording


def pytest_runtest_setup(item) -> None:
    _capture["test"] = item.nodeid


def pytest_sessionfinish(session) -> None:
    path = os.environ.get("SYBR_COMPLIANCE_CAPTURE")
    if not path:
        return
    texts = sorted(_capture["texts"], key=_capture["texts"].__getitem__)
    Path(path).write_text(
        json.dumps({"texts": texts, "calls": _capture["calls"]}, ensure_ascii=False),
        encoding="utf-8",
    )


# ── Building the input set ────────────────────────────────────────────────────


def _read_files() -> set[str]:
    """Every collector file the map can look at: the ones it names, plus evidence."""
    from app.reports.evidence import _EVIDENCE_MAP

    src = (Path(__file__).parents[1] / "app/reports/compliance.py").read_text(encoding="utf-8")
    named = set(re.findall(r"""["']([0-9]{2}[a-z]?_[A-Za-z0-9_]+\.(?:txt|json))["']""", src))
    return named | {f for files in _EVIDENCE_MAP.values() for f in files}


# The fields the map reads from each parsed section. The rest (the MFA
# section's per-user rows, say) would only bloat the snapshot.
_READ_FIELDS = {
    "mfa": ("has_data", "pct", "no_mfa"),
    "ca": ("has_data", "enabled", "has_client_app_data", "blocks_legacy_auth"),
    "secure_score": ("has_data", "pct"),
    "admin_roles": ("has_data", "global_admin_count"),
    "sharepoint": (
        "has_data",
        "legacy_auth_known",
        "legacy_auth",
        "sharing_level",
        "sharing",
        "sharing_label",
    ),
    "intune": (
        "unavailable",
        "unavailable_reason",
        "has_data",
        "total",
        "entra_total",
        "compliance_pct",
        "noncompliant",
    ),
    "oauth": ("total_grants", "unique_apps", "app_registrations", "high_privilege_apps"),
    "purview": ("dlp_policies", "sensitivity_labels", "retention_policies"),
}
_READ_ITEM_FIELDS = {
    "spf_dmarc": ("domain", "spf", "dmarc", "dmarc_record", "dkim", "dkim1", "dkim2"),
    "licenses": ("part", "used"),
}


def _pick(value, fields: tuple[str, ...]):
    if not isinstance(value, dict):
        return value
    return {k: v for k, v in value.items() if k in fields}


def _reduce(context: dict, read: set[str]) -> dict:
    out = dict(context)
    fc = out.get("file_contents")
    if isinstance(fc, dict):
        out["file_contents"] = {k: v for k, v in fc.items() if k in read}
    for key, fields in _READ_FIELDS.items():
        if key in out:
            out[key] = _pick(out[key], fields)
    for key, fields in _READ_ITEM_FIELDS.items():
        if isinstance(out.get(key), list):
            out[key] = [_pick(item, fields) for item in out[key]]
    return out


def _captured(path: Path, build: Callable) -> list[tuple[str, dict]]:
    """Suite contexts, cut down to what the map reads and deduplicated.

    The cut is verified, not assumed: each reduced context must produce the
    same output as the one the suite passed.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    read = _read_files()
    seen: set[str] = set()
    per_test: dict[str, int] = {}
    out = []
    for call in data["calls"]:
        full = decode(call["context"], data["texts"])
        reduced = _reduce(full, read)
        for lang in LANGS:
            a = observe(build, clone(full), lang, "all")
            b = observe(build, clone(reduced), lang, "all")
            if a.get("dump") != b.get("dump") or a.get("raises") != b.get("raises"):
                reduced = full
                break
        key = json.dumps(encode(reduced, {}), sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        n = per_test.get(call["test"], 0)
        per_test[call["test"]] = n + 1
        out.append((f"suite: {call['test']}" + (f" #{n}" if n else ""), reduced))
    return out


def _base(captured: list[tuple[str, dict]], audit: dict[str, str]) -> dict:
    """The suite's render of an audit fixture, found by its collector files."""
    read = _read_files()
    want = {k: v for k, v in audit.items() if k in read}
    for _name, context in captured:
        fc = context.get("file_contents")
        if fc == want and context.get("mfa", {}).get("has_data"):
            return context
    raise SystemExit("the suite no longer renders this audit fixture; pick another base")


def main(argv: list[str]) -> int:
    # Sandbox app's data directories before app is imported, as the suite does.
    import tests.conftest
    from app.reports.compliance import _build_compliance_map

    if "--inputs-from" in argv:
        from tests.compliance_cases import synthetic_contexts

        captured = _captured(Path(argv[argv.index("--inputs-from") + 1]), _build_compliance_map)
        from tests.audit_fixture import BROKEN_AUDIT, FULL_AUDIT

        bases = {"full": _base(captured, FULL_AUDIT), "broken": _base(captured, BROKEN_AUDIT)}
        named = captured + list(synthetic_contexts(bases))
    else:
        named = [(name, ctx) for name, ctx, _ in stored_contexts(load())]
    names = [n for n, _ in named]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise SystemExit(f"duplicate context names: {dupes}")
    write(named, _build_compliance_map)
    print(f"{len(named)} contexts written to {SNAPSHOT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

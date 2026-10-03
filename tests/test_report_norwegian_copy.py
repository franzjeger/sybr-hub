"""The Norwegian text in the reports keeps to one voice and one glossary.

The PDF and HTML reports go to the MSP's customers. Em and en dashes read as
translated English in Norwegian, so each sentence takes a colon, a full stop, a
comma or parentheses instead. The 0-100 score where 100 is best was labelled a
risk score, so a strong tenant read as a high risk: it is Sikkerhetsscore, and
its letter is a Karakter. tests/test_norwegian_copy.py holds the same line for
the interface; these tests hold it for the report engine.

A lone em dash standing in for an empty value is a symbol, not prose, and is
the one dash allowed.
"""

from __future__ import annotations

import ast
import html
import pathlib
import re

import pytest

from app.reports.i18n import TRANSLATIONS

ROOT = pathlib.Path(__file__).resolve().parent.parent
DASHES = ("\N{EM DASH}", "\N{EN DASH}")
PLACEHOLDER = "\N{EM DASH}"

# Modules whose string literals reach a report or the report e-mail.
MODULES = (
    "app/reports/compliance.py",
    "app/reports/risk.py",
    "app/reports/evidence.py",
    "app/reports/recommendations.py",
    "app/reports/summary.py",
    "app/reports/generator.py",
    "app/core/email_sender.py",
)
TEMPLATES = (
    "app/reports/templates/report_customer.html.j2",
    "app/reports/templates/report_tech.html.j2",
)
_LOGGERS = {"log", "logger"}

# Jinja, HTML, CSS and script comments: nothing in them reaches the reader.
_COMMENTS = re.compile(r"\{#.*?#\}|<!--.*?-->|/\*.*?\*/|^\s*//[^\n]*", re.S | re.M)
# The empty-value placeholder: a template literal that is only the dash, or the
# dash as the whole content between tags or {% %} blocks. Not between two {{ }}
# expressions: "{{ a }} — {{ b }}" is a dash used as punctuation.
_PLACEHOLDERS = re.compile(r"(['\"])\N{EM DASH}\1|(?:(?<=>)|(?<=%\}))\N{EM DASH}(?=<|\{%)")


def _has_dash(text: str) -> bool:
    return text != PLACEHOLDER and any(d in text for d in DASHES)


def _norwegian() -> dict[str, str]:
    return {key: values["no"] for key, values in TRANSLATIONS.items() if "no" in values}


def _literals(path: str) -> list[tuple[int, str]]:
    """String constants a reader can see: not docstrings, not log messages."""
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    hidden: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                hidden.add(id(first.value))
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in _LOGGERS
        ):
            hidden.update(id(sub) for sub in ast.walk(node))
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in hidden
    ]


def _template_text(path: str) -> str:
    """The template without its comments, with &mdash; and &ndash; as characters."""
    text = _COMMENTS.sub("", (ROOT / path).read_text(encoding="utf-8"))
    return html.unescape(text)


def test_no_dashes_in_the_norwegian_translations():
    dashed = sorted(key for key, value in _norwegian().items() if _has_dash(value))
    assert not dashed, f"Norwegian report strings with an em or en dash: {dashed}"


@pytest.mark.parametrize("path", MODULES)
def test_no_dashes_in_report_literals(path):
    dashed = [f"line {line}: {text!r}" for line, text in _literals(path) if _has_dash(text)]
    assert not dashed, f"{path} has text with an em or en dash:\n" + "\n".join(dashed)


@pytest.mark.parametrize("path", TEMPLATES)
def test_no_dashes_in_report_templates(path):
    text = _PLACEHOLDERS.sub("", _template_text(path))
    dashed = [line.strip() for line in text.splitlines() if _has_dash(line)]
    assert not dashed, f"{path} has text with an em or en dash:\n" + "\n".join(dashed)


def test_the_placeholder_exemption_is_only_a_lone_em_dash():
    # The exemption must not swallow prose that happens to start with a dash.
    assert not _has_dash(PLACEHOLDER)
    assert _has_dash("\N{EN DASH}")
    assert _has_dash(f"{PLACEHOLDER} ")
    assert _PLACEHOLDERS.sub("", "<td>\N{EM DASH}</td>") == "<td></td>"
    assert _PLACEHOLDERS.sub("", "{% else %}\N{EM DASH}{% endif %}") == "{% else %}{% endif %}"
    assert _PLACEHOLDERS.sub("", "{{ x or '\N{EM DASH}' }}") == "{{ x or  }}"
    for prose in (
        "<td>Ingen data \N{EM DASH} kjør på nytt</td>",
        "{{ t.title }} \N{EM DASH} {{ customer }}",
        "<span>\n  \N{EM DASH} {{ t.note }}</span>",
        "{% if x %} \N{EM DASH} {{ t.note }}{% endif %}",
    ):
        assert _has_dash(_PLACEHOLDERS.sub("", prose)), prose


@pytest.mark.parametrize(
    ("pattern", "use"),
    [
        (r"\b[Rr]isikoscore", "Sikkerhetsscore (the 0-100 score, 100 is best)"),
        (r"\b[Rr]isikograd", "Karakter (the letter grade)"),
        (r"(?<!tidligere )\bAzure AD\b", "Entra ID"),
    ],
)
def test_the_glossary_holds(pattern, use):
    found = re.compile(pattern)
    hits = sorted(f"i18n:{key}" for key, value in _norwegian().items() if found.search(value))
    hits += [
        f"{path}:{line}" for path in MODULES for line, text in _literals(path) if found.search(text)
    ]
    hits += [path for path in TEMPLATES if found.search(_template_text(path))]
    assert not hits, f"{hits} use {pattern!r}; write {use}"

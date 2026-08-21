"""Guards against nested Streamlit expanders in the frontend.

Streamlit raises StreamlitAPIException at render time when an expander is
created inside another expander, which takes down the whole page rather than
degrading. This is invisible to import checks and to ruff, and it reaches the
user only when the containing tab is opened, so it is checked statically here.
"""

import ast
import collections
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[1] / "src" / "frontend"


def _call_name(node: ast.Call):
    """Return the called name for a Call node, attribute or bare."""
    return getattr(node.func, "attr", None) or getattr(node.func, "id", None)


def _build_index():
    """Index frontend functions, their calls, and which create expanders."""
    defined, calls, creates = {}, collections.defaultdict(set), set()
    for path in sorted(FRONTEND.glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            defined[node.name] = path.name
            for sub in ast.walk(node):
                if not isinstance(sub, ast.Call):
                    continue
                name = _call_name(sub)
                if name == "expander":
                    creates.add(node.name)
                elif name:
                    calls[node.name].add(name)
    return defined, calls, creates


def _creates_expander(fn, defined, calls, creates, seen=None):
    """Report whether fn opens an expander directly or via anything it calls."""
    seen = seen or set()
    if fn in seen:
        return False
    seen.add(fn)
    if fn in creates:
        return True
    return any(
        _creates_expander(callee, defined, calls, creates, seen)
        for callee in calls.get(fn, ())
        if callee in defined
    )


def _find_nested():
    """Return a list of human-readable nested-expander findings."""
    defined, calls, creates = _build_index()
    findings = []
    for path in sorted(FRONTEND.glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.With):
                continue
            opens_expander = any(
                isinstance(item.context_expr, ast.Call)
                and _call_name(item.context_expr) == "expander"
                for item in node.items
            )
            if not opens_expander:
                continue
            for inner in ast.walk(node):
                if not isinstance(inner, ast.Call):
                    continue
                name = _call_name(inner)
                if name == "expander" and inner.lineno != node.lineno:
                    findings.append(
                        f"{path.name}:{inner.lineno} expander inside the "
                        f"expander opened at line {node.lineno}"
                    )
                elif name in defined and _creates_expander(
                    name, defined, calls, creates
                ):
                    findings.append(
                        f"{path.name}:{inner.lineno} calls {name}(), which opens "
                        f"an expander, inside the expander at line {node.lineno}"
                    )
    return findings


def test_frontend_directory_is_present():
    assert FRONTEND.is_dir(), f"frontend not found at {FRONTEND}"


def test_every_frontend_module_parses():
    for path in FRONTEND.glob("*.py"):
        ast.parse(path.read_text())


def test_no_nested_expanders():
    findings = _find_nested()
    assert not findings, "Nested expanders found:\n  " + "\n  ".join(findings)


@pytest.mark.parametrize("module", ["streamlit_app.py", "evidence.py", "sidebar.py"])
def test_named_modules_are_scanned(module):
    assert (FRONTEND / module).exists()

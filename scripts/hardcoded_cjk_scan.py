"""Gatekeeper: find hard-coded CJK strings that never reach ``tr()`` (v0.38.0).

A string literal containing Chinese that is *not* the argument of a ``tr(...)``
call (and is not a docstring) will show up in Chinese even when the UI language
is English — the single biggest blocker to a proper release.  This AST scan
lists every such literal so they can be wrapped in ``tr()`` (or whitelisted when
the Chinese is legitimate data, not UI text).

Scope: the app entry file + ui/ widgets/ dialogs/ controllers/ services/.
Excluded outright: i18n/ (the dictionaries), scripts/, build/, dist/,
data_samples/, __pycache__.

Whitelisting legitimate data-layer Chinese:
  * end-of-line ``# noqa: cjk`` on the string's first or last line, or
  * a whole file listed in ``FILE_WHITELIST`` below.

Deferred contexts: strings passed to ``log(...)`` or a ``messagebox`` /
``_mb`` dialog are the v0.38.1 localisation batch, so by default they are NOT
counted (they'll be wrapped in ``tr()`` then, which excludes them anyway).
Pass ``--strict`` to count them too (used to verify v0.38.1 completeness).

Usage::

    python scripts/hardcoded_cjk_scan.py            # static-UI gate (v0.38.0)
    python scripts/hardcoded_cjk_scan.py --strict    # include log/messagebox
    python scripts/hardcoded_cjk_scan.py --dump P    # write violations JSON to P

Console printing of CJK mangles on Windows, so use ``--dump`` and read the file.
Exit code is non-zero while any violation remains, so this can gate regression.
"""
from __future__ import annotations

import argparse
import ast
import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Directories (top-level segment) never scanned.
EXCLUDE_TOP = {"i18n", "scripts", "build", "dist", "data_samples", "__pycache__",
               ".git", ".venv", "venv"}

# In-scope top-level segments (plus the app entry file at the root).
INCLUDE_TOP = {"ui", "widgets", "dialogs", "controllers", "services"}
ENTRY_FILE = "StoryMaster.py"

# Whole files exempt from the scan (relative POSIX paths). Keep this list short
# and justified — each entry is a promise that its Chinese is data, not UI.
FILE_WHITELIST: set[str] = set()

_CJK = re.compile(r"[一-鿿]")          # CJK unified ideographs
_NOQA = re.compile(r"#\s*noqa:\s*cjk\b")

# Calls whose CJK string arguments are deferred to the v0.38.1 batch.
_DEFERRED_ATTRS = {"log", "showinfo", "showwarning", "showerror",
                   "askyesno", "askokcancel", "askquestion", "askyesnocancel"}
_DEFERRED_NAMES = {"log"}


def _in_scope(rel: str) -> bool:
    if rel == ENTRY_FILE:
        return True
    top = rel.split("/", 1)[0]
    return top in INCLUDE_TOP


def _docstring_ids(tree: ast.AST) -> set[int]:
    """id() of every Constant that is a module/class/function docstring."""
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            body = getattr(node, "body", None) or []
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                out.add(id(body[0].value))
    return out


def _tr_arg_ids(tree: ast.AST) -> set[int]:
    """id() of *plain* string Constants that are a ``tr("literal")`` argument.

    NOTE: only plain ``Constant`` args are exempted.  ``tr(f"...")`` is NOT —
    an f-string builds a key that is never in the dictionary, so tr() returns
    the raw f-string (Chinese) in every non-mother-tongue language.  Its CJK
    parts are therefore left in the violation set (see ``_tr_fstring_part_ids``)
    so the gate flags them; the fix is ``tr("...{x}").format(x=...)``.
    """
    out: set[int] = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "tr" and node.args):
            a = node.args[0]
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                out.add(id(a))
    return out


def _tr_fstring_part_ids(tree: ast.AST) -> set[int]:
    """id() of CJK Constant parts inside a ``tr(f"...")`` call (broken keys)."""
    out: set[int] = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "tr" and node.args
                and isinstance(node.args[0], ast.JoinedStr)):
            for part in node.args[0].values:
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    out.add(id(part))
    return out


def _deferred_arg_ids(tree: ast.AST) -> set[int]:
    """id() of string Constants inside a log()/messagebox() call subtree."""
    out: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        attr = f.attr if isinstance(f, ast.Attribute) else None
        name = f.id if isinstance(f, ast.Name) else None
        if attr in _DEFERRED_ATTRS or name in _DEFERRED_NAMES:
            for sub in ast.walk(node):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    out.add(id(sub))
    return out


def scan_file(path: Path, strict: bool = False) -> list[dict]:
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines()
    try:
        tree = ast.parse(src, str(path))
    except SyntaxError:
        return []
    skip = _docstring_ids(tree) | _tr_arg_ids(tree)
    if not strict:
        skip |= _deferred_arg_ids(tree)
    fstring_parts = _tr_fstring_part_ids(tree)

    out: list[dict] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if id(node) in skip:
            continue
        if not _CJK.search(node.value):
            continue
        # Line-level whitelist: # noqa: cjk on the first or last source line.
        lo = node.lineno
        hi = getattr(node, "end_lineno", lo) or lo
        span = "\n".join(lines[lo - 1:hi])
        if _NOQA.search(span):
            continue
        out.append({
            "line": lo,
            "col": node.col_offset,
            "text": node.value[:60].replace("\n", "⏎"),
            "reason": "tr(f-string)" if id(node) in fstring_parts else "hardcoded",
        })
    return out


def iter_files():
    for f in glob.glob(str(ROOT / "**" / "*.py"), recursive=True):
        rel = Path(f).relative_to(ROOT).as_posix()
        top = rel.split("/", 1)[0]
        if top in EXCLUDE_TOP:
            continue
        if not _in_scope(rel):
            continue
        if rel in FILE_WHITELIST:
            continue
        yield rel, Path(f)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", metavar="PATH", default=None,
                    help="write the full violation list (JSON) to PATH")
    ap.add_argument("--strict", action="store_true",
                    help="also count log()/messagebox strings (v0.38.1 scope)")
    args = ap.parse_args()

    findings: dict[str, list[dict]] = {}
    total = 0
    for rel, path in iter_files():
        v = scan_file(path, strict=args.strict)
        if v:
            findings[rel] = v
            total += len(v)

    print(f"files scanned with violations : {len(findings)}")
    print(f"hard-coded CJK literals       : {total}")
    # Per-file counts are ASCII-safe to print; the strings themselves are not.
    for rel in sorted(findings):
        print(f"  {rel}: {len(findings[rel])}")

    if args.dump:
        Path(args.dump).write_text(
            json.dumps(findings, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"dumped violations -> {args.dump}")

    if total:
        print(f"[FAIL] {total} hard-coded CJK literal(s) — wrap in tr() or whitelist")
        return 1
    print("[PASS] no hard-coded CJK literals")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

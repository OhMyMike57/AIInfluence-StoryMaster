"""Gatekeeper #2: catch the ``tr(var)`` display-leak blind spot (v0.38.0 收尾).

``i18n_coverage_check`` only sees *literal* ``tr("...")`` keys.  A display string
kept in a module-level dict/list and translated at use via ``tr(dict[k])`` or
``tr(var)`` is invisible to it — if its key was never added to ``en.py`` it shows
Chinese in English mode (exactly how the Database column headers leaked).

This scan flags every CJK string literal that is **not** in ``en.STRINGS`` and is
**not** in a benign context: a ``tr("literal")`` arg, a docstring, or a deferred
``log()`` / ``messagebox`` call (the v0.38.1 batch).  What remains is a display
value that must either be surfaced as a literal ``tr("...")`` (e.g. a function
returning ``{k: tr("中文")}``) or listed in ``INTENTIONAL`` below.

Fix a hit by making the string a literal ``tr("...")`` (preferred — then the
coverage checker enforces it) rather than adding it here.
"""
from __future__ import annotations

import ast
import glob
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from i18n import en as ENMOD  # noqa: E402

_CJK = re.compile(r"[一-鿿]")
EXCLUDE_TOP = {"i18n", "scripts", "build", "dist", "data_samples", "__pycache__",
               ".git", ".venv", "venv"}
INCLUDE_TOP = {"ui", "widgets", "dialogs", "controllers", "services"}
ENTRY_FILE = "StoryMaster.py"
_DEFERRED_ATTRS = {"log", "showinfo", "showwarning", "showerror",
                   "askyesno", "askokcancel", "askquestion", "askyesnocancel"}

# Legitimately-untranslated CJK that is NOT display text needing localization:
#   • canonical data markers written to / parsed from the save JSON,
#   • theme-name tails (transitional; the theme list is replaced in v0.39.0),
#   • language names (i18n convention: always shown in their own script).
INTENTIONAL = {
    "[劇情記憶]", "[消息傳聞]", "[軍事情報]",
    "Sandstone（暖灰，預設）", "Journal（米黃紙質）", "Litera（簡潔白）",
    "Yeti（冷灰）", "Flatly（扁平清爽）", "Cosmo（現代藍）", "United（橘紅）",
    "Morph（立體）", "Darkly（暗色）", "Solar（暗橘）", "Cyborg（暗科技）",
    "繁體中文", "简体中文",
    # 說話者欄的搜尋同義詞 (widgets/speaker_field.py) — matched against what the
    # user types, never displayed, so they are input data rather than UI text.
    "陌生", "不明",
}


def _in_scope(rel: str) -> bool:
    return rel == ENTRY_FILE or rel.split("/", 1)[0] in INCLUDE_TOP


def _benign_ids(tree: ast.AST) -> set[int]:
    """Constants that are a tr('literal') arg, a docstring, or in a deferred call."""
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            b = getattr(node, "body", None) or []
            if (b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant)
                    and isinstance(b[0].value.value, str)):
                out.add(id(b[0].value))
        if isinstance(node, ast.Call):
            f = node.func
            attr = f.attr if isinstance(f, ast.Attribute) else None
            name = f.id if isinstance(f, ast.Name) else None
            if name == "tr" and node.args and isinstance(node.args[0], ast.Constant):
                out.add(id(node.args[0]))
            if attr in _DEFERRED_ATTRS or name == "log":
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                        out.add(id(sub))
    return out


def scan_file(path: Path) -> list[tuple[int, str]]:
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    benign = _benign_ids(tree)
    out = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if id(node) in benign or not _CJK.search(node.value):
            continue
        v = node.value
        if v in ENMOD.STRINGS or v in INTENTIONAL:
            continue
        out.append((node.lineno, v))
    return out


def main() -> int:
    findings: dict[str, list[tuple[int, str]]] = {}
    for f in glob.glob(str(ROOT / "**" / "*.py"), recursive=True):
        rel = Path(f).relative_to(ROOT).as_posix()
        if rel.split("/", 1)[0] in EXCLUDE_TOP or not _in_scope(rel):
            continue
        v = scan_file(Path(f))
        if v:
            findings[rel] = v
    total = sum(len(v) for v in findings.values())
    print(f"files with tr(var) display leaks : {len(findings)}")
    print(f"un-translated display literals    : {total}")
    for rel in sorted(findings):
        print(f"  {rel}: {len(findings[rel])}")
    if total:
        print("[FAIL] display CJK not in en.STRINGS — surface as literal tr(\"...\") "
              "or add to INTENTIONAL")
        return 1
    print("[PASS] no tr(var) display leaks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

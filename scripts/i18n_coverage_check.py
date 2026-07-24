"""i18n coverage audit for the trilingual UI (zh_TW base / zh_CN / en).

Statically scans every ``tr("literal")`` call site (AST-based, so it ignores
f-string keys which can't be statically translated) and reports how many keys
are missing from the zh_CN and en dictionaries.

Usage::

    python scripts/i18n_coverage_check.py            # summary + exit code
    python scripts/i18n_coverage_check.py --dump P   # also write missing keys
                                                     # (JSON) to path P

Exit code is 0 unless ``--min PCT`` is given and coverage falls below it, so
it can act as a soft regression gate once coverage is driven up.
"""
from __future__ import annotations

import argparse
import ast
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from i18n import zh_CN, en  # noqa: E402


def collect_static_keys() -> tuple[set[str], set[str]]:
    """Return ``(static_keys, files_with_fstring_keys)``."""
    keys: set[str] = set()
    fstr_files: set[str] = set()
    for f in glob.glob(str(ROOT / "**" / "*.py"), recursive=True):
        rel = Path(f).relative_to(ROOT).as_posix()
        if rel.split("/", 1)[0] in ("i18n", "scripts", "build", "dist"):
            continue
        try:
            tree = ast.parse(Path(f).read_text(encoding="utf-8"), f)
        except Exception:
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "tr" and node.args):
                a = node.args[0]
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    keys.add(a.value)
                elif isinstance(a, ast.JoinedStr):
                    fstr_files.add(rel)
    return keys, fstr_files


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", metavar="PATH", default=None,
                    help="write missing-key lists (JSON) to PATH")
    ap.add_argument("--min", type=float, default=0.0,
                    help="fail if either language's coverage < this percent")
    args = ap.parse_args()

    keys, fstr_files = collect_static_keys()
    total = len(keys)
    miss_en = sorted(k for k in keys if k not in en.STRINGS)

    # zh_CN is glyph-only conversion of the zh_TW base, so a key that is
    # identical under Traditional→Simplified needs no dict entry (tr() falls
    # back to the key and renders correctly).  When zhconv is available we
    # treat such keys as covered; otherwise we fall back to dict-only.
    try:
        import zhconv  # type: ignore
        def _needs_cn(k: str) -> bool:
            return zhconv.convert(k, "zh-hans") != k
    except Exception:
        def _needs_cn(k: str) -> bool:
            return True
    miss_cn = sorted(k for k in keys if k not in zh_CN.STRINGS and _needs_cn(k))
    cov_en = 100.0 * (total - len(miss_en)) / total if total else 100.0
    cov_cn = 100.0 * (total - len(miss_cn)) / total if total else 100.0

    print(f"static tr() literal keys : {total}")
    print(f"en  coverage             : {total - len(miss_en)}/{total}"
          f"  ({cov_en:.1f}%)   missing {len(miss_en)}")
    print(f"zh_CN coverage           : {total - len(miss_cn)}/{total}"
          f"  ({cov_cn:.1f}%)   missing {len(miss_cn)}")
    print(f"files with f-string keys : {len(fstr_files)} (not statically translatable)")

    if args.dump:
        Path(args.dump).write_text(
            json.dumps({"missing_en": miss_en, "missing_zh_CN": miss_cn},
                       ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"dumped missing keys -> {args.dump}")

    if args.min and (cov_en < args.min or cov_cn < args.min):
        print(f"[FAIL] coverage below {args.min:.0f}%")
        return 1
    print("[PASS] i18n coverage check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

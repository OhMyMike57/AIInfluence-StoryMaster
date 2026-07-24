"""Unit checks for services/doc_staging.py (v0.36.0 主工作區暫存機制).

Run: python scripts/doc_staging_check.py
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.doc_staging import DocStaging, list_delta  # noqa: E402

FAILS = []


def check(label, cond):
    print(f"  {'ok ' if cond else 'FAIL'} - {label}")
    if not cond:
        FAILS.append(label)


def _loader(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return None


def main():
    tmp = Path(tempfile.mkdtemp(prefix="docstage_"))
    f1 = tmp / "elga.json"
    f1.write_text(json.dumps({"Name": "埃爾加", "TrustLevel": 5,
                              "KnownInfo": ["a", "b"]}, ensure_ascii=False),
                  encoding="utf-8")

    st = DocStaging()

    # checkout creates working copy + baseline; same dict returned on re-checkout
    d = st.checkout(f1, _loader)
    check("checkout loads disk data", d["TrustLevel"] == 5)
    check("checkout not dirty yet", not st.is_dirty(f1))
    d2 = st.checkout(f1, _loader)
    check("re-checkout returns same working copy", d is d2)

    # mutate → dirty; peek returns the staged doc
    d["TrustLevel"] = 0
    check("mutation makes it dirty", st.is_dirty(f1))
    check("peek returns staged view", st.peek(f1, _loader)["TrustLevel"] == 0)
    check("disk untouched before commit", _loader(f1)["TrustLevel"] == 5)

    # diff_all reports only the changed field
    diff = st.diff_all(lambda p: "埃爾加")
    check("diff has exactly 1 record", len(diff) == 1)
    check("diff record correct", diff[0]["field"] == "TrustLevel"
          and diff[0]["old"] == 5 and diff[0]["new"] == 0)

    # revert to base value → prune_clean drops the entry
    d["TrustLevel"] = 5
    st.prune_clean()
    check("no-op edit pruned", f1 not in st.pending)

    # list_delta derives owned adds/removes from staged vs base
    d = st.checkout(f1, _loader)
    d["KnownInfo"] = ["a", "c"]          # -b +c
    adds, removes = list_delta(st.base[f1], st.pending[f1], "KnownInfo")
    check("list_delta adds", adds == {"c"})
    check("list_delta removes", removes == {"b"})

    # put replaces wholesale but keeps the original baseline
    st.put(f1, {"Name": "埃爾加", "TrustLevel": 9, "KnownInfo": ["a", "b"]}, _loader)
    diff = st.diff_all(lambda p: "x")
    check("put keeps original baseline (diff vs disk)",
          len(diff) == 1 and diff[0]["field"] == "TrustLevel" and diff[0]["new"] == 9)

    # mtime conflict detection
    check("no conflict initially", st.conflicted_paths() == [])
    time.sleep(0.05)
    f1.write_text(json.dumps({"Name": "埃爾加", "TrustLevel": 5,
                              "KnownInfo": ["a", "b"]}), encoding="utf-8")
    os.utime(f1, (time.time() + 5, time.time() + 5))
    check("external write detected as conflict", st.conflicted_paths() == [f1])

    # commit writes pending and clears staging
    wrote = {}
    def _writer(p, doc):
        wrote[Path(p)] = doc
        Path(p).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        return True
    results = st.commit_all(_writer)
    check("commit reports success", results.get(f1) is None)
    check("commit wrote staged doc", wrote[f1]["TrustLevel"] == 9)
    check("staging empty after commit", not st.pending and not st.base)

    # failed write stays staged
    d = st.checkout(f1, _loader)
    d["TrustLevel"] = 1
    results = st.commit_all(lambda p, doc: False)
    check("failed write reported", results.get(f1) == "writer returned False")
    check("failed write stays staged", st.is_dirty(f1))

    # discard drops everything
    n = st.discard()
    check("discard clears all", n == 1 and not st.pending)

    print()
    if FAILS:
        print(f"[FAIL] doc_staging check: {len(FAILS)} failing")
        sys.exit(1)
    print("[PASS] doc_staging check passed")


if __name__ == "__main__":
    main()

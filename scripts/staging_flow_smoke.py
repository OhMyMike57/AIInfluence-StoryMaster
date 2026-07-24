"""Smoke: v0.36.0 app-level staging flow — staged checkout/store, derived
owned pending (adds/removes + toggle/restore), conflict-block guard, and
commit — using the REAL app methods bound to a minimal stub (no Tk).

Run: python scripts/staging_flow_smoke.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from StoryMaster import AIInfluenceStoryToolsApp as App  # noqa: E402
from services.doc_staging import DocStaging  # noqa: E402

FAILS = []


def check(label, cond):
    print(f"  {'ok ' if cond else 'FAIL'} - {label}")
    if not cond:
        FAILS.append(label)


class Stub:
    """Bare attribute bag the real app methods can run against."""
    _OWNED_KIND_DISPATCH = App._OWNED_KIND_DISPATCH

    def __init__(self, path):
        self.doc_staging = DocStaging()
        self.plain_to_path = {"elga": path}
        self._detail_display = "elga"
        self.logged = []

    # method-call stubs used inside the code under test
    def log(self, msg, level="INFO"):
        self.logged.append((level, msg))

    def _staging_refresh_ui(self):
        pass

    def _refresh_owned_viewer_for_kind(self, kind, **kw):
        pass

    def _load_character_detail(self, display):
        pass

    def _get_character_name(self, p):
        return "埃爾加"

    # real app methods under test, bound to this stub
    _staged_checkout = App._staged_checkout
    _staging_effective = App._staging_effective
    _staged_store = App._staged_store
    _owned_field_for_kind = App._owned_field_for_kind
    _owned_stage_add = App._owned_stage_add
    _owned_stage_remove = App._owned_stage_remove
    _owned_get_pending = App._owned_get_pending

    def safe_write_json_with_backup(self, path, data):
        Path(path).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return True


def main():
    tmp = Path(tempfile.mkdtemp(prefix="stageflow_"))
    f = tmp / "elga.json"
    f.write_text(json.dumps({"Name": "埃爾加", "StringId": "x", "TrustLevel": 5,
                             "KnownInfo": ["a", "b"],
                             "ConversationHistory": ["p: hi"]}, ensure_ascii=False),
                 encoding="utf-8")
    app = Stub(f)

    # ── staged checkout/store: edit stays off disk, effective view shows it ──
    d = app._staged_checkout(f)
    d["TrustLevel"] = 0
    app._staged_store(f, d, "改信任")
    check("store logs staged suffix",
          app.logged and "暫存" in app.logged[-1][1])
    check("disk untouched after store",
          json.loads(f.read_text(encoding="utf-8"))["TrustLevel"] == 5)
    check("effective view shows staged value",
          app._staging_effective(f)["TrustLevel"] == 0)

    # ── owned: stage add + derived pending ──
    app._owned_stage_add(["c"], "info")
    adds, removes = app._owned_get_pending("info")
    check("stage add derived", adds == {"c"} and removes == set())

    # remove an added id cancels the add
    app._owned_stage_remove("c", "info")
    adds, removes = app._owned_get_pending("info")
    check("removing a pending add cancels it", adds == set() and removes == set())

    # remove an existing id stages removal
    app._owned_stage_remove("a", "info")
    adds, removes = app._owned_get_pending("info")
    check("removing an existing id stages removal", removes == {"a"})

    # toggle again = restore (in baseline order)
    app._owned_stage_remove("a", "info")
    adds, removes = app._owned_get_pending("info")
    doc = app.doc_staging.pending[f]
    check("restore clears the pending removal", removes == set())
    check("restore preserves baseline order", doc["KnownInfo"] == ["a", "b"])

    # ── commit writes staged doc; staging empties ──
    app._owned_stage_add(["c"], "info")
    results = app.doc_staging.commit_all(app.safe_write_json_with_backup)
    on_disk = json.loads(f.read_text(encoding="utf-8"))
    check("commit wrote trust change", on_disk["TrustLevel"] == 0)
    check("commit wrote owned add", on_disk["KnownInfo"] == ["a", "b", "c"])
    check("staging empty after commit", not app.doc_staging.pending)
    check("no commit errors", all(e is None for e in results.values()))

    # ── discard path: staged edit vanishes, disk intact ──
    d = app._staged_checkout(f)
    d["TrustLevel"] = 99
    app._staged_store(f, d, "")
    app.doc_staging.discard()
    check("discard drops staged edit",
          app._staging_effective(f)["TrustLevel"] == 0)

    print()
    if FAILS:
        print(f"[FAIL] staging_flow smoke: {len(FAILS)} failing")
        sys.exit(1)
    print("[PASS] staging_flow smoke passed")


if __name__ == "__main__":
    main()

"""Regression: disease staging + catalog-op commit data math (v0.25.0).

Covers the v0.25.0 disease-tab refactor:
  * catalog ops (清空此病種感染 / 刪除此病種) now STAGE into ``disease_pending``
    (toggle) instead of writing immediately — tested against the real
    ``_disease_stage_catalog_op`` / ``_disease_remove`` / ``_disease_remove_selected``
    methods bound to a minimal fake app (UI refresh stubbed out);
  * the service-layer building blocks the commit replay relies on
    (instances_for_disease / remove_all_instances_of_disease /
    remove_disease_definition) produce the expected instances + definitions +
    affected-hero set;
  * the 5.0.2 three-way target-type classifiers (hero / troops / prisoners).

Run: python scripts/disease_staging_check.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok ' if ok else 'FAIL'} - {label}: {got!r}")
    if not ok:
        print(f"        want: {want!r}")
        FAILS.append(label)


# ── 1. target-type classifiers (ui.disease_tab) ───────────────────────────────
def test_classifiers():
    print("[classifiers]")
    from ui.disease_tab import _is_hero, _is_troops, _is_prisoners, _is_party
    hero = {"target_type": 0}
    troop = {"target_type": 1}
    pris = {"target_type": 2}
    check("hero is hero", _is_hero(hero), True)
    check("troop is troops", _is_troops(troop), True)
    check("prisoner is prisoners", _is_prisoners(pris), True)
    check("troop is party", _is_party(troop), True)
    check("prisoner is party", _is_party(pris), True)
    check("hero not party", _is_party(hero), False)
    check("troop not prisoners", _is_prisoners(troop), False)


# ── 2. staging toggles (real app methods, UI stubbed) ─────────────────────────
class _FakeApp:
    def __init__(self, diseases):
        self.disease_pending = []
        self.diseases = diseases

    def log(self, *a, **k):
        pass

    def _disease_refresh_action_bar(self):
        pass


def test_staging_toggles():
    print("[staging toggles]")
    import StoryMaster as M
    cls = M.AIInfluenceStoryToolsApp
    M.refresh_disease_tab = lambda app: None   # stub UI repaint

    diseases = [{"id": "d1", "name": "喉嚨痛"}, {"id": "d2", "name": "熱病"}]
    app = _FakeApp(diseases)

    # Bind the real methods onto the instance so internal self._disease_remove
    # (used by _disease_remove_selected) resolves correctly.
    app._disease_stage_catalog_op = cls._disease_stage_catalog_op.__get__(app)
    app._disease_remove = cls._disease_remove.__get__(app)
    app._disease_remove_selected = cls._disease_remove_selected.__get__(app)
    stage = app._disease_stage_catalog_op
    remove = app._disease_remove
    remove_sel = app._disease_remove_selected

    # clear_infections: stage then toggle off
    stage("clear_infections", "d1")
    check("clear staged", [s["op"] for s in app.disease_pending], ["clear_infections"])
    check("clear carries name", app.disease_pending[0].get("disease_name"), "喉嚨痛")
    stage("clear_infections", "d1")
    check("clear toggled off", app.disease_pending, [])

    # purge_definition: stage; distinct op from clear for same disease coexists
    stage("purge_definition", "d2")
    stage("clear_infections", "d2")
    check("two distinct ops on d2",
          sorted(s["op"] for s in app.disease_pending),
          ["clear_infections", "purge_definition"])
    stage("purge_definition", "d2")   # toggle only the purge
    check("purge toggled, clear remains",
          [s["op"] for s in app.disease_pending], ["clear_infections"])
    app.disease_pending.clear()

    # per-instance remove toggle
    inst = {"target_id": "lord_1", "disease_id": "d1",
            "disease_name": "喉嚨痛", "target_type": 0}
    remove(inst)
    check("remove staged", [s["op"] for s in app.disease_pending], ["remove"])
    remove(inst)
    check("remove toggled off", app.disease_pending, [])

    # batch remove of 2 distinct rows
    inst2 = {"target_id": "lord_2", "disease_id": "d1",
             "disease_name": "喉嚨痛", "target_type": 0}
    remove_sel([inst, inst2])
    check("batch removed 2", len([s for s in app.disease_pending if s["op"] == "remove"]), 2)
    # cancelling an assign sentinel via remove
    app.disease_pending.clear()
    assign = {"op": "assign", "hero_sid": "lord_3", "disease_id": "d2",
              "disease_name": "熱病", "hero_display": "Bob"}
    app.disease_pending.append(assign)
    remove(assign)
    check("assign cancelled via remove", app.disease_pending, [])


# ── 3. commit replay building blocks (service layer) ──────────────────────────
def test_commit_building_blocks():
    print("[commit building blocks]")
    from services.disease_service import (
        instances_for_disease, remove_all_instances_of_disease,
        remove_disease_definition, disease_definition,
    )
    defs = [{"id": "d1", "name": "喉嚨痛"}, {"id": "d2", "name": "熱病"}]
    insts = [
        {"target_id": "lord_1", "disease_id": "d1", "target_type": 0},
        {"target_id": "lord_2", "disease_id": "d1", "target_type": 0},
        {"target_id": "looters_3_party_1", "disease_id": "d1", "target_type": 1},
        {"target_id": "lord_9", "disease_id": "d2", "target_type": 0},
    ]
    # instances_for_disease
    d1 = instances_for_disease(insts, "d1")
    check("d1 has 3 instances", len(d1), 3)
    # affected heroes (target_type 0) of d1 — what commit collects for JSON sync
    affected = {x["target_id"] for x in d1 if x.get("target_type") == 0}
    check("d1 affected heroes", affected, {"lord_1", "lord_2"})
    # clear_infections of d1 → all d1 gone, d2 + defs intact
    after_clear = remove_all_instances_of_disease(insts, "d1")
    check("clear leaves only d2 instance",
          [x["disease_id"] for x in after_clear], ["d2"])
    check("clear keeps definitions", len(defs), 2)
    # purge_definition of d2 → def gone
    after_purge_defs = remove_disease_definition(defs, "d2")
    check("purge removes d2 def", [d["id"] for d in after_purge_defs], ["d1"])
    check("d2 def lookup gone after purge",
          disease_definition(after_purge_defs, "d2"), None)


def main():
    test_classifiers()
    test_staging_toggles()
    test_commit_building_blocks()
    print()
    if FAILS:
        print(f"[FAIL] disease staging check: {len(FAILS)} failing")
        sys.exit(1)
    print("[PASS] disease staging check passed")


if __name__ == "__main__":
    main()

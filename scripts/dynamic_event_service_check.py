"""Stage D acceptance check for services.dynamic_event_service (event editing).

Covers the Phase 6 Stage D additions:
  1. apply_event_edits — new fields (player_involved / applicable_npcs /
     participating_kingdoms / kingdom_engagement / economic_effects /
     schedule maps) normalise + clamp; non-whitelisted fields stay immutable.
  2. new_event_template — shape, uuid id, +100-day expiry, Initial Event entry.
  3. normalize_economic_effect — float/int coercion + market_price_modifiers.
  4. Commit write-path E2E — delete + edit + new event applied to a temp copy of
     the real 5.0.3 bundle; sibling keys preserved; round-trips on read-back.

Exit 0 + [PASS] when everything holds.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.json_utils import safe_load_json, save_json_file
from services.world_service import data_samples_base
from services.dynamic_event_service import (
    apply_event_edits,
    event_involves_player,
    filter_events,
    new_event_template,
    normalize_economic_effect,
    EDITABLE_EVENT_FIELDS,
    APPLICABLE_NPC_KEYS,
)
from services.diplomacy_service import (
    apply_statement_changes,
    remove_events_cascade,
    write_bundle_update,
)

_DS = data_samples_base(ROOT)
SAMPLE = next(
    (
        _c
        for _ver in ("AIInfluence 5.0.3", "AIInfluence 5.0.2")
        for _c in [_DS / _ver / "save_data" / "oRHQTILfrj64" / "aiinfluence_campaign_diplomacy.json"]
        if _c.exists()
    ),
    _DS / "AIInfluence 5.0.3" / "save_data" / "oRHQTILfrj64" / "aiinfluence_campaign_diplomacy.json",
)

errors: list[str] = []


def check(cond: bool, label: str) -> None:
    print(("  ok  " if cond else "  FAIL") + " - " + label)
    if not cond:
        errors.append(label)


def main() -> int:
    # ── 1. apply_event_edits new fields ──────────────────────────────────
    print("[1] apply_event_edits new fields")
    base = {"id": "x", "type": "political", "creation_campaign_days": 5,
            "kingdom_engagement": {"a": 10}}
    out = apply_event_edits(base, {
        "player_involved": 1,
        "applicable_npcs": ["lords", "lords", "merchants"],
        "participating_kingdoms": ["vlandia", "vlandia"],
        "kingdom_engagement": {"vlandia": 150, "nord": -5, "bad": "x"},
        "next_statement_attempt_days": {},
        "failed_statement_attempts": {},
        "economic_effects": [{"target_type": "kingdom",
                              "prosperity_delta_per_day": "1.2",
                              "duration_days": "21",
                              "market_price_modifiers": [
                                  {"category_id": "grain", "price_change_percent": "-25"}]}],
        # non-whitelisted — must be ignored
        "id": "hacked", "creation_campaign_days": 999,
    })
    check(out["player_involved"] is True, "player_involved coerced to bool")
    check(out["applicable_npcs"] == ["lords", "merchants"], "applicable_npcs dedup")
    check(out["participating_kingdoms"] == ["vlandia"], "participating_kingdoms dedup")
    check(out["kingdom_engagement"] == {"vlandia": 100, "nord": 0},
          "kingdom_engagement clamp 0-100 + drop non-int")
    ee = out["economic_effects"][0]
    check(ee["prosperity_delta_per_day"] == 1.2 and ee["duration_days"] == 21,
          "economic_effects numeric coercion")
    check(ee["market_price_modifiers"][0] == {"category_id": "grain", "price_change_percent": -25.0},
          "market_price_modifiers coercion")
    check(out["id"] == "x" and out["creation_campaign_days"] == 5,
          "id / creation immutable (non-whitelisted dropped)")
    check(set(("player_involved", "applicable_npcs", "participating_kingdoms",
               "kingdom_engagement", "economic_effects",
               "next_statement_attempt_days", "failed_statement_attempts"))
          <= set(EDITABLE_EVENT_FIELDS), "new fields whitelisted")

    # ── 2. new_event_template ────────────────────────────────────────────
    print("[2] new_event_template")
    import uuid
    t = new_event_template(event_type="economic", creation_campaign_days=91100.5,
                           title="T", description="D", importance=12)
    check(t["type"] == "economic" and t["importance"] == 9, "type kept, importance clamped")
    check(abs(t["expiration_campaign_days"] - 91200.5) < 1e-9, "expiry = creation + 100")
    check(t["event_history"][0]["update_reason"] == "Initial Event"
          and t["event_history"][0]["campaign_days"] == 91100.5, "Initial Event entry")
    try:
        uuid.UUID(t["id"]); ok_uuid = True
    except ValueError:
        ok_uuid = False
    check(ok_uuid, "id is a valid uuid4")
    check(all(k in t for k in ("kingdom_engagement", "participating_kingdoms",
                               "applicable_npcs", "economic_effects", "kingdom_statements")),
          "template carries all diplomacy/economic collections")

    # ── 3. normalize_economic_effect ─────────────────────────────────────
    print("[3] normalize_economic_effect")
    n = normalize_economic_effect({"target_type": "kingdom", "income_multiplier": "1.5",
                                   "duration_days": "7.0", "reason": 123,
                                   "market_price_modifiers": [{"category_id": "iron",
                                                               "price_change_percent": "10"}]})
    check(n["income_multiplier"] == 1.5 and n["duration_days"] == 7, "float/int coercion")
    check(n["reason"] == "123", "reason coerced to str")
    check(n["market_price_modifiers"][0]["price_change_percent"] == 10.0, "mpm percent float")

    # ── 4. Commit write-path E2E on a temp bundle copy ───────────────────
    print("[4] commit write-path E2E")
    if not SAMPLE.exists():
        check(False, f"sample bundle not found: {SAMPLE}")
        return _summary()
    tmpdir = Path(tempfile.mkdtemp())
    try:
        tmp = tmpdir / "aiinfluence_campaign_diplomacy.json"
        shutil.copy(SAMPLE, tmp)
        bundle = safe_load_json(tmp)
        evs = bundle["dynamic_events"]
        edit_id, del_id = str(evs[0]["id"]), str(evs[1]["id"])
        edits = {edit_id: {"player_involved": True, "kingdom_engagement": {"vlandia": 77}}}
        deletes = {del_id}
        new_ev = apply_event_edits(
            new_event_template(event_type="economic", creation_campaign_days=91200.0,
                               title="工具新增測試事件"),
            {"applicable_npcs": ["lords", "merchants"], "participating_kingdoms": ["vlandia"]},
        )

        nb, _ = apply_statement_changes(bundle, edits={}, deletes=set(), new=[])
        nb, casc = remove_events_cascade(nb, deletes)
        new_events = []
        for ev in nb.get("dynamic_events", []) or []:
            eid = str(ev.get("id", ""))
            if eid in deletes:
                continue
            new_events.append(apply_event_edits(ev, edits[eid]) if eid in edits else ev)
        new_events.extend([new_ev])
        ok = write_bundle_update(tmp, writer=save_json_file, loader=safe_load_json,
                                 events=new_events, statements=nb.get("kingdom_statements", []),
                                 pressure=nb.get("kingdom_response_pressure"))
        check(bool(ok), "write_bundle_update succeeded")

        rb = safe_load_json(tmp)
        ids = [str(e["id"]) for e in rb["dynamic_events"]]
        check(del_id not in ids, "deleted event removed")
        check(str(new_ev["id"]) in ids, "new event written")
        edited = next(e for e in rb["dynamic_events"] if str(e["id"]) == edit_id)
        check(edited["player_involved"] is True and edited["kingdom_engagement"]["vlandia"] == 77,
              "event edit applied")
        nb2 = next(e for e in rb["dynamic_events"] if str(e["id"]) == str(new_ev["id"]))
        check(nb2["title"] == "工具新增測試事件"
              and nb2["applicable_npcs"] == ["lords", "merchants"]
              and nb2["participating_kingdoms"] == ["vlandia"], "new event fields intact")
        check(all(k in rb for k in ("Version", "kingdom_statements",
                                    "kingdom_response_pressure", "saved_campaign_days", "kingdom_tax")),
              "sibling keys preserved")
        check(casc["statements_removed"] >= 0, "cascade ran (statements_removed reported)")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    # ── 5. player_only filter (R4-S1 fix) ────────────────────────────────
    print("\nplayer_only filter:")
    flagged   = {"id": "a", "player_involved": True,  "characters_involved": []}
    by_char   = {"id": "b", "player_involved": False, "characters_involved": ["lord_1_1", "main_hero"]}
    by_npcs   = {"id": "c", "applicable_npcs": ["main_hero"]}
    unrelated = {"id": "d", "player_involved": False, "characters_involved": ["lord_1_1"]}
    bare      = {"id": "e"}
    pool = [flagged, by_char, by_npcs, unrelated, bare]

    check(event_involves_player(flagged),    "explicit player_involved flag counts")
    check(event_involves_player(by_char),    "main_hero in characters_involved counts (the reported bug)")
    check(event_involves_player(by_npcs),    "main_hero in applicable_npcs counts")
    check(not event_involves_player(unrelated), "unrelated event excluded")
    check(not event_involves_player(bare),   "event without either field excluded")

    got = [e["id"] for e in filter_events(pool, player_only=True)]
    check(got == ["a", "b", "c"], f"filter_events(player_only) keeps a/b/c (got {got})")
    check(len(filter_events(pool, player_only=False)) == 5, "player_only=False keeps everything")

    return _summary()


def _summary() -> int:
    print()
    if errors:
        print(f"[FAIL] dynamic event service check failed ({len(errors)} issue(s))")
        return 1
    print("[PASS] dynamic event service check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

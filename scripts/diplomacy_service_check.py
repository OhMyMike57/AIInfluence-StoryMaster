"""Stage A acceptance check for services.diplomacy_service.

Validates against REAL campaign data (oRHQTILfrj64, AIInfluence 5.0.2):
  1. Enum integrity + name/value normalization.
  2. Top-level statements: parse(embedded=False) → serialize → deep-equal.
  3. Event-embedded statements: parse(embedded=True) → serialize → deep-equal.
  4. settlement_id alignment (3-action comma-join) + unaligned passthrough.
  5. Cross-format conversion (embedded ints → top-level strings).
  6. Edit + re-encode (comma-join rebuild).
  7. Bundle accessors: statements_for_event / remove / clear_pressure_event.
  8. Validators: orphan statements, unknown kingdoms.

Exit 0 + [PASS] when everything holds.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.diplomacy_service import (  # noqa: E402
    DIPLOMATIC_ACTIONS,
    action_name,
    action_value,
    parse_statement,
    parse_statement_with_twin,
    serialize_statement,
    new_statement,
    statement_key,
    statement_keys,
    split_settlement_ids,
    join_settlement_ids,
    bundle_statements,
    statements_for_event,
    remove_statements_of_event,
    clear_pressure_event,
    find_orphan_statements,
    find_unknown_kingdoms,
    find_embedded_twin_index,
    apply_statement_changes,
    remove_events_cascade,
    write_bundle_update,
)

from services.world_service import data_samples_base

# Resolve the sample bundle from the (possibly relocated) data_samples library.
# Pinned to the 5.0.2 campaign: this is a fixture-based regression and the
# assertion counts (statements removed, pressure assignments cleared, …) are
# calibrated against that exact bundle.  5.0.3 falls back only if 5.0.2 is gone.
_DS = data_samples_base(ROOT)
SAMPLE = next(
    (
        _c
        for _ver in ("AIInfluence 5.0.2", "AIInfluence 5.0.3")
        for _c in [_DS / _ver / "save_data" / "oRHQTILfrj64" / "aiinfluence_campaign_diplomacy.json"]
        if _c.exists()
    ),
    _DS / "AIInfluence 5.0.2" / "save_data" / "oRHQTILfrj64" / "aiinfluence_campaign_diplomacy.json",
)

errors: list[str] = []


def check(cond: bool, label: str) -> None:
    print(("  ok  " if cond else "  FAIL") + " - " + label)
    if not cond:
        errors.append(label)


def main() -> int:
    bundle = json.loads(SAMPLE.read_text(encoding="utf-8-sig"))

    # ── 1. Enum ─────────────────────────────────────────────────────────
    print("[1] enum")
    check(len(DIPLOMATIC_ACTIONS) == 28, "28 values")
    check(action_name(14) == "DemandTerritory" and action_name(0) == "None"
          and action_name(27) == "SetKingdomTaxPolicy", "int → name")
    check(action_value("QuarantineSettlement") == 26
          and action_value("ProposePeace") == 2, "name → int")
    check(action_name("demandterritory") == "DemandTerritory", "case-insensitive name")
    check(action_name("99") == "99" and action_value("99") == 99, "unknown numeric passthrough")
    try:
        action_value("NotAnAction")
        check(False, "action_value raises on unknown name")
    except ValueError:
        check(True, "action_value raises on unknown name")

    # ── 2. Top-level round-trip (string actions) ───────────────────────
    print("[2] top-level statements round-trip")
    top = bundle_statements(bundle)
    check(len(top) == 12, f"sample has 12 top-level statements (got {len(top)})")
    bad = 0
    for s in top:
        out = serialize_statement(parse_statement(s, embedded=False), embedded=False)
        if out != s:
            bad += 1
            kdiff = {k for k in set(s) | set(out) if s.get(k) != out.get(k)}
            print(f"        diff @ {statement_key(s)}: {sorted(kdiff)}")
    check(bad == 0, f"all 12 deep-equal after round-trip ({12 - bad}/12)")

    # ── 3. Embedded round-trip (int actions) ───────────────────────────
    print("[3] event-embedded statements round-trip")
    emb_total = emb_bad = 0
    for ev in bundle.get("dynamic_events", []):
        for s in ev.get("kingdom_statements", []) or []:
            emb_total += 1
            out = serialize_statement(parse_statement(s, embedded=True), embedded=True)
            if out != s:
                emb_bad += 1
                kdiff = {k for k in set(s) | set(out) if s.get(k) != out.get(k)}
                print(f"        diff @ {statement_key(s)}: {sorted(kdiff)}")
    check(emb_total > 0, f"embedded statements found ({emb_total})")
    check(emb_bad == 0, f"all {emb_total} deep-equal after round-trip")

    # ── 4. settlement_id alignment ──────────────────────────────────────
    print("[4] settlement_id handling")
    multi = next(s for s in top
                 if isinstance(s.get("settlement_id"), str) and "," in s["settlement_id"])
    m = parse_statement(multi, embedded=False)
    check(m["settlement_ids"] == ["town_V9", None, "castle_V5"],
          f"3-action comma-join aligned → {m['settlement_ids']}")
    check(len(m["action_names"]) == 3, "alignment matches action count")
    # Unaligned case: 2 actions sharing one settlement (embedded battania sample)
    shared = {"kingdom_id": "battania", "actions": [2, 14], "campaign_days": 1.0,
              "settlement_id": "town_EW1"}
    sm = parse_statement(shared, embedded=True)
    check(sm["settlement_ids"] is None and sm["settlement_id_raw"] == "town_EW1",
          "unaligned single value → raw passthrough")
    back = serialize_statement(sm, embedded=True)
    check(back["settlement_id"] == "town_EW1", "unaligned raw survives serialize")
    # join helper directly
    check(join_settlement_ids(["a", None, "c"]) == "a,null,c", "join with null placeholder")
    check(join_settlement_ids(["only"]) == "only", "single action plain value")
    check(join_settlement_ids([None, None]) is None, "all-None → omitted")
    check(split_settlement_ids(None, 2) == ([None, None], None), "absent → vacuous alignment")

    # ── 5. Cross-format conversion ──────────────────────────────────────
    print("[5] cross-format conversion")
    emb_battania = None
    for ev in bundle.get("dynamic_events", []):
        for s in ev.get("kingdom_statements", []) or []:
            if isinstance(s.get("actions"), list) and len(s["actions"]) >= 2:
                emb_battania = s
                break
        if emb_battania:
            break
    cm = parse_statement(emb_battania, embedded=True)
    as_top = serialize_statement(cm, embedded=False)
    check(all(isinstance(a, str) for a in as_top["actions"]),
          f"embedded ints → top-level strings {as_top['actions']}")
    check(as_top.get("action") == as_top["actions"][0], "scalar action = first")
    check("relation_changes" not in as_top and "quarantine_duration_days" not in as_top,
          "embedded-only fields stripped for top-level")
    back_emb = serialize_statement(parse_statement(as_top, embedded=False), embedded=True)
    check(back_emb["actions"] == emb_battania["actions"],
          "…and back to the original int actions")

    # ── 6. Edit + re-encode ─────────────────────────────────────────────
    print("[6] edit + re-encode")
    em = parse_statement(multi, embedded=False)
    em["settlement_ids"][2] = "castle_NEW"
    edited = serialize_statement(em, embedded=False)
    check(edited["settlement_id"] == "town_V9,null,castle_NEW",
          f"comma-join rebuilt → {edited['settlement_id']}")
    em2 = parse_statement(top[0], embedded=False)
    em2["action_names"] = ["DeclareWar"]
    e2 = serialize_statement(em2, embedded=False)
    check(e2["actions"] == ["DeclareWar"] and e2["action"] == "DeclareWar",
          "action list edit reflected in scalar + list")
    nm = new_statement("nord", "evt-123", 91100.5)
    ns = serialize_statement(nm, embedded=False)
    # A fresh, action-less statement omits the plural ``actions`` key, mirroring
    # how 5.0.3 writes pure announcements (NullValueHandling.Ignore); editing in a
    # real action re-materialises it (verified above at "action list edit …").
    check(ns["kingdom_id"] == "nord" and ns["event_id"] == "evt-123"
          and "actions" not in ns and "relation_changes" not in ns,
          "new statement minimal serialize (no-op omits actions)")

    # ── 7. Bundle accessors ─────────────────────────────────────────────
    print("[7] bundle accessors")
    eid = bundle["dynamic_events"][0]["id"]
    linked = statements_for_event(bundle, eid)
    check(len(linked) >= 1, f"statements_for_event({eid[:8]}) → {len(linked)}")
    nb, removed = remove_statements_of_event(bundle, eid)
    check(removed == len(linked)
          and len(bundle_statements(nb)) == 12 - removed
          and len(bundle_statements(bundle)) == 12,
          f"remove_statements_of_event: {removed} removed, original untouched")
    # pressure: pick an event id actually assigned
    assigned = bundle["kingdom_response_pressure"]["ResponseEventIdByKingdom"]
    target_eid = next(iter(assigned.values()))
    n_assigned = sum(1 for v in assigned.values() if v == target_eid)
    pb, affected = clear_pressure_event(bundle, target_eid)
    p_after = pb["kingdom_response_pressure"]
    check(len(affected) == n_assigned
          and all(v != target_eid for v in p_after["ResponseEventIdByKingdom"].values())
          and p_after["PressureByKingdomId"]
              == bundle["kingdom_response_pressure"]["PressureByKingdomId"],
          f"clear_pressure_event: {len(affected)} kingdoms unassigned, pressure values kept")

    # ── 8. Validators ───────────────────────────────────────────────────
    print("[8] validators")
    check(find_orphan_statements(bundle) == [], "real bundle: no orphan statements")
    orphan_b = remove_statements_of_event(bundle, eid)[0]
    orphan_b = dict(orphan_b)
    orphan_b["dynamic_events"] = [e for e in bundle["dynamic_events"] if e["id"] != eid]
    orphan_b["kingdom_statements"] = bundle["kingdom_statements"]  # keep all 12 incl. linked
    orphans = find_orphan_statements(orphan_b)
    check(len(orphans) == len(linked), f"orphans detected after event removal ({len(orphans)})")
    kingdoms = {"empire", "empire_w", "empire_s", "battania", "sturgia",
                "vlandia", "khuzait", "aserai", "nord"}
    check(find_unknown_kingdoms(bundle, kingdoms) == [], "real bundle: all kingdoms known")
    check(find_unknown_kingdoms(bundle, set()) == [], "empty universe disables check")
    missing = find_unknown_kingdoms(bundle, kingdoms - {"nord"})
    check(any(k == "nord" for _w, k in missing), "removing nord from universe flags it")

    # ── 9. Stage C: apply_statement_changes (dual-format sync) ──────────
    print("[9] apply_statement_changes")
    keys = statement_keys(top)
    check(len(set(keys)) == 12, "statement_keys unique for 12 entries")
    i_edit = next(i for i, s in enumerate(top) if s.get("campaign_days") == 91087.42)
    i_del = next(i for i, s in enumerate(top) if s.get("campaign_days") == 91084.25)
    ev07 = next(e for e in bundle["dynamic_events"] if e["id"].startswith("07b4da82"))

    em = parse_statement_with_twin(top[i_edit], ev07)
    check(em.get("_embedded_overlay") is True and len(em["relation_changes"]) > 0,
          "parse_statement_with_twin overlays relation_changes")
    em["statement_text"] = "【C】" + em["statement_text"][:20]
    em["settlement_ids"] = ["castle_C"]
    nm2 = new_statement("sturgia", bundle["dynamic_events"][2]["id"], 91104.0)
    nm2["action_names"] = ["DeclareWar"]
    nm2["target_kingdom_ids"] = ["nord"]

    nb, summ = apply_statement_changes(
        bundle, edits={keys[i_edit]: em}, deletes={keys[i_del]}, new=[nm2])
    check(summ["edited"] == 1 and summ["deleted"] == 1 and summ["added"] == 1
          and summ["twin_updated"] == 1 and summ["twin_removed"] == 1
          and summ["twin_added"] == 1 and not summ["missing_event"],
          f"summary counts {summ}")
    nt = bundle_statements(nb)
    check(len(nt) == 12, "top list 12-1+1")
    es = next(s for s in nt if s.get("campaign_days") == 91087.42)
    check(es["statement_text"].startswith("【C】") and es.get("settlement_id") == "castle_C",
          "top edit applied")
    nev = next(e for e in nb["dynamic_events"] if e["id"].startswith("07b4da82"))
    ti = find_embedded_twin_index(nev, es)
    tw = nev["kingdom_statements"][ti]
    check(tw["statement_text"].startswith("【C】")
          and isinstance(tw["actions"][0], int)
          and len(tw.get("relation_changes", [])) > 0,
          "twin updated: int actions + relation_changes preserved")
    check(find_embedded_twin_index(
        nev, {"kingdom_id": "vlandia", "campaign_days": 91084.25}) is None,
        "deleted statement's twin removed")
    emb_new = nb["dynamic_events"][2]["kingdom_statements"][-1]
    check(emb_new["kingdom_id"] == "sturgia" and emb_new["actions"] == [1],
          "new statement appended embedded (int)")
    check(nt[-1]["actions"] == ["DeclareWar"], "new statement appended top (str)")
    check(len(bundle_statements(bundle)) == 12
          and nb["kingdom_response_pressure"] == bundle["kingdom_response_pressure"]
          and nb["kingdom_tax"] == bundle["kingdom_tax"],
          "original untouched + sibling keys preserved")

    # overlay semantics: plain top model must NOT wipe twin rels
    pm = parse_statement(top[i_edit], embedded=False)
    pm["statement_text"] = "Y" + pm["statement_text"]
    nb_p, _ = apply_statement_changes(bundle, edits={keys[i_edit]: pm})
    ev_p = next(e for e in nb_p["dynamic_events"] if e["id"].startswith("07b4da82"))
    tw_p = ev_p["kingdom_statements"][find_embedded_twin_index(
        ev_p, {"kingdom_id": "nord", "campaign_days": 91087.42})]
    check(len(tw_p.get("relation_changes", [])) > 0,
          "non-overlay edit keeps twin relation_changes")

    # ── 10. Stage C: event-delete cascade + bundle write ────────────────
    print("[10] cascade + write_bundle_update")
    eid8 = next(e["id"] for e in bundle["dynamic_events"] if e["id"].startswith("8ed7fc2e"))
    cb, cs = remove_events_cascade(bundle, {eid8})
    n_linked = len(statements_for_event(bundle, eid8))
    check(cs["statements_removed"] == n_linked and n_linked > 0,
          f"cascade removed {n_linked} linked statements")
    check(len(cs["pressure_cleared"]) == 5
          and all(v != eid8 for v in cb["kingdom_response_pressure"]["ResponseEventIdByKingdom"].values()),
          "cascade cleared 5 pressure assignments")

    import tempfile, shutil
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / SAMPLE.name
        shutil.copy(SAMPLE, tmp)
        def _writer(p, data):
            p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return True
        def _loader(p):
            return json.loads(p.read_text(encoding="utf-8-sig"))
        ok = write_bundle_update(tmp, writer=_writer, loader=_loader,
                                 events=nb["dynamic_events"],
                                 statements=nb["kingdom_statements"])
        after = _loader(tmp)
        check(ok and len(after["kingdom_statements"]) == 12
              and after["kingdom_tax"] == bundle["kingdom_tax"]
              and after["saved_campaign_days"] == bundle["saved_campaign_days"],
              "write_bundle_update: sections replaced, siblings preserved")
        bad = Path(td) / "corrupt.json"
        bad.write_text("NOT JSON", encoding="utf-8")
        check(write_bundle_update(bad, writer=_writer, loader=lambda p: None) is False
              and bad.read_text(encoding="utf-8") == "NOT JSON",
              "corrupt bundle refused, file untouched")

    print()
    if errors:
        print(f"[FAIL] diplomacy service check failed ({len(errors)} issue(s))")
        return 1
    print("[PASS] diplomacy service check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

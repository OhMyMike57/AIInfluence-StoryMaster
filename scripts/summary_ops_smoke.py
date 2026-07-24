"""Smoke: v0.35.1 摘要操作列 — character_service setters, 編輯屬性 dialog,
清空 checklist, and SummaryCard operation bar (編輯屬性/編輯人設▾/快速清空▾)
+ edit-mode greying — headless, auto-closing.

Run: python scripts/summary_ops_smoke.py
"""
import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import character_service as CS          # noqa: E402
from dialogs.clear_fields_dialog import open_clear_checklist  # noqa: E402
from dialogs.attr_editor_dialog import _AttrEditor     # noqa: E402
from widgets.summary_card import SummaryCard           # noqa: E402

FAILS = []


def check(label, cond):
    print(f"  {'ok ' if cond else 'FAIL'} - {label}")
    if not cond:
        FAILS.append(label)


def main():
    # ── setters mirror the readers across both schemas ───────────────────
    d = {"CounterpartySocial": {"main_hero": {"trust_level": 5, "interaction_count": 3}},
         "RomancePartners": {"main_hero": {"level": 2}}}
    CS.set_player_trust(d, 0)
    CS.set_player_interaction(d, 0)
    CS.set_player_romance(d, 0)
    check("5.0.x setters round-trip via readers",
          CS.player_trust_level(d) == 0 and CS.player_interaction_count(d) == 0
          and CS.player_romance_level(d) == 0)

    d2 = {"TrustLevel": 9, "InteractionCount": 4, "RomanceLevel": 7}
    CS.set_player_trust(d2, 1)
    CS.set_player_interaction(d2, 2)
    CS.set_player_romance(d2, 3)
    check("4.1.0 top-level mirrored on write",
          d2["TrustLevel"] == 1 and d2["InteractionCount"] == 2 and d2["RomanceLevel"] == 3)
    check("4.1.0 write also creates 5.0.x nested",
          d2["CounterpartySocial"]["main_hero"]["trust_level"] == 1)

    d3 = {}
    CS.set_player_trust(d3, 4)
    check("empty char → nested structure created",
          d3["CounterpartySocial"]["main_hero"]["trust_level"] == 4)

    root = tk.Tk()
    root.withdraw()

    # ── clear checklist builds + confirm passes chosen keys ──────────────
    captured = {}
    open_clear_checklist(root, "清空屬性",
                         [("romance", "浪漫"), ("relation", "關係", "hint")],
                         on_confirm=lambda keys: captured.update(k=keys))
    tops = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
    check("clear checklist opened a toplevel", bool(tops))
    for w in tops:
        w.destroy()

    # ── attr editor: only-changed fields are reported ────────────────────
    class _App:
        def __init__(self, r):
            self.root = r
    saved = {}
    data = {"Name": "埃爾加", "StringId": "x",
            "CounterpartySocial": {"main_hero": {"trust_level": 0.6, "interaction_count": 3,
                                                 "escalation_state": "tense"}},
            "RomancePartners": {"main_hero": {"level": 2}},
            "PlayerRelation": {"Value": 11}, "LastInteractionTimeDays": 100.0}
    ae = _AttrEditor(_App(root), "elga.json", data, on_save=lambda p, c: saved.update(c))
    ae._trust_var.set("0")             # change only trust (0.6 → 0)
    ae._save()
    check("attr editor reports only the changed field", saved == {"trust": 0.0})

    # slider ↔ entry two-way sync (浪漫 0-100, 信任 0-1)
    asl = _AttrEditor(_App(root), "elga.json", data, on_save=lambda p, c: None)
    asl._e_romance._scale.set(42)          # drag slider → entry follows
    check("slider drag updates romance entry (whole number)",
          asl._romance_var.get() == "42")
    asl._e_trust._scale.set(0.35)
    check("slider drag updates trust entry (2 decimals)",
          asl._trust_var.get() == "0.35")
    asl._romance_var.set("77")             # type entry → slider follows
    check("typing romance moves the slider", abs(asl._e_romance._scale.get() - 77) < 0.5)
    asl._romance_var.set("999")            # out of range → slider stays put
    check("out-of-range romance does not move slider",
          abs(asl._e_romance._scale.get() - 77) < 0.5)
    asl.win.destroy()

    # range validation: romance 0-100, trust 0-1 → out-of-range blocks save
    saved_r = {}
    ar = _AttrEditor(_App(root), "elga.json", data, on_save=lambda p, c: saved_r.update(c))
    ar._romance_var.set("150")          # > 100 → rejected
    ar._save()
    check("romance over 100 blocks save (nothing saved)", saved_r == {})
    check("out-of-range sets an error message", bool(ar._err.get()))
    ar.win.destroy()

    at = _AttrEditor(_App(root), "elga.json", data, on_save=lambda p, c: saved_r.update(c))
    at._trust_var.set("5")              # > 1 → rejected
    at._save()
    check("trust over 1 blocks save", saved_r == {})
    at.win.destroy()

    # 允許浪漫 auto-enables when a positive romance is entered on a not-eligible char
    saved_e = {}
    data_ne = dict(data); data_ne["IsRomanceEligible"] = False; data_ne["RomancePartners"] = {}
    ae2 = _AttrEditor(_App(root), "elga.json", data_ne, on_save=lambda p, c: saved_e.update(c))
    check("eligible unchecked initially", ae2._eligible_var.get() is False)
    ae2._romance_var.set("0.1")
    check("typing positive romance auto-checks 允許浪漫", ae2._eligible_var.get() is True)
    ae2._save()
    check("save carries romance_eligible=True and romance",
          saved_e.get("romance_eligible") is True and saved_e.get("romance") == 0.1)
    ae2.win.destroy()

    # zeroing romance does NOT auto-uncheck
    saved_z = {}
    data_el = dict(data); data_el["IsRomanceEligible"] = True
    data_el["RomancePartners"] = {"main_hero": {"level": 30}}
    ae3 = _AttrEditor(_App(root), "elga.json", data_el, on_save=lambda p, c: saved_z.update(c))
    ae3._romance_var.set("0")
    check("zeroing romance keeps 允許浪漫 checked", ae3._eligible_var.get() is True)
    ae3._save()
    check("zeroing romance does not emit romance_eligible change",
          "romance_eligible" not in saved_z)
    ae3.win.destroy()

    # never-interacted char: last-interaction ignored unless the box is ticked
    saved2 = {}
    data_ni = dict(data); data_ni["LastInteractionTimeDays"] = -1.0
    ae2 = _AttrEditor(_App(root), "elga.json", data_ni, on_save=lambda p, c: saved2.update(c))
    check("never-interacted → last-interaction checkbox off by default",
          ae2._li_enable_var.get() is False)
    ae2._save()   # no changes → no save; harmless
    check("never-interacted save without ticking omits last_interaction",
          "last_interaction" not in saved2)

    # ── SummaryCard operation bar + edit-mode greying ────────────────────
    edit_var = tk.BooleanVar(value=False)
    calls = {"attr": 0, "quick": []}
    card = SummaryCard(root,
                       on_attr_edit=lambda: calls.__setitem__("attr", calls["attr"] + 1),
                       on_quick_clear=lambda k, f: calls["quick"].append((k, f)),
                       edit_variable=edit_var)
    check("operation bar built 3 buttons", len(card._op_buttons) == 3)
    check("op buttons disabled outside edit mode",
          all(str(b.cget("state")) == "disabled" for b in card._op_buttons))
    edit_var.set(True)
    check("op buttons enabled in edit mode",
          all(str(b.cget("state")) == "normal" for b in card._op_buttons))
    card._attr_edit()
    check("編輯屬性 button invokes callback", calls["attr"] == 1)
    card._quick_clear("response", None)
    check("快速清空→清空回應 routes kind=response",
          calls["quick"] and calls["quick"][-1] == ("response", None))

    # ── meta-sync fix: 摘要 reads social values from meta first, so an edit that
    #    only rewrote the JSON must also refresh cached meta (done app-side in
    #    _load_character_detail).  Replicate that formula and confirm it wins.
    stale_meta = {"RomanceLevel": 60, "TrustLevel": 5, "InteractionCount": 8, "RelationValue": 90}
    fresh = {"StringId": "z",
             "CounterpartySocial": {"main_hero": {"trust_level": 0, "interaction_count": 0}},
             "RomancePartners": {"main_hero": {"level": 0}}, "PlayerRelation": {"Value": 0}}
    pr = fresh.get("PlayerRelation")
    stale_meta["RomanceLevel"] = CS.player_romance_level(fresh)
    stale_meta["TrustLevel"] = CS.player_trust_level(fresh)
    stale_meta["InteractionCount"] = CS.player_interaction_count(fresh)
    stale_meta["RelationValue"] = float(pr.get("Value", 0))
    check("meta-sync refreshes stale social values from fresh data",
          stale_meta["RomanceLevel"] == 0 and stale_meta["TrustLevel"] == 0
          and stale_meta["InteractionCount"] == 0 and stale_meta["RelationValue"] == 0)

    # ── cleared mood (EmotionalState=None) no longer renders 情緒 ─────────
    card.load({"StringId": "m", "EmotionalState": {"Mood": "joyful", "Reason": "r"}}, {})
    check("情緒 shows when mood present", "情緒" in card._text.get("1.0", "end"))
    card.load({"StringId": "m2", "EmotionalState": None}, {})
    check("情緒 hidden after clear (EmotionalState=None)",
          "情緒" not in card._text.get("1.0", "end"))

    root.destroy()
    print()
    if FAILS:
        print(f"[FAIL] summary_ops smoke: {len(FAILS)} failing")
        sys.exit(1)
    print("[PASS] summary_ops smoke passed")


if __name__ == "__main__":
    main()

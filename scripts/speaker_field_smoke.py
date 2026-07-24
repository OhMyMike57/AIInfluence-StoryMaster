"""Smoke: the shared 說話者 field (widgets.speaker_field).

The field holds the literal prefix, so these checks are mostly "does each quick
setting produce exactly the text the mod expects".  Also pins the two behaviours
the feature exists for:

  * search hits come from the heroes-only ``speakers`` scope, not ``characters``
    (which merges troop templates and offered 帝國步兵 / 「盾女」 as speakers);
  * picking a character does not lock the name — it stays hand-editable, because
    ``as introduced`` legitimately carries a claimed or false name.

Run: python scripts/speaker_field_smoke.py
"""
import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import speaker_format as SF  # noqa: E402
from widgets import speaker_field as CHF  # noqa: E402
from widgets.speaker_field import SpeakerField, channel_label  # noqa: E402

FAILS = []


def check(label, cond):
    print(f"  {'ok ' if cond else 'FAIL'} - {label}")
    if not cond:
        FAILS.append(label)


class FakeApp:
    """Terminology stub — records which category the field searched."""
    HEROES = {"main_hero": "祿肯", "CharacterObject_2783": "「釤刀」蘇雷納",
              "bloodraven_elga": "埃爾加"}
    TROOPS = {"spc_wanderer_sturgia_8": "「盾女」"}

    def __init__(self):
        self.searched = []

    def terminology_suggest(self, category, prefix, limit=50):
        self.searched.append(category)
        pool = dict(self.HEROES)
        if category == "characters":       # the polluted scope
            pool.update(self.TROOPS)
        p = prefix.lower()
        return [(i, n) for i, n in pool.items() if p in i.lower() or p in n.lower()][:limit]

    def terminology_name_for(self, category, id_):
        return self.HEROES.get(id_, id_)


def main():
    root = tk.Tk()
    root.withdraw()
    app = FakeApp()
    field = SpeakerField(root, app,
                         get_self=lambda: ("「學者」阿馬托爾", "CharacterObject_4449"),
                         get_day=lambda: 42.0)
    field.pack()

    # ── search scope ─────────────────────────────────────────────────────
    print("search scope:")
    rows = field._suggestions("盾")
    check("searches the heroes-only scope", app.searched == ["speakers"])
    check("troop templates are not offered as speakers",
          all("spc_wanderer" not in prefix for prefix, _ in rows))
    rows = field._suggestions("蘇雷納")
    check("a real character is found",
          any("CharacterObject_2783" in prefix for prefix, _ in rows))

    # special identities float in on their own keywords
    check("typing I offers 自己",
          any("I (" in p for p, _ in field._suggestions("I")))
    check("typing main_hero offers 玩家",
          any("main_hero" in p for p, _ in field._suggestions("main_hero")))
    check("typing Stranger offers 陌生人",
          any(p == SF.IDENTITY_STRANGER for p, _ in field._suggestions("Stranger")))
    check("typing Unidentified offers 身分不明",
          any(p == SF.IDENTITY_UNIDENTIFIED
              for p, _ in field._suggestions("Unidentified")))

    # ── quick settings produce the exact mod format ──────────────────────
    print("\nquick settings:")
    field._set_self()
    check("自己 → I (名字, `id`)",
          field.get_prefix() == "I (「學者」阿馬托爾, `CharacterObject_4449`)")
    field._set_player()
    check("玩家 → 名字 (`main_hero`)", field.get_prefix() == "祿肯 (`main_hero`)")

    field._set_identity(SF.IDENTITY_STRANGER)
    check("陌生人 swaps the name, keeps the id",
          field.get_prefix() == "Stranger (`main_hero`)")
    field._toggle_introduced()
    check("已介紹 adds the marker",
          field.get_prefix() == "Stranger (as introduced, `main_hero`)")
    field._toggle_introduced()
    check("已介紹 toggles back off",
          field.get_prefix() == "Stranger (`main_hero`)")

    field._set_identity(SF.IDENTITY_UNIDENTIFIED)
    check("身分不明", field.get_prefix() == "Unidentified person (`main_hero`)")

    # the name stays editable after picking — this is why identity and id are
    # separate fields in the first place (claimed / false names)
    field.set_prefix("Unidentified person (`main_hero`)")
    sp = SF.with_identity(field.speaker(), "假名字")
    field.set_prefix(SF.build(SF.with_relation(sp, SF.RELATION_INTRODUCED)))
    check("a hand-written claimed name survives",
          field.get_prefix() == "假名字 (as introduced, `main_hero`)")

    # ── wrappers ─────────────────────────────────────────────────────────
    print("\nwrappers:")
    field.set_prefix("埃爾加 (`bloodraven_elga`)")
    field._date.set_value(0)
    field._set_overheard("ambient-npc")
    check("旁聽 wraps the speaker and defaults the day from context",
          field.get_prefix() ==
          "[Overheard nearby, day 42, approx. 3.0m, ambient-npc] 埃爾加 (`bloodraven_elga`)")
    check("the wrapper detail row appears", field._wrap_row.winfo_manager() == "pack")
    check("the day picker holds the campaign day", int(field._date.get()) == 42)
    field._date.set_value(100)
    check("changing the date rewrites the prefix", "day 100" in field.get_prefix())
    field._dist_var.set("7.5")
    check("editing the distance rewrites the prefix",
          "approx. 7.5m" in field.get_prefix())
    field._clear_wrapper()
    check("移除包裹 restores the bare speaker",
          field.get_prefix() == "埃爾加 (`bloodraven_elga`)")
    check("the detail row hides again", field._wrap_row.winfo_manager() == "")

    # ── 戰場喊話 engagement ──────────────────────────────────────────────
    field.set_prefix("巴索洛恩")
    field._set_battle()
    check("戰場喊話 wraps the speaker",
          field.get_prefix().startswith("[BATTLE_ORDER]"))
    check("the engagement row appears", field._battle_row.winfo_manager() == "pack")
    field._side_a.set("赫芬斯汀")
    field._side_b.set("劫掠者")
    check("both sides compose the engagement",
          field.get_prefix() == "[BATTLE_ORDER][赫芬斯汀 vs 劫掠者] 巴索洛恩")
    # loading an existing engagement splits it back into the two sides
    field.set_prefix("[BATTLE_ORDER][弗蘭迪亞 vs 維達爾's party] 巴索洛恩")
    check("an existing engagement splits into its sides",
          field._side_a.get() == "弗蘭迪亞" and field._side_b.get() == "維達爾's party")
    check("a one-sided engagement is allowed",
          CHF._split_engagement("劫掠者") == ("劫掠者", ""))
    check("every channel has a localised label",
          all(channel_label(c) and channel_label(c) != c for c in SF.CHANNELS))

    # ── free text / plain ────────────────────────────────────────────────
    print("\nfree text:")
    field.set_prefix("[劇情記憶]")
    check("a story tag is accepted verbatim", field.get_prefix() == "[劇情記憶]")
    check("…and reported as a custom prefix", field.speaker().kind == "raw")
    field.clear()
    check("empty = plain text line", field.get_prefix() == "")

    # 自己 is refused where it has no meaning (batch write)
    batch = SpeakerField(root, app)          # no get_self
    batch._set_self()
    check("自己 does nothing in a batch context (no target yet)",
          batch.get_prefix() == "")

    root.destroy()
    print()
    if FAILS:
        print(f"[FAIL] speaker field smoke: {len(FAILS)} failing")
        sys.exit(1)
    print("[PASS] speaker field smoke passed")


if __name__ == "__main__":
    main()

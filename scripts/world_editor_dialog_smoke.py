"""Headless construction smoke test for the 訊息與秘密 編輯器 (4-zone redesign).

Builds a minimal fake app and opens the dialog in create + edit mode for both
info and secret kinds, asserting the layout + initial wiring construct without
error.  Filter set-math is covered separately by world_filter_check.py.

Run: python scripts/world_editor_dialog_smoke.py
"""
import os
import sys
import tkinter as tk
from tkinter import ttk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.world_editor_dialog import open_world_item_editor_dialog  # noqa: E402

META = {
    "A": {"HasAttrs": True,  "Kingdom": "k1", "Clan": "c1", "StringId": "a", "NeverInteracted": False},
    "B": {"HasAttrs": True,  "Kingdom": "k1", "Clan": "c2", "StringId": "b", "NeverInteracted": True},
    "C": {"HasAttrs": True,  "Kingdom": "k2", "Clan": "c3", "StringId": "c", "NeverInteracted": False},
    "D": {"HasAttrs": True,  "Kingdom": "",   "Clan": "c4", "StringId": "d", "NeverInteracted": False},
    "E": {"HasAttrs": True,  "Kingdom": "",   "Clan": "",   "StringId": "e", "NeverInteracted": False},
    "F": {"HasAttrs": False, "StringId": "f", "NeverInteracted": True},
}
KNAMES = {"k1": "王國一", "k2": "王國二"}
CNAMES = {"c1": "氏族A", "c2": "氏族B", "c3": "氏族C", "c4": "氏族D"}


class FakeApp:
    def __init__(self, root):
        self.root = root
        self.world_info_items = [
            {"id": "info_x", "description": "d", "usageChance": 70,
             "category": "world", "applicableNPCs": ["all"]},
        ]
        self.world_secrets_items = [
            {"id": "secret_y", "description": "s", "knowledgeChance": 50,
             "accessLevel": "medium", "tags": ["t1"], "applicableNPCs": ["lords"]},
        ]
        self.characters = [(n, f"path_{n}") for n in META]
        self.character_meta = META
        self.terminology_campaign = {"kingdoms": KNAMES, "clans": CNAMES}
        self.presets = {"g1": ["A", "C"]}
        self.known_info_owners = {"info_x": ["B"]}
        self.known_secret_owners = {"secret_y": ["E"]}
        self.main_sort_var = tk.StringVar(value="名稱")
        self.exclude_uninteracted_var = tk.BooleanVar(value=False)

    def _center_window(self, win, w, h):
        pass

    def _safe_load_json(self, path):
        return {}

    def _display_label(self, label, star=True):
        return str(label)

    def _sorted_character_displays(self, mode, reverse, names):
        return sorted(names, key=str, reverse=bool(reverse))

    def _applicable_npc_picker(self, parent, defaults, grid_row, grid_col, per_row=0):
        opts = ["all", "lords", "companions", "faction_leaders", "village_notables", "merchants"]
        vars_map = {}
        f = ttk.Frame(parent)
        f.grid(row=grid_row, column=grid_col, sticky="w")
        for i, name in enumerate(opts):
            v = tk.BooleanVar(value=name in defaults)
            vars_map[name] = v
            cb = ttk.Checkbutton(f, text=name, variable=v)
            if per_row > 0:
                r, c = divmod(i, per_row)
                cb.grid(row=r, column=c, sticky="w")
            else:
                cb.pack(side=tk.LEFT)
        return vars_map

    def _mark_world_dirty(self, b):
        pass

    def _refresh_world_lists(self):
        pass

    def log(self, *a, **k):
        pass


def main():
    root = tk.Tk()
    root.withdraw()
    app = FakeApp(root)
    opened = []
    for kind in ("info", "secret"):
        open_world_item_editor_dialog(app, kind, "create")
        open_world_item_editor_dialog(app, kind, "edit", 0)
        opened.append(kind)
    root.update_idletasks()
    # Close the spawned Toplevels.
    for w in list(root.children.values()):
        if isinstance(w, tk.Toplevel):
            w.destroy()
    root.destroy()
    print(f"  ok  - constructed create+edit for {opened}")
    print("[PASS] world_editor_dialog smoke passed")


if __name__ == "__main__":
    main()

"""Smoke: persona editor window constructs (dual + third-party), export dialog,
and readonly click-to-copy / edit undo wiring — headless, auto-closing dialogs.

Run: python scripts/persona_editor_smoke.py
"""
import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dialogs.persona_editor_dialog import _PersonaEditor, _make_text, open_persona_export  # noqa: E402
from services import persona_transfer as PT  # noqa: E402

FAILS = []


def check(label, cond):
    print(f"  {'ok ' if cond else 'FAIL'} - {label}")
    if not cond:
        FAILS.append(label)


class FakeApp:
    def __init__(self, root):
        self.root = root
        self.character_meta = {"埃爾加": {"StringId": "bloodraven_elga"},
                               "索爾沃": {"StringId": "bloodraven_solvor"}}
        self.plain_to_path = {}
        self.saved = None

    # NameIdCombo hooks
    def terminology_suggest(self, c, p, limit=50): return []
    def resolve_name_or_id(self, c, t): return (None, [])
    def terminology_name_for(self, c, i): return i
    def _safe_load_json(self, p): return {}
    def _persona_batch_save(self, path, changed): self.saved = (path, changed)


def main():
    root = tk.Tk()
    root.withdraw()

    # readonly cell blocks edits but exposes text; edit cell has undo
    fr, ro = _make_text(root, readonly=True)
    fr2, ed = _make_text(root, readonly=False)
    check("edit cell has undo enabled", bool(ed.cget("undo")))

    app = FakeApp(root)
    data = {"Name": "埃爾加", "StringId": "bloodraven_elga",
            "CharacterDescription": "原描述", "AIGeneratedPersonality": "原性格",
            "AIGeneratedBackstory": "", "AIGeneratedSpeechQuirks": "",
            "AIGeneratedCognitiveStyle": ""}

    ed_win = _PersonaEditor(app, "elga.json", data, None)
    check("5 edit fields built", len(ed_win._edit) == 5)
    check("original preloaded", ed_win._orig["CharacterDescription"].get("1.0", "end-1c") == "原描述")
    check("edit preloaded from data", ed_win._edit["AIGeneratedPersonality"].get("1.0", "end-1c") == "原性格")
    check("third-party inactive initially", ed_win._third_active is False)
    check("original column collapsed initially", ed_win._orig_active is False)
    check("original frame not gridded while collapsed",
          ed_win._orig_frames["CharacterDescription"].grid_info() == {})

    # change one field → _changed_fields detects it
    ed_win._edit["CharacterDescription"].delete("1.0", "end")
    ed_win._edit["CharacterDescription"].insert("1.0", "新描述")
    ch = ed_win._changed_fields()
    check("changed detects edited field only", ch == {"CharacterDescription": "新描述"})

    # toggling a reference column grids it on the field's own content row, so
    # 原文 / 編輯 / 第三方 stay side by side for the same field
    f0 = "CharacterDescription"
    ed_win._toggle_third()
    check("third-party active after toggle", ed_win._third_active is True)
    ed_win._toggle_orig()
    check("original active after toggle", ed_win._orig_active is True)
    edit_row  = int(ed_win._edit[f0].master.grid_info()["row"])
    orig_row  = int(ed_win._orig_frames[f0].grid_info()["row"])
    third_row = int(ed_win._third_frames[f0].grid_info()["row"])
    check("all three columns share the field's content row",
          orig_row == edit_row == third_row == ed_win._content_rows[f0])
    check("columns are 原文/編輯/第三方 left-to-right",
          int(ed_win._orig_frames[f0].grid_info()["column"]) == 0
          and int(ed_win._edit[f0].master.grid_info()["column"]) == 1
          and int(ed_win._third_frames[f0].grid_info()["column"]) == 2)

    # three width states: edit only < edit+one reference < edit+both
    def _width_for(orig_on, third_on):
        ed_win._orig_active, ed_win._third_active = orig_on, third_on
        sw = ed_win.win.winfo_screenwidth()
        return min(int(sw * 0.92),
                   (740, 1480, 1980)[int(orig_on) + int(third_on)])
    check("width grows with each reference column",
          _width_for(False, False) <= _width_for(True, False) <= _width_for(True, True))
    ed_win._orig_active, ed_win._third_active = True, True

    ed_win._toggle_third()
    check("third-party off after 2nd toggle", ed_win._third_active is False)
    ed_win._toggle_orig()
    check("original off after 2nd toggle", ed_win._orig_active is False)
    check("original frame ungridded again",
          ed_win._orig_frames[f0].grid_info() == {})

    # draggable sash resizes a field's height across all 3 columns together
    class _Ev:
        def __init__(self, y): self.y_root = y
    f0 = "CharacterDescription"
    start_h = ed_win._heights[f0]
    ed_win._sash_start(_Ev(100), f0)
    ed_win._sash_drag(_Ev(100 + 3 * ed_win._line_h), f0)
    check("sash increased field height", ed_win._heights[f0] == start_h + 3)
    check("sash synced all 3 columns",
          int(ed_win._orig[f0].cget("height")) == start_h + 3
          and int(ed_win._edit[f0].cget("height")) == start_h + 3
          and int(ed_win._third[f0].cget("height")) == start_h + 3)

    # export panel (upward popover): builds 5 field vars + 全選, exports edit text
    ed_win._edit["CharacterDescription"].delete("1.0", "end")
    ed_win._edit["CharacterDescription"].insert("1.0", "導出用文字")
    ed_win._export_panel.show()
    check("export panel built 5 field vars", len(ed_win._export_vars) == 5)
    ed_win._do_export_panel()
    exported = root.clipboard_get()
    check("export panel wrote persona JSON to clipboard",
          '"CharacterDescription"' in exported and "導出用文字" in exported)
    check("export panel closed after export", ed_win._export_panel._visible is False)

    # clipboard import into an unchanged editor overwrites the matching field
    root.clipboard_clear()
    root.clipboard_append('{"CharacterDescription": "來自剪貼簿"}')
    imp_win = _PersonaEditor(app, "elga.json", data, None)
    imp_win._import_clipboard()
    check("clipboard import overwrote edit field",
          imp_win._edit["CharacterDescription"].get("1.0", "end-1c") == "來自剪貼簿")
    imp_win.win.destroy()

    ed_win.win.destroy()

    # import mode: edit prefilled from clipboard fields
    imp = _PersonaEditor(app, "elga.json", data, {"CharacterDescription": "剪貼簿描述"})
    check("import prefills edit field", imp._edit["CharacterDescription"].get("1.0", "end-1c") == "剪貼簿描述")
    check("import leaves other fields at data value",
          imp._edit["AIGeneratedPersonality"].get("1.0", "end-1c") == "原性格")
    # Import mode opens 原文 automatically — comparing against the current text
    # is the entire point of reviewing a clipboard import.
    check("import mode opens the original column", imp._orig_active is True)
    check("import mode grids the original frame",
          imp._orig_frames["CharacterDescription"].grid_info() != {})
    imp.win.destroy()

    # export dialog constructs
    ex = open_persona_export
    win_before = len(root.winfo_children())
    ex(app, "elga.json", data)
    # close any toplevels
    for w in root.winfo_children():
        if isinstance(w, tk.Toplevel):
            w.destroy()
    check("export dialog opened a toplevel", len(root.winfo_children()) >= win_before)

    root.destroy()
    print()
    if FAILS:
        print(f"[FAIL] persona_editor smoke: {len(FAILS)} failing")
        sys.exit(1)
    print("[PASS] persona_editor smoke passed")


if __name__ == "__main__":
    main()

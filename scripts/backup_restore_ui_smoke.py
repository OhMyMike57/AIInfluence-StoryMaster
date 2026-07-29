"""Smoke: Backup Center restore wiring (v1.2.1 B-4).

The service layer is covered by ``backup_restore_check.py``; this checks the
parts only the UI can get wrong:

  1. the confirm dialog builds and reports the user's choice;
  2. the snapshot kind reaches the tab's filter/label helpers;
  3. the restore handler refuses to act while the game is running, and stops
     when the user cancels the dialog — i.e. nothing is written unless the
     confirmation actually came back True.

Run: python scripts/backup_restore_ui_smoke.py
"""
import os
import sys
import tempfile
import tkinter as tk
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ttkbootstrap as tb  # noqa: E402

from i18n import set_lang  # noqa: E402
from services import backup_service as B  # noqa: E402
from ui import backup_tab as BT  # noqa: E402
from dialogs import restore_confirm_dialog as RCD  # noqa: E402

FAILS = []


def check(label, cond):
    print(f"  {'ok ' if cond else 'FAIL'} - {label}")
    if not cond:
        FAILS.append(label)


class FakeApp:
    """Enough of the app for the restore handler to run headless."""

    def __init__(self, root, tmp: Path):
        self.root = root
        self.save_data_dir = tmp / "sd"
        self.config_dir = tmp / "cfg"
        self.campaign_dir = None
        self.backup_dir_var = tk.StringVar(value=str(tmp / "backups"))
        self.logs = []
        self.game_running = False
        self.refreshed = 0

    def log(self, msg, level="INFO"):
        self.logs.append((level, msg))

    def _confirm_if_game_running(self, op):
        return self.game_running          # True == caller should abort

    def refresh(self, ask_dirty=True):
        self.refreshed += 1


def make_backup(tmp: Path):
    """A campaign backup whose live folder has drifted, so a plan is non-empty."""
    base = tmp / "backups"
    camp = tmp / "sd" / "CID"
    camp.mkdir(parents=True, exist_ok=True)
    (camp / "a.json").write_text("recorded", encoding="utf-8")
    bk = B.backup_campaign_dir(camp, base)
    (camp / "a.json").write_text("drifted", encoding="utf-8")
    (camp / "extra.json").write_text("will be deleted", encoding="utf-8")
    entry = B.BackupEntry(kind=B.KIND_CAMPAIGN, path=Path(bk), name=Path(bk).name,
                          campaign_id="CID", timestamp=None)
    return entry, camp


def test_labels():
    print("\n[snapshot kind reaches the tab helpers]")
    kinds = [k for _lbl, k in BT._filter_options()]
    check("filter offers the snapshot kind", B.KIND_SNAPSHOT in kinds)
    check("filter still offers all four others",
          all(k in kinds for k in ("", B.KIND_CAMPAIGN, B.KIND_DB, B.KIND_CONFIG)))
    for k in (B.KIND_CAMPAIGN, B.KIND_DB, B.KIND_CONFIG, B.KIND_SNAPSHOT):
        check(f"{k} has a column label", BT._kind_col_label(k) != k)
        check(f"{k} has a dialog label", RCD._kind_label(k) != k)


def _find_button(widget, label):
    """Depth-first search for a ttk.Button whose text is *label*."""
    try:
        if isinstance(widget, tk.Widget) and "text" in widget.keys():
            if str(widget.cget("text")) == label:
                return widget
    except Exception:
        pass
    for child in widget.winfo_children():
        found = _find_button(child, label)
        if found is not None:
            return found
    return None


def _shown_text(win):
    """All text in the dialog's disabled Text widget (the sample-paths pane)."""
    out = []

    def walk(w):
        if isinstance(w, tk.Text):
            out.append(w.get("1.0", "end"))
        for c in w.winfo_children():
            walk(c)

    walk(win)
    return "\n".join(out)


def test_dialog(root, tmp: Path):
    print("\n[confirm dialog: real build, real buttons]")
    entry, camp = make_backup(tmp)
    plan = B.plan_restore(entry, camp)
    app = FakeApp(root, tmp)

    # Drive the real modal: after it maps, click the named button for it.
    for label, want in ((tr_confirm(), True), (tr_cancel(), False)):
        clicked = {"found": False, "body": ""}

        def press(_label=label, _c=clicked):
            win = [w for w in root.winfo_children()
                   if isinstance(w, tk.Toplevel) and w.winfo_exists()]
            if not win:
                return
            top = win[-1]
            _c["body"] = _shown_text(top)
            btn = _find_button(top, _label)
            if btn is not None:
                _c["found"] = True
                btn.invoke()
            else:                            # pragma: no cover - keeps the run finite
                top.destroy()

        root.after(120, press)
        got = RCD.open_restore_confirm_dialog(app, plan)
        check(f"button 〔{label}〕 exists", clicked["found"])
        check(f"〔{label}〕 returns {want}", got is want)
        if want:
            body = clicked["body"]
            check("dialog lists the file it will delete", "extra.json" in body)
            check("dialog lists the file it will overwrite", "a.json" in body)

    check("dialog left no window behind",
          not [w for w in root.winfo_children()
               if isinstance(w, tk.Toplevel) and w.winfo_exists()])


def tr_confirm():
    from i18n import tr
    return tr("確認還原")


def tr_cancel():
    from i18n import tr
    return tr("取消")


def test_handler_guards(root, tmp: Path):
    print("\n[handler guards: game running, user cancel]")
    entry, camp = make_backup(tmp)
    app = FakeApp(root, tmp)

    # Stub the selection, the confirm dialog and every modal so the handler runs
    # headless — a real showinfo would block forever with no one to click it.
    BT._selected_entry = lambda _a: entry
    BT.messagebox.showinfo = lambda *a, **k: None
    BT.messagebox.showwarning = lambda *a, **k: None
    BT.messagebox.showerror = lambda *a, **k: None
    BT.messagebox.askyesno = lambda *a, **k: True
    calls = {"confirm": 0}

    def deny(_a, _p):
        calls["confirm"] += 1
        return False

    BT.open_restore_confirm_dialog = deny
    BT.refresh_backup_center = lambda _a: None

    app.game_running = True
    BT._restore(app)
    check("game running → no dialog, no write", calls["confirm"] == 0
          and (camp / "a.json").read_text() == "drifted")

    app.game_running = False
    BT._restore(app)
    check("user cancelled → dialog shown, still no write",
          calls["confirm"] == 1 and (camp / "a.json").read_text() == "drifted")
    check("cancel is logged", any("取消" in m or "cancel" in m.lower()
                                  for _lv, m in app.logs))

    # Now allow it: the write must happen and the campaign reload must fire.
    BT.open_restore_confirm_dialog = lambda _a, _p: True
    app.campaign_dir = camp
    BT._restore(app)
    check("confirmed → target restored", (camp / "a.json").read_text() == "recorded")
    check("confirmed → extra file removed", not (camp / "extra.json").exists())
    check("confirmed → campaign reloaded", app.refreshed == 1)


def main():
    set_lang("zh_TW")
    root = tb.Window(themename="sandstone")
    root.withdraw()
    try:
        with tempfile.TemporaryDirectory(prefix="sm_restore_ui_") as td:
            tmp = Path(td)
            test_labels()
            test_dialog(root, tmp / "d")
            test_handler_guards(root, tmp / "h")
    finally:
        root.destroy()

    if FAILS:
        print(f"\n[FAIL] {len(FAILS)} check(s) failed:")
        for f in FAILS:
            print(f"  - {f}")
        sys.exit(1)
    print("\n[PASS] backup restore UI smoke passed")


if __name__ == "__main__":
    main()

"""Smoke: 對話歷史 page (list + preview rework, v1.1.0).

Covers what the rework actually changed:
  1. Rows land in the list with the right line number, speaker and category tag.
  2. Native multi-select + Ctrl+A, and selected_indices() mapping back to the
     real ConversationHistory indices (the tree is keyed by iid, not row order).
  3. Edit-mode gating of the action row.
  4. 快速寫入 hands (speaker, text, position) to the app — including an EMPTY
     speaker, which must stay empty so a pure prompt line is written verbatim.
  5. Delete / sync refuse to fire with nothing selected.

Run: python scripts/conversation_history_page_smoke.py
"""
import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import conversation_transfer as CT  # noqa: E402
from widgets import conversation_history_page as CHP  # noqa: E402
from widgets.conversation_history_page import ConversationHistoryPage  # noqa: E402

FAILS = []


def check(label, cond):
    print(f"  {'ok ' if cond else 'FAIL'} - {label}")
    if not cond:
        FAILS.append(label)


ENTRIES = [
    "Unidentified person (`main_hero`): 你認得這本書？",                      # player
    "I (「學者」阿馬托爾, `CharacterObject_4449`): 「你認得這本書？」",        # self
    "祿肯·赫芬斯汀 (as introduced, `main_hero`): 我叫祿肯。",                  # player (introduced)
    "埃爾加 (`bloodraven_elga`): *坐起身*",                                    # other
    "[劇情記憶]: 手動插入的劇情。",                                            # tag
    "[Overheard nearby, day 91114, approx. 2.7m, dialog/player] "
    "Unidentified person (`main_hero`): 親愛的",                               # overheard
    '[BATTLE_ORDER][巴坦尼亞 vs X\'s party] 阿匹斯: "架起盾牆！"',             # battle
    "MEMORY (day 91115): 洛迪爾在旅店與埃爾加會合。",                          # memory
    "Your last conversation was 3 days ago.",                                  # gap
    "沒有說話者的純提示詞。",                                                  # note
]


def main():
    root = tk.Tk()
    root.withdraw()

    # Every dialog here is modal — record instead of blocking.  askyesno answers
    # yes so the import paths run all the way through to the app callback.
    warnings = []
    infos = []
    CHP.messagebox.showwarning = lambda title, msg, **kw: warnings.append(title)
    CHP.messagebox.showinfo = lambda title, msg, **kw: infos.append(title)
    CHP.messagebox.showerror = lambda title, msg, **kw: warnings.append(title)
    CHP.messagebox.askyesno = lambda title, msg, **kw: True

    calls = {}
    page = ConversationHistoryPage(
        root,
        on_delete=lambda idx: calls.__setitem__("delete", idx),
        on_sync_menu=lambda idx, btn: calls.__setitem__("sync", idx),
        on_sync_all=lambda idx: calls.__setitem__("sync_all", idx),
        on_insert=lambda s, t, p: calls.__setitem__("insert", (s, t, p)),
        on_edit_line=lambda i, t, pos: calls.__setitem__("edit_line", (i, t, pos)),
        on_replace_all=lambda e, src: calls.__setitem__("replace_all", (e, src)),
        on_patch_lines=lambda u, src: calls.__setitem__("patch_lines", (u, src)),
        on_view_eavesdroppers=lambda i: calls.__setitem__("view_eaves", i),
        on_view_sharers=lambda i: calls.__setitem__("view_share", i),
        on_clear_eavesdroppers=lambda idxs: calls.__setitem__("clear_eaves", list(idxs)),
    )
    page.pack(fill="both", expand=True)
    page.load(ENTRIES, npc_name="「學者」阿馬托爾", npc_id="CharacterObject_4449")

    rows = page._tree.get_children()
    check("every entry got a row", len(rows) == len(ENTRIES))
    check("line numbers are 1-based", page._tree.set(rows[0], "line") == "1")

    tags = [page._tree.item(r, "tags")[0] for r in rows]
    check("categories in entry order",
          tags == ["player", "self", "player", "other", "tag",
                   "overheard", "battle", "memory", "gap", "note"])
    check("every category has a colour + badge",
          all(t in CHP._CATEGORY_STYLE for t in tags))

    # the player placeholder is spelled out, not shown as raw English
    check("unidentified player relabelled",
          page._tree.set(rows[0], "speaker") != "Unidentified person")
    check("introduced player keeps their name",
          "祿肯·赫芬斯汀" in page._tree.set(rows[2], "speaker"))

    # ── selection ────────────────────────────────────────────────────────
    check("multi-select enabled", str(page._tree.cget("selectmode")) == "extended")
    page._tree.selection_set([rows[1], rows[4], rows[7]])
    check("selected_indices maps to real indices", page.selected_indices() == [1, 4, 7])
    page._select_all_event()
    check("Ctrl+A selects everything",
          page.selected_indices() == list(range(len(ENTRIES))))
    page._tree.selection_remove(page._tree.selection())
    check("cleared selection", page.selected_indices() == [])

    # ── edit gating ──────────────────────────────────────────────────────
    # winfo_manager() (not winfo_ismapped) — the root is withdrawn here, so
    # nothing is ever "mapped" and ismapped would pass both ways.  The page is
    # laid out with grid (see _build_ui), and grid_remove() clears the manager.
    check("action row hidden outside edit mode", page._action_bar.winfo_manager() == "")
    page._edit_var.set(True)
    root.update_idletasks()
    check("action row shown in edit mode", page._action_bar.winfo_manager() == "grid")

    # delete / sync need a selection
    calls.clear()
    warnings.clear()
    page._delete_selected()
    check("delete with no selection does nothing", "delete" not in calls)
    page._show_sync_menu()
    check("sync with no selection does nothing", "sync" not in calls)
    check("both warned the user instead", len(warnings) == 2)
    page._tree.selection_set([rows[3], rows[5]])
    page._delete_selected()
    check("delete passes the selected indices", calls.get("delete") == [3, 5])
    page._show_sync_menu()
    check("sync passes the selected indices", calls.get("sync") == [3, 5])

    # ── 快速寫入 ─────────────────────────────────────────────────────────
    page._toggle_insert_panel()
    check("write panel opened", page._insert_open is True)
    check("position defaults to the end", page._pos_var.get() == str(len(ENTRIES) + 1))
    page._insert_text.insert("1.0", "新的一行")
    page._on_insert_confirm()
    check("write panel closed after confirm", page._insert_open is False)
    speaker, text, pos = calls.get("insert", (None, None, None))
    check("empty speaker stays empty (pure prompt)", speaker == "")
    check("write passed the text", text == "新的一行")
    check("write passed the end position", pos == len(ENTRIES) + 1)

    # ── right-click context menu ─────────────────────────────────────────
    class _Ev:
        def __init__(self, iid_y):
            self.y = iid_y
            self.x_root = 400
            self.y_root = 300

    # identify_row() needs real geometry, which a withdrawn root has none of —
    # stub the hit test so the menu-building logic is what gets exercised.
    def _open_ctx(row_iids):
        page._tree.selection_set(row_iids)
        page._tree.focus(row_iids[0])
        page._tree.identify_row = lambda _y, _iid=row_iids[0]: _iid
        page._on_right_click(_Ev(10))
        return page._ctx_menu

    # single row → sync / insert-here / compose-this / delete-this, all live
    menu = _open_ctx([rows[1]])
    check("right-click opened a context menu", menu is not None and menu._visible)
    labels = [i[0] for i in menu.items if i]
    check("single-row menu is sync / insert-here / compose-this / delete-this / clear-eaves",
          len(labels) == 5
          and "同步至已選角色" in labels[0]
          and "在此插入對話行" in labels[1]
          and "編寫此對話行" in labels[2]
          and "刪除此對話行" in labels[3]
          and "清空此對話行旁聽者" in labels[4])
    check("every single-row entry is clickable",
          all(callable(i[1]) for i in menu.items if i))
    check("single-row menu has no separators", menu.items.count(None) == 0)
    check("context menu opens at the pointer", menu.at == (400, 300))
    menu.hide()

    # several rows → counted wording, count follows the selection, all live
    menu = _open_ctx([rows[1], rows[3], rows[4]])
    labels = [i[0] for i in menu.items if i]
    check("multi-row menu counts the selection",
          "編寫 3 個對話行" in labels[1] and "刪除 3 個對話行" in labels[2])
    check("multi-row 編寫 entry is now clickable (was disabled)",
          callable(menu.items[1][1]))
    check("multi-row menu has no separators", menu.items.count(None) == 0)
    menu.hide()

    # 同步至已選角色 goes straight to sync-all, it is not the 同步 ▾ chooser
    calls.clear()
    page._sync_all_selected()
    check("context sync calls sync-all directly", calls.get("sync_all") == [1, 3, 4])
    check("context sync did NOT open the target chooser", "sync" not in calls)

    # focus must follow the RIGHT-clicked row, not the last left-click —
    # otherwise 在此插入／編寫此對話行 targeted the wrong line.  Left-focus row 0,
    # then right-click row 5 (not selected) and check "this line" = row 5.
    # (Bypass _open_ctx here — it pre-sets focus, which would mask the fix.)
    page._tree.selection_set([rows[0]])
    page._tree.focus(rows[0])
    page._tree.identify_row = lambda _y: rows[5]
    page._on_right_click(_Ev(10))
    check("right-click moves focus to the clicked row (not the last left-click)",
          page._focused_index() == 5)
    page._ctx_menu.hide()

    # 在此插入對話行 opens 寫入對話行 with the position pre-filled to that row
    page._tree.selection_set([rows[2]])
    page._tree.focus(rows[2])
    page._insert_at_focused()
    check("insert-here opened the write panel", page._insert_open is True)
    check("insert-here pre-filled the picked line's position",
          page._pos_var.get() == "3")
    page._toggle_insert_panel()

    # 編寫 ▾ menu: bulk compose on top, the two single-line editors below
    page._tree.selection_set([rows[1], rows[3], rows[4]])
    citems = page._compose_items()
    clabels = [i[0] for i in citems if i]
    check("compose menu order: 編寫 N / 編寫對話行 / 寫入對話行",
          "編寫 3 個對話行" in clabels[0]
          and "編寫對話行" in clabels[1] and "寫入對話行" in clabels[2])
    check("完整編寫 is gone", not any("完整編寫" in l for l in clabels))
    check("compose menu separates bulk from the single-line tools",
          citems.count(None) == 1 and citems.index(None) == 1)
    check("every compose entry is live",
          len(clabels) == 3 and all(callable(i[1]) for i in citems if i))

    # ── 編輯此對話行 (bottom panel, replaced the modal dialog) ────────────
    calls.clear()
    page._tree.selection_set([rows[3]])
    page._tree.focus(rows[3])
    page._edit_focused_line()
    check("line-edit panel opened", page._line_edit_open is True)
    check("line-edit panel is gridded", page._line_edit_panel.winfo_manager() == "grid")
    check("panel split the speaker prefix out",
          page._le_speaker.get_prefix() == "埃爾加 (`bloodraven_elga`)")
    check("panel content is the text without the prefix",
          page._line_edit_text.get("1.0", "end-1c") == "*坐起身*")
    check("line number prefilled with the current position",
          page._le_pos_var.get() == "4")
    check("write panel and line-edit panel are mutually exclusive",
          page._insert_open is False)
    page._line_edit_text.delete("1.0", "end")
    page._line_edit_text.insert("1.0", "改過的內容")
    page._le_pos_var.set("1")          # …and move it to the top
    page._on_line_edit_confirm()
    check("confirm closed the panel", page._line_edit_open is False)
    check("confirm rejoined prefix + content and passed the new position",
          calls.get("edit_line") == (3, "埃爾加 (`bloodraven_elga`): 改過的內容", 1))

    warnings.clear()
    page._tree.selection_remove(page._tree.selection())
    page._edit_focused_line()
    check("edit with no selection warns instead of opening",
          page._line_edit_open is False and len(warnings) == 1)

    # opening 快速寫入 closes the line editor (they share the bottom slot)
    page._tree.selection_set([rows[2]])
    page._tree.focus(rows[2])
    page._edit_focused_line()
    page._toggle_insert_panel()
    check("opening quick-write closed the line editor",
          page._insert_open is True and page._line_edit_open is False)
    page._toggle_insert_panel()

    # ── 導出/導入 ────────────────────────────────────────────────────────
    page.load(ENTRIES, npc_name="「學者」阿馬托爾", npc_id="CharacterObject_4449")
    page._tree.selection_set([rows[1], rows[6]])
    titems = [i for i in page._transfer_items() if i]
    tlabels = [i[0] for i in titems]
    check("transfer menu has 5 live entries",
          len(titems) == 5 and all(callable(i[1]) for i in titems))
    check("export labels renamed (全部為 MD / 全部到剪貼簿 / N 行到剪貼簿)",
          "導出全部為 MD" in tlabels[0]
          and "導出全部到剪貼簿" in tlabels[1]
          and "導出 2 行到剪貼簿" in tlabels[2])

    # clipboard export → the page's own clipboard, read back through the parser
    page._tree.selection_set([rows[1], rows[6]])
    page._clip_export_selected()
    pasted = page.clipboard_get()
    check("selected export numbers the real line numbers",
          pasted.startswith("[#2] ") and "\n[#7] " in pasted)

    page._clip_export_all()
    res = CT.parse_clipboard(page.clipboard_get(), len(ENTRIES))
    check("clipboard-all export re-imports to the same history",
          res.kind == "replace" and res.entries == ENTRIES)

    # MD headings carry the readable label the list shows
    md = CT.build_markdown("x", ENTRIES, row_label=page._md_row_label)
    check("MD label uses the page's own category + speaker wording",
          "⚔ 戰場喊話" in md and "👂 旁聽" in md)
    check("MD from the page round-trips", CT.parse_markdown(md) == ENTRIES)

    # import: patch path (confirm dialog auto-accepted)
    calls.clear()
    page._to_clipboard("[#3] 改寫的第三行")
    page._import_clipboard()
    check("clipboard patch import reaches the app",
          calls.get("patch_lines", ({}, ""))[0] == {2: "改寫的第三行"})

    # import: replace path
    calls.clear()
    page._to_clipboard(CT.build_clipboard_all(ENTRIES[:3]))
    page._import_clipboard()
    check("clipboard replace import reaches the app",
          calls.get("replace_all", ([], ""))[0] == ENTRIES[:3])

    # import: a bad paste warns and changes nothing
    calls.clear()
    warnings.clear()
    page._to_clipboard("[#99] 不存在的行")
    page._import_clipboard()
    check("out-of-range paste warns instead of writing",
          not calls and len(warnings) == 1)

    calls.clear()
    warnings.clear()
    page._to_clipboard("隨便貼的一段話")
    page._import_clipboard()
    check("unrecognised paste warns instead of writing",
          not calls and len(warnings) == 1)

    # ── 關聯（旁聽＋共用）徽章 / 預覽 / RAG 表頭 / 入口 ─────────────────────
    page.load(ENTRIES, npc_name="「學者」阿馬托爾", npc_id="CharacterObject_4449",
              rag_status="indexed")
    check("RAG header reflects status", "已建立" in page._rag_var.get())
    check("關聯 column exists", "assoc" in page._tree.cget("columns"))
    check("行 column is left-aligned", str(page._tree.column("line", "anchor")) == "w")

    # counts arrive asynchronously via set_relation_counts
    eaves = [0] * len(ENTRIES); eaves[3] = 2      # line 4 overheard by 2
    share = [0] * len(ENTRIES); share[6] = 8      # line 7 shared by 8
    page.set_relation_counts(eaves, share)
    prows = page._tree.get_children()
    check("overheard line shows 👂 in the 關聯 column",
          "👂2" in page._tree.set(prows[3], "assoc"))
    check("shared line shows 🔗 in the 關聯 column",
          "🔗8" in page._tree.set(prows[6], "assoc"))
    check("un-related line has an empty 關聯 cell",
          page._tree.set(prows[0], "assoc") == "")
    check("類型 column no longer carries the badge",
          "👂" not in page._tree.set(prows[3], "kind"))

    page._tree.selection_set([prows[3]])
    page._tree.focus(prows[3])
    page._render_detail(3)
    check("preview shows the eavesdropper count",
          "👂" in page._detail.get("1.0", "end") and "2 位旁聽" in page._detail.get("1.0", "end"))
    page._render_detail(6)
    check("preview shows the sharer count",
          "🔗" in page._detail.get("1.0", "end") and "8 位共用" in page._detail.get("1.0", "end"))

    # 關聯 ▾ menu: 查看共用者 / 查看旁聽者 / 清空旁聽者 (clear counts with selection)
    page._tree.selection_set([prows[3]])
    ritems = page._relations_items()
    rlabels = [i[0] for i in ritems if i]
    check("關聯 menu: view-sharers / view-eaves / clear (single)",
          "查看共用者" in rlabels[0] and "查看旁聽者" in rlabels[1]
          and "清空旁聽者" in rlabels[2] and "清空 " not in rlabels[2])
    page._tree.selection_set([prows[1], prows[3], prows[6]])
    rlabels = [i[0] for i in page._relations_items() if i]
    check("關聯 menu: 清空 counts the selection", "清空 3 行旁聽者" in rlabels[2])

    # view-sharers / view-eaves are single-line only
    calls.clear()
    page._tree.selection_set([prows[3]]); page._tree.focus(prows[3])
    page._view_selected_eavesdroppers()
    page._view_selected_sharers()
    check("view eaves / sharers open the right line",
          calls.get("view_eaves") == 3 and calls.get("view_share") == 3)
    calls.clear(); infos_before = len(infos)
    page._tree.selection_set([prows[1], prows[3]])
    page._view_selected_eavesdroppers()
    check("view eaves with 2 lines refuses",
          "view_eaves" not in calls and len(infos) == infos_before + 1)

    # 清空旁聽者 supports multi-line
    calls.clear()
    page._tree.selection_set([prows[1], prows[3], prows[6]])
    page._clear_selected_eavesdroppers()
    check("清空旁聽者 passes all selected lines", calls.get("clear_eaves") == [1, 3, 6])

    # right-click single-row: 清空此對話行旁聽者 (replaces the old 查看)
    menu = _open_ctx([prows[2]])
    labels = [i[0] for i in menu.items if i]
    check("single-row menu includes 清空此對話行旁聽者 (not 查看)",
          any("清空此對話行旁聽者" in l for l in labels)
          and not any("查看此對話行旁聽者" in l for l in labels))
    menu.hide()
    calls.clear()
    page._tree.selection_set([prows[2]]); page._tree.focus(prows[2])
    page._clear_focused_eavesdroppers()
    check("清空此對話行旁聽者 targets the focused line", calls.get("clear_eaves") == [2])

    # right-click multi-row: 清空 N 個對話行旁聽者
    menu = _open_ctx([prows[1], prows[3], prows[5]])
    labels = [i[0] for i in menu.items if i]
    check("multi-row menu includes 清空 3 個對話行旁聽者",
          any("清空 3 個對話行旁聽者" in l for l in labels))
    menu.hide()

    # RAG "none" hides the label
    page.load(ENTRIES, npc_name="x", npc_id="x", rag_status="none")
    check("RAG none → header blank", page._rag_var.get() == "")

    # ── reload keeps working, clear empties the list ─────────────────────
    page.load(ENTRIES, npc_name="別人", npc_id="other_id")
    check("reload for another character re-rows",
          len(page._tree.get_children()) == len(ENTRIES))
    check("self line is now 'other' for a different character",
          page._tree.item(page._tree.get_children()[1], "tags")[0] == "self")
    page.clear()
    check("clear empties the list", page._tree.get_children() == ())

    root.destroy()
    print()
    if FAILS:
        print(f"[FAIL] conversation history page smoke: {len(FAILS)} failing")
        sys.exit(1)
    print("[PASS] conversation history page smoke passed")


if __name__ == "__main__":
    main()

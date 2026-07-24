"""說話者 input — one field shared by every place that writes a conversation line.

    說話者：[ 前綴 ................................ ][⚡ 快速設定 ▾]
            [ 戰役日 ___  距離 ___m  頻道 ______ ]   ← only while 旁聽 is set

The entry holds the **literal prefix** that will be written, so what you see is
what lands in the save.  That single decision covers three of the requirements
at once: hand-editing a name after picking a character, pasting a complete
prefix, and inventing a form the tool has never seen.

Typing a bare word searches characters and drops a results list; the moment the
text parses as a speaker prefix the list stops appearing, so editing a prefix is
never fought by autocomplete.

Search hits come from the **speakers** category (heroes only).  ``characters``
merges troop templates in so ids still resolve to names, which makes it useless
here — it offers 帝國步兵 and title words like 「盾女」 next to real people.

The special identities the mod uses are searchable by their own names — typing
``I``, ``main_hero``, ``Stranger`` or ``Unidentified`` floats them to the top —
and the 快速設定 menu applies them (and the 旁聽 / 戰場喊話 wrappers) without
the user having to remember any of the syntax.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional, Tuple

from i18n import tr
from services import dialogue_tag_service as TAGS
from services import speaker_format as SF
from ui.theme import tcol
from widgets.game_date_field import GameDateField
from widgets.popover_menu import PopoverMenu

_SEARCH_CATEGORY = "speakers"

# Search synonyms for the special identities.  These are matched against what the
# user *types* — they are data, not UI text, so they stay literal (the displayed
# labels next to them go through tr() as usual).  Both scripts are accepted
# because the mod writes English placeholders into a Chinese save.
_SYN_SELF = ("i", "self", "自己")                    # noqa: cjk (input synonyms)
_SYN_PLAYER = ("main_hero", "player", "玩家")        # noqa: cjk (input synonyms)
_SYN_STRANGER = ("stranger", "陌生")                 # noqa: cjk (input synonyms)
_SYN_UNKNOWN = ("unidentified", "不明", "未知")       # noqa: cjk (input synonyms)


def _matches(term: str, synonyms) -> bool:
    """True when *term* looks like one of *synonyms* (case-insensitive)."""
    t = term.strip().lower()
    if not t:
        return False
    return any(s == t or (len(s) > 1 and s in t) for s in synonyms)


def _split_engagement(engagement: str) -> Tuple[str, str]:
    """Split ``"<A> vs <B>"`` into its two sides (B empty when there is no ``vs``).

    Real captures: ``弗蘭迪亞 vs 維達爾's party``, ``赫芬斯汀 vs 劫掠者``,
    ``巴坦尼亞 vs 執政官·阿匹斯's party``.  Only the first ``vs`` is a
    separator — a side could contain the word itself.
    """
    if not engagement:
        return ("", "")
    parts = engagement.split(" vs ", 1)
    return (parts[0].strip(), parts[1].strip() if len(parts) > 1 else "")


def channel_label(channel: str) -> str:
    """Localised name for an overheard channel (literal tr(), never tr(var))."""
    return {
        "dialog/player": tr("旁聽：玩家的對話"),
        "dialog/npc":    tr("旁聽：NPC 之間的對話"),
        "group/player":  tr("旁聽：群體對話中的玩家"),
        "group/npc":     tr("旁聽：群體對話中的 NPC"),
        "ambient-npc":   tr("旁聽：NPC 的環境自語"),
    }.get(channel, tr("旁聽"))



class _SuggestPopup:
    """A borderless listbox under an entry, offering ``(value, label)`` rows.

    Deliberately never takes focus: an autocomplete that focuses itself
    interrupts the typing that opened it (the 交戰 field used a PopoverMenu at
    first, which calls focus_force and swallowed every other keystroke).  The
    entry keeps focus; Up/Down/Enter are forwarded from it.
    """

    def __init__(self, anchor_entry, rows: int = 8):
        self.entry = anchor_entry
        self.rows = rows
        self._top = None
        self._lb = None
        self._values: List[str] = []
        self._on_pick = None

    def _ensure(self) -> None:
        if self._top is not None:
            return
        top = tk.Toplevel(self.entry)
        top.wm_overrideredirect(True)
        try:
            top.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        lb = tk.Listbox(top, exportselection=False, activestyle="none",
                        height=self.rows, highlightthickness=1,
                        font=("Microsoft JhengHei", 10))
        lb.pack(fill="both", expand=True)
        lb.bind("<ButtonRelease-1>", lambda _e: self.accept())
        self._top, self._lb = top, lb
        top.withdraw()

    def show(self, rows, on_pick) -> None:
        """*rows* is a sequence of ``(value, label)``."""
        rows = list(rows)
        if not rows:
            self.hide()
            return
        self._ensure()
        self._on_pick = on_pick
        self._values = [v for v, _ in rows]
        lb = self._lb
        lb.delete(0, tk.END)
        for _v, label in rows:
            lb.insert(tk.END, label)
        lb.configure(height=min(self.rows, lb.size()))
        self.entry.update_idletasks()
        x = self.entry.winfo_rootx()
        y = self.entry.winfo_rooty() + self.entry.winfo_height()
        w = max(self.entry.winfo_width(), lb.winfo_reqwidth())
        self._top.wm_geometry(f"{w}x{lb.winfo_reqheight()}+{x}+{y}")
        self._top.deiconify()
        self._top.lift()          # no focus_force — the entry keeps the caret

    def visible(self) -> bool:
        try:
            return self._top is not None and self._top.state() == "normal"
        except tk.TclError:
            return False

    def hide(self) -> None:
        if self._top is not None:
            try:
                self._top.withdraw()
            except tk.TclError:
                pass

    def destroy(self) -> None:
        if self._top is not None:
            try:
                self._top.destroy()
            except tk.TclError:
                pass
            self._top = None

    def move(self, delta: int) -> None:
        lb = self._lb
        if lb is None or lb.size() == 0:
            return
        cur = lb.curselection()
        i = max(0, min(lb.size() - 1, (cur[0] if cur else -1) + delta))
        lb.selection_clear(0, tk.END)
        lb.selection_set(i)
        lb.see(i)

    def accept(self) -> None:
        lb = self._lb
        sel = lb.curselection() if lb is not None else ()
        idx = sel[0] if sel else -1
        if 0 <= idx < len(self._values) and callable(self._on_pick):
            self._on_pick(self._values[idx])
        self.hide()
        try:
            self.entry.focus_set()
        except tk.TclError:
            pass


class _SideEntry(ttk.Frame):
    """One side of a 戰場喊話 engagement: free text plus a 🔍 lookup.

    The engagement is written with **display names**, not ids — real captures
    show a kingdom (``弗蘭迪亞``), the player's clan (``赫芬斯汀``), a party
    owner (``維達爾's party``) and a bare enemy label (``劫掠者``).  So the field
    stays free text and the lookup only helps you spell the name: it searches
    kingdoms, clans and characters, and offers the ``…'s party`` form for a
    character because that is how the game writes a party side.
    """

    def __init__(self, parent, app, on_change, *, width: int = 18, **kw):
        super().__init__(parent, **kw)
        self.app = app
        self._suppress = False
        self.var = tk.StringVar()
        self.entry = ttk.Entry(self, textvariable=self.var, width=width)
        self.entry.pack(side=tk.LEFT)
        ttk.Button(self, text="🔍", width=3,          # icon only
                   style="secondary.TButton",
                   command=self._open_lookup).pack(side=tk.LEFT, padx=(2, 0))
        self.var.trace_add("write", lambda *_a: on_change())
        # Suggest while typing, not only on the 🔍 button: otherwise nobody
        # discovers that typing a character name can become "…'s party".
        self._popup = _SuggestPopup(self.entry)
        self.entry.bind("<KeyRelease>", self._on_key)
        self.entry.bind("<Down>", self._nav_down)
        self.entry.bind("<Up>", self._nav_up)
        self.entry.bind("<Return>", self._nav_return)
        self.entry.bind("<Escape>", lambda _e: self._popup.hide())
        self.entry.bind("<FocusOut>", lambda _e: self.after(150, self._popup.hide))
        self.bind("<Destroy>", lambda _e: self._popup.destroy())

    def get(self) -> str:
        return self.var.get().strip()

    def set(self, value: str) -> None:
        self._suppress = True
        try:
            self.var.set(value or "")
        finally:
            self._suppress = False

    def _on_key(self, event) -> None:
        if self._suppress or event.keysym in ("Up", "Down", "Return", "Tab",
                                              "Escape", "Left", "Right"):
            return
        term = self.get()
        if term:
            self._popup.show([(v, v) for v, _g in self.matches(term)], self.set)
        else:
            self._popup.hide()

    def _nav_down(self, _e):
        if self._popup.visible():
            self._popup.move(1)
        else:
            self._popup.show([(v, v) for v, _g in self.matches(self.get())], self.set)
        return "break"

    def _nav_up(self, _e):
        if self._popup.visible():
            self._popup.move(-1)
            return "break"
        return None

    def _nav_return(self, _e):
        if self._popup.visible():
            self._popup.accept()
            return "break"
        return None

    def matches(self, term: str) -> List[Tuple[str, str]]:
        """``(label, group)`` candidates for *term*, across all side sources."""
        out: List[Tuple[str, str]] = []
        if self.app is None or not term.strip():
            return out
        for category, party in (("kingdoms", False), ("clans", False),
                                ("speakers", True)):
            try:
                hits = self.app.terminology_suggest(category, term.strip(), 6)
            except Exception:
                hits = []
            for _hid, name in hits:
                out.append((f"{name}'s party" if party else name, category))
        return out

    def _open_lookup(self) -> None:
        rows = self.matches(self.get())
        items: List = []
        last_group = None
        for label, group in rows:
            if last_group is not None and group != last_group:
                items.append(None)
            last_group = group
            items.append((label, lambda v=label: self.set(v)))
        if not items:
            items = [(tr("（找不到符合的名稱，可直接輸入）"), None, "muted")]
        PopoverMenu(self, items, direction="down", min_width=200).show()


class SpeakerField(ttk.Frame):
    def __init__(
        self,
        parent,
        app=None,
        *,
        width: int = 44,
        popup_rows: int = 8,
        get_self: Optional[Callable[[], Tuple[str, str]]] = None,
        get_day: Optional[Callable[[], float]] = None,
        **kw,
    ):
        """*get_self* returns ``(name, hero_id)`` of the character being edited —
        what 「自己（I）」 fills in.  It returns ``("", "")`` for batch targets,
        where "self" is meaningless up front (see ``resolve_for_target``)."""
        super().__init__(parent, **kw)
        self.app = app
        self._get_self = get_self or (lambda: ("", ""))
        self._get_day = get_day or (lambda: 0.0)
        self._popup_rows = popup_rows
        self._suppress = False

        self.var = tk.StringVar()
        row = ttk.Frame(self)
        row.pack(fill=tk.X)
        self.entry = ttk.Entry(row, textvariable=self.var, width=width)
        self.entry.pack(side=tk.LEFT)
        self._quick_btn = ttk.Button(row, text=tr("⚡ 快速設定 ▾"),
                                     style="secondary.TButton",
                                     command=self._open_quick_menu)
        self._quick_btn.pack(side=tk.LEFT, padx=(4, 0))
        self._status = ttk.Label(row, text="", foreground=tcol("#888888"))
        self._status.pack(side=tk.LEFT, padx=(6, 0))

        # Wrapper detail row — only shown while a 旁聽 wrapper is applied, so the
        # numbers are editable without picking them out of the prefix by hand.
        self._wrap_row = ttk.Frame(self)
        self._dist_var = tk.StringVar(value="3.0")
        ttk.Label(self._wrap_row, text=tr("戰役日:")).pack(side=tk.LEFT)
        # 年/季/日 picker, same as the dynamic-event editor — nobody can read a
        # raw campaign day like 91119, and the default lands on "now".
        self._date = GameDateField(self._wrap_row, initial_value=self._get_day(),
                                   show_raw=False)
        self._date.frame.pack(side=tk.LEFT, padx=(2, 10))
        self._date.on_change = self._apply_wrap_row
        ttk.Label(self._wrap_row, text=tr("距離:")).pack(side=tk.LEFT)
        ttk.Spinbox(self._wrap_row, from_=0, to=999, increment=0.5, width=6,
                    textvariable=self._dist_var,
                    command=self._apply_wrap_row).pack(side=tk.LEFT, padx=(2, 2))
        ttk.Label(self._wrap_row, text=tr("公尺")).pack(side=tk.LEFT)
        self._chan_lbl = ttk.Label(self._wrap_row, text="", foreground=tcol("#6B5B3E"))
        self._chan_lbl.pack(side=tk.LEFT, padx=(10, 0))
        self._dist_var.trace_add("write", lambda *_a: self._apply_wrap_row())

        # ── 戰場喊話 engagement row (shown while a Battle wrapper is set) ──
        self._battle_row = ttk.Frame(self)
        ttk.Label(self._battle_row, text=tr("交戰:")).pack(side=tk.LEFT)
        self._side_a = _SideEntry(self._battle_row, app, self._apply_battle_row)
        self._side_a.pack(side=tk.LEFT)
        ttk.Label(self._battle_row, text=" vs ").pack(side=tk.LEFT)   # mod literal
        self._side_b = _SideEntry(self._battle_row, app, self._apply_battle_row)
        self._side_b.pack(side=tk.LEFT)
        ttk.Label(self._battle_row,
                  text=tr("　（可搜尋王國／氏族／角色，或直接輸入，例如「劫掠者」）"),
                  foreground=tcol("#9AA0A6")).pack(side=tk.LEFT)

        self._popup = None
        self._popup_lb = None
        self._popup_rowdata: List[str] = []

        self.entry.bind("<KeyRelease>", self._on_key)
        self.entry.bind("<Down>", self._nav_down)
        self.entry.bind("<Up>", self._nav_up)
        self.entry.bind("<Return>", self._nav_return)
        self.entry.bind("<Escape>", lambda _e: self._hide_popup())
        self.entry.bind("<FocusOut>", lambda _e: self.after(150, self._hide_popup))
        self.bind("<Destroy>", lambda _e: self._destroy_popup())
        self._refresh_status()

    # ── public API ────────────────────────────────────────────────────────
    def get_prefix(self) -> str:
        """The literal prefix to write ("" = no speaker → plain text line)."""
        return self.var.get().strip()

    def set_prefix(self, prefix: str) -> None:
        self._suppress = True
        try:
            self.var.set(prefix or "")
        finally:
            self._suppress = False
        self._sync_wrap_row()
        self._refresh_status()

    def clear(self) -> None:
        self.set_prefix("")

    def speaker(self) -> SF.Speaker:
        return SF.parse(self.get_prefix())

    # ── search ────────────────────────────────────────────────────────────
    def _special_matches(self, term: str) -> List[Tuple[str, str]]:
        """``(prefix, label)`` special identities matching *term*, most useful first."""
        out: List[Tuple[str, str]] = []
        self_name, self_id = self._get_self()
        if self_id and _matches(term, _SYN_SELF):
            out.append((SF.build(SF.make_self(self_name, self_id)),
                        tr("自己（I）") + f" — {self_name}"))
        if self.app is not None and _matches(term, _SYN_PLAYER):
            name = self._name_for(SF.PLAYER_ID)
            out.append((SF.build(SF.make_named(name, SF.PLAYER_ID)),
                        tr("玩家") + f" — {name}"))
        if _matches(term, _SYN_STRANGER):
            out.append((SF.IDENTITY_STRANGER, tr("陌生人（Stranger）")))
        if _matches(term, _SYN_UNKNOWN):
            out.append((SF.IDENTITY_UNIDENTIFIED, tr("身分不明（Unidentified person）")))
        return out

    def _name_for(self, hero_id: str) -> str:
        if self.app is None:
            return hero_id
        try:
            return self.app.terminology_name_for(_SEARCH_CATEGORY, hero_id) or hero_id
        except Exception:
            return hero_id

    def _suggestions(self, term: str) -> List[Tuple[str, str]]:
        out = self._special_matches(term)
        if self.app is not None and term.strip():
            try:
                for hid, name in self.app.terminology_suggest(
                        _SEARCH_CATEGORY, term.strip(), 40):
                    out.append((SF.build(SF.make_named(name, hid)), f"{name}  （{hid}）"))
            except Exception:
                pass
        return out

    # ── quick-set menu ────────────────────────────────────────────────────
    def _open_quick_menu(self) -> None:
        sp = self.speaker()
        items = [
            (tr("無（純文本，不設說話者）"), self.clear),
            None,
            (tr("自己（I）"), self._set_self),
            (tr("玩家"), self._set_player),
            (tr("陌生人（Stranger）"),
             lambda: self._set_identity(SF.IDENTITY_STRANGER)),
            (tr("身分不明（Unidentified person）"),
             lambda: self._set_identity(SF.IDENTITY_UNIDENTIFIED)),
            (tr("已介紹（as introduced）"), self._toggle_introduced),
            None,
            (tr("🏷 自訂標籤 ▸"), self._open_tag_menu),
            (tr("👂 旁聽 ▸"), self._open_channel_menu),
            (tr("⚔ 戰場喊話"), self._set_battle),
        ]
        if sp.kind == "speech" and sp.wrapper is not None:
            items.append((tr("移除情境包裹"), self._clear_wrapper))
        PopoverMenu(self._quick_btn, items, direction="down").show()

    def _open_tag_menu(self) -> None:
        """Story tags — narration / inner voice / rumour, plus the user's own."""
        raw = getattr(self.app, "settings", {}).get(TAGS.SETTINGS_KEY) if self.app else None
        items = [(label, lambda v=label: self.set_prefix(v))
                 for label in TAGS.visible_tags(raw)]
        if items:
            items.append(None)
        items.append((tr("⚙ 管理自訂標籤…"), self._manage_tags))
        PopoverMenu(self._quick_btn, items, direction="down", min_width=200).show()

    def _manage_tags(self) -> None:
        if self.app is None:
            return
        from dialogs.dialogue_tag_dialog import open_dialogue_tag_dialog
        open_dialogue_tag_dialog(self.app)

    def _open_channel_menu(self) -> None:
        items = [(channel_label(c), lambda c=c: self._set_overheard(c))
                 for c in SF.CHANNELS]
        PopoverMenu(self._quick_btn, items, direction="down", min_width=220).show()

    # ── quick-set actions ─────────────────────────────────────────────────
    def _set_self(self) -> None:
        name, hid = self._get_self()
        if not hid:
            self._flash(tr("此處為批量寫入，請直接選擇角色"))
            return
        self.set_prefix(SF.build(SF.make_self(name, hid, wrapper=self.speaker().wrapper)))

    def _set_player(self) -> None:
        name = self._name_for(SF.PLAYER_ID)
        self.set_prefix(SF.build(SF.make_named(name, SF.PLAYER_ID,
                                               wrapper=self.speaker().wrapper)))

    def _set_identity(self, identity: str) -> None:
        sp = self.speaker()
        if sp.kind != "speech":
            # Nothing usable to modify — start a bare identity.
            self.set_prefix(identity)
            return
        if sp.is_self:
            # "I" has no name position to swap; drop back to third person first.
            sp = SF.make_named(sp.self_name, sp.hero_id, wrapper=sp.wrapper)
        self.set_prefix(SF.build(SF.with_identity(sp, identity)))

    def _toggle_introduced(self) -> None:
        sp = self.speaker()
        if sp.kind != "speech" or not sp.hero_id:
            self._flash(tr("請先選擇角色"))
            return
        if sp.is_self:
            sp = SF.make_named(sp.self_name, sp.hero_id, wrapper=sp.wrapper)
        new = (SF.RELATION_NONE if sp.relation == SF.RELATION_INTRODUCED
               else SF.RELATION_INTRODUCED)
        self.set_prefix(SF.build(SF.with_relation(sp, new)))

    def _set_overheard(self, channel: str) -> None:
        sp = self.speaker()
        if sp.kind != "speech":
            self._flash(tr("請先設定說話者"))
            return
        try:
            day = float(self._date.get())
        except (ValueError, TypeError):
            day = 0.0
        if not day:
            day = float(self._get_day() or 0.0)
            self._date.set_value(day)
        try:
            dist = float(self._dist_var.get())
        except ValueError:
            dist = 3.0
        self.set_prefix(SF.build(SF.with_wrapper(
            sp, SF.Overheard(day=day, distance=dist, channel=channel))))

    def _set_battle(self) -> None:
        sp = self.speaker()
        if sp.kind != "speech":
            # A battle shout's speaker is a bare name with no id — that is how
            # the game writes it — so plain text is a legitimate starting point
            # here, unlike the other wrappers.  Bracketed story tags are not.
            text = self.get_prefix()
            if not text or text[0] in "[(":
                self._flash(tr("請先設定說話者"))
                return
            sp = SF.Speaker(identity=text, hero_id="")
        cur = sp.wrapper.engagement if isinstance(sp.wrapper, SF.Battle) else ""
        if not cur:
            a, b = self._side_a.get(), self._side_b.get()
            cur = f"{a} vs {b}" if (a and b) else (a or b)
        self.set_prefix(SF.build(SF.with_wrapper(sp, SF.Battle(engagement=cur))))

    def _clear_wrapper(self) -> None:
        self.set_prefix(SF.build(SF.with_wrapper(self.speaker(), None)))

    # ── wrapper detail row ────────────────────────────────────────────────
    def _sync_wrap_row(self) -> None:
        sp = self.speaker()
        wrap = sp.wrapper if sp.kind == "speech" else None
        if isinstance(wrap, SF.Overheard):
            self._suppress = True
            try:
                self._date.set_value(wrap.day)
                self._dist_var.set(f"{wrap.distance:.1f}")
            finally:
                self._suppress = False
            self._chan_lbl.configure(text=channel_label(wrap.channel))
            if not self._wrap_row.winfo_manager():
                self._wrap_row.pack(fill=tk.X, pady=(4, 0))
        else:
            self._wrap_row.pack_forget()

        if isinstance(wrap, SF.Battle):
            self._suppress = True
            try:
                a, b = _split_engagement(wrap.engagement)
                self._side_a.set(a)
                self._side_b.set(b)
            finally:
                self._suppress = False
            if not self._battle_row.winfo_manager():
                self._battle_row.pack(fill=tk.X, pady=(4, 0))
        else:
            self._battle_row.pack_forget()

    def _apply_battle_row(self) -> None:
        if self._suppress:
            return
        sp = self.speaker()
        if sp.kind != "speech" or not isinstance(sp.wrapper, SF.Battle):
            return
        a, b = self._side_a.get(), self._side_b.get()
        engagement = f"{a} vs {b}" if (a and b) else (a or b)
        self._suppress = True
        try:
            self.var.set(SF.build(SF.with_wrapper(sp, SF.Battle(engagement=engagement))))
        finally:
            self._suppress = False
        self._refresh_status()

    def _apply_wrap_row(self) -> None:
        if self._suppress:
            return
        sp = self.speaker()
        if sp.kind != "speech" or not isinstance(sp.wrapper, SF.Overheard):
            return
        try:
            day = float(self._date.get())
            dist = float(self._dist_var.get())
        except (ValueError, TypeError):
            return
        self._suppress = True
        try:
            self.var.set(SF.build(SF.with_wrapper(
                sp, SF.Overheard(day=day, distance=dist, channel=sp.wrapper.channel))))
        finally:
            self._suppress = False
        self._refresh_status()

    # ── status ────────────────────────────────────────────────────────────
    def _flash(self, msg: str) -> None:
        self._status.configure(text=msg, foreground=tcol("#E67E22"))
        self.after(2500, self._refresh_status)

    def _refresh_status(self) -> None:
        text = self.get_prefix()
        if not text:
            self._status.configure(text=tr("（純文本）"), foreground=tcol("#888888"))
            return
        sp = SF.parse(text)
        if sp.kind != "speech":
            self._status.configure(text=tr("自訂前綴"), foreground=tcol("#888888"))
            return
        bits = []
        if sp.is_self:
            bits.append(tr("自己"))
        elif sp.is_player:
            bits.append(tr("玩家"))
        if sp.is_anonymous:
            bits.append(tr("身分未明"))
        if sp.relation == SF.RELATION_INTRODUCED:
            bits.append(tr("已介紹"))
        if isinstance(sp.wrapper, SF.Overheard):
            bits.append(tr("旁聽"))
        elif isinstance(sp.wrapper, SF.Battle):
            bits.append(tr("戰場"))
        label = "・".join(bits) if bits else tr("一般發言")
        self._status.configure(text=f"✓ {label}", foreground=tcol("#1F9D55"))

    # ── suggestion popup ──────────────────────────────────────────────────
    def _on_key(self, event) -> None:
        if self._suppress or event.keysym in (
                "Up", "Down", "Return", "Tab", "Escape", "Left", "Right"):
            return
        self._sync_wrap_row()
        self._refresh_status()
        term = self.get_prefix()
        # Once the text is a valid prefix the user is editing, not searching.
        if not term or SF.parse(term).kind == "speech":
            self._hide_popup()
            return
        self._show_suggestions(term)

    def _ensure_popup(self) -> None:
        if self._popup is not None:
            return
        top = tk.Toplevel(self)
        top.wm_overrideredirect(True)
        try:
            top.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        lb = tk.Listbox(top, exportselection=False, activestyle="none",
                        height=self._popup_rows, highlightthickness=1,
                        font=("Microsoft JhengHei", 10))
        lb.pack(fill="both", expand=True)
        lb.bind("<ButtonRelease-1>", lambda _e: self._accept(self._lb_index()))
        self._popup, self._popup_lb = top, lb
        top.withdraw()

    def _show_suggestions(self, term: str) -> None:
        rows = self._suggestions(term)
        if not rows:
            self._hide_popup()
            return
        self._ensure_popup()
        lb = self._popup_lb
        lb.delete(0, tk.END)
        self._popup_rowdata = []
        for prefix, label in rows:
            lb.insert(tk.END, label)
            self._popup_rowdata.append(prefix)
        lb.configure(height=min(self._popup_rows, lb.size()))
        self.update_idletasks()
        x = self.entry.winfo_rootx()
        y = self.entry.winfo_rooty() + self.entry.winfo_height()
        w = max(self.entry.winfo_width(), lb.winfo_reqwidth())
        self._popup.wm_geometry(f"{w}x{lb.winfo_reqheight()}+{x}+{y}")
        self._popup.deiconify()
        self._popup.lift()

    def _lb_index(self) -> int:
        sel = self._popup_lb.curselection() if self._popup_lb else ()
        return sel[0] if sel else -1

    def _accept(self, idx: int) -> None:
        if 0 <= idx < len(self._popup_rowdata):
            self.set_prefix(self._popup_rowdata[idx])
        self._hide_popup()
        self.entry.focus_set()

    def _popup_visible(self) -> bool:
        try:
            return self._popup is not None and self._popup.state() == "normal"
        except Exception:
            return False

    def _move(self, delta: int) -> None:
        lb = self._popup_lb
        if lb is None or lb.size() == 0:
            return
        cur = lb.curselection()
        i = max(0, min(lb.size() - 1, (cur[0] if cur else -1) + delta))
        lb.selection_clear(0, tk.END)
        lb.selection_set(i)
        lb.see(i)

    def _nav_down(self, _e):
        if self._popup_visible():
            self._move(1)
            return "break"
        self._show_suggestions(self.get_prefix())
        return "break"

    def _nav_up(self, _e):
        if self._popup_visible():
            self._move(-1)
            return "break"
        return None

    def _nav_return(self, _e):
        if self._popup_visible():
            self._accept(self._lb_index())
            return "break"
        return None

    def _hide_popup(self) -> None:
        if self._popup is not None:
            self._popup.withdraw()

    def _destroy_popup(self) -> None:
        if self._popup is not None:
            try:
                self._popup.destroy()
            except Exception:
                pass
            self._popup = None

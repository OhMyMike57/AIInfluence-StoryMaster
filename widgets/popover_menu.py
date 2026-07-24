"""Custom popover menus / panels — a prettier, collapsible replacement for
``tk.Menu`` whose native styling looks dated.

Two flavours share the same positioning + open/close machinery
(:class:`_PopoverBase`):

* :class:`PopoverMenu` — a vertical list of clickable rows (like a dropdown /
  drop-up menu). Supports separators, per-item text style, hover highlight,
  and keyboard navigation (Up/Down/Return/Escape) so it is no less convenient
  than the native menu it replaces.
* :class:`PopoverPanel` — a bordered card the caller fills with arbitrary
  widgets (checkboxes, buttons…). Clicking *inside* the panel does NOT close it
  (only an outside click / Escape / re-clicking the anchor does).

Positioning: ``direction="down"`` anchors the top-left of the popover to the
anchor widget's bottom-left; ``"up"`` stacks it above. Both auto-flip and clamp
so the popover never spills off-screen.

Open/close: shown via ``toggle()`` (wired to the anchor button's command).
A press anywhere outside the popover closes it; re-clicking the anchor toggles
it off (a short guard window suppresses the reopen that the same click would
otherwise trigger). ``Escape`` also closes.
"""
from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional, Sequence, Tuple, Union

from i18n import tr
from ui.theme import paint, tcol

# One menu item: a separator sentinel, or (label, command[, style_key]).
MenuItem = Union[str, None, Tuple]

_BORDER = "#B8B8B8"
_BORDER_PX = 1          # normal hairline — the highlight-ring technique renders
                        # reliably, so no need for the thick/dark emphasis
_CARD_BG = "#FFFFFF"
_HOVER_BG = "#EFEAE0"
_TEXT = "#333333"
# Separator rule.  It used to be #E2E2E2, which on a white card is a hairline
# nobody can see — menus read as one undivided list, hiding the grouping the
# separators exist to convey.  Same weight as the card border.
_SEP = "#B8B8B8"
_STYLE_FG = {
    "danger":  "#C0392B",
    "success": "#1A8A4A",
    "info":    "#1F6FB2",
    "muted":   "#888888",
}
_FONT = ("Microsoft JhengHei", 10)


class _PopoverBase:
    """Shared overrideredirect Toplevel with up/down positioning + auto-close."""

    def __init__(self, anchor: tk.Widget, *, direction: str = "down",
                 at: Optional[Tuple[int, int]] = None,
                 on_hide: Optional[Callable[[], None]] = None):
        self.anchor = anchor
        self.direction = direction
        # (x_root, y_root) to open at instead of beside the anchor — how a
        # right-click context menu lands under the pointer while still using
        # the themed popover rather than a dated native tk.Menu.
        self.at = at
        self._on_hide = on_hide
        self._top: Optional[tk.Toplevel] = None
        self._visible = False
        self._closed_at = 0.0
        self._root_bind_id = None
        self._cfg_bind_id = None
        self._root = anchor.winfo_toplevel()

    # ── subclasses build their content into self._container ──────────────
    def _build_body(self) -> None:
        raise NotImplementedError

    # ── open / close ─────────────────────────────────────────────────────
    def toggle(self) -> None:
        # Suppress the reopen when the same physical click just closed us
        # (outside-click handler fires on press; button command on release).
        if self._visible:
            self.hide()
            return
        if (time.monotonic() - self._closed_at) < 0.3:
            return
        self.show()

    def show(self) -> None:
        if self._visible:
            return
        top = tk.Toplevel(self.anchor)
        top.wm_overrideredirect(True)
        try:
            top.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        self._top = top
        # Card border: draw it with the frame's own highlight ring so it does
        # not depend on padding/geometry propagation (an inset-padding border
        # rendered invisibly in practice). The toplevel bg is set to the border
        # colour too, as a fallback hairline.
        top.configure(bg=tcol(_BORDER))
        self._container = paint(
            tk.Frame(top, bd=0, highlightthickness=_BORDER_PX),
            bg=tcol(_CARD_BG),
            highlightbackground=tcol(_BORDER), highlightcolor=tcol(_BORDER),
        )
        self._container.pack(fill="both", expand=True)
        self._build_body()

        top.update_idletasks()
        self._place()
        top.deiconify()
        top.lift()
        try:
            top.focus_force()
        except tk.TclError:
            pass

        self._visible = True
        # Close on any press outside the popover (bound on the root so it
        # catches clicks anywhere in the app window).
        self._root_bind_id = self._root.bind("<Button-1>", self._on_root_click, add="+")
        top.bind("<Escape>", lambda e: self.hide())
        # Close when focus leaves the popover — covers clicking another window
        # or Alt+Tab, neither of which fires the in-app <Button-1> above.
        top.bind("<FocusOut>", self._on_focus_out)
        # Close when the main window is moved/resized (the popover is anchored
        # to a widget and would otherwise float in a stale position).
        self._cfg_bind_id = self._root.bind("<Configure>", self._on_root_configure, add="+")

    def _place(self) -> None:
        top = self._top
        a = self.anchor
        w, h = top.winfo_reqwidth(), top.winfo_reqheight()
        sw, sh = top.winfo_screenwidth(), top.winfo_screenheight()
        if self.at is not None:
            x, y = self.at
            # Flip up / left when the menu would run off the screen edge.
            if y + h > sh:
                y = max(0, y - h)
            top.wm_geometry(f"{w}x{h}+{max(0, min(x, sw - w))}+{max(0, y)}")
            return
        ax, ay = a.winfo_rootx(), a.winfo_rooty()
        ah = a.winfo_height()

        direction = self.direction
        if direction == "down" and ay + ah + h > sh and ay - h > 0:
            direction = "up"      # not enough room below → flip up
        elif direction == "up" and ay - h < 0 and ay + ah + h <= sh:
            direction = "down"    # not enough room above → flip down

        y = (ay - h) if direction == "up" else (ay + ah)
        x = ax
        # Clamp on-screen.
        x = max(0, min(x, sw - w))
        y = max(0, min(y, sh - h))
        top.wm_geometry(f"{w}x{h}+{x}+{y}")

    def hide(self) -> None:
        if not self._visible:
            return
        self._visible = False
        self._closed_at = time.monotonic()
        if self._root_bind_id is not None:
            try:
                self._root.unbind("<Button-1>", self._root_bind_id)
            except Exception:
                pass
            self._root_bind_id = None
        if self._cfg_bind_id is not None:
            try:
                self._root.unbind("<Configure>", self._cfg_bind_id)
            except Exception:
                pass
            self._cfg_bind_id = None
        if self._top is not None:
            try:
                self._top.destroy()
            except Exception:
                pass
            self._top = None
        if self._on_hide is not None:
            try:
                self._on_hide()
            except Exception:
                pass

    def _on_root_click(self, event) -> None:
        # A click inside the popover is handled by the popover itself.
        if self._top is not None and self._point_in_top(event):
            return
        self.hide()

    def _point_in_top(self, event) -> bool:
        try:
            top = self._top
            x, y = event.x_root, event.y_root
            tx, ty = top.winfo_rootx(), top.winfo_rooty()
            return tx <= x <= tx + top.winfo_width() and ty <= y <= ty + top.winfo_height()
        except Exception:
            return False

    def _on_focus_out(self, event) -> None:
        # Focus left the popover's toplevel. Keep it open only if focus went to
        # a widget *inside* the popover (e.g. a checkbox in a PopoverPanel);
        # otherwise (another app window, Alt+Tab) close.
        try:
            focused = self._top.focus_get()
        except (tk.TclError, KeyError):
            focused = None
        if focused is not None and self._is_descendant(focused):
            return
        self.hide()

    def _on_root_configure(self, event) -> None:
        # Only react to the main window itself moving/resizing, not <Configure>
        # bubbling from some inner widget.
        if event.widget is self._root:
            self.hide()

    def _is_descendant(self, widget) -> bool:
        try:
            return str(widget).startswith(str(self._top))
        except Exception:
            return False


class PopoverMenu(_PopoverBase):
    """A dropdown/drop-up list of clickable items."""

    def __init__(self, anchor: tk.Widget, items: Sequence[MenuItem], *,
                 direction: str = "down", min_width: int = 150,
                 at: Optional[Tuple[int, int]] = None,
                 on_hide: Optional[Callable[[], None]] = None):
        super().__init__(anchor, direction=direction, at=at, on_hide=on_hide)
        self.items = list(items)
        self.min_width = min_width
        self._rows: List[Tuple[tk.Label, Callable]] = []
        self._active = -1

    def _build_body(self) -> None:
        self._rows = []
        self._active = -1
        c = self._container
        # Zero-height spacer forces a comfortable minimum width; rows pack
        # fill="x" so they all stretch to the widest content / this minimum.
        paint(tk.Frame(c, height=0, width=self.min_width),
              bg=tcol(_CARD_BG)).pack(fill="x")
        for item in self.items:
            if item is None or item == "-":
                # paint(): a constructor bg is dropped under ttkbootstrap, which
                # is why separators were rendering white-on-white.
                sep = paint(tk.Frame(c, height=2), bg=tcol(_SEP))
                sep.pack(fill="x", padx=6, pady=4)
                sep.pack_propagate(False)   # keep the height with no children
                continue
            label = item[0]
            command = item[1]
            style_key = item[2] if len(item) > 2 else None
            fg = tcol(_STYLE_FG.get(style_key, _TEXT))
            row = paint(tk.Label(c, text=label, font=_FONT,
                                 anchor="w", padx=14, pady=6),
                        bg=tcol(_CARD_BG), fg=fg)
            row.pack(fill="x")
            idx = len(self._rows)
            row.bind("<Enter>", lambda e, i=idx: self._activate(i))
            row.bind("<Button-1>", lambda e, cmd=command: self._invoke(cmd))
            self._rows.append((row, command))
        # Keyboard nav on the popup.
        top = self._top
        top.bind("<Down>", lambda e: self._nav(1))
        top.bind("<Up>", lambda e: self._nav(-1))
        top.bind("<Return>", lambda e: self._nav_return())

    def _activate(self, idx: int) -> None:
        for i, (r, _) in enumerate(self._rows):
            r.configure(bg=tcol(_HOVER_BG) if i == idx else tcol(_CARD_BG))
        self._active = idx

    def _nav(self, delta: int):
        if not self._rows:
            return "break"
        i = self._active + delta
        i = max(0, min(len(self._rows) - 1, i))
        self._activate(i)
        return "break"

    def _nav_return(self):
        if 0 <= self._active < len(self._rows):
            self._invoke(self._rows[self._active][1])
        return "break"

    def _invoke(self, command: Callable) -> None:
        self.hide()
        if callable(command):
            command()


class PopoverPanel(_PopoverBase):
    """A bordered card the caller fills. Clicks inside do not dismiss it.

    Usage::

        panel = PopoverPanel(button, direction="up")
        panel.build(lambda body: ... add widgets to body ...)
        button.configure(command=panel.toggle)
    """

    def __init__(self, anchor: tk.Widget, *, direction: str = "down",
                 builder: Optional[Callable[[tk.Frame], None]] = None,
                 on_hide: Optional[Callable[[], None]] = None):
        super().__init__(anchor, direction=direction, on_hide=on_hide)
        self._builder = builder

    def build(self, builder: Callable[[tk.Frame], None]) -> None:
        self._builder = builder

    def _build_body(self) -> None:
        if self._builder is not None:
            self._builder(self._container)


def attach_menu(button: tk.Widget, items_provider, *, direction: str = "down") -> Callable:
    """Wire *button* to a :class:`PopoverMenu`.

    *items_provider* is either a static item list or a zero-arg callable
    returning one (so the menu can be rebuilt with fresh state each open).
    Returns the toggle callable (also set as the button command).
    """
    state = {"menu": None, "closed_at": 0.0}

    def _mark_closed():
        state["closed_at"] = time.monotonic()

    def _toggle():
        m = state["menu"]
        if m is not None and m._visible:
            m.hide()
            return
        # Suppress the reopen when the same click that closed us also fired
        # the button command (press closes via outside-click, release toggles).
        if (time.monotonic() - state["closed_at"]) < 0.3:
            return
        items = items_provider() if callable(items_provider) else items_provider
        menu = PopoverMenu(button, items, direction=direction, on_hide=_mark_closed)
        state["menu"] = menu
        menu.show()

    button.configure(command=_toggle)
    return _toggle

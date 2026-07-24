from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import json

from i18n import tr


class SortKey:
    """Canonical sort key constants used across services, controllers, and UI.

    UI layers map these keys to localized display strings; business logic
    uses the constants so sort behaviour is independent of display language.
    """
    # Canonical sort keys (stored in settings, compared in sort logic). They are
    # zh-Hant by history; the UI translates them at *display* time via the
    # sort-dropdown display-map. NOT tr()-wrapped here — the
    # stored value must stay canonical or comparisons break.
    NAME       = "名稱"       # noqa: cjk
    ID         = "ID"
    FAVORITES  = "收藏"       # noqa: cjk
    PARTY      = "隊伍"       # noqa: cjk
    ROMANCE    = "浪漫"       # noqa: cjk
    TRUST      = "信任"       # noqa: cjk
    RELATION   = "關係"       # noqa: cjk
    INTERACTION = "互動"      # noqa: cjk
    SICK       = "患病"       # noqa: cjk
    AGE        = "年齡"       # noqa: cjk


DEFAULT_SORT_OPTIONS = [
    SortKey.NAME,
    SortKey.ID,
    SortKey.FAVORITES,
    SortKey.PARTY,
    SortKey.ROMANCE,
    SortKey.TRUST,
    SortKey.RELATION,
    SortKey.INTERACTION,
    SortKey.SICK,
    SortKey.AGE,
]

# Two bundled themes (v0.39.0): 明亮 = Sandstone (light), 黑夜 = Darkly (dark).
# Display labels are canonical zh-Hant keys, tr()-translated at use (see
# ``ui.settings_tab``); the theme_name is what ttkbootstrap.theme_use expects.
AVAILABLE_THEMES = [
    ("sandstone", "明亮"),   # noqa: cjk (label tr()-translated at use)
    ("darkly",    "黑夜"),   # noqa: cjk (label tr()-translated at use)
]

# Language display names are ALWAYS shown in their own script (standard i18n
# practice — a French user must recognise 简体中文/繁體中文), never translated.
AVAILABLE_LANGUAGES = [
    ("zh_TW", "繁體中文"),   # noqa: cjk
    ("zh_CN", "简体中文"),   # noqa: cjk
    ("en", "English"),
]


def load_json_dict(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_json_dict(path: Path, payload: Dict[str, Any]) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def normalize_default_sort(value: str) -> str:
    """Return value if it is a valid sort key, otherwise fall back to SortKey.FAVORITES."""
    value = (value or "").strip()
    return value if value in DEFAULT_SORT_OPTIONS else SortKey.FAVORITES


# ── Sort-dropdown display-map (顯示譯文、儲存標準鍵) ──────────────────────────
# The combobox shows a *localized label*; settings + sort logic keep the
# canonical SortKey.  UI code stores the label in its StringVar and converts
# back with ``sort_key_from_label`` at every logic boundary.  tr() is called at
# runtime (never module scope) so the language chosen at startup is honoured.
def sort_label(key: str) -> str:
    """Canonical SortKey → localized display label."""
    return tr((key or "").strip())


def sort_display_options() -> List[str]:
    """``DEFAULT_SORT_OPTIONS`` rendered as localized labels (combobox values)."""
    return [tr(k) for k in DEFAULT_SORT_OPTIONS]


def sort_key_from_label(label: str) -> str:
    """Localized label (or an already-canonical value) → canonical SortKey.

    Unknown input falls back to ``SortKey.FAVORITES`` — matching
    ``normalize_default_sort`` — so a stale persisted value never crashes sort.
    """
    label = (label or "").strip()
    for k in DEFAULT_SORT_OPTIONS:
        if k == label or tr(k) == label:
            return k
    return SortKey.FAVORITES


def _os_locale_code() -> str:
    """Best-effort read of the OS UI/locale code (e.g. ``zh_TW``, ``en_US``).

    Windows UI language first (most reliable for "what language is the desktop
    in"), then the process default locale, then the POSIX locale env vars.
    Returns ``""`` when nothing can be determined.
    """
    import locale as _loc
    try:
        import ctypes
        windll = getattr(ctypes, "windll", None)
        if windll is not None:
            lcid = windll.kernel32.GetUserDefaultUILanguage()
            name = _loc.windows_locale.get(lcid)
            if name:
                return name
    except Exception:
        pass
    try:
        import warnings
        with warnings.catch_warnings():   # getdefaultlocale is deprecated (3.11+)
            warnings.simplefilter("ignore")
            code = _loc.getdefaultlocale()[0]
        if code:
            return code
    except Exception:
        pass
    import os
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        v = os.environ.get(var)
        if v:
            return v.split(".")[0].split(":")[0]
    return ""


def detect_default_language() -> str:
    """OS locale → app language, for the very first launch only (before the
    user has saved a preference).  Ensures an international user never opens to
    Chinese they can't read: any non-Chinese, non-English locale falls back to
    English.  Traditional regions/scripts → ``zh_TW``; other Chinese → ``zh_CN``.
    """
    code = _os_locale_code().replace("-", "_").lower()
    if code.startswith("zh"):
        if any(t in code for t in ("tw", "hk", "mo", "hant")):
            return "zh_TW"
        return "zh_CN"
    return "en"


def build_settings(script_dir: Path, settings_file: str) -> tuple[Path, Dict[str, Any]]:
    path = script_dir / settings_file
    settings = load_json_dict(path)
    return path, settings

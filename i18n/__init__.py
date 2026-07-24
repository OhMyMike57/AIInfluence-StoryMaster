"""Dictionary-based i18n module for AI Influence: Story Master.

Supported language codes: 'zh_TW', 'zh_CN', 'en'

Usage::

    from i18n import tr, set_lang, get_lang

    set_lang("en")
    print(tr("清除"))   # "Clear"

The default language is 'zh_TW'. If a key is not found in the active
language's dictionary the key itself is returned, so zh_TW strings always
work out of the box without any entry in zh_TW.STRINGS.
"""
from __future__ import annotations

_lang: str = "zh_TW"
_dicts: dict = {}


def _load() -> None:
    """Lazy-load all language dictionaries (runs once)."""
    global _dicts
    if _dicts:
        return
    from . import zh_TW, zh_CN, en
    _dicts = {
        "zh_TW": zh_TW.STRINGS,
        "zh_CN": zh_CN.STRINGS,
        "en": en.STRINGS,
    }


def set_lang(lang: str) -> None:
    """Set active UI language ('zh_TW', 'zh_CN', or 'en')."""
    global _lang
    _load()
    if lang in _dicts:
        _lang = lang


def get_lang() -> str:
    """Return the current language code."""
    return _lang


def tr(key: str) -> str:
    """Translate *key* to the current language; falls back to *key* if not found."""
    _load()
    return _dicts.get(_lang, {}).get(key, key)

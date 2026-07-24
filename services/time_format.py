"""Bannerlord in-game time utilities.

Mount & Blade II uses a continuous campaign-day counter.
One in-game year  = 84 days  (4 seasons × 21 days each)
Season map:  0-20 → 春  21-41 → 夏  42-62 → 秋  63-83 → 冬

Usage::

    from services.time_format import format_game_time, game_days_to_date

    format_game_time(91163.56)   # "1085年夏3日"
    game_days_to_date(91163.56)  # (1085, '夏', 3)
"""
from __future__ import annotations

import datetime as _dt
import re as _re
from typing import List, Tuple

from i18n import tr

# Canonical season identifiers — stored and round-tripped via _SEASONS.index().
# These zh-Hant tokens are the *canonical* value (also the i18n keys); the UI
# shows localized labels via ``season_display_options`` and converts input back
# with ``season_key_from_label`` so display and logic stay decoupled.
_SEASONS = ["春", "夏", "秋", "冬"]   # noqa: cjk
SEASONS = tuple(_SEASONS)   # public copy for callers (e.g. UI dropdowns)
DAYS_PER_SEASON = 21
SEASONS_PER_YEAR = 4
DAYS_PER_YEAR = DAYS_PER_SEASON * SEASONS_PER_YEAR   # 84

# The absolute campaign day the standard campaign starts on: 1084年春1日.
# Bannerlord's counter runs from year 0, so the start is 1084 × 84 = 91056.
# Needed because AI Influence 6.0 began storing some values as *days elapsed
# since the campaign started* rather than as absolute days
# (see ``memory_service.entry_day``).
CAMPAIGN_START_DAY = 1084 * DAYS_PER_YEAR   # 91056


def game_days_to_date(days: float) -> Tuple[int, str, int]:
    """Return (year, season_zh, day_in_season) for a campaign-day value.

    Example:
        >>> game_days_to_date(91163.56)
        (1085, '夏', 3)
    """
    days = max(0.0, float(days))
    year = int(days // DAYS_PER_YEAR)
    day_of_year = days % DAYS_PER_YEAR
    season_idx = min(3, int(day_of_year // DAYS_PER_SEASON))   # clamp to [0, 3]
    season_zh = _SEASONS[season_idx]
    day_in_season = int(day_of_year % DAYS_PER_SEASON) + 1     # 1-based
    return year, season_zh, day_in_season


def date_to_game_days(
    year: int, season_zh: str, day_in_season: int,
    *, fraction: float = 0.0,
) -> float:
    """Inverse of :func:`game_days_to_date`.

    Returns a campaign-day float for the given calendar tuple.  The
    optional *fraction* (0.0–1.0) preserves the time-of-day component
    so callers can round-trip a value without losing precision::

        y, s, d = game_days_to_date(91216.29)
        date_to_game_days(y, s, d, fraction=0.29) == 91216.29

    Inputs are clamped to legal ranges (year ≥ 0, season ∈ {春夏秋冬},
    day ∈ [1, 21]) so the result is always a non-negative day index.
    """
    y = max(0, int(year))
    try:
        s_idx = _SEASONS.index(season_zh)
    except ValueError:
        s_idx = 0
    d = max(1, min(DAYS_PER_SEASON, int(day_in_season)))
    integer_day = y * DAYS_PER_YEAR + s_idx * DAYS_PER_SEASON + (d - 1)
    frac = max(0.0, min(0.9999999, float(fraction)))
    return float(integer_day) + frac


def format_game_time(days: float) -> str:
    """Return a localized date string (zh: '1085年夏3日', en: 'Yr 1085, Summer 3')."""
    y, s, d = game_days_to_date(days)
    return tr("{y}年{s}{d}日").format(y=y, s=tr(s), d=d)


# ── Season display-map (顯示譯文、儲存標準鍵) ─────────────────────────────────
def season_label(season_zh: str) -> str:
    """Canonical season token → localized display label."""
    return tr(season_zh)


def season_display_options() -> List[str]:
    """The four seasons as localized labels (combobox values)."""
    return [tr(s) for s in _SEASONS]


def season_key_from_label(label: str) -> str:
    """Localized label (or an already-canonical token) → canonical season token."""
    label = (label or "").strip()
    for s in _SEASONS:
        if s == label or tr(s) == label:
            return s
    return _SEASONS[0]


# ── Wall-clock (export) timestamps ────────────────────────────────────────────
# The companion mod writes ``exported_at`` as a UTC ISO-8601 string, e.g.
# ``2026-06-19T19:02:55.3657693Z`` (DateTime.UtcNow.ToString("o"), 7-digit
# fraction + trailing Z).  Displaying it raw made the time look ~8h stale for
# UTC+8 users, so we convert UTC → the viewer's local timezone here.
_ISO_RE = _re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})"
    r"(?:\.(\d+))?\s*(Z|[+-]\d{2}:?\d{2})?$"
)


def format_export_time(iso_str: str, *, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """Convert a mod ``exported_at`` UTC ISO-8601 string to local time.

    Robust to .NET's 7-digit fractional seconds and the trailing ``Z`` (which
    ``datetime.fromisoformat`` rejects before 3.11).  A bare timestamp with no
    offset is assumed to be UTC.  Returns ``""`` for empty/unparseable input,
    or the original string trimmed when it parses but has no recognizable
    shape, so the UI degrades gracefully rather than hiding the value.
    """
    s = (iso_str or "").strip()
    if not s:
        return ""
    m = _ISO_RE.match(s)
    if not m:
        return s[:16].replace("T", " ")  # best-effort fallback
    year, mon, day, hh, mm, ss = (int(m.group(i)) for i in range(1, 7))
    off = m.group(8)
    try:
        naive = _dt.datetime(year, mon, day, hh, mm, ss)
    except ValueError:
        return s[:16].replace("T", " ")
    if off in (None, "", "Z"):
        tz = _dt.timezone.utc
    else:
        off = off.replace(":", "")
        sign = 1 if off[0] == "+" else -1
        tz = _dt.timezone(sign * _dt.timedelta(hours=int(off[1:3]), minutes=int(off[3:5])))
    return naive.replace(tzinfo=tz).astimezone().strftime(fmt)

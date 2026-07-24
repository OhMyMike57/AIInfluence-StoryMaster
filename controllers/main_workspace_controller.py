from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable, List, Optional, Tuple

from i18n import tr
from ui.theme import tcol


def resolve_current_target(selected: List[str], manual_source: str) -> Tuple[str, bool]:
    """Return (source_display, changed) — picks manual source or first selected character."""
    if not selected:
        return "", False
    source = manual_source.strip()
    if source in selected:
        return source, False
    return selected[0], True


def build_quick_speaker_values(
    selected_paths: Iterable[Path],
    get_character_name: Callable[[Path], str],
) -> List[str]:
    """Build speaker dropdown values for plot insert: preset tags + selected character names."""
    values = ["[劇情記憶]", "[消息傳聞]", "[軍事情報]", "Player"]  # noqa: cjk (data tags written to save)
    seen = set(values)
    for path in selected_paths:
        name = get_character_name(path)
        if name and name not in seen:
            values.append(name)
            seen.add(name)
    return values


def normalize_plot_text(raw_text: str) -> str:
    """Collapse multi-line plot text into a single whitespace-normalised line."""
    return " ".join([seg.strip() for seg in raw_text.splitlines() if seg.strip()]).strip()


def build_selected_members_view(selected: List[str], manual_source: str) -> Tuple[str, List[str]]:
    """Return (source_display, numbered_lines) for the selected-members panel."""
    source, _ = resolve_current_target(selected, manual_source)
    lines = [f"{i}. {name}" for i, name in enumerate(selected, 1)]
    return source, lines


def resolve_character_name(data: dict, fallback_name: str) -> str:
    """Extract the display name from a character data dict, falling back to fallback_name."""
    for k in ("Name", "CharacterName", "NPCName", "DisplayName"):
        v = data.get(k) if isinstance(data, dict) else None
        if isinstance(v, str) and v.strip():
            return v.strip()
    return fallback_name


def build_selected_members_lines(selected: List[str], manual_source: str) -> Tuple[str, List[str], int]:
    source_index, source = selected_source_state(selected, manual_source)
    lines = [f"{i}. {name}" for i, name in enumerate(selected, 1)]
    return source, lines, source_index


def empty_selected_members_state() -> Tuple[str, str]:
    return tr("（尚未選擇角色）"), tr("（請先在左側勾選並點選角色）")


def selected_source_state(selected: List[str], manual_source: str) -> Tuple[int, str]:
    source, _ = resolve_current_target(selected, manual_source)
    source_index = selected.index(source) if source in selected else -1
    return source_index, source


def selected_row_style(row_index: int, source_index: int) -> Tuple[str, str]:
    if row_index == source_index:
        return tcol("#0b5ed7"), tcol("#e7f1ff")
    return "black", "white"


def should_switch_source(current_source: str, picked_source: Optional[str]) -> bool:
    if not picked_source:
        return False
    return current_source.strip() != picked_source


def current_target_from_source_index(mapping: List[str], source_index: int) -> str:
    if source_index < 0 or source_index >= len(mapping):
        return ""
    return mapping[source_index]

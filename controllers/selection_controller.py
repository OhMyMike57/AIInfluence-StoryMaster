from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Any


def selected_display_from_list(selection: Sequence[int], mapping: Sequence[str]) -> Optional[str]:
    """Return the display string at the first selected listbox index, or None."""
    if not selection:
        return None
    idx = selection[0]
    if idx < 0 or idx >= len(mapping):
        return None
    return mapping[idx]


def source_path_from_characters(characters: Sequence[Tuple[str, Path]], manual_source: str) -> Optional[Path]:
    """Return the Path for the manually selected source character, or None."""
    src = manual_source.strip()
    if not src:
        return None
    for display, path in characters:
        if display == src:
            return path
    return None




def checked_displays_from_scene(scene_checked: Dict[str, Any]) -> List[str]:
    """Return display names for all checked characters in scene_checked."""
    return [display for display, var in scene_checked.items() if var is not None and bool(var.get())]

def checked_paths_from_scene(
    characters: Sequence[Tuple[str, Path]],
    scene_checked: Dict[str, Any],
) -> List[Path]:
    """Return file Paths for all checked characters."""
    out: List[Path] = []
    for display, path in characters:
        v = scene_checked.get(display)
        if v is not None and bool(v.get()):
            out.append(path)
    return out


def scene_targets_without_source(
    characters: Sequence[Tuple[str, Path]],
    scene_checked: Dict[str, Any],
    path_to_plain: Dict[Path, str],
    source_plain: str,
) -> List[Path]:
    """Return checked paths excluding the source character's path."""
    selected = checked_paths_from_scene(characters, scene_checked)
    return [p for p in selected if path_to_plain.get(p, "") != source_plain]


def checked_count_from_scene(scene_checked: Dict[str, Any]) -> int:
    return len(checked_displays_from_scene(scene_checked))


def resolve_source_after_checked_change(
    changed_display: Optional[str],
    scene_checked: Dict[str, Any],
) -> Optional[str]:
    if not changed_display:
        return None
    var = scene_checked.get(changed_display)
    if var is None or not bool(var.get()):
        return None
    return changed_display


def manual_source_after_list_click(
    selection: Sequence[int],
    mapping: Sequence[str],
) -> Optional[str]:
    return selected_display_from_list(selection, mapping)


def source_from_listbox_click(
    event_y: int,
    nearest_index: Optional[int],
    item_bbox: Optional[Tuple[int, int, int, int]],
    mapping: Sequence[str],
) -> Optional[str]:
    if nearest_index is None or item_bbox is None:
        return None
    _, y0, _, height = item_bbox
    if event_y < y0 or event_y > (y0 + height):
        return None
    return selected_display_from_list([nearest_index], mapping)


def resolve_source_from_selected_list_click(
    event_y: Optional[int],
    nearest_index: Optional[int],
    item_bbox: Optional[Tuple[int, int, int, int]],
    selection: Sequence[int],
    mapping: Sequence[str],
) -> Optional[str]:
    if event_y is not None:
        picked = source_from_listbox_click(event_y, nearest_index, item_bbox, mapping)
        if picked is not None:
            return picked
    return manual_source_after_list_click(selection, mapping)

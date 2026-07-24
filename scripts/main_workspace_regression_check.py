from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from controllers.main_workspace_controller import (
    resolve_current_target,
    build_quick_speaker_values,
    normalize_plot_text,
    build_selected_members_view,
    build_selected_members_lines,
    resolve_character_name,
    empty_selected_members_state,
    selected_source_state,
    selected_row_style,
    should_switch_source,
    current_target_from_source_index,
)
from controllers.selection_controller import (
    selected_display_from_list,
    source_path_from_characters,
    checked_paths_from_scene,
    checked_displays_from_scene,
    checked_count_from_scene,
    resolve_source_after_checked_change,
    manual_source_after_list_click,
    source_from_listbox_click,
    resolve_source_from_selected_list_click,
    scene_targets_without_source,
)


def expect(cond: bool, msg: str):
    if not cond:
        raise AssertionError(msg)


def main():
    src, changed = resolve_current_target(["A", "B"], "B")
    expect(src == "B" and changed is False, "existing source should be kept")

    src, changed = resolve_current_target(["A", "B"], "C")
    expect(src == "A" and changed is True, "fallback source should use first selected")

    src, changed = resolve_current_target([], "C")
    expect(src == "" and changed is False, "empty selected should return empty")

    source, lines = build_selected_members_view(["甲", "乙"], "乙")
    expect(source == "乙", "selected member view should keep valid source")
    expect(lines == ["1. 甲", "2. 乙"], "selected member numbered lines mismatch")

    source, lines, source_idx = build_selected_members_lines(["甲", "乙"], "乙")
    expect(source == "乙", "selected member lines should keep valid source")
    expect(lines == ["1. 甲", "2. 乙"], "selected member lines mismatch")
    expect(source_idx == 1, "source index should point to source member")

    idx, source = selected_source_state(["甲", "乙"], "乙")
    expect(idx == 1 and source == "乙", "selected source state should return index and source")

    fg, bg = selected_row_style(1, 1)
    expect((fg, bg) == ("#0b5ed7", "#e7f1ff"), "selected row style should highlight source row")

    fg, bg = selected_row_style(0, 1)
    expect((fg, bg) == ("black", "white"), "non-source row style should use default colors")

    expect(should_switch_source("甲", "乙") is True, "source should switch when target differs")
    expect(should_switch_source("甲", "甲") is False, "source should not switch when target is same")
    expect(should_switch_source("甲", None) is False, "source should not switch on empty target")

    target = current_target_from_source_index(["甲", "乙"], 1)
    expect(target == "乙", "current target should resolve from source index")

    target = current_target_from_source_index(["甲", "乙"], 0)
    expect(target == "甲", "current target helper should support first item index")

    target = current_target_from_source_index(["甲", "乙"], -1)
    expect(target == "", "current target should be empty for invalid source index")

    fake_names = {
        Path("a.json"): "艾莉",
        Path("b.json"): "波爾",
        Path("c.json"): "艾莉",
    }
    vals = build_quick_speaker_values(fake_names.keys(), lambda p: fake_names[p])
    expect(vals[:4] == ["[劇情記憶]", "[消息傳聞]", "[軍事情報]", "Player"], "base quick speaker values mismatch")
    expect(vals[4:] == ["艾莉", "波爾"], "name list should be unique and name-only")

    norm = normalize_plot_text("第一段\n\n第二段\n")
    expect(norm == "第一段 第二段", "plot text should be merged into one line")

    pick = selected_display_from_list([1], ["甲", "乙"])
    expect(pick == "乙", "selected_display_from_list should pick mapped item")
    pick = selected_display_from_list([], ["甲"])
    expect(pick is None, "empty selection should return None")

    click_source = manual_source_after_list_click([0], ["甲", "乙"])
    expect(click_source == "甲", "list click should resolve clicked source")

    click_source = manual_source_after_list_click([], ["甲", "乙"])
    expect(click_source is None, "empty list click should not resolve source")

    click_source = source_from_listbox_click(40, 1, (2, 10, 180, 20), ["甲", "乙"])
    expect(click_source is None, "blank area click should not resolve source")

    click_source = source_from_listbox_click(25, 1, (2, 10, 180, 20), ["甲", "乙"])
    expect(click_source == "乙", "item area click should resolve mapped source")

    click_source = resolve_source_from_selected_list_click(25, 1, (2, 10, 180, 20), [], ["甲", "乙"])
    expect(click_source == "乙", "resolver should prefer valid event click")

    click_source = resolve_source_from_selected_list_click(40, 1, (2, 10, 180, 20), [0], ["甲", "乙"])
    expect(click_source == "甲", "resolver should fallback to selection when click is blank area")

    chars = [("甲", Path("a.json")), ("乙", Path("b.json"))]
    src_path = source_path_from_characters(chars, "乙")
    expect(src_path == Path("b.json"), "source path should match selected display")

    class _V:
        def __init__(self, v): self._v = v
        def get(self): return self._v

    checked = checked_paths_from_scene(chars, {"甲": _V(True), "乙": _V(False)})
    expect(checked == [Path("a.json")], "checked paths should include only checked members")

    checked_displays = checked_displays_from_scene({"甲": _V(True), "乙": _V(False)})
    expect(checked_displays == ["甲"], "checked displays should include only checked display names")

    count = checked_count_from_scene({"甲": _V(True), "乙": _V(False)})
    expect(count == 1, "checked count should match checked display total")

    source = resolve_source_after_checked_change("甲", {"甲": _V(True), "乙": _V(False)})
    expect(source == "甲", "checked change should promote checked display as source")

    source = resolve_source_after_checked_change("乙", {"甲": _V(True), "乙": _V(False)})
    expect(source is None, "unchecked display should not become source")

    filtered = scene_targets_without_source(
        chars,
        {"甲": _V(True), "乙": _V(True)},
        {Path("a.json"): "甲", Path("b.json"): "乙"},
        "乙",
    )
    expect(filtered == [Path("a.json")], "scene targets should exclude source display")

    name = resolve_character_name({"DisplayName": "  測試角色  "}, "Fallback")
    expect(name == "測試角色", "resolve_character_name should trim display name")

    name = resolve_character_name({}, "Fallback")
    expect(name == "Fallback", "resolve_character_name should fallback when no fields exist")

    # (build_status_text retired in v0.36 — its spot hosts the global staging bar.)

    empty_line, target_hint = empty_selected_members_state()
    expect(empty_line == "（尚未選擇角色）", "empty selected line should match UI placeholder")
    expect(target_hint == "（請先在左側勾選並點選角色）", "empty target hint should match UI placeholder")

    print("[PASS] main workspace regression check passed")


if __name__ == "__main__":
    main()

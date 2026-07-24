from __future__ import annotations

from i18n import tr

from typing import List, Tuple


def world_files_changed(world_info_items: List[dict], world_info_original: List[dict], world_secret_items: List[dict], world_secret_original: List[dict]) -> Tuple[bool, bool]:
    """Return (info_changed, secret_changed) by comparing current vs original item lists."""
    return world_info_items != world_info_original, world_secret_items != world_secret_original


def world_save_log_message(info_changed: bool, secret_changed: bool, owner_changed: bool) -> str:
    """Build a human-readable save result message based on which data changed."""
    world_changed = info_changed or secret_changed
    if world_changed and owner_changed:
        return tr("訊息與秘密與擁有者變更已儲存")
    if world_changed:
        return tr("僅訊息與秘密條目變更已儲存")
    if owner_changed:
        return tr("僅擁有者變更已儲存（world 檔未重寫）")
    return tr("目前沒有可寫入變更")

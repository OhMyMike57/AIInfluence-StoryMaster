from __future__ import annotations

from i18n import tr

from typing import List, Optional, Tuple


def resolve_owner_context(
    focus_kind: str,
    selected_info_index: Optional[int],
    selected_secret_index: Optional[int],
    world_info_items: List[dict],
    world_secrets_items: List[dict],
) -> Optional[Tuple[str, str, str, str]]:
    """Return (kind, item_id, field_name, label) for the currently focused world item, or None."""
    if focus_kind == "secret":
        if selected_secret_index is None or selected_secret_index >= len(world_secrets_items):
            return None
        item_id = str(world_secrets_items[selected_secret_index].get("id", "")).strip()
        return ("secret", item_id, "KnownSecrets", tr("秘密"))

    if selected_info_index is None or selected_info_index >= len(world_info_items):
        return None
    item_id = str(world_info_items[selected_info_index].get("id", "")).strip()
    return ("info", item_id, "KnownInfo", tr("公開訊息"))

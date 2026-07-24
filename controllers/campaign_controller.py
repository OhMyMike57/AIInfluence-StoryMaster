from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from services.path_service import is_campaign_folder_name, looks_like_campaign_dir


def list_campaigns(save_data_dir: Optional[Path]) -> List[str]:
    """Return sorted list of campaign subdirectory names from save_data_dir.

    Two filters, matching what the core module does when it picks a campaign:

    1. Known helper folders (``storytools/``, ``_portrait_tmp/``) are skipped by
       name — see :func:`services.path_service.is_campaign_folder_name`.
    2. What is left must *look* like campaign data (the diplomacy bundle or a
       ``prompts/`` tree).  Name filtering alone let anything through: a folder
       of hand-copied character files, or a backup someone dropped beside the
       real campaign, appeared in the campaign picker as if it were playable.

    Falls back to the name-filtered list when the content check would leave
    nothing, so a campaign the mod has not finished writing yet never becomes
    invisible — the same fallback the module uses.
    """
    if not save_data_dir or not save_data_dir.is_dir():
        return []
    named = [
        c for c in save_data_dir.iterdir()
        if c.is_dir() and is_campaign_folder_name(c.name)
    ]
    real = [c.name for c in named if looks_like_campaign_dir(c)]
    camps = real if real else [c.name for c in named]
    camps.sort()
    return camps


def choose_target_campaign(camps: List[str], preferred_campaign: str, current_campaign: str) -> str:
    """Select the best campaign: preferred > current > first available."""
    if not camps:
        return ""
    if preferred_campaign and preferred_campaign in camps:
        return preferred_campaign
    if current_campaign and current_campaign in camps:
        return current_campaign
    return camps[0]

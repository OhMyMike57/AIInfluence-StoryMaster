"""JSON validation for character files and world data files."""
from __future__ import annotations

from i18n import tr

import json
from pathlib import Path
from typing import Callable, List, Tuple


def validate_character_files(
    paths: List[Path],
    name_resolver: Callable[[Path], str],
) -> Tuple[int, List[str]]:
    """Validate character JSON files. Returns (total_count, failure_names)."""
    failures = []
    for p in paths:
        try:
            text = p.read_text(encoding="utf-8")
            data = json.loads(text)
            if not isinstance(data, dict):
                failures.append(name_resolver(p))
        except Exception:
            failures.append(name_resolver(p))
    return len(paths), failures


def validate_world_files(
    info_path: Path, secret_path: Path
) -> List[str]:
    """Validate world_info.json and world_secrets.json. Returns list of failure descriptions."""
    failures = []
    for pth, label in ((info_path, "world_info.json"), (secret_path, "world_secrets.json")):
        try:
            parsed = json.loads(pth.read_text(encoding="utf-8"))
            if not isinstance(parsed, list):
                failures.append(tr("{label}（根節點需為陣列）").format(label=label))
        except Exception as e:
            failures.append(tr("{label}（{err}）").format(label=label, err=e))
    return failures


# ── Content-level validity: per-entry schema + cross-reference orphans ────────

REQUIRED_INFO_FIELDS    = ("id", "description")
REQUIRED_SECRET_FIELDS  = ("id", "description")


def validate_world_items_content(
    info_items: List[dict],
    secret_items: List[dict],
) -> Tuple[List[str], List[str], List[str]]:
    """Scan world_info / world_secrets entries for structural issues.

    Returns (info_issues, secret_issues, duplicate_id_issues).
    Each issue is a human-readable line.
    """
    def _scan(items: List[dict], required: tuple, label: str) -> Tuple[List[str], List[str]]:
        problems: List[str] = []
        seen: dict = {}
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                problems.append(tr("  • {label} 第 {n} 筆：不是物件（type={t}）").format(
                    label=label, n=idx + 1, t=type(item).__name__))
                continue
            iid = str(item.get("id", "")).strip()
            if not iid:
                problems.append(tr("  • {label} 第 {n} 筆：缺少 id").format(label=label, n=idx + 1))
            else:
                seen[iid] = seen.get(iid, 0) + 1
            missing = [f for f in required if not item.get(f)]
            if missing:
                disp = (item.get("description") or iid or "?")[:30]
                problems.append(tr("  • {label}「{disp}」({iid}…)：缺少欄位 {fields}").format(
                    label=label, disp=disp, iid=iid[:8], fields=', '.join(missing)))
        dups = [(k, v) for k, v in seen.items() if v > 1]
        dup_lines = [
            tr("  • {label} 重複 id：{k} 出現 {v} 次").format(label=label, k=k, v=v)
            for k, v in dups
        ]
        return problems, dup_lines

    info_probs, info_dups = _scan(info_items, REQUIRED_INFO_FIELDS, tr("訊息"))
    sec_probs,  sec_dups  = _scan(secret_items, REQUIRED_SECRET_FIELDS, tr("秘密"))
    return info_probs, sec_probs, info_dups + sec_dups


def find_orphan_world_refs(
    char_iter,
    valid_info_ids: set,
    valid_secret_ids: set,
) -> Tuple[List[Tuple[str, List[str]]], List[Tuple[str, List[str]]]]:
    """Find character JSONs that reference info/secret IDs that no longer exist.

    ``char_iter`` yields (display_name, char_data_dict) pairs.
    Returns (info_orphans, secret_orphans) where each entry is
    (display_name, list_of_orphan_ids).
    """
    info_orphans: List[Tuple[str, List[str]]] = []
    sec_orphans:  List[Tuple[str, List[str]]] = []
    for display, data in char_iter:
        if not isinstance(data, dict):
            continue
        known_info = data.get("KnownInfo", []) or []
        known_sec  = data.get("KnownSecrets", []) or []
        bad_info = [str(x) for x in known_info if str(x) and str(x) not in valid_info_ids]
        bad_sec  = [str(x) for x in known_sec  if str(x) and str(x) not in valid_secret_ids]
        if bad_info:
            info_orphans.append((display, bad_info))
        if bad_sec:
            sec_orphans.append((display, bad_sec))
    return info_orphans, sec_orphans

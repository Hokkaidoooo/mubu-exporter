"""Publish a complete backup only after all documents have been validated."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .errors import ExportError
from .schema import validate_payload, validate_tree
from .storage import atomic_write_json


def sync_cache(api, cache_root: Path, *, include_daily: bool = True) -> dict:
    cache_root = cache_root.absolute()
    if cache_root.exists() or cache_root.is_symlink():
        raise ExportError("backup destination already exists; select a new directory")
    cache_root.parent.mkdir(parents=True, exist_ok=True)
    tree = api.full_tree()
    validate_tree(tree)
    documents = {item["id"]: item for item in tree["documents"]}
    if include_daily:
        daily = api.daily_notes()
        if not isinstance(daily, dict) or not isinstance(daily.get("docs"), list):
            raise ExportError("daily-notes response schema changed")
        for item in daily["docs"]:
            validate_tree({"folders": [], "documents": [item]})
            existing = documents.get(item["id"])
            if existing is not None and any(
                key in existing and key in item and existing[key] != item[key]
                for key in ("name", "folderId", "updateTime")
            ):
                raise ExportError("daily-notes metadata disagrees with the listing")
            if existing is None:
                documents[item["id"]] = item
    tree = {"folders": tree["folders"], "documents": list(documents.values())}
    validate_tree(tree)
    with tempfile.TemporaryDirectory(prefix=".mubu-backup-", dir=cache_root.parent) as temporary:
        stage = Path(temporary) / "snapshot"
        (stage / "docs").mkdir(parents=True)
        for meta in tree["documents"]:
            payload = {"meta": meta, "data": api.document(meta["id"])}
            validate_payload(payload, meta["id"])
            atomic_write_json(stage / "docs" / f"{meta['id']}.json", payload)
        atomic_write_json(stage / "tree.json", tree)
        summary = {"schema_version": 1, "document_count": len(documents),
                   "daily_notes_included": include_daily}
        atomic_write_json(stage / "manifest.json", summary)
        if cache_root.exists() or cache_root.is_symlink():
            raise ExportError("backup destination appeared during download")
        os.rename(stage, cache_root)
    return summary

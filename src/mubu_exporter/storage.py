"""Atomic local files and an authoritative cache reader."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .errors import ExportError
from .schema import validate_payload, validate_tree


def atomic_write_json(path: Path, value: object) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent,
            prefix=".mubu-", suffix=".part", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def read_json(path: Path) -> object:
    if path.is_symlink():
        raise ExportError("cache files must not be symbolic links")
    try:
        with path.open(encoding="utf-8-sig") as handle:
            return json.load(handle)
    except json.JSONDecodeError:
        raise ExportError("cache contains invalid JSON") from None


def load_cache(root: Path) -> tuple[dict, dict[str, dict]]:
    root = root.resolve(strict=True)
    tree = read_json(root / "tree.json")
    listed = validate_tree(tree)
    docs_root = root / "docs"
    if docs_root.is_symlink():
        raise ExportError("cache docs directory must not be a symbolic link")
    documents = {}
    for meta in listed:
        doc_id = meta["id"]
        payload = read_json(docs_root / f"{doc_id}.json")
        validate_payload(payload, doc_id)
        for key in ("name", "updateTime", "folderId"):
            if key in meta and payload["meta"].get(key) != meta[key]:
                raise ExportError("cache document metadata is stale; create a fresh backup")
        documents[doc_id] = payload
    return tree, documents

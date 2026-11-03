"""Deterministic paths without case-insensitive or generated-name collisions."""
from __future__ import annotations

import re
import unicodedata
from pathlib import PurePosixPath

from .errors import ExportError

MAX_COMPONENT = 80
MAX_FOLDER_DEPTH = 32
ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED = {"CON", "PRN", "AUX", "NUL", "CLOCK$"} | {
    f"{prefix}{n}" for prefix in ("COM", "LPT") for n in range(1, 10)
}
OUTPUT_RESERVED = {"index.md", "manifest.json", "images"}


def key(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def safe_name(name: str, fallback: str = "未命名") -> str:
    name = unicodedata.normalize("NFC", name)
    name = re.sub(r"\s+", " ", ILLEGAL.sub("_", name)).strip(" .")
    name = name[:MAX_COMPONENT].rstrip(" .") or fallback
    if name.split(".", 1)[0].upper() in RESERVED:
        name = "_" + name
    return name


def _unique(base: str, used: set[str], suffix: str = "") -> str:
    number = 1
    while True:
        tag = "" if number == 1 else f" ({number})"
        candidate = base[:MAX_COMPONENT - len(tag)].rstrip(" .") + tag + suffix
        if key(candidate) not in used:
            used.add(key(candidate))
            return candidate
        number += 1


def plan_paths(tree: dict, docs: dict[str, dict]) -> tuple[dict[str, str], dict[str, str]]:
    folders = {item["id"]: item for item in tree["folders"]}
    parents: dict[str, str] = {}
    labels: dict[str, str] = {}
    for payload in docs.values():
        parent = ""
        for part in payload["data"].get("directory", []):
            fid = part["id"]
            label = safe_name(part.get("name", ""), "未命名文件夹")
            if fid in parents and (parents[fid] != parent or labels[fid] != label):
                raise ExportError("folder directory chains disagree")
            parents[fid], labels[fid] = parent, label
            parent = fid
    for fid, folder in folders.items():
        if fid not in parents:
            parent = str(folder.get("folderId") or "0")
            parents[fid] = "" if parent == "0" else parent
            labels[fid] = safe_name(folder.get("name", ""), "未命名文件夹")
    for fid in parents:
        seen = set()
        current = fid
        while current:
            if current in seen:
                raise ExportError("folder hierarchy contains a cycle")
            if current not in parents:
                raise ExportError("folder hierarchy refers to a missing parent")
            seen.add(current)
            if len(seen) > MAX_FOLDER_DEPTH:
                raise ExportError("folder hierarchy exceeds 32 levels")
            current = parents[current]
    children: dict[str, list[str]] = {}
    for fid, parent in parents.items():
        children.setdefault(parent, []).append(fid)
    paths = {}
    occupied = {"": {key(name) for name in OUTPUT_RESERVED}}

    def assign(parent: str, base: str) -> None:
        used = occupied.setdefault(base, set())
        for fid in sorted(children.get(parent, [])):
            name = _unique(labels[fid], used)
            path = str(PurePosixPath(base) / name)
            paths[fid] = path
            assign(fid, path)

    assign("", "")
    document_paths = {}
    for doc_id in sorted(docs):
        payload = docs[doc_id]
        chain = payload["data"].get("directory", [])
        fid = chain[-1]["id"] if chain else str(payload["meta"].get("folderId") or "0")
        if fid not in ("0", "") and fid not in paths:
            raise ExportError("document refers to an unknown folder")
        folder = paths.get(fid, "")
        stem = safe_name(payload["meta"].get("name", ""), "未命名笔记")
        name = _unique(stem, occupied.setdefault(folder, set()), ".md")
        document_paths[doc_id] = str(PurePosixPath(folder) / name)
    return paths, document_paths

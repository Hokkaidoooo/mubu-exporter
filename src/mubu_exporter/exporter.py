"""Render a validated snapshot and atomically publish a new export directory."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import tempfile
from pathlib import Path, PurePosixPath

from .errors import ExportError
from .images import download_images, plan_images
from .paths import plan_paths
from .renderer import RenderOptions, escape_md, relative_link, render_nodes
from .schema import validate_payload
from .storage import atomic_write_json, atomic_write_text, load_cache


def _timestamp(value: object) -> str:
    if value is None:
        return ""
    if type(value) not in (int, float):
        raise ExportError("document timestamp must be milliseconds since the epoch")
    try:
        return dt.datetime.fromtimestamp(value / 1000, tz=dt.timezone.utc).isoformat()
    except (ValueError, OSError, OverflowError):
        raise ExportError("document timestamp is outside the supported range") from None


def _node_count(nodes: list[dict]) -> int:
    total, pending = 0, list(nodes)
    while pending:
        node = pending.pop()
        total += 1
        pending.extend(node.get("children", []))
    return total


def _front_matter(meta: dict, count: int, source_metadata: bool) -> str:
    fields = {"title": meta.get("name", "") or "未命名笔记", "nodes": count}
    for key, field_name in (("createTime", "created"), ("updateTime", "updated")):
        if meta.get(key) is not None:
            fields[field_name] = _timestamp(meta[key])
    if source_metadata:
        fields["mubu_id"] = meta["id"]
        fields["source"] = f"https://mubu.com/doc/{meta['id']}"
    # JSON strings are also YAML strings; escaping is delegated to one serializer.
    lines = [f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in fields.items()]
    return "---\n" + "\n".join(lines) + "\n---\n\n"


def export_cache(cache: Path, out: Path, *, image_mode: str = "remote",
                 style: str = "adaptive", keep_color: bool = True,
                 preserve_unsafe: bool = False, allow_private_images: bool = False,
                 source_metadata: bool = False) -> dict:
    if style not in {"adaptive", "bullets"}:
        raise ExportError("unsupported outline style")
    if image_mode not in {"remote", "local", "skip"}:
        raise ExportError("unsupported image mode")
    out = out.absolute()
    if out.exists() or out.is_symlink():
        raise ExportError("export destination already exists; select a new directory")
    tree, docs = load_cache(cache)
    folder_paths, doc_paths = plan_paths(tree, docs)
    nodes = {doc_id: validate_payload(payload, doc_id) for doc_id, payload in docs.items()}
    image_names = plan_images(nodes) if image_mode == "local" else {}
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".mubu-export-", dir=out.parent) as temporary:
        stage = Path(temporary) / "export"
        stage.mkdir()
        for folder in folder_paths.values():
            (stage / folder).mkdir(parents=True, exist_ok=True)
        files, total_nodes = [], 0
        for doc_id, relative in sorted(doc_paths.items(), key=lambda item: item[1]):
            meta = docs[doc_id]["meta"]
            count = _node_count(nodes[doc_id])
            total_nodes += count
            parent = str(PurePosixPath(relative).parent)
            opts = RenderOptions(
                keep_color=keep_color, image_mode=image_mode, image_names=image_names,
                doc_paths=doc_paths, current_dir="" if parent == "." else parent,
                preserve_unsafe=preserve_unsafe,
            )
            title = escape_md(meta.get("name", "") or "未命名笔记").replace("\r", " ").replace("\n", " ")
            body = "\n".join(render_nodes(nodes[doc_id], opts, style))
            text = _front_matter(meta, count, source_metadata) + f"# {title}\n\n{body}\n"
            atomic_write_text(stage / relative, text)
            files.append({"path": relative, "sha256": hashlib.sha256(text.encode()).hexdigest()})
        if image_names:
            download_images(image_names, stage / "images", allow_private=allow_private_images)
        index = ["# 笔记目录", "", f"文档：{len(docs)} · 节点：{total_nodes}", ""]
        for relative in sorted(doc_paths.values()):
            label = escape_md(relative[:-3])
            index.append(f"- [{label}]({relative_link('', relative)})")
        atomic_write_text(stage / "index.md", "\n".join(index) + "\n")
        summary = {"schema_version": 1, "documents": len(docs), "folders": len(folder_paths),
                   "nodes": total_nodes, "images": len(image_names), "image_mode": image_mode,
                   "style": style, "files": files}
        atomic_write_json(stage / "manifest.json", summary)
        if out.exists() or out.is_symlink():
            raise ExportError("export destination appeared while rendering")
        os.rename(stage, out)
    return {key: value for key, value in summary.items() if key != "files"}

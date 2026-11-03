"""Validate the cache contract before reading or writing any document."""
from __future__ import annotations

import json
import re

from .errors import ExportError

ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
MAX_NODE_DEPTH = 64


def require_id(value: object, context: str = "id") -> str:
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise ExportError(f"{context}: expected 1..128 letters, digits, '_' or '-'")
    return value


def _records(value: object, context: str) -> list[dict]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ExportError(f"{context}: expected a list of objects")
    return value


def validate_tree(tree: object) -> list[dict]:
    if not isinstance(tree, dict):
        raise ExportError("tree: expected an object")
    for group in ("folders", "documents"):
        records = _records(tree.get(group), f"tree.{group}")
        seen = set()
        for item in records:
            item_id = require_id(item.get("id"), f"tree.{group}.id")
            if item_id in seen:
                raise ExportError(f"tree.{group}: duplicate id")
            seen.add(item_id)
            if not isinstance(item.get("name", ""), str):
                raise ExportError(f"tree.{group}.name: expected text")
    return tree["documents"]


def validate_payload(payload: object, expected_id: str | None = None) -> list[dict]:
    if not isinstance(payload, dict):
        raise ExportError("document: expected an object")
    meta, data = payload.get("meta"), payload.get("data")
    if not isinstance(meta, dict) or not isinstance(data, dict):
        raise ExportError("document: expected meta and data objects")
    doc_id = require_id(meta.get("id"), "document.meta.id")
    if expected_id is not None and doc_id != expected_id:
        raise ExportError("document id does not match the tree")
    if not isinstance(meta.get("name", ""), str):
        raise ExportError("document.meta.name: expected text")
    directory = _records(data.get("directory", []), "document.directory")
    for folder in directory:
        require_id(folder.get("id"), "document.directory.id")
        if not isinstance(folder.get("name", ""), str):
            raise ExportError("document.directory.name: expected text")
    definition = data.get("definition")
    if isinstance(definition, str):
        try:
            definition = json.loads(definition)
        except json.JSONDecodeError:
            raise ExportError("document.definition: invalid JSON") from None
    if not isinstance(definition, dict):
        raise ExportError("document.definition: expected a JSON object")
    nodes = _records(definition.get("nodes"), "document.definition.nodes")
    _validate_nodes(nodes)
    return nodes


def _validate_nodes(nodes: list[dict]) -> None:
    pending = [(nodes, 1)]
    seen = set()
    while pending:
        current, depth = pending.pop()
        if depth > MAX_NODE_DEPTH:
            raise ExportError(f"document exceeds {MAX_NODE_DEPTH} node levels")
        for node in current:
            for key in ("text", "note", "emoji", "color"):
                if key in node and not isinstance(node[key], str):
                    raise ExportError(f"node.{key}: expected text")
            if "id" in node:
                node_id = require_id(node["id"], "node.id")
                if node_id in seen:
                    raise ExportError("document contains duplicate node anchors")
                seen.add(node_id)
            if "taskStatus" in node and node["taskStatus"] not in (0, 1, 2, None):
                raise ExportError("node.taskStatus: unsupported checkbox state")
            for image in _records(node.get("images", []), "node.images"):
                if not isinstance(image.get("uri"), str) or not image["uri"]:
                    raise ExportError("node.images.uri: expected nonempty text")
            children = _records(node.get("children", []), "node.children")
            if children:
                pending.append((children, depth + 1))

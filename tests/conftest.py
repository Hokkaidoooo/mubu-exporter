import json

import pytest


@pytest.fixture
def cache(tmp_path):
    root = tmp_path / "cache"
    (root / "docs").mkdir(parents=True)
    meta = {"id": "sample_doc", "name": "示例文档", "folderId": "0", "updateTime": 1000}
    payload = {"meta": meta, "data": {"directory": [], "definition": json.dumps({
        "nodes": [{"id": "sample_node", "text": "<b>示例内容</b>", "children": []}]
    })}}
    (root / "tree.json").write_text(json.dumps({"folders": [], "documents": [meta]}), encoding="utf-8")
    (root / "docs" / "sample_doc.json").write_text(json.dumps(payload), encoding="utf-8")
    return root

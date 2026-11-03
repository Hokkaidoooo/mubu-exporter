import json

import pytest
import yaml

from mubu_exporter.errors import ExportError
from mubu_exporter.exporter import export_cache
from mubu_exporter.paths import plan_paths, safe_name
from mubu_exporter.storage import load_cache


def test_export_is_complete_and_preserves_cache(cache, tmp_path):
    original = (cache / "docs" / "sample_doc.json").read_bytes()
    output = tmp_path / "export"
    summary = export_cache(cache, output, image_mode="skip")
    assert summary["documents"] == 1 and summary["nodes"] == 1
    assert (output / "index.md").is_file()
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    note = output / manifest["files"][0]["path"]
    text = note.read_text(encoding="utf-8")
    assert "**示例内容**" in text and "mubu_id:" not in text
    assert (cache / "docs" / "sample_doc.json").read_bytes() == original


def test_old_cache_files_do_not_revive_deleted_notes(cache):
    (cache / "docs" / "deleted.json").write_text("INVALID OLD DATA", encoding="utf-8")
    _, docs = load_cache(cache)
    assert set(docs) == {"sample_doc"}


def test_incomplete_cache_does_not_publish(cache, tmp_path):
    (cache / "docs" / "sample_doc.json").unlink()
    out = tmp_path / "export"
    with pytest.raises(FileNotFoundError):
        export_cache(cache, out)
    assert not out.exists()


def test_existing_output_is_never_overwritten(cache, tmp_path):
    out = tmp_path / "export"
    out.mkdir()
    (out / "keep").write_text("original", encoding="utf-8")
    with pytest.raises(ExportError, match="already exists"):
        export_cache(cache, out)
    assert (out / "keep").read_text() == "original"


def test_render_failure_leaves_no_export_or_staging(cache, tmp_path):
    doc = cache / "docs" / "sample_doc.json"
    payload = json.loads(doc.read_text())
    payload["data"]["definition"] = {"nodes": [{"text": '<a href="javascript:alert(1)">X</a>'}]}
    doc.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ExportError):
        export_cache(cache, tmp_path / "export")
    assert {p.name for p in tmp_path.iterdir()} == {"cache"}


def test_yaml_title_is_escaped_by_serializer(cache, tmp_path):
    special = 'Quotes " and \\ paths: # example\nNew line'
    tree_path, doc_path = cache / "tree.json", cache / "docs" / "sample_doc.json"
    tree = json.loads(tree_path.read_text())
    doc = json.loads(doc_path.read_text())
    tree["documents"][0]["name"] = special
    doc["meta"]["name"] = special
    tree_path.write_text(json.dumps(tree), encoding="utf-8")
    doc_path.write_text(json.dumps(doc), encoding="utf-8")
    out = tmp_path / "export"
    export_cache(cache, out, source_metadata=True)
    manifest = json.loads((out / "manifest.json").read_text())
    text = (out / manifest["files"][0]["path"]).read_text(encoding="utf-8")
    front = yaml.safe_load(text.split("---", 2)[1])
    assert front["title"] == special and front["mubu_id"] == "sample_doc"


def test_stale_cache_is_not_reported_successful(cache):
    tree_file = cache / "tree.json"
    tree = json.loads(tree_file.read_text())
    tree["documents"][0]["updateTime"] = 2000
    tree_file.write_text(json.dumps(tree), encoding="utf-8")
    with pytest.raises(ExportError, match="stale"):
        load_cache(cache)


@pytest.mark.parametrize(("name", "expected"), [
    ("CON", "_CON"), ("con.txt", "_con.txt"), ("NUL.", "_NUL"),
    ("a/b:c", "a_b_c"), (" . ", "未命名"), ("A\nB", "A_B"),
])
def test_portable_names(name, expected):
    assert safe_name(name) == expected


def test_folders_files_generated_suffixes_and_index_never_collide():
    tree = {"folders": [
        {"id": "f1", "name": "Lab"}, {"id": "f2", "name": "lab"},
        {"id": "f3", "name": "Lab (2)"}, {"id": "f4", "name": "index.md"},
    ], "documents": []}
    docs = {doc_id: {"meta": {"id": doc_id, "name": name}, "data": {}}
            for doc_id, name in (("a", "index"), ("b", "INDEX"), ("c", "Lab"))}
    folders, paths = plan_paths(tree, docs)
    all_paths = [*folders.values(), *paths.values(), "index.md", "manifest.json", "images"]
    assert len({p.casefold() for p in all_paths}) == len(all_paths)


@pytest.mark.parametrize("folders", [
    [{"id": "a", "name": "A", "folderId": "a"}],
    [{"id": "a", "name": "A", "folderId": "b"}, {"id": "b", "name": "B", "folderId": "a"}],
    [{"id": "a", "name": "A", "folderId": "missing"}],
])
def test_invalid_hierarchy_fails(folders):
    with pytest.raises(ExportError):
        plan_paths({"folders": folders, "documents": []}, {})

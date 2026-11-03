import pytest

from mubu_exporter.errors import ExportError
from mubu_exporter.storage import load_cache
from mubu_exporter.sync import sync_cache


class API:
    def full_tree(self):
        return {"folders": [], "documents": [{"id": "doc", "name": "Example"}]}

    def daily_notes(self):
        return {"docs": [{"id": "daily", "name": "Daily example"}]}

    def document(self, doc_id):
        return {"definition": {"nodes": [{"text": f"Content {doc_id}"}]}}


def test_complete_backup_includes_daily_and_can_be_loaded(tmp_path):
    out = tmp_path / "backup"
    assert sync_cache(API(), out)["document_count"] == 2
    _, documents = load_cache(out)
    assert set(documents) == {"doc", "daily"}


def test_daily_failure_is_visible_and_no_backup_is_published(tmp_path):
    class BadDaily(API):
        def daily_notes(self):
            raise ExportError("daily API failed")

    with pytest.raises(ExportError, match="daily API failed"):
        sync_cache(BadDaily(), tmp_path / "backup")
    assert list(tmp_path.iterdir()) == []


def test_daily_can_be_explicitly_excluded(tmp_path):
    class NoDaily(API):
        def daily_notes(self):
            raise AssertionError("must not call")

    result = sync_cache(NoDaily(), tmp_path / "backup", include_daily=False)
    assert result["document_count"] == 1 and result["daily_notes_included"] is False


def test_failed_document_does_not_publish_partial_backup(tmp_path):
    class BadDoc(API):
        def document(self, doc_id):
            if doc_id == "daily":
                raise ExportError("document failed")
            return super().document(doc_id)

    with pytest.raises(ExportError):
        sync_cache(BadDoc(), tmp_path / "backup")
    assert list(tmp_path.iterdir()) == []


def test_existing_cache_is_protected(cache):
    before = (cache / "tree.json").read_bytes()
    with pytest.raises(ExportError, match="already exists"):
        sync_cache(API(), cache)
    assert (cache / "tree.json").read_bytes() == before


def test_conflicting_daily_metadata_fails(tmp_path):
    class Conflict(API):
        def daily_notes(self):
            return {"docs": [{"id": "doc", "name": "Changed"}]}

    with pytest.raises(ExportError, match="disagrees"):
        sync_cache(Conflict(), tmp_path / "backup")

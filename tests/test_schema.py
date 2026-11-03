import pytest

from mubu_exporter.errors import ExportError
from mubu_exporter.schema import validate_payload, validate_tree


@pytest.mark.parametrize("bad_id", ["../secret", "a/b", "a\\b", "C:secret", "", None])
def test_tree_rejects_path_traversal_and_invalid_ids(bad_id):
    with pytest.raises(ExportError):
        validate_tree({"folders": [], "documents": [{"id": bad_id}]})


@pytest.mark.parametrize("definition", [None, "", "INVALID", [], {}, {"nodes": "lost"},
                                         {"nodes": [{"text": 12}]}, {"nodes": [{"children": {}}]}])
def test_bad_definition_is_not_an_empty_document(definition):
    with pytest.raises(ExportError):
        validate_payload({"meta": {"id": "example"}, "data": {"definition": definition}})


def test_valid_empty_document_is_supported():
    assert validate_payload({"meta": {"id": "empty"}, "data": {"definition": {"nodes": []}}}) == []


def test_excessive_depth_fails_without_recursion_error():
    node = {"text": "leaf"}
    for _ in range(65):
        node = {"children": [node]}
    with pytest.raises(ExportError, match="64"):
        validate_payload({"meta": {"id": "deep"}, "data": {"definition": {"nodes": [node]}}})

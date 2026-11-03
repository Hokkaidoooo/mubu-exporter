import json

import pytest
import requests

from mubu_exporter.api import MubuClient
from mubu_exporter.errors import ExportError


def response(status=200, data=None, *, raw=None):
    result = requests.Response()
    result.status_code = status
    result._content = raw if raw is not None else json.dumps({"code": 0, "data": data or {}}).encode()
    result._content_consumed = True
    return result


class Session:
    def __init__(self, *results):
        self.results = iter(results)
        self.calls = []

    def post(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        return result


def test_retry_only_transient_failures_and_never_redirect():
    delays = []
    session = Session(response(503), requests.Timeout(), response(data={"ok": True}))
    api = MubuClient("synthetic-token", session=session, sleep=delays.append)
    assert api.post("/test") == {"ok": True}
    assert delays == [1, 2]
    assert all(call[1]["allow_redirects"] is False for call in session.calls)


@pytest.mark.parametrize("status", [301, 302, 400, 401, 403, 404])
def test_nontransient_status_is_not_retried(status):
    session = Session(response(status))
    with pytest.raises(ExportError, match=f"HTTP {status}"):
        MubuClient("synthetic-token", session=session).post("/test")
    assert len(session.calls) == 1


def test_final_attempt_has_no_extra_sleep_or_secret_in_error():
    delays = []
    session = Session(requests.Timeout("synthetic-secret"), requests.Timeout("synthetic-secret"))
    with pytest.raises(ExportError) as caught:
        MubuClient("synthetic-secret", session=session, retries=2, sleep=delays.append).post("/test")
    assert "synthetic-secret" not in str(caught.value)
    assert delays == [1]


@pytest.mark.parametrize("raw", [b"<html>login</html>", b'{"code":16,"msg":"private response"}',
                                   b'{"code":0,"data":[]}'])
def test_bad_response_is_never_assumed_successful(raw):
    with pytest.raises(ExportError) as caught:
        MubuClient("synthetic-token", session=Session(response(raw=raw))).post("/test")
    assert "private response" not in str(caught.value)


def test_pagination_follows_total_even_with_short_pages():
    session = Session(
        response(data={"documents": [{"id": "a"}], "folders": [], "total": 2}),
        response(data={"documents": [{"id": "b"}], "folders": [], "total": 2}),
    )
    result = MubuClient("synthetic-token", session=session).full_tree()
    assert [item["id"] for item in result["documents"]] == ["a", "b"]
    assert [call[1]["json"]["page"] for call in session.calls] == [1, 2]


def test_repeated_page_fails_instead_of_looping():
    page = {"documents": [{"id": "a"}], "folders": [], "hasMore": True}
    with pytest.raises(ExportError, match="repeats"):
        MubuClient("synthetic-token", session=Session(response(data=page), response(data=page))).full_tree()


def test_premature_empty_page_fails():
    with pytest.raises(ExportError, match="declared end"):
        MubuClient("synthetic-token", session=Session(response(data={
            "documents": [], "folders": [], "total": 10,
        }))).full_tree()


@pytest.mark.parametrize("token", ["", "\nsecret", "secret\r"])
def test_invalid_auth_is_rejected_before_network(token):
    with pytest.raises(ExportError):
        MubuClient(token)

"""Read-only Mubu HTTP API, with bounded and observable failure handling."""
from __future__ import annotations

import threading
import time
from typing import Callable

import requests

from .errors import ExportError

BASE_URL = "https://api2.mubu.com"
RETRY_STATUSES = {429, 500, 502, 503, 504}
PAGE_SIZE = 500
MAX_PAGES = 1000


class MubuClient:
    def __init__(self, token: str, unique_id: str = "", *, session=None,
                 retries: int = 3, timeout: float = 30,
                 sleep: Callable[[float], None] = time.sleep):
        if not isinstance(token, str) or not token.strip():
            raise ExportError("MUBU_TOKEN is required")
        if retries < 1 or timeout <= 0:
            raise ExportError("retries and timeout must be positive")
        if any(c in token + unique_id for c in "\r\n"):
            raise ExportError("authentication headers contain a line break")
        self._headers = {
            "Accept": "application/json", "Jwt-Token": token,
            "Origin": "https://mubu.com", "Referer": "https://mubu.com/",
            "platform": "web", "version": "3.0.0",
            "data-unique-id": unique_id,
        }
        self._injected = session
        self._local = threading.local()
        self._sessions = []
        self.retries, self.timeout, self.sleep = retries, timeout, sleep

    @property
    def session(self):
        if self._injected is not None:
            return self._injected
        if not hasattr(self._local, "session"):
            session = requests.Session()
            self._local.session = session
            self._sessions.append(session)
        return self._local.session

    def close(self) -> None:
        for session in self._sessions:
            session.close()
        self._sessions.clear()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def post(self, path: str, payload: dict | None = None) -> dict:
        for attempt in range(self.retries):
            response = None
            try:
                response = self.session.post(
                    BASE_URL + path, json=payload or {}, headers=self._headers,
                    timeout=self.timeout, allow_redirects=False,
                )
                status = response.status_code
                if status not in RETRY_STATUSES:
                    if status != 200:
                        raise ExportError(f"Mubu request failed: HTTP {status}")
                    try:
                        body = response.json()
                    except (ValueError, requests.exceptions.JSONDecodeError):
                        raise ExportError("Mubu response is not valid JSON") from None
                    if not isinstance(body, dict) or body.get("code") != 0:
                        raise ExportError("Mubu rejected the request; check login and API compatibility")
                    if not isinstance(body.get("data"), dict):
                        raise ExportError("Mubu response data must be an object")
                    return body["data"]
                reason = f"HTTP {status}"
            except (requests.ConnectionError, requests.Timeout):
                reason = "connection error or timeout"
            finally:
                if response is not None:
                    response.close()
            if attempt + 1 < self.retries:
                self.sleep(min(2 ** attempt, 8))
        raise ExportError(f"Mubu request failed after {self.retries} attempts: {reason}")

    def full_tree(self) -> dict:
        documents, folders = {}, {}
        for page in range(1, MAX_PAGES + 1):
            data = self.post("/v3/api/list/get_all_documents_page",
                             {"page": page, "pageSize": PAGE_SIZE})
            batch = data.get("documents")
            folder_batch = data.get("folders")
            if not isinstance(batch, list) or not isinstance(folder_batch, list):
                raise ExportError("Mubu listing schema changed")
            for folder in folder_batch:
                self._merge(folders, folder, "folder", allow_existing=True)
            for document in batch:
                self._merge(documents, document, "document", allow_existing=False)
            total = data.get("total")
            more = data.get("hasMore")
            if total is not None and (type(total) is not int or total < len(documents)):
                raise ExportError("Mubu listing has an inconsistent total")
            if more is not None and not isinstance(more, bool):
                raise ExportError("Mubu listing has an invalid hasMore flag")
            remaining = (total is not None and len(documents) < total)
            if not batch and (remaining or more is True):
                raise ExportError("Mubu listing stopped before the declared end")
            if more is False and remaining:
                raise ExportError("Mubu listing completion markers disagree")
            if not remaining and more is not True and (
                total is not None or more is False or len(batch) < PAGE_SIZE
            ):
                return {"folders": list(folders.values()), "documents": list(documents.values())}
        raise ExportError("Mubu listing exceeded the pagination limit")

    @staticmethod
    def _merge(target: dict, item: object, label: str, *, allow_existing: bool) -> None:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ExportError(f"Mubu listing contains an invalid {label}")
        item_id = item["id"]
        if item_id in target:
            if not allow_existing or target[item_id] != item:
                raise ExportError(f"Mubu listing repeats or changes a {label}")
        target[item_id] = item

    def daily_notes(self) -> dict:
        return self.post("/v3/api/document/dailyNotes?action=1")

    def document(self, doc_id: str) -> dict:
        return self.post("/v3/api/document/get", {"docId": doc_id})

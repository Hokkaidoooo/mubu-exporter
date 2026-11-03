"""Real socket tests with a synthetic server; no external account is needed."""
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from mubu_exporter.api import MubuClient
from mubu_exporter.errors import ExportError
from mubu_exporter.exporter import export_cache
from mubu_exporter.images import download_images
from mubu_exporter.sync import sync_cache

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a1ioAAAAASUVORK5CYII="
)


@pytest.fixture
def server():
    observed = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Synthetic HTTP access logs are irrelevant to test assertions.

        def send(self, body, status=200, content_type="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            observed.append(("POST", self.path, self.headers.get("Jwt-Token")))
            if self.path.endswith("get_all_documents_page"):
                data = {"documents": [{"id": "http_doc", "name": "HTTP example"}],
                        "folders": [], "total": 1}
            elif "dailyNotes" in self.path:
                data = {"docs": []}
            elif self.path.endswith("/get"):
                data = {"definition": {"nodes": [{
                    "text": "Downloaded image", "images": [{"uri": f"{base_url}/image.png"}]
                }]}}
            else:
                self.send(b"not found", 404, "text/plain")
                return
            self.send(json.dumps({"code": 0, "data": data}).encode())

        def do_GET(self):
            observed.append(("GET", self.path, self.headers.get("Jwt-Token")))
            if self.path == "/image.png":
                self.send(PNG, content_type="image/png")
            elif self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", f"{base_url}/image.png")
                self.send_header("Content-Length", "0")
                self.end_headers()
            else:
                self.send(b"not an image", content_type="text/html")

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    base_url = f"http://127.0.0.1:{httpd.server_port}"
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield base_url, observed
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def test_real_http_backup_and_local_image_export(server, tmp_path):
    base_url, observed = server

    class LocalSession(requests.Session):
        def post(self, url, **kwargs):
            assert url.startswith("https://api2.mubu.com/")
            return super().post(url.replace("https://api2.mubu.com", base_url, 1), **kwargs)

    with LocalSession() as session:
        session.trust_env = False
        with MubuClient("synthetic-http-token", session=session) as api:
            sync_cache(api, tmp_path / "backup")
    result = export_cache(tmp_path / "backup", tmp_path / "export", image_mode="local",
                          allow_private_images=True)
    assert result["images"] == 1 and result["documents"] == 1
    image = next((tmp_path / "export" / "images").iterdir())
    assert image.read_bytes() == PNG
    assert any(method == "POST" and token == "synthetic-http-token" for method, _, token in observed)
    assert [(path, token) for method, path, token in observed if method == "GET"] == [("/image.png", None)]


def test_private_network_requires_explicit_opt_in(server, tmp_path):
    base_url, observed = server
    with pytest.raises(ExportError, match="requires HTTPS"):
        download_images({f"{base_url}/image.png": "image.png"}, tmp_path / "images")
    assert observed == []


@pytest.mark.parametrize(("path", "message"), [("/redirect", "HTTP 302"), ("/html", "non-image")])
def test_redirect_and_html_are_real_failures(server, tmp_path, path, message):
    base_url, observed = server
    with pytest.raises(ExportError, match=message):
        download_images({f"{base_url}{path}": "image.png"}, tmp_path / "images", allow_private=True)
    assert not (tmp_path / "images" / "image.png").exists()
    assert [item[1] for item in observed] == [path]

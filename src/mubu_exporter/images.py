"""Download note images without forwarding account authentication."""
from __future__ import annotations

import hashlib
import ipaddress
import socket
import urllib.parse
from pathlib import Path

import requests

from .errors import ExportError
from .renderer import collect_image_uris, image_url

MAX_IMAGE_BYTES = 32 * 1024 * 1024
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".bmp", ".svg"}


def plan_images(nodes_by_document: dict[str, list[dict]]) -> dict[str, str]:
    uris = {uri for nodes in nodes_by_document.values() for uri in collect_image_uris(nodes)}
    result = {}
    for uri in sorted(uris):
        extension = Path(urllib.parse.urlsplit(image_url(uri)).path).suffix.lower()
        if extension not in IMAGE_EXTENSIONS:
            extension = ".img"
        result[uri] = hashlib.sha256(uri.encode()).hexdigest() + extension
    return result


def _validate_url(url: str, allow_private: bool) -> None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.username or parsed.password or not parsed.hostname:
        raise ExportError("image URL must not contain credentials")
    if parsed.scheme not in ({"http", "https"} if allow_private else {"https"}):
        raise ExportError("image download requires HTTPS; trusted local sources need --allow-private-images")
    if allow_private:
        return
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise ExportError("image hostname could not be resolved") from None
    if not addresses or any(not ipaddress.ip_address(record[4][0]).is_global for record in addresses):
        raise ExportError("private-network image blocked; use --allow-private-images only for trusted sources")


def download_images(names: dict[str, str], destination: Path, *,
                    allow_private: bool = False, session=None) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    own_session = session is None
    session = requests.Session() if own_session else session
    try:
        for uri, filename in names.items():
            url = image_url(uri)
            _validate_url(url, allow_private)
            target = destination / filename
            try:
                with session.get(url, timeout=30, stream=True, allow_redirects=False) as response:
                    if response.status_code != 200:
                        raise ExportError(f"image download failed: HTTP {response.status_code}")
                    content_type = response.headers.get("Content-Type", "").split(";", 1)[0]
                    if not content_type.lower().startswith("image/"):
                        raise ExportError("image response has a non-image Content-Type")
                    size = 0
                    with target.open("xb") as handle:
                        for chunk in response.iter_content(65536):
                            size += len(chunk)
                            if size > MAX_IMAGE_BYTES:
                                raise ExportError("image exceeds the 32 MiB download limit")
                            handle.write(chunk)
                    if size == 0:
                        raise ExportError("image response is empty")
            except (requests.RequestException, OSError):
                raise ExportError("image transfer failed; export has not been published") from None
    finally:
        if own_session:
            session.close()

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from steadylink import SteadyLink, SteadyLinkError, UploadFile


def test_sends_api_key_and_normalizes_upload_manifest():
    captured = {}

    def transport(method, url, headers, body):
        captured.update(method=method, url=url, headers=headers, body=json.loads(body))
        return 201, b'{"id":"batch"}'

    client = SteadyLink(api_key="slk_test", base_url="https://api.example", transport=transport)
    assert client.create_upload_batch("bucket", [UploadFile("hero.png", 12, "image/png")]) == {"id": "batch"}
    assert captured["headers"]["X-API-Key"] == "slk_test"
    assert captured["body"]["files"] == [{"filename": "hero.png", "size": 12, "contentType": "image/png", "path": ""}]


def test_presigned_upload_never_receives_api_credentials():
    captured = {}

    def binary_transport(url, body, content_type):
        captured.update(url=url, body=body, content_type=content_type)
        return 200, b""

    client = SteadyLink(api_key="secret", binary_transport=binary_transport)
    client.upload_to_url("https://storage.example/upload", b"bytes", "image/png")
    assert captured == {"url": "https://storage.example/upload", "body": b"bytes", "content_type": "image/png"}


def test_upload_file_completes_the_full_upload_flow():
    api_calls = []
    storage_calls = []

    def transport(method, url, headers, body):
        api_calls.append((method, url, headers, body))
        if url.endswith("/api/upload-batches"):
            return 201, b'{"id":"batch","files":[{"id":"session","uploadUrl":"https://storage.example/upload"}]}'
        return 202, b'{"status":"committing"}'

    def binary_transport(url, body, content_type):
        storage_calls.append((url, body, content_type))
        return 200, b""

    client = SteadyLink(api_key="secret", base_url="https://api.example", transport=transport, binary_transport=binary_transport)
    assert client.upload_file("bucket", "hero.png", b"abc", "image/png") == {"status": "committing"}
    assert storage_calls == [("https://storage.example/upload", b"abc", "application/octet-stream")]
    assert json.loads(api_calls[0][3])["files"] == [{"filename": "hero.png", "size": 3, "contentType": "image/png", "path": ""}]


def test_replace_file_sends_octet_stream_to_storage():
    api_calls = []
    storage_calls = []

    def transport(method, url, headers, body):
        api_calls.append((method, url))
        if "/objects/upload-temp" in url:
            return 200, b'{"uploadUrl":"https://storage.example/temp","tempKey":"tmp/1"}'
        return 200, b'{"ok":true}'

    def binary_transport(url, body, content_type):
        storage_calls.append((url, body, content_type))
        return 200, b""

    client = SteadyLink(api_key="secret", base_url="https://api.example", transport=transport, binary_transport=binary_transport)
    assert client.replace_file("bucket", "campaign/hero.webp", "hero.webp", b"abcd", "image/webp") == {"ok": True}
    assert storage_calls == [("https://storage.example/temp", b"abcd", "application/octet-stream")]
    assert "content_type=image%2Fwebp" in api_calls[0][1]
    assert "upload_temp_key=tmp%2F1" in api_calls[1][1]


def test_preserves_structured_errors_and_request_ids():
    def transport(*_):
        return 422, b'{"detail":{"code":"invalid_policy","message":"Nope"}}', {"x-request-id": "req_1"}

    with pytest.raises(SteadyLinkError) as caught:
        SteadyLink(api_key="slk_test", transport=transport).set_delivery_policy({"mode": "allow", "countries": []})
    assert caught.value.status == 422
    assert caught.value.code == "invalid_policy"
    assert caught.value.request_id == "req_1"
    assert str(caught.value) == "Nope"


def test_retries_safe_requests_but_not_unsafe_mutations(monkeypatch):
    statuses = [503, 200]
    calls = []

    def transport(method, *_):
        calls.append(method)
        status = statuses.pop(0)
        return status, b'{"items":[]}' if status == 200 else b"{}"

    monkeypatch.setattr(SteadyLink, "_sleep", staticmethod(lambda _: None))
    client = SteadyLink(api_key="slk_test", transport=transport)
    assert client.list_buckets() == {"items": []}
    assert calls == ["GET", "GET"]

    mutation_calls = []
    def failing_transport(method, *_):
        mutation_calls.append(method)
        return 503, b"{}"

    with pytest.raises(SteadyLinkError):
        SteadyLink(api_key="slk_test", transport=failing_transport, max_retries=2).create_upload_batch("bucket", [])
    assert mutation_calls == ["POST"]


def test_requires_exactly_one_authentication_method():
    with pytest.raises(ValueError):
        SteadyLink()
    with pytest.raises(ValueError):
        SteadyLink(api_key="a", access_token="b")

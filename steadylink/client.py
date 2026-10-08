from __future__ import annotations

import json
import random
import time
from dataclasses import asdict, dataclass
from email.message import Message
from typing import Any, Callable, Literal, TypedDict
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


class SteadyLinkError(RuntimeError):
    """A non-success response returned by the SteadyLink API."""

    def __init__(self, status: int, body: Any, headers: Message | dict[str, str] | None = None):
        detail = body.get("detail", body) if isinstance(body, dict) else body
        if isinstance(detail, str) and detail:
            message = detail
        elif isinstance(detail, dict) and isinstance(detail.get("message"), str):
            message = detail["message"]
        else:
            message = f"SteadyLink request failed with HTTP {status}"
        super().__init__(message)
        self.status = status
        self.detail = detail
        self.code = detail.get("code") if isinstance(detail, dict) else None
        self.request_id = _header(headers, "x-request-id") or (body.get("requestId") if isinstance(body, dict) else None)
        retry_after = _header(headers, "retry-after")
        self.retry_after = float(retry_after) if retry_after and retry_after.replace(".", "", 1).isdigit() else None


class SteadyLinkNetworkError(RuntimeError):
    """The request could not reach SteadyLink or exceeded its timeout."""


# SteadyLink signs presigned PUT URLs for this content type. The real type is
# sent in the upload manifest and detected again when the upload completes.
PRESIGNED_CONTENT_TYPE = "application/octet-stream"


@dataclass(frozen=True)
class UploadFile:
    filename: str
    size: int
    contentType: str = "application/octet-stream"
    path: str = ""


class _DeliveryPolicyRequired(TypedDict):
    mode: Literal["all", "allow", "deny"]
    countries: list[str]


class DeliveryPolicy(_DeliveryPolicyRequired, total=False):
    storageRegion: str


Transport = Callable[[str, str, dict[str, str], bytes | None], tuple[int, bytes] | tuple[int, bytes, Any]]
BinaryTransport = Callable[[str, bytes, str], tuple[int, bytes] | tuple[int, bytes, Any]]


def _header(headers: Any, name: str) -> str | None:
    if headers is None:
        return None
    return headers.get(name) or headers.get(name.title())


def _decode(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return raw.decode("utf-8", errors="replace")


def _default_transport(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, bytes, Any]:
    try:
        with urlopen(Request(url, method=method, headers=headers, data=body), timeout=30) as response:
            return response.status, response.read(), response.headers
    except HTTPError as exc:
        return exc.code, exc.read(), exc.headers


def _default_binary_transport(url: str, body: bytes, content_type: str) -> tuple[int, bytes, Any]:
    try:
        with urlopen(Request(url, method="PUT", headers={"Content-Type": content_type}, data=body), timeout=60) as response:
            return response.status, response.read(), response.headers
    except HTTPError as exc:
        return exc.code, exc.read(), exc.headers


class SteadyLink:
    """Synchronous client for SteadyLink's management API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        access_token: str | None = None,
        workspace_id: str | None = None,
        base_url: str = "https://api.steadylink.io",
        transport: Transport = _default_transport,
        binary_transport: BinaryTransport = _default_binary_transport,
        max_retries: int = 2,
    ):
        if bool(api_key) == bool(access_token):
            raise ValueError("Use exactly one of api_key or access_token")
        self.api_key = api_key
        self.access_token = access_token
        self.workspace_id = workspace_id
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.binary_transport = binary_transport
        self.max_retries = max(0, max_retries)

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        idempotency_key: str | None = None,
        retry: bool = True,
    ) -> Any:
        method = method.upper()
        headers = {"Accept": "application/json", "User-Agent": "steadylink-python/0.1.1"}
        headers["X-API-Key" if self.api_key else "Authorization"] = self.api_key or f"Bearer {self.access_token}"
        if self.workspace_id:
            headers["X-Workspace-Id"] = self.workspace_id
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        body = json.dumps(payload, separators=(",", ":")).encode() if payload is not None else None
        if body is not None:
            headers["Content-Type"] = "application/json"
        may_retry = retry and (method in {"GET", "HEAD", "OPTIONS"} or bool(idempotency_key))
        attempt = 0
        while True:
            try:
                result = self.transport(method, self.base_url + path, headers, body)
            except (URLError, TimeoutError, OSError) as exc:
                if may_retry and attempt < self.max_retries:
                    self._sleep(attempt)
                    attempt += 1
                    continue
                raise SteadyLinkNetworkError("The SteadyLink API could not be reached") from exc
            status, raw, response_headers = (*result, None) if len(result) == 2 else result
            decoded = _decode(raw)
            if 200 <= status < 300:
                return decoded
            if may_retry and status in {429, 502, 503, 504} and attempt < self.max_retries:
                retry_after = _header(response_headers, "retry-after")
                if retry_after and retry_after.replace(".", "", 1).isdigit():
                    time.sleep(float(retry_after))
                else:
                    self._sleep(attempt)
                attempt += 1
                continue
            raise SteadyLinkError(status, decoded, response_headers)

    @staticmethod
    def _sleep(attempt: int) -> None:
        time.sleep((0.25 * (2**attempt)) + random.uniform(0, 0.1))

    def upload_to_url(self, upload_url: str, body: bytes, content_type: str = PRESIGNED_CONTENT_TYPE) -> None:
        """Upload bytes to a presigned URL without sending SteadyLink credentials.

        SteadyLink signs its upload URLs for ``application/octet-stream``.
        Sending any other ``content_type`` makes storage reject the upload
        with 403.
        """
        try:
            result = self.binary_transport(upload_url, body, content_type)
        except (URLError, TimeoutError, OSError) as exc:
            raise SteadyLinkNetworkError("The presigned upload could not be completed") from exc
        status, raw, headers = (*result, None) if len(result) == 2 else result
        if not 200 <= status < 300:
            raise SteadyLinkError(status, _decode(raw), headers)

    def upload_file(self, bucket_id: str, filename: str, body: bytes, content_type: str = "application/octet-stream", path: str = "") -> dict[str, Any]:
        """Create, upload, and finalize one file."""
        batch = self.create_upload_batch(bucket_id, [UploadFile(filename, len(body), content_type, path)])
        upload = batch["files"][0]
        if not upload.get("uploadUrl"):
            raise SteadyLinkError(500, "The API did not return a presigned upload URL")
        self.upload_to_url(upload["uploadUrl"], body)
        return self.complete_upload(upload["id"])

    def list_buckets(self, limit: int = 100) -> dict[str, Any]:
        return self.request("GET", f"/api/assets/?limit={quote(str(limit))}")

    def get_asset(self, asset_id: str) -> dict[str, Any]:
        return self.request("GET", f"/api/assets/{quote(asset_id, safe='')}")

    def create_upload_batch(self, bucket_id: str, files: list[UploadFile]) -> dict[str, Any]:
        return self.request("POST", "/api/upload-batches", {"bucketId": bucket_id, "files": [asdict(file) for file in files]})

    def complete_upload(self, session_id: str, idempotency_key: str | None = None) -> dict[str, Any]:
        return self.request("POST", f"/api/upload-sessions/{quote(session_id, safe='')}/complete", idempotency_key=idempotency_key or f"complete-{session_id}")

    def cancel_upload(self, session_id: str) -> None:
        self.request("DELETE", f"/api/upload-sessions/{quote(session_id, safe='')}")

    def create_replacement_upload(self, bucket_id: str, size: int, content_type: str = "application/octet-stream") -> dict[str, Any]:
        query = urlencode({"size": size, "content_type": content_type})
        return self.request("POST", f"/api/assets/{quote(bucket_id, safe='')}/objects/upload-temp?{query}")

    def finish_replacement(self, bucket_id: str, key: str, temp_key: str, original_filename: str | None = None) -> dict[str, Any]:
        values = {"key": key, "upload_temp_key": temp_key}
        if original_filename:
            values["original_filename"] = original_filename
        return self.request("POST", f"/api/assets/{quote(bucket_id, safe='')}/objects/replace?{urlencode(values)}")

    def replace_file(self, bucket_id: str, key: str, filename: str, body: bytes, content_type: str = "application/octet-stream") -> dict[str, Any]:
        """Upload a new revision while preserving the asset's delivery URL."""
        replacement = self.create_replacement_upload(bucket_id, len(body), content_type)
        self.upload_to_url(replacement["uploadUrl"], body)
        return self.finish_replacement(bucket_id, key, replacement["tempKey"], filename)

    def create_migration(self, bucket_id: str, files: list[UploadFile]) -> dict[str, Any]:
        return self.request("POST", "/api/platform/migrations", {"bucketId": bucket_id, "files": [asdict(file) for file in files]})

    def set_focal_point(self, asset_id: str, x: float, y: float) -> dict[str, Any]:
        return self.request("PUT", f"/api/platform/assets/{quote(asset_id, safe='')}/focal-point", {"x": x, "y": y})

    def list_delivery_domains(self) -> dict[str, Any]:
        return self.request("GET", "/api/platform/domains")

    def add_delivery_domain(self, hostname: str) -> dict[str, Any]:
        return self.request("POST", "/api/platform/domains", {"hostname": hostname})

    def verify_delivery_domain(self, domain_id: str) -> dict[str, Any]:
        return self.request("POST", f"/api/platform/domains/{quote(domain_id, safe='')}/verify")

    def get_delivery_policy(self) -> DeliveryPolicy:
        return self.request("GET", "/api/platform/delivery-policy")

    def set_delivery_policy(self, policy: DeliveryPolicy) -> DeliveryPolicy:
        return self.request("PUT", "/api/platform/delivery-policy", dict(policy))

    def create_webhook(self, url: str, events: list[str]) -> dict[str, Any]:
        return self.request("POST", "/api/platform/webhooks", {"url": url, "events": events})

    def list_webhooks(self) -> dict[str, Any]:
        return self.request("GET", "/api/platform/webhooks")

    def test_webhook(self, webhook_id: str) -> dict[str, Any]:
        return self.request("POST", f"/api/platform/webhooks/{quote(webhook_id, safe='')}/test")

    def list_migrations(self) -> dict[str, Any]:
        return self.request("GET", "/api/platform/migrations")

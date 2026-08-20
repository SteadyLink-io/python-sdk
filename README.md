# SteadyLink Python SDK

[![CI](https://github.com/SteadyLink-io/python-sdk/actions/workflows/ci.yml/badge.svg)](https://github.com/SteadyLink-io/python-sdk/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/steadylink.svg?cacheSeconds=300)](https://pypi.org/project/steadylink/)
[![Python](https://img.shields.io/pypi/pyversions/steadylink.svg?cacheSeconds=300)](https://pypi.org/project/steadylink/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

The official Python client for the [SteadyLink API](https://steadylink.io/docs/developers/api-reference).

## Requirements

- Python 3.10 or newer
- A SteadyLink workspace and API key

The package has no runtime dependencies. Management API keys must only be used in trusted server environments.

## Installation

```bash
python -m pip install steadylink
```

## Quick start

```python
import os
from steadylink import SteadyLink

client = SteadyLink(
    api_key=os.environ["STEADYLINK_API_KEY"],
    workspace_id=os.environ.get("STEADYLINK_WORKSPACE_ID"),
)

buckets = client.list_buckets()["items"]
```

Create a scoped API key in **Dashboard > Developers**. You can use `access_token` instead of `api_key` for a signed-in user session. Pass exactly one authentication method.

## Upload a file

```python
from pathlib import Path

path = Path("campaign-hero.webp")
data = path.read_bytes()

asset = client.upload_file(
    "bucket_id",
    filename=path.name,
    body=data,
    content_type="image/webp",
    path="campaign/",
)
```

`upload_file` creates an upload session, sends the bytes to the presigned storage URL, and finalizes the upload. SteadyLink credentials are never attached to the storage request.

## Replace a file

```python
client.replace_file(
    "bucket_id",
    "campaign/campaign-hero.webp",
    filename=path.name,
    body=data,
    content_type="image/webp",
)
```

The replacement creates a new revision. Existing delivery URLs continue to work.

## Configuration

```python
client = SteadyLink(
    api_key=os.environ["STEADYLINK_API_KEY"],
    workspace_id="workspace_id",
    base_url="https://api.steadylink.io",
    max_retries=2,
)
```

| Option | Description |
| --- | --- |
| `api_key` | Server-side management API key. |
| `access_token` | User access token. Use this or `api_key`, not both. |
| `workspace_id` | Workspace used for workspace-scoped operations. |
| `base_url` | API origin. Useful for private or preview environments. |
| `max_retries` | Maximum transient retries. Defaults to `2`. |
| `transport` | Custom JSON transport for testing or alternate runtimes. |
| `binary_transport` | Custom presigned-upload transport. |

## Errors and retries

```python
from steadylink import SteadyLinkError, SteadyLinkNetworkError

try:
    client.list_buckets()
except SteadyLinkError as error:
    print(error.status, error.code, error.request_id, error.detail)
except SteadyLinkNetworkError as error:
    print(str(error))
```

The client retries `429`, `502`, `503`, and `504` responses for safe HTTP methods. A mutating request is only retried when it carries an idempotency key.

## Type checking

The package includes a `py.typed` marker and inline type annotations for type checkers that implement PEP 561.

## Security

- Keep management API keys out of browser bundles, mobile apps, logs, and source control.
- Give each integration the smallest set of scopes it needs.
- Use `upload_to_url` for presigned storage uploads. It does not attach SteadyLink authentication headers.
- Report vulnerabilities through [GitHub private vulnerability reporting](https://github.com/SteadyLink-io/python-sdk/security/advisories/new).

## Documentation

- [SDK guide](https://steadylink.io/docs/sdks)
- [API reference](https://steadylink.io/docs/developers/api-reference)
- [Issues](https://github.com/SteadyLink-io/python-sdk/issues)

## Development

```bash
python -m pip install build pytest twine
pytest
python -m build
python -m twine check dist/*
```

See the [contributing guide](https://github.com/SteadyLink-io/python-sdk/blob/main/CONTRIBUTING.md) for the development and release process.

## License

[MIT](LICENSE)

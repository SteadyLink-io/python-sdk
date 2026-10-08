# Changelog

## 0.1.1

- Fix: `upload_file()` and `replace_file()` now always send `Content-Type: application/octet-stream` to the presigned storage URL, which is what SteadyLink signs. Passing another `content_type`, such as `image/png`, made the upload fail with 403. The real type is still sent to the API in the upload manifest.

## 0.1.0

- Initial public preview of the SteadyLink Python SDK.
- Typed management API authentication, upload batches, replacements, delivery policy, migrations, and webhook helpers.
- Safe presigned uploads, structured errors, and idempotency-aware retries.

"""
src/backup/r2_client.py

Thin S3-compatible client for Cloudflare R2 (boto3), plus an in-memory fake
implementing the identical interface for tests — no real R2 bucket, no real
network call, ever required to exercise this module's logic. See
docs/09_Architecture_Decisions.md ADR-020 for why R2 was chosen and why
Railway never keeps a local copy of anything this client uploads, and its
Phase 27.3 "Production Hardening" addendum for the error-classification and
timeout/retry design below.

R2 credentials AND connection tuning come from environment variables only
(R2_ENABLED, R2_ACCOUNT_ID or R2_ENDPOINT_URL, R2_ACCESS_KEY_ID,
R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME, R2_REGION, R2_CONNECT_TIMEOUT_SECONDS,
R2_READ_TIMEOUT_SECONDS, R2_MAX_RETRY_ATTEMPTS) — see
src/backup/config.py::get_r2_settings(). Nothing here reads config.json
directly.

boto3 is imported lazily (inside R2Client.__init__), not at module level —
so an environment with R2 disabled never needs boto3 importable at all to
run the rest of the backup subsystem against FakeR2Client in tests.

Every real operation below classifies the botocore exception it catches
into one of three meanings, so a caller (and, ultimately, whoever reads a
log line or an API error response) can tell at a glance what actually went
wrong, without ever seeing a raw botocore stack trace or — critically — any
credential value:
- R2ConnectionError — the endpoint could not be reached at all (DNS,
  network, connect/read timeout).
- R2PermissionError — the endpoint was reached but the request was
  rejected on authentication/authorization grounds (wrong keys, wrong
  bucket permissions).
- R2OperationError — the endpoint was reached, credentials were accepted,
  but the specific operation still failed for some other reason (the
  server-reported code/message is included, never the request itself).
R2ObjectNotFoundError (a 404) is deliberately kept separate from all three
above — it is normal, expected control flow (e.g. an index entry with no
matching object yet), not an operational failure.
"""
from __future__ import annotations

from dataclasses import dataclass


class R2NotConfiguredError(RuntimeError):
    """Raised when R2 credentials/bucket are missing or R2_ENABLED is false."""


class R2ObjectNotFoundError(RuntimeError):
    """Raised by head_object/get_object when the key does not exist."""


class R2ConnectionError(RuntimeError):
    """The R2 endpoint could not be reached (DNS/network/timeout) — distinct
    from a permission or generic operation failure, since the remediation is
    different (check connectivity/endpoint URL, not credentials)."""


class R2PermissionError(RuntimeError):
    """The R2 endpoint was reached but rejected the request on
    authentication/authorization grounds (HTTP 401/403). Never includes the
    actual access key or secret — only the operation and R2's own error code."""


class R2OperationError(RuntimeError):
    """The R2 endpoint was reached and credentials were accepted, but the
    specific operation still failed. Carries R2's own error Code/Message
    only — never the raw request/response, which could theoretically
    contain signed-request headers."""


@dataclass
class R2ObjectInfo:
    key: str
    size: int
    last_modified: str | None = None


def _classify_and_raise(operation: str, key: str | None, e: "Exception") -> None:
    """Shared by every R2Client method — one implementation of "what kind of
    failure was this," so the five operations (put/head/get/delete/list)
    can never classify the same underlying error differently. Always raises;
    never returns. `key` is included in the raised message for
    diagnosability (it's an object key, e.g. "backups/manual/....zip", never
    a credential) — see the module docstring's classification rules."""
    from botocore.exceptions import (
        ClientError,
        ConnectTimeoutError,
        EndpointConnectionError,
        ReadTimeoutError,
    )

    target = f"{operation} {key}" if key else operation

    if isinstance(e, (EndpointConnectionError, ConnectTimeoutError, ReadTimeoutError)):
        raise R2ConnectionError(f"R2 {target}: could not reach the R2 endpoint ({type(e).__name__})") from e

    if isinstance(e, ClientError):
        error = e.response.get("Error", {}) if hasattr(e, "response") else {}
        code = error.get("Code", "")
        status = e.response.get("ResponseMetadata", {}).get("HTTPStatusCode") if hasattr(e, "response") else None
        message = error.get("Message", "") or str(e)

        if code in ("404", "NoSuchKey", "NotFound"):
            raise R2ObjectNotFoundError(key or target) from e

        if code in ("403", "AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch") or status in (401, 403):
            raise R2PermissionError(
                f"R2 {target}: access denied by R2 (code={code!r}) — check R2_ACCESS_KEY_ID/"
                f"R2_SECRET_ACCESS_KEY and that the key has permission on this bucket. "
                f"R2's own message: {message}"
            ) from e

        raise R2OperationError(f"R2 {target}: failed (code={code!r}): {message}") from e

    # Any other, unclassified exception — still never let a raw exception
    # (which could in principle embed request internals) propagate unwrapped.
    raise R2OperationError(f"R2 {target}: unexpected error ({type(e).__name__}): {e}") from e


class R2Client:
    """Real Cloudflare R2 client (S3-compatible API via boto3)."""

    def __init__(self, endpoint_url: str, access_key_id: str, secret_access_key: str, bucket: str,
                 region: str = "auto", connect_timeout_seconds: float = 10, read_timeout_seconds: float = 60,
                 max_retry_attempts: int = 3):
        import boto3
        from botocore.config import Config as BotoConfig
        from botocore.exceptions import BotoCoreError

        self._bucket = bucket
        try:
            self._client = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                region_name=region,
                config=BotoConfig(
                    signature_version="s3v4",
                    retries={"max_attempts": max_retry_attempts, "mode": "standard"},
                    connect_timeout=connect_timeout_seconds,
                    read_timeout=read_timeout_seconds,
                ),
            )
        except BotoCoreError as e:
            # Construction itself can fail on a malformed endpoint URL or
            # region — never let this be an unclassified crash.
            raise R2OperationError(f"R2 client construction failed: {type(e).__name__}: {e}") from e

    def put_object(self, key: str, body: bytes) -> None:
        try:
            self._client.put_object(Bucket=self._bucket, Key=key, Body=body)
        except Exception as e:
            _classify_and_raise("put_object", key, e)

    def head_object(self, key: str) -> R2ObjectInfo:
        try:
            resp = self._client.head_object(Bucket=self._bucket, Key=key)
        except Exception as e:
            _classify_and_raise("head_object", key, e)
        return R2ObjectInfo(key=key, size=resp.get("ContentLength", 0))

    def get_object(self, key: str) -> bytes:
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=key)
        except Exception as e:
            _classify_and_raise("get_object", key, e)
        return resp["Body"].read()

    def delete_object(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except Exception as e:
            _classify_and_raise("delete_object", key, e)

    def list_objects(self, prefix: str) -> list[R2ObjectInfo]:
        results: list[R2ObjectInfo] = []
        continuation_token = None
        while True:
            kwargs = {"Bucket": self._bucket, "Prefix": prefix}
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token
            try:
                resp = self._client.list_objects_v2(**kwargs)
            except Exception as e:
                _classify_and_raise("list_objects", prefix, e)
            for obj in resp.get("Contents", []):
                results.append(R2ObjectInfo(
                    key=obj["Key"],
                    size=obj.get("Size", 0),
                    last_modified=obj["LastModified"].isoformat() if obj.get("LastModified") else None,
                ))
            if resp.get("IsTruncated"):
                continuation_token = resp.get("NextContinuationToken")
            else:
                break
        return results


class FakeR2Client:
    """In-memory R2 double for tests — identical interface to R2Client, zero
    network I/O. Mirrors the basketball-over-bot project's
    r2Replication._setTestMode() precedent (a fault-injectable in-memory
    store), adapted for this project's Python stack. Set fail_next_put /
    fail_next_head to True to inject a one-shot failure for a test case."""

    def __init__(self):
        self._store: dict[str, bytes] = {}
        self.fail_next_put = False
        self.fail_next_head = False

    def put_object(self, key: str, body: bytes) -> None:
        if self.fail_next_put:
            self.fail_next_put = False
            raise RuntimeError("Simulated R2 put failure")
        self._store[key] = bytes(body)

    def head_object(self, key: str) -> R2ObjectInfo:
        if self.fail_next_head:
            self.fail_next_head = False
            raise RuntimeError("Simulated R2 head failure")
        if key not in self._store:
            raise R2ObjectNotFoundError(key)
        return R2ObjectInfo(key=key, size=len(self._store[key]))

    def get_object(self, key: str) -> bytes:
        if key not in self._store:
            raise R2ObjectNotFoundError(key)
        return self._store[key]

    def delete_object(self, key: str) -> None:
        self._store.pop(key, None)

    def list_objects(self, prefix: str) -> list[R2ObjectInfo]:
        return [
            R2ObjectInfo(key=k, size=len(v))
            for k, v in self._store.items()
            if k.startswith(prefix)
        ]

    # Test-only convenience, not part of the R2Client interface.
    def _external_delete(self, key: str) -> None:
        """Simulates an out-of-band deletion (an operator in the R2
        console) — used by integrity-verification tests."""
        self._store.pop(key, None)


def get_r2_client(settings: dict | None = None) -> R2Client:
    """Builds a real R2Client from environment-sourced settings. Raises
    R2NotConfiguredError if disabled or incomplete — callers must catch this
    and fail closed (log + skip), never crash a production job over it.
    Every field this function itself validates is checked for *presence*
    only (never logged or echoed back with its actual value — only the
    *names* of missing fields ever appear in the raised message, see
    docs/09_Architecture_Decisions.md ADR-020's Phase 27.3 addendum on
    never surfacing credential values). Connectivity/permission validation
    happens lazily, on the first real operation — see R2Client's
    per-operation error classification above, which is where a wrong
    key/endpoint/region actually gets diagnosed."""
    from src.backup.config import get_r2_settings
    s = settings or get_r2_settings()
    if not s.get("enabled"):
        raise R2NotConfiguredError("R2_ENABLED is not set to true")

    endpoint = s.get("endpoint_url") or (
        f"https://{s['account_id']}.r2.cloudflarestorage.com" if s.get("account_id") else ""
    )
    missing = [k for k in ("access_key_id", "secret_access_key", "bucket") if not s.get(k)]
    if not endpoint:
        missing.append("endpoint_url (or account_id)")
    if missing:
        raise R2NotConfiguredError(f"R2 configuration incomplete, missing: {', '.join(missing)}")

    return R2Client(
        endpoint_url=endpoint,
        access_key_id=s["access_key_id"],
        secret_access_key=s["secret_access_key"],
        bucket=s["bucket"],
        region=s.get("region") or "auto",
        connect_timeout_seconds=s.get("connect_timeout_seconds") or 10,
        read_timeout_seconds=s.get("read_timeout_seconds") or 60,
        max_retry_attempts=s.get("max_retry_attempts") or 3,
    )

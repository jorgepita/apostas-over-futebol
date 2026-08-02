"""
src/backup/r2_client.py

Thin S3-compatible client for Cloudflare R2 (boto3), plus an in-memory fake
implementing the identical interface for tests — no real R2 bucket, no real
network call, ever required to exercise this module's logic. See
docs/09_Architecture_Decisions.md ADR-020 for why R2 was chosen and why
Railway never keeps a local copy of anything this client uploads.

R2 credentials come from environment variables only (R2_ENABLED,
R2_ACCOUNT_ID or R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY,
R2_BUCKET_NAME) — see src/backup/config.py::get_r2_settings(). Nothing here
reads config.json directly.

boto3 is imported lazily (inside R2Client.__init__), not at module level —
so an environment with R2 disabled (this repository's default, as of Phase
27.2 — no real bucket/credentials exist yet, see the Phase 27.2 handover)
never needs boto3 importable at all to run the rest of the backup subsystem
against FakeR2Client in tests.
"""
from __future__ import annotations

from dataclasses import dataclass


class R2NotConfiguredError(RuntimeError):
    """Raised when R2 credentials/bucket are missing or R2_ENABLED is false."""


class R2ObjectNotFoundError(RuntimeError):
    """Raised by head_object/get_object when the key does not exist."""


@dataclass
class R2ObjectInfo:
    key: str
    size: int
    last_modified: str | None = None


class R2Client:
    """Real Cloudflare R2 client (S3-compatible API via boto3)."""

    def __init__(self, endpoint_url: str, access_key_id: str, secret_access_key: str, bucket: str):
        import boto3
        from botocore.config import Config as BotoConfig

        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=BotoConfig(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}),
        )

    def put_object(self, key: str, body: bytes) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=body)

    def head_object(self, key: str) -> R2ObjectInfo:
        from botocore.exceptions import ClientError
        try:
            resp = self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchKey", "NotFound"):
                raise R2ObjectNotFoundError(key) from e
            raise
        return R2ObjectInfo(key=key, size=resp.get("ContentLength", 0))

    def get_object(self, key: str) -> bytes:
        from botocore.exceptions import ClientError
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchKey", "NotFound"):
                raise R2ObjectNotFoundError(key) from e
            raise
        return resp["Body"].read()

    def delete_object(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def list_objects(self, prefix: str) -> list[R2ObjectInfo]:
        results: list[R2ObjectInfo] = []
        continuation_token = None
        while True:
            kwargs = {"Bucket": self._bucket, "Prefix": prefix}
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token
            resp = self._client.list_objects_v2(**kwargs)
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
    and fail closed (log + skip), never crash a production job over it."""
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
    )

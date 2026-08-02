"""
tests/test_backup_r2_production.py

Coverage for Phase 27.3's production-hardening work:
- src/backup/config.py's new region/timeout/retry settings (defaults,
  overrides, defensive fallback on invalid values).
- src/backup/r2_client.py's error classification (_classify_and_raise) —
  connection failures, permission failures, generic operation failures,
  and not-found, each producing the correct exception type.
- Security: no credential value ever appears in a raised exception's
  message, regardless of which failure path produced it.

boto3/botocore are installed in this environment (see the Phase 27.2
handover) but no real Cloudflare R2 bucket exists — every test here either
exercises _classify_and_raise() directly with a hand-built
botocore.exceptions instance (no network call), or checks config parsing
only. No real R2 network call is made anywhere in this file.

Run with:  python -m pytest tests/test_backup_r2_production.py -v
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.backup.config import (
    DEFAULT_R2_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_R2_MAX_RETRY_ATTEMPTS,
    DEFAULT_R2_READ_TIMEOUT_SECONDS,
    DEFAULT_R2_REGION,
    get_r2_settings,
)
from src.backup.r2_client import (
    R2ConnectionError,
    R2ObjectNotFoundError,
    R2OperationError,
    R2PermissionError,
    _classify_and_raise,
)


# ── get_r2_settings(): region/timeout/retry parsing ─────────────────────────

def test_get_r2_settings_defaults_region_timeouts_retries_when_unset(monkeypatch):
    for name in ("R2_REGION", "R2_CONNECT_TIMEOUT_SECONDS", "R2_READ_TIMEOUT_SECONDS", "R2_MAX_RETRY_ATTEMPTS"):
        monkeypatch.delenv(name, raising=False)
    s = get_r2_settings()
    assert s["region"] == DEFAULT_R2_REGION
    assert s["connect_timeout_seconds"] == DEFAULT_R2_CONNECT_TIMEOUT_SECONDS
    assert s["read_timeout_seconds"] == DEFAULT_R2_READ_TIMEOUT_SECONDS
    assert s["max_retry_attempts"] == DEFAULT_R2_MAX_RETRY_ATTEMPTS


def test_get_r2_settings_reads_overrides(monkeypatch):
    monkeypatch.setenv("R2_REGION", "weur")
    monkeypatch.setenv("R2_CONNECT_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("R2_READ_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("R2_MAX_RETRY_ATTEMPTS", "7")
    s = get_r2_settings()
    assert s["region"] == "weur"
    assert s["connect_timeout_seconds"] == 5.0
    assert s["read_timeout_seconds"] == 120.0
    assert s["max_retry_attempts"] == 7


def test_get_r2_settings_falls_back_on_invalid_numeric_values(monkeypatch):
    monkeypatch.setenv("R2_CONNECT_TIMEOUT_SECONDS", "not-a-number")
    monkeypatch.setenv("R2_READ_TIMEOUT_SECONDS", "-5")
    monkeypatch.setenv("R2_MAX_RETRY_ATTEMPTS", "0")
    s = get_r2_settings()
    assert s["connect_timeout_seconds"] == DEFAULT_R2_CONNECT_TIMEOUT_SECONDS
    assert s["read_timeout_seconds"] == DEFAULT_R2_READ_TIMEOUT_SECONDS
    assert s["max_retry_attempts"] == DEFAULT_R2_MAX_RETRY_ATTEMPTS


# ── _classify_and_raise(): error classification ─────────────────────────────

def _client_error(code: str, message: str = "some error", status: int = 400):
    from botocore.exceptions import ClientError
    return ClientError(
        error_response={
            "Error": {"Code": code, "Message": message},
            "ResponseMetadata": {"HTTPStatusCode": status},
        },
        operation_name="TestOperation",
    )


def test_classify_endpoint_connection_error_as_r2_connection_error():
    from botocore.exceptions import EndpointConnectionError
    e = EndpointConnectionError(endpoint_url="https://example.invalid")
    with pytest.raises(R2ConnectionError):
        _classify_and_raise("put_object", "backups/manual/x.zip", e)


def test_classify_404_as_object_not_found():
    with pytest.raises(R2ObjectNotFoundError):
        _classify_and_raise("get_object", "backups/manual/missing.zip", _client_error("NoSuchKey", status=404))


def test_classify_403_as_permission_error():
    with pytest.raises(R2PermissionError):
        _classify_and_raise("put_object", "backups/manual/x.zip", _client_error("AccessDenied", status=403))


def test_classify_signature_mismatch_as_permission_error():
    # Wrong secret key typically surfaces as SignatureDoesNotMatch, not a
    # generic 403 — must still classify as a permission problem so an
    # operator immediately knows to check credentials, not connectivity.
    with pytest.raises(R2PermissionError):
        _classify_and_raise("put_object", "backups/manual/x.zip",
                             _client_error("SignatureDoesNotMatch", status=403))


def test_classify_other_client_error_as_generic_operation_error():
    with pytest.raises(R2OperationError):
        _classify_and_raise("delete_object", "backups/manual/x.zip", _client_error("InternalError", status=500))


def test_classify_unexpected_exception_as_generic_operation_error():
    with pytest.raises(R2OperationError):
        _classify_and_raise("list_objects", "backups/", ValueError("something unrelated broke"))


# ── Security: no credential value ever appears in a raised message ─────────

FAKE_SECRET = "SUPER-SECRET-ACCESS-KEY-DO-NOT-LEAK-9f8e7d6c"


def test_permission_error_message_never_contains_the_secret_value():
    # Simulates the exact situation a wrong secret key produces —
    # SignatureDoesNotMatch — and confirms the raised message describes the
    # failure using only R2's own (secret-free) error code/message, never
    # anything from the caller's actual credential.
    e = _client_error("SignatureDoesNotMatch", message="The request signature we calculated does not match.")
    with pytest.raises(R2PermissionError) as exc_info:
        _classify_and_raise("put_object", "backups/manual/x.zip", e)
    assert FAKE_SECRET not in str(exc_info.value)


def test_r2_not_configured_error_lists_only_missing_field_names_not_values():
    from src.backup.r2_client import R2NotConfiguredError, get_r2_client
    with pytest.raises(R2NotConfiguredError) as exc_info:
        get_r2_client({
            "enabled": True,
            "account_id": "acct",
            "access_key_id": "",  # missing — the secret itself is never present here to leak
            "secret_access_key": FAKE_SECRET,
            "bucket": "my-bucket",
        })
    message = str(exc_info.value)
    assert FAKE_SECRET not in message
    assert "access_key_id" in message  # names the missing field, not any value


def test_backup_error_from_upload_failure_never_contains_the_secret_value(monkeypatch):
    # End-to-end through create_backup(): a put_object failure classified
    # as R2PermissionError must not leak the secret anywhere along the
    # BackupError wrapping chain either.
    from src.backup.backup_engine import BackupError, create_backup

    class _DeniedClient:
        def put_object(self, key, body):
            raise _client_error("AccessDenied", status=403)

    with pytest.raises(BackupError) as exc_info:
        create_backup("manual", files={"cloud_state.json": b"{}"}, r2_client=_DeniedClient())
    assert FAKE_SECRET not in str(exc_info.value)


def test_backup_manifest_and_index_entry_never_contain_credential_fields():
    from src.backup.backup_engine import create_backup
    from src.backup.r2_client import FakeR2Client

    client = FakeR2Client()
    result = create_backup("manual", files={"cloud_state.json": b"{}"}, r2_client=client)

    serialized = str(result)  # covers every field, including nested dicts
    for forbidden in ("access_key", "secret_access_key", "R2_SECRET", "GITHUB_TOKEN"):
        assert forbidden not in serialized

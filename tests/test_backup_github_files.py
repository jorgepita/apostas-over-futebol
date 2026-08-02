"""
tests/test_backup_github_files.py

Coverage for src/backup/github_files.py — the thin adapter over
update_results.py's existing GitHub Contents API primitives. Monkeypatches
those primitives directly (no real GitHub credentials/network needed),
confirming the adapter calls them with the right arguments and handles a
404 (file doesn't exist yet) the same way update_results.py's own
load_cloud_state_from_github() does.

Run with:  python -m pytest tests/test_backup_github_files.py -v
"""
import sys
from pathlib import Path
from urllib import error

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import update_results as ur
from src.backup import github_files


@pytest.fixture(autouse=True)
def _github_env(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    monkeypatch.setenv("GITHUB_OWNER", "test-owner")
    monkeypatch.setenv("GITHUB_REPO", "test-repo")
    monkeypatch.setenv("GITHUB_BRANCH", "main")


def test_fetch_file_returns_decoded_text(monkeypatch):
    calls = {}

    def fake_get_file_bytes(owner, repo, path, branch, token):
        calls["args"] = (owner, repo, path, branch, token)
        return b'{"hello": "world"}'

    monkeypatch.setattr(ur, "github_get_file_bytes", fake_get_file_bytes)

    text = github_files.fetch_file("cloud_state.json")
    assert text == '{"hello": "world"}'
    assert calls["args"] == ("test-owner", "test-repo", "cloud_state.json", "main", "fake-token")


def test_fetch_file_returns_none_on_404(monkeypatch):
    def fake_get_file_bytes(owner, repo, path, branch, token):
        raise error.HTTPError(url="x", code=404, msg="not found", hdrs=None, fp=None)

    monkeypatch.setattr(ur, "github_get_file_bytes", fake_get_file_bytes)
    assert github_files.fetch_file("sent_state.json") is None


def test_fetch_file_reraises_non_404_errors(monkeypatch):
    def fake_get_file_bytes(owner, repo, path, branch, token):
        raise error.HTTPError(url="x", code=500, msg="server error", hdrs=None, fp=None)

    monkeypatch.setattr(ur, "github_get_file_bytes", fake_get_file_bytes)
    with pytest.raises(error.HTTPError):
        github_files.fetch_file("cloud_state.json")


def test_fetch_file_without_token_raises_clear_error(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="GITHUB_TOKEN"):
        github_files.fetch_file("cloud_state.json")


def test_write_file_calls_github_put_file_with_encoded_content(monkeypatch):
    calls = {}

    def fake_put_file(owner, repo, path, content_bytes, branch, token, message):
        calls["args"] = (owner, repo, path, content_bytes, branch, token, message)

    monkeypatch.setattr(ur, "github_put_file", fake_put_file)

    github_files.write_file("cloud_state.json", '{"a": 1}', "restore: test")
    owner, repo, path, content_bytes, branch, token, message = calls["args"]
    assert (owner, repo, path, branch, token, message) == (
        "test-owner", "test-repo", "cloud_state.json", "main", "fake-token", "restore: test",
    )
    assert content_bytes == b'{"a": 1}'


def test_fetch_files_omits_404s_and_keeps_successful_ones(monkeypatch):
    def fake_get_file_bytes(owner, repo, path, branch, token):
        if path == "sent_state.json":
            raise error.HTTPError(url="x", code=404, msg="not found", hdrs=None, fp=None)
        return b"content-for-" + path.encode()

    monkeypatch.setattr(ur, "github_get_file_bytes", fake_get_file_bytes)

    result = github_files.fetch_files(["cloud_state.json", "sent_state.json"])
    assert "sent_state.json" not in result
    assert result["cloud_state.json"] == b"content-for-cloud_state.json"

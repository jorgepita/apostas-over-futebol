"""
tests/test_fixture_fetch_no_substitution.py

Regression coverage for the removal of the silent competition-substitution
fallback in fetch_oddsapi_fixtures.py.

Background: fetch_fixtures_for_league_date() used to retry a zero-fixture
response by fuzzy-searching API-Football's /leagues for a name containing the
configured league's short name (e.g. "MLS"). Because "major league soccer"
does not contain the substring "mls" but "MLS Next Pro" does, this could only
ever resolve to a different competition (MLS Next Pro) — never back to the
correctly configured one — and did so silently, with no warning surfaced
anywhere. This is what produced reserve-team fixtures mislabelled "MLS" in
picks_history.csv. See docs/05_Known_Issues.md and the ADR-004 update.

A configured canonical league ID must remain authoritative: zero fixtures for
a date means no fixtures that day, not "try a different competition".

Run with:  python -m pytest tests/test_fixture_fetch_no_substitution.py -v
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import fetch_oddsapi_fixtures as fx


def test_zero_fixture_response_does_not_trigger_substitution(monkeypatch):
    calls = []

    def fake_http_get(path, params):
        calls.append(dict(params))
        return {"response": [], "results": 0, "errors": []}

    search_calls = []

    def fake_search(league_key, season):
        search_calls.append((league_key, season))
        return 909  # would be MLS Next Pro if it were ever invoked

    monkeypatch.setattr(fx, "http_get_json_api_football", fake_http_get)
    monkeypatch.setattr(fx, "search_league_id_by_api", fake_search)

    response, from_cache = fx.fetch_fixtures_for_league_date(
        league_id=253, season=2026, date_iso="2026-07-20", league_key="mls",
    )

    assert response == []
    assert from_cache is False
    # Exactly one /fixtures call — no retry with a different league id.
    assert len(calls) == 1
    assert calls[0]["league"] == 253
    # search_league_id_by_api must never be invoked from this call path anymore.
    assert search_calls == []


def test_nonzero_fixture_response_is_returned_unmodified(monkeypatch):
    fixture_payload = [{"fixture": {"id": 1}, "teams": {"home": {"name": "Chicago Fire"}, "away": {"name": "Vancouver Whitecaps"}}}]

    def fake_http_get(path, params):
        return {"response": fixture_payload, "results": 1, "errors": []}

    def fake_search(league_key, season):
        raise AssertionError("search_league_id_by_api should not be called when fixtures were found")

    monkeypatch.setattr(fx, "http_get_json_api_football", fake_http_get)
    monkeypatch.setattr(fx, "search_league_id_by_api", fake_search)

    response, from_cache = fx.fetch_fixtures_for_league_date(
        league_id=253, season=2026, date_iso="2026-07-17", league_key="mls",
    )

    assert response == fixture_payload


def test_cached_response_short_circuits_before_any_api_call(monkeypatch):
    def fake_http_get(path, params):
        raise AssertionError("should not call the API when the cache already has this key")

    monkeypatch.setattr(fx, "http_get_json_api_football", fake_http_get)

    cache = {(253, 2026, "2026-07-17"): [{"cached": True}]}
    response, from_cache = fx.fetch_fixtures_for_league_date(
        league_id=253, season=2026, date_iso="2026-07-17", league_key="mls",
        fixtures_cache=cache,
    )

    assert from_cache is True
    assert response == [{"cached": True}]

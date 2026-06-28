#!/usr/bin/env python3
"""
audit_settlement.py -- Settlement pipeline execution audit.

Reads every LIVE (unsettled) bet from picks_history.csv,
picks_hoje_simplificado.csv and manual_bets.csv, then traces
every decision gate in the settlement pipeline using the real
APIs, printing structured per-bet diagnostics.

Does NOT write to any file. Does NOT change any CSV.

Usage:
    python audit_settlement.py

Required env vars (.env or environment):
    FOOTBALL_DATA_API_KEY   -- for EU leagues via football-data.org
    API_FOOTBALL_KEY        -- for non-EU leagues via API-Football
"""

import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib import error as urllib_error
from collections import Counter

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).resolve().parent))

# -- Import every helper from the real settlement module -----------------------
from update_results import (
    safe_read_csv,
    safe_read_manual_csv,
    LEAGUE_CODE_MAP,
    SUPPORTED_MARKETS,
    RESULT_READY_DELAY,
    FD_FINISHED_STATUS,
    AF_FINISHED_STATUS,
    MATCH_MIN_TOTAL_SCORE,
    MATCH_MIN_SIDE_SCORE,
    parse_float,
    split_game,
    is_future_date,
    get_today_lisbon_iso,
    should_use_api_football_fallback,
    fetch_api_football_fixtures_for_league_date,
    fetch_matches_for_league_date,
    find_best_fixture_match,
    score_fixture_match,
    get_fixture_status,
    get_fixture_score,
    get_fixture_kickoff_dt,
    should_try_result_update_from_fixture,
    market_result,
    extract_fixture_team_names,
    get_fixture_id,
    api_football_season_from_date,
    BLOCKED_FOOTBALL_DATA_CODES,
    API_FOOTBALL_FALLBACK_COMPETITIONS,
    AF_SEASON_MODELS,
    DAILY_FILE,
    HISTORY_FILE,
    MANUAL_FILE,
    make_shared_runtime_state,
    API_TOKEN,
    API_FOOTBALL_KEY,
)

SEP = "-" * 60


# -----------------------------------------------------------------------------
def _top_candidates(home_csv, away_csv, fixtures, shared_state, n=3):
    """Return top N fixture candidates with scores for diagnostic display."""
    scored = []
    for fx in (fixtures or []):
        api_h, api_a = extract_fixture_team_names(fx)
        total, hs, aws = score_fixture_match(home_csv, away_csv, api_h, api_a, shared_state)
        scored.append((total, hs, aws, api_h, api_a))
    scored.sort(reverse=True)
    return scored[:n]


# -----------------------------------------------------------------------------
def audit_row(row_num, row, source_label, shared_state, today_iso):
    """
    Trace one LIVE row through the full settlement decision chain.
    Returns the final reason string (e.g. "WOULD_UPDATE", "FIXTURE_NOT_FOUND").
    """
    data        = str(row.get("Data", "")).strip()
    liga        = str(row.get("Liga", "")).strip()
    jogo        = str(row.get("Jogo", "")).strip()
    mercado     = str(row.get("Mercado", "")).strip()
    odd_raw     = row.get("Odd", "")
    stake_raw   = row.get("Stake€", row.get("Stake", ""))
    kickoff_str = str(row.get("KickoffUTC", "")).strip()

    odd   = parse_float(odd_raw, 0.0)
    stake = parse_float(stake_raw, 0.0)

    home_csv, away_csv = split_game(jogo)
    now_utc = datetime.now(timezone.utc)

    print(SEP)
    print(f"Row #{row_num}  [{source_label}]")
    print()
    print(f"  Competition : {liga}")
    print(f"  Date        : {data}")
    print(f"  Kickoff     : {kickoff_str or '(not set in CSV)'}")
    print(f"  Home        : {home_csv or '???'}")
    print(f"  Away        : {away_csv or '???'}")
    print(f"  Market      : {mercado}")
    print(f"  Odds        : {odd_raw}")
    print(f"  Stake       : {stake_raw}")
    print()
    print("  [OK] CSV row loaded")
    print()

    # -- Gate 1: row completeness / validity -----------------------------------
    if not data or not liga or not jogo or odd <= 1.01 or stake <= 0:
        missing = []
        if not data:    missing.append("Data missing")
        if not liga:    missing.append("Liga missing")
        if not jogo:    missing.append("Jogo missing")
        if odd <= 1.01: missing.append(f"Odd invalid ({odd})")
        if stake <= 0:  missing.append(f"Stake invalid ({stake})")
        detail = ", ".join(missing)
        print(f"  [!!] Row validation FAILED: {detail}")
        print()
        print("  Decision: IGNORED")
        print(f"  Reason: Invalid row -- {detail}")
        return "INVALID_ROW"

    # -- Gate 2: KickoffUTC pre-filter (if CSV already has it) ----------------
    if kickoff_str:
        try:
            ko_dt = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
            if ko_dt.tzinfo is None:
                ko_dt = ko_dt.replace(tzinfo=timezone.utc)
            ko_dt = ko_dt.astimezone(timezone.utc)
            ready_at = ko_dt + RESULT_READY_DELAY
            passed = now_utc >= ready_at
            print(f"  [OK] Delay check (CSV KickoffUTC):")
            print(f"      kickoff     : {ko_dt.isoformat()}")
            print(f"      current UTC : {now_utc.isoformat()}")
            print(f"      required    : kickoff + {RESULT_READY_DELAY}")
            print(f"      ready at    : {ready_at.isoformat()}")
            print(f"      passed      : {passed}")
            print()
            if not passed:
                print("  Decision: IGNORED")
                print(
                    f"  Reason: Delay not reached -- kickoff={ko_dt.isoformat()}, "
                    f"ready_at={ready_at.isoformat()}, now={now_utc.isoformat()}"
                )
                return "DELAY_NOT_REACHED"
        except Exception as e:
            print(f"  [!!] KickoffUTC parse error: {kickoff_str!r} -> {e}")
            print()
    else:
        print("  [OK] Delay check: no KickoffUTC in CSV -- gate skipped here, will recheck from fixture")
        print()

    # -- Gate 3: market --------------------------------------------------------
    mercado_upper = mercado.upper()
    in_supported = mercado_upper in SUPPORTED_MARKETS
    print(f"  [OK] Market check: '{mercado_upper}' in {sorted(SUPPORTED_MARKETS)} -> {in_supported}")
    print()
    if not in_supported:
        print("  Decision: IGNORED")
        print(f"  Reason: Unsupported market -- '{mercado}' not in {sorted(SUPPORTED_MARKETS)}")
        return "UNSUPPORTED_MARKET"

    # -- Gate 4: date not in future --------------------------------------------
    future = is_future_date(data, today_iso)
    print(f"  [OK] Date check: pick_date={data}  today={today_iso}  future={future}")
    print()
    if future:
        print("  Decision: IGNORED")
        print(f"  Reason: Future date -- {data} is after today ({today_iso})")
        return "FUTURE_DATE"

    # -- Gate 5: league mapping ------------------------------------------------
    league_code = LEAGUE_CODE_MAP.get(liga)
    print(f"  [OK] League mapping:")
    print(f"      input     : '{liga}'")
    print(f"      mapped id : '{league_code or '(NONE - not in LEAGUE_CODE_MAP)'}'")
    print()
    if not league_code:
        print("  Decision: IGNORED")
        print(f"  Reason: League mapping missing -- '{liga}' has no entry in LEAGUE_CODE_MAP")
        return "LEAGUE_MAPPING_MISSING"

    # -- Gate 6: game format ---------------------------------------------------
    if not home_csv or not away_csv:
        print(f"  [!!] Game format: cannot split '{jogo}' on ' vs '")
        print()
        print("  Decision: IGNORED")
        print(f"  Reason: Bad game format -- '{jogo}' has no ' vs ' separator")
        return "BAD_GAME_FORMAT"
    print(f"  [OK] Game format: home='{home_csv}'  away='{away_csv}'")
    print()

    # -- Gate 7: provider routing ----------------------------------------------
    use_af_direct = should_use_api_football_fallback(league_code)
    is_blocked_fd = league_code in BLOCKED_FOOTBALL_DATA_CODES
    af_conf = API_FOOTBALL_FALLBACK_COMPETITIONS.get(league_code, {})
    af_id_for_season = af_conf.get("af_id") if af_conf else None
    season_model = AF_SEASON_MODELS.get(af_id_for_season, "european") if af_id_for_season else "european"
    computed_season = api_football_season_from_date(data, league_id=af_id_for_season)

    provider_label = "API-Football (direct)" if use_af_direct else "football-data.org"
    print(f"  [OK] Provider routing:")
    print(f"      selected  : {provider_label}")
    print(f"      league_code = '{league_code}'")
    print(f"      blocked_on_FD = {is_blocked_fd}")
    if af_conf:
        print(f"      af_id     : {af_id_for_season or '(lookup needed)'}")
        print(
            f"      season model: {season_model}"
            f"  =>  season={computed_season}  (date={data}, month={data[5:7]})"
        )
    print()

    # -------------------------------------------------------------------------
    # Fixture search
    # -------------------------------------------------------------------------
    fixtures = None
    provider_used = provider_label
    fd_matches_cache = shared_state["fd_matches_cache"]

    print(f"  [OK] Fixture search:")

    if use_af_direct:
        af_id = af_conf.get("af_id", "?")
        print(f"      method    : API-Football  /fixtures")
        print(f"                  league={af_id}  season={computed_season}  date={data}")
        try:
            fixtures, af_reason = fetch_api_football_fixtures_for_league_date(
                league_code, data, shared_state
            )
        except Exception as exc:
            print(f"      result    : EXCEPTION -- {type(exc).__name__}: {exc}")
            print()
            print("  Decision: IGNORED")
            print(f"  Reason: Exception fetching from API-Football -- {type(exc).__name__}: {exc}")
            return "EXCEPTION_FETCH_AF"

        if fixtures is None:
            print(f"      result    : FAILED -- {af_reason or 'no reason returned'}")
            print()
            print("  Decision: IGNORED")
            print(
                f"  Reason: API returned no fixtures -- reason={af_reason or 'unknown'}"
                f"  (league_code={league_code}, season={computed_season}, date={data})"
            )
            return f"API_FOOTBALL_FAILED:{af_reason or 'unknown'}"

        print(f"      result    : {len(fixtures)} fixture(s) returned")
        print()

    else:
        # football-data.org path
        cache_key = (league_code, data)
        print(f"      method    : football-data.org")
        print(f"                  /competitions/{league_code}/matches?dateFrom={data}&dateTo={data}")

        if cache_key in fd_matches_cache:
            entry = fd_matches_cache[cache_key]
            if entry["ok"]:
                fixtures = entry["matches"]
                print(f"      result    : {len(fixtures)} match(es) found (cached)")
            else:
                print(f"      result    : CACHED FAILURE -- {entry['reason']}")
        else:
            try:
                raw_matches = fetch_matches_for_league_date(league_code, data)
                fd_matches_cache[cache_key] = {"ok": True, "matches": raw_matches, "reason": ""}
                fixtures = raw_matches
                print(f"      result    : {len(fixtures)} match(es) found")
            except urllib_error.HTTPError as e:
                code = getattr(e, "code", None)
                fd_reason = f"HTTP {code}" if code is not None else "HTTP"
                fd_matches_cache[cache_key] = {"ok": False, "matches": [], "reason": fd_reason}
                print(f"      result    : FAILED -- {fd_reason}")

            except Exception as e:
                fd_matches_cache[cache_key] = {"ok": False, "matches": [], "reason": "OTHER"}
                print(f"      result    : FAILED -- {type(e).__name__}: {e}")

        # If FD failed, try AF fallback
        entry = fd_matches_cache.get(cache_key, {})
        if not entry.get("ok") and entry:
            fd_fail_reason = entry.get("reason", "UNKNOWN")
            if should_use_api_football_fallback(league_code, fd_fail_reason):
                print(f"      -> FD failed ({fd_fail_reason}), trying API-Football fallback")
                af_id = af_conf.get("af_id", "?")
                print(f"        AF: league={af_id}  season={computed_season}  date={data}")
                try:
                    fixtures, af_reason = fetch_api_football_fixtures_for_league_date(
                        league_code, data, shared_state
                    )
                    provider_used = "API-Football (fallback after FD fail)"
                    if fixtures is None:
                        print(f"        AF result: FAILED -- {af_reason}")
                    else:
                        print(f"        AF result: {len(fixtures)} fixture(s) returned")
                except Exception as exc:
                    print(f"        AF result: EXCEPTION -- {type(exc).__name__}: {exc}")
                    fixtures = None
            else:
                print()
                print("  Decision: IGNORED")
                print(
                    f"  Reason: football-data.org failed ({fd_fail_reason}) and "
                    f"no API-Football fallback configured for '{league_code}'"
                )
                return f"FD_FAILED_NO_AF:{fd_fail_reason}"

        print()

    # -- No fixtures at all ----------------------------------------------------
    if fixtures is None or len(fixtures) == 0:
        if fixtures is None:
            print("  Decision: IGNORED")
            print(
                f"  Reason: API returned no fixtures (None) for {liga} on {data} "
                f"(provider={provider_used})"
            )
            return "NO_FIXTURES_RETURNED"
        # fixtures is an empty list
        print(f"  [OK] Fixture match: 0 fixtures in API response -- nothing to match against")
        print()
        print("  Decision: IGNORED")
        print(f"  Reason: API returned 0 fixtures for {liga} on {data} (provider={provider_used})")
        return "ZERO_FIXTURES"

    # -- Gate 9: fixture matching ----------------------------------------------
    print(f"  [OK] Fixture match:")
    print(f"      pool      : {len(fixtures)} fixture(s)")
    print(f"      searching : '{home_csv} vs {away_csv}'")
    print(f"      thresholds: total>={MATCH_MIN_TOTAL_SCORE}  each_side>={MATCH_MIN_SIDE_SCORE}")

    matched, best_score, meta = find_best_fixture_match(
        home_csv, away_csv, fixtures, shared_state,
        min_total_score=MATCH_MIN_TOTAL_SCORE,
        min_side_score=MATCH_MIN_SIDE_SCORE,
    )

    if not matched:
        # Late-kickoff fallback: try date-1 for 23:00 UTC games stored with next-day date
        try:
            prev_date = (datetime.strptime(data, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
            fixtures_prev, _ = fetch_api_football_fixtures_for_league_date(league_code, prev_date, shared_state)
            if fixtures_prev:
                matched2, score2, meta2 = find_best_fixture_match(
                    home_csv, away_csv, fixtures_prev, shared_state,
                    min_total_score=MATCH_MIN_TOTAL_SCORE, min_side_score=MATCH_MIN_SIDE_SCORE,
                )
                if matched2:
                    print(f"      result    : NO MATCH on {data}, but MATCHED via date-1 fallback ({prev_date})")
                    matched, best_score, meta, fixtures = matched2, score2, meta2, fixtures_prev
        except Exception:
            pass

    if not matched:
        print(f"      result    : NO MATCH  (best_score={best_score})")
        candidates = _top_candidates(home_csv, away_csv, fixtures, shared_state)
        print(f"      top candidates from API:")
        if candidates:
            for total, hs, aws, api_h, api_a in candidates:
                print(f"          '{api_h} vs {api_a}'  score={total} (h={hs} a={aws})")
        else:
            print("          (none)")
        print()
        print("  Decision: IGNORED")
        print(
            f"  Reason: Fixture not found -- no fixture in API matched '{home_csv} vs {away_csv}' "
            f"(best_score={best_score}, need total>={MATCH_MIN_TOTAL_SCORE} and each_side>={MATCH_MIN_SIDE_SCORE})"
        )
        return "FIXTURE_NOT_FOUND"

    api_home = (meta or {}).get("api_home", "?")
    api_away = (meta or {}).get("api_away", "?")
    mode = (meta or {}).get("mode", "?")
    print(
        f"      result    : MATCHED  '{api_home} vs {api_away}' "
        f"id={get_fixture_id(matched)}  score={best_score}  mode={mode}"
    )
    print(
        f"                  h_score={(meta or {}).get('home_score','?')}  "
        f"a_score={(meta or {}).get('away_score','?')}"
    )
    print()

    # -- Gate 10: delay re-check from fixture kickoff --------------------------
    fixture_ko = get_fixture_kickoff_dt(matched)
    can_try, _ = should_try_result_update_from_fixture(matched, now_utc)

    print(f"  [OK] Delay check (fixture kickoff):")
    print(f"      kickoff     : {fixture_ko.isoformat() if fixture_ko else 'n/a'}")
    print(f"      current UTC : {now_utc.isoformat()}")
    print(f"      required    : kickoff + {RESULT_READY_DELAY}")
    if fixture_ko:
        ready_at = fixture_ko + RESULT_READY_DELAY
        print(f"      ready at    : {ready_at.isoformat()}")
    print(f"      passed      : {can_try}")
    print()

    if not can_try:
        ready_at_txt = (fixture_ko + RESULT_READY_DELAY).isoformat() if fixture_ko else "unknown"
        print("  Decision: IGNORED")
        print(
            f"  Reason: Delay not reached -- fixture kickoff={fixture_ko.isoformat() if fixture_ko else 'n/a'}, "
            f"ready_at={ready_at_txt}, now={now_utc.isoformat()}"
        )
        return "DELAY_NOT_REACHED_FIXTURE"

    # -- Gate 11: match status -------------------------------------------------
    status = str(get_fixture_status(matched)).upper()
    finished_set = AF_FINISHED_STATUS if use_af_direct else FD_FINISHED_STATUS
    is_finished = status in finished_set

    print(f"  [OK] Match status:")
    print(f"      status    : '{status or '(empty)'}'")
    print(f"      accepted  : {sorted(finished_set)}")
    print(f"      finished  : {is_finished}")
    print()

    if not is_finished:
        print("  Decision: IGNORED")
        print(
            f"  Reason: Match not finished -- status='{status}', "
            f"accepted statuses={sorted(finished_set)}"
        )
        return "MATCH_NOT_FINISHED"

    # -- Gate 12: score --------------------------------------------------------
    home_goals, away_goals = get_fixture_score(matched)
    print(f"  [OK] Final score:")
    print(f"      home : {home_goals}")
    print(f"      away : {away_goals}")
    print()

    if home_goals is None or away_goals is None:
        print("  Decision: IGNORED")
        print(f"  Reason: Score unavailable -- API returned goals={home_goals}-{away_goals}")
        return "SCORE_UNAVAILABLE"

    # -- Gate 13: market evaluation --------------------------------------------
    total_goals = int(home_goals) + int(away_goals)
    resultado = market_result(mercado_upper, int(home_goals), int(away_goals))

    print(f"  [OK] Market evaluation:")
    print(f"      market   : {mercado_upper}")
    print(f"      score    : {home_goals}-{away_goals}  (total={total_goals})")
    print(f"      expected : {_market_expectation(mercado_upper)}")
    print(f"      result   : {resultado}")
    print()

    if resultado is None:
        print("  Decision: IGNORED")
        print(f"  Reason: Unsupported market -- '{mercado_upper}' unrecognised by market_result()")
        return "UNSUPPORTED_MARKET_EVAL"

    print(f"  Decision: WOULD BE UPDATED  ->  {resultado}  ({home_goals}-{away_goals})")
    print(f"            via {provider_used}")
    return "WOULD_UPDATE"


def _market_expectation(m: str) -> str:
    if m == "O1.5": return "WIN if total >= 2"
    if m == "O2.5": return "WIN if total >= 3"
    if m == "O3.5": return "WIN if total >= 4"
    if m == "BTTS":  return "WIN if both teams scored"
    return f"(unknown market: {m})"


# -----------------------------------------------------------------------------
def audit_source(label, df, shared_state, today_iso, is_manual=False):
    """Audit all rows in a dataframe. Returns per-row reason list."""
    total = len(df)
    already_settled = 0
    results = []      # (row_num, reason) for LIVE rows
    global_row = 0

    for i, row in df.iterrows():
        global_row += 1
        res_col = "Resultado"
        resultado_atual = str(row.get(res_col, "")).strip().upper()

        if resultado_atual in {"W", "L", "P"}:
            already_settled += 1
            continue

        reason = audit_row(global_row, row, label, shared_state, today_iso)
        results.append((global_row, reason))

    return total, already_settled, results


# -----------------------------------------------------------------------------
def print_summary(label, total, already_settled, results):
    live = len(results)
    would_update = sum(1 for _, r in results if r == "WOULD_UPDATE")
    ignored = live - would_update
    reason_counts = Counter(r for _, r in results if r != "WOULD_UPDATE")

    print()
    print("=" * 60)
    print(f"SUMMARY -- {label}")
    print("=" * 60)
    print(f"  Total rows       : {total}")
    print(f"  Already settled  : {already_settled}")
    print(f"  LIVE rows        : {live}")
    print(f"  Would be updated : {would_update}")
    print(f"  Ignored          : {ignored}")
    print()
    if reason_counts:
        print("  Ignore reasons:")
        for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1]):
            print(f"    {reason:<40} {count}")
    print()
    return would_update, ignored, reason_counts


# -----------------------------------------------------------------------------
def main():
    today_iso = get_today_lisbon_iso()
    print(f"[AUDIT] date_lisbon={today_iso}  now_utc={datetime.now(timezone.utc).isoformat()}")
    print(f"[AUDIT] FOOTBALL_DATA_API_KEY set: {bool(API_TOKEN)}")
    print(f"[AUDIT] API_FOOTBALL_KEY set:      {bool(API_FOOTBALL_KEY)}")
    print(f"[AUDIT] RESULT_READY_DELAY:        {RESULT_READY_DELAY}")
    print(f"[AUDIT] MATCH_MIN_TOTAL_SCORE:     {MATCH_MIN_TOTAL_SCORE}")
    print(f"[AUDIT] MATCH_MIN_SIDE_SCORE:      {MATCH_MIN_SIDE_SCORE}")
    print(f"[AUDIT] FD_FINISHED:               {sorted(FD_FINISHED_STATUS)}")
    print(f"[AUDIT] AF_FINISHED:               {sorted(AF_FINISHED_STATUS)}")
    print()

    shared_state = make_shared_runtime_state()

    history_df = safe_read_csv(HISTORY_FILE)
    daily_df   = safe_read_csv(DAILY_FILE)
    manual_df  = safe_read_manual_csv(MANUAL_FILE)

    print(f"[AUDIT] history rows: {len(history_df)}")
    print(f"[AUDIT] daily rows:   {len(daily_df)}")
    print(f"[AUDIT] manual rows:  {len(manual_df)}")
    print()

    # -- Audit each source -----------------------------------------------------
    print()
    print("=" * 60)
    print("HISTORY  (picks_history.csv)")
    print("=" * 60)
    h_total, h_settled, h_results = audit_source(
        "history", history_df, shared_state, today_iso
    )

    print()
    print("=" * 60)
    print("DAILY  (picks_hoje_simplificado.csv)")
    print("=" * 60)
    d_total, d_settled, d_results = audit_source(
        "daily", daily_df, shared_state, today_iso
    )

    print()
    print("=" * 60)
    print("MANUAL  (manual_bets.csv)")
    print("=" * 60)
    m_total, m_settled, m_results = audit_source(
        "manual", manual_df, shared_state, today_iso, is_manual=True
    )

    # -- Per-source summaries --------------------------------------------------
    h_upd, h_ign, h_reasons = print_summary("HISTORY",  h_total, h_settled, h_results)
    d_upd, d_ign, d_reasons = print_summary("DAILY",    d_total, d_settled, d_results)
    m_upd, m_ign, m_reasons = print_summary("MANUAL",   m_total, m_settled, m_results)

    # -- Grand total -----------------------------------------------------------
    all_results = h_results + d_results + m_results
    grand_total      = h_total + d_total + m_total
    grand_settled    = h_settled + d_settled + m_settled
    grand_live       = len(all_results)
    grand_would_upd  = h_upd + d_upd + m_upd
    grand_ignored    = h_ign + d_ign + m_ign
    grand_reasons    = Counter()
    for rc in (h_reasons, d_reasons, m_reasons):
        grand_reasons.update(rc)

    print()
    print("=" * 60)
    print("GRAND TOTAL")
    print("=" * 60)
    print(f"  History rows     : {h_total}")
    print(f"  Daily rows       : {d_total}")
    print(f"  Manual rows      : {m_total}")
    print(f"  -----------------------------")
    print(f"  Total rows       : {grand_total}")
    print(f"  Already settled  : {grand_settled}")
    print(f"  LIVE rows        : {grand_live}")
    print(f"  Would be updated : {grand_would_upd}")
    print(f"  Ignored          : {grand_ignored}")
    print()
    if grand_reasons:
        print("  Ignore reasons (all sources combined):")
        total_ign = sum(grand_reasons.values())
        for reason, count in sorted(grand_reasons.items(), key=lambda x: -x[1]):
            bar = "." * max(1, 36 - len(reason))
            print(f"    {reason} {bar} {count}")
    print("=" * 60)


if __name__ == "__main__":
    main()

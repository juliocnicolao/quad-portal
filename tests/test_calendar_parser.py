"""Unit tests para collectors.economic_calendar (parser puro, sem rede)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from collectors.economic_calendar import (
    extract_next_data,
    parse_event_page,
    parse_occurrences,
)


# ─── fixtures ────────────────────────────────────────────────────────────────

_SAMPLE_META = {
    "event_id": 733,
    "long_name": "U.S. Consumer Price Index (CPI) YoY",
    "short_name": "CPI",
    "event_meta_title": "United States Consumer Price Index (CPI) YoY",
    "event_translated": "CPI (YoY)",
    "category": "inflation",
    "importance": "high",
    "country_id": 5,
    "currency": "USD",
    "event_cycle_suffix": "YoY",
    "source": "U.S Bureau of Labor Statistics",
    "page_link": "/economic-calendar/cpi-733",
}

_SAMPLE_OCC_RELEASED = {
    "actual": 3.3,
    "actual_to_forecast": "negative",
    "event_id": 733,
    "forecast": 3.4,
    "occurrence_id": 544735,
    "occurrence_time": "2026-04-10T12:30:00Z",
    "precision": 1,
    "preliminary": False,
    "previous": 2.4,
    "reference_period": "Mar",
    "revised_to_previous": "neutral",
    "unit": "%",
}

_SAMPLE_OCC_UPCOMING = {
    "actual_to_forecast": "neutral",
    "event_id": 733,
    "occurrence_id": 546684,
    "occurrence_time": "2026-05-12T12:30:00Z",
    "precision": 1,
    "preliminary": False,
    "previous": 3.3,
    "reference_period": "Apr",
    "revised_to_previous": "neutral",
    "unit": "%",
    # sem actual, sem forecast
}


def _mk_next_data(meta, occurrences):
    return {"props": {"pageProps": {"state": {"economicCalendarEventStore": {
        "event":       meta,
        "occurrences": occurrences,
    }}}}}


# ─── extract_next_data ───────────────────────────────────────────────────────

def test_extract_next_data_happy_path():
    payload = {"foo": "bar"}
    html = (f'<html><body>prefix<script id="__NEXT_DATA__" type="application/json">'
            f'{json.dumps(payload)}</script>suffix</body></html>')
    assert extract_next_data(html) == payload


def test_extract_next_data_multiline_html():
    payload = {"x": [1, 2, 3]}
    html = ('<html>\n  <body>\n    <div>hi</div>\n    '
            f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}'
            '</script>\n  </body>\n</html>')
    assert extract_next_data(html) == payload


def test_extract_next_data_missing_raises():
    html = "<html><body>no script here</body></html>"
    with pytest.raises(ValueError, match="NEXT_DATA"):
        extract_next_data(html)


# ─── parse_event_page ────────────────────────────────────────────────────────

def test_parse_event_page_happy():
    nd = _mk_next_data(_SAMPLE_META, [_SAMPLE_OCC_RELEASED])
    meta, occ = parse_event_page(nd)
    assert meta["event_id"] == 733
    assert meta["importance"] == "high"
    assert len(occ) == 1
    assert occ[0]["actual"] == 3.3


def test_parse_event_page_missing_structure_raises():
    with pytest.raises(ValueError, match="estrutura"):
        parse_event_page({"props": {"wrong": {}}})


def test_parse_event_page_empty_event_raises():
    nd = _mk_next_data({}, [])
    with pytest.raises(ValueError, match="event"):
        parse_event_page(nd)


# ─── parse_occurrences ───────────────────────────────────────────────────────

def test_parse_occurrences_released_event_has_surprise():
    now = datetime(2026, 4, 22, tzinfo=timezone.utc)
    rows = parse_occurrences(
        _SAMPLE_META, [_SAMPLE_OCC_RELEASED],
        event_name="CPI YoY", now_utc=now,
        lookback_days=30, lookahead_days=14,
    )
    assert len(rows) == 1
    r = rows[0]
    assert r["country"] == "US"
    assert r["event_name"] == "CPI YoY"
    assert r["impact"] == "high"
    assert r["actual"] == 3.3
    assert r["forecast"] == 3.4
    assert r["previous"] == 2.4
    assert r["surprise"] == pytest.approx(-0.1)
    assert r["surprise_pct"] == pytest.approx(-0.1 / 3.4)
    assert r["unit"] == "%"
    # source_raw eh JSON com metadata do occurrence
    meta = json.loads(r["source_raw"])
    assert meta["occurrence_id"] == 544735
    assert meta["reference_period"] == "Mar"
    assert meta["actual_to_forecast"] == "negative"


def test_parse_occurrences_upcoming_event_has_no_surprise():
    now = datetime(2026, 4, 22, tzinfo=timezone.utc)
    rows = parse_occurrences(
        _SAMPLE_META, [_SAMPLE_OCC_UPCOMING],
        event_name="CPI YoY", now_utc=now,
        lookback_days=30, lookahead_days=30,
    )
    assert len(rows) == 1
    r = rows[0]
    assert r["actual"] is None
    assert r["forecast"] is None
    assert r["surprise"] is None
    assert r["surprise_pct"] is None
    assert r["previous"] == 3.3


def test_parse_occurrences_filters_by_window():
    # ocurrencia fora da janela: 90 dias atras
    too_old = dict(_SAMPLE_OCC_RELEASED,
                   occurrence_time="2026-01-10T12:30:00Z",
                   occurrence_id=999)
    too_new = dict(_SAMPLE_OCC_RELEASED,
                   occurrence_time="2027-01-10T12:30:00Z",
                   occurrence_id=1000)
    in_range = _SAMPLE_OCC_RELEASED
    now = datetime(2026, 4, 22, tzinfo=timezone.utc)
    rows = parse_occurrences(
        _SAMPLE_META, [too_old, in_range, too_new],
        event_name="CPI YoY", now_utc=now,
        lookback_days=30, lookahead_days=14,
    )
    ids = [json.loads(r["source_raw"])["occurrence_id"] for r in rows]
    assert ids == [544735]


def test_parse_occurrences_unknown_country_returns_empty():
    meta = dict(_SAMPLE_META, country_id=999)
    now = datetime(2026, 4, 22, tzinfo=timezone.utc)
    rows = parse_occurrences(meta, [_SAMPLE_OCC_RELEASED],
                             event_name="X", now_utc=now,
                             lookback_days=30, lookahead_days=14)
    assert rows == []


def test_parse_occurrences_br_country_id_32_maps_to_BR():
    meta = dict(_SAMPLE_META, country_id=32, currency="BRL",
                long_name="Brazil CPI YoY", importance="medium")
    now = datetime(2026, 4, 22, tzinfo=timezone.utc)
    rows = parse_occurrences(meta, [_SAMPLE_OCC_RELEASED],
                             event_name="IPCA YoY", now_utc=now,
                             lookback_days=30, lookahead_days=14)
    assert rows[0]["country"] == "BR"
    assert rows[0]["impact"] == "medium"


def test_parse_occurrences_surprise_with_zero_forecast():
    occ = dict(_SAMPLE_OCC_RELEASED, forecast=0.0, actual=0.2)
    now = datetime(2026, 4, 22, tzinfo=timezone.utc)
    rows = parse_occurrences(_SAMPLE_META, [occ], "X", now, 30, 14)
    assert rows[0]["surprise"] == pytest.approx(0.2)
    # forecast=0 → surprise_pct None (evita div by zero)
    assert rows[0]["surprise_pct"] is None


def test_parse_occurrences_event_time_formatted_utc_z():
    now = datetime(2026, 4, 22, tzinfo=timezone.utc)
    rows = parse_occurrences(_SAMPLE_META, [_SAMPLE_OCC_RELEASED],
                             "X", now, 30, 14)
    assert rows[0]["event_time"] == "2026-04-10T12:30:00Z"


def test_parse_occurrences_invalid_time_skipped():
    occ = dict(_SAMPLE_OCC_RELEASED, occurrence_time="not-a-date")
    now = datetime(2026, 4, 22, tzinfo=timezone.utc)
    rows = parse_occurrences(_SAMPLE_META, [occ], "X", now, 30, 14)
    assert rows == []

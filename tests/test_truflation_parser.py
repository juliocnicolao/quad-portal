"""Unit tests para collectors.truflation.parse_payload.

Nao bate em rede — usa fixtures sinteticas no shape real do endpoint.
"""
from __future__ import annotations

import math

import pytest

from collectors.truflation import parse_payload


def _mkpayload(labels, data, **extras):
    return {
        "labels": labels,
        "datasets": [{"slug": "us-inflation-rate", "title": "TruCPI-US",
                      "unit": "%", "data": data, **extras.get("ds0", {})}],
        "isTransformedToDaily": True,
    }


def test_happy_path_basic_shape():
    labels = ["2026-04-18", "2026-04-19", "2026-04-20"]
    data   = [1.70, 1.75, 1.80]
    rows = parse_payload(_mkpayload(labels, data))
    assert len(rows) == 3
    assert rows[0] == {"date": "2026-04-18", "value": 1.70,
                       "change_1d": None, "change_7d": None, "change_30d": None}
    assert rows[1]["change_1d"] == pytest.approx(0.05)
    assert rows[2]["change_1d"] == pytest.approx(0.05)
    # 7d/30d ainda None (historico insuficiente)
    assert rows[2]["change_7d"] is None
    assert rows[2]["change_30d"] is None


def test_change_7d_and_30d_with_enough_history():
    # 40 dias, valor sobe 0.01 por dia
    labels = [f"2026-03-{str(i).zfill(2)}" if i <= 31
              else f"2026-04-{str(i-31).zfill(2)}" for i in range(1, 41)]
    data = [1.00 + i * 0.01 for i in range(40)]
    rows = parse_payload(_mkpayload(labels, data))
    last = rows[-1]
    # change_1d: diff para o dia anterior = 0.01
    assert last["change_1d"] == pytest.approx(0.01)
    # change_7d: diff para 7 dias atras = 0.07
    assert last["change_7d"] == pytest.approx(0.07)
    # change_30d: diff para 30 dias atras = 0.30
    assert last["change_30d"] == pytest.approx(0.30)


def test_sorts_out_of_order_labels():
    labels = ["2026-04-20", "2026-04-18", "2026-04-19"]
    data   = [1.80, 1.70, 1.75]
    rows = parse_payload(_mkpayload(labels, data))
    assert [r["date"] for r in rows] == ["2026-04-18", "2026-04-19", "2026-04-20"]
    assert [r["value"] for r in rows] == [1.70, 1.75, 1.80]


def test_filters_nulls_in_data():
    labels = ["2026-04-18", "2026-04-19", "2026-04-20"]
    data   = [1.70, None, 1.80]
    rows = parse_payload(_mkpayload(labels, data))
    assert len(rows) == 2
    assert rows[0]["date"] == "2026-04-18"
    assert rows[1]["date"] == "2026-04-20"


def test_coerces_numeric_strings():
    labels = ["2026-04-18", "2026-04-19"]
    data   = ["1.70", "1.80"]          # vem como string — converter
    rows = parse_payload(_mkpayload(labels, data))
    assert rows[0]["value"] == pytest.approx(1.70)
    assert rows[1]["value"] == pytest.approx(1.80)


def test_mismatched_lengths_raises():
    with pytest.raises(ValueError, match="tamanhos diferentes"):
        parse_payload(_mkpayload(["2026-04-18", "2026-04-19"], [1.70]))


def test_missing_labels_raises():
    with pytest.raises(ValueError, match="labels"):
        parse_payload({"datasets": [{"data": [1.0]}]})


def test_missing_datasets_raises():
    with pytest.raises(ValueError, match="datasets"):
        parse_payload({"labels": ["2026-04-18"]})


def test_empty_data_returns_empty_list():
    # shape valido mas sem pontos validos
    rows = parse_payload(_mkpayload(["2026-04-18"], [None]))
    assert rows == []


def test_realistic_shape_matches_endpoint():
    """Replica a shape exata retornada pelo endpoint descoberto no recon."""
    labels = ["2025-04-22", "2025-04-23", "2025-04-24"]
    data   = [1.378826, 1.390311, 1.402742]
    payload = {
        "labels": labels,
        "datasets": [{
            "slug": "us-inflation-rate",
            "title": "Truflation US CPI Inflation Index",
            "unit": "%",
            "data": data,
        }],
        "isTransformedToDaily": True,
    }
    rows = parse_payload(payload)
    assert len(rows) == 3
    assert all(math.isfinite(r["value"]) for r in rows)
    assert rows[-1]["value"] == pytest.approx(1.402742)

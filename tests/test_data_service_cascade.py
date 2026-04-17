"""Testa a cascata yfinance → stooq no data_service."""
from unittest.mock import patch
from services import data_service as data


def test_quote_usa_yfinance_quando_ok():
    with patch.object(data, "yf_svc") as yf, \
         patch.object(data, "stooq") as st_:
        yf.get_quote.return_value = {"ticker": "X", "price": 100, "error": False}
        q = data.quote("X")
    assert q["source"] == "yfinance"
    assert q["price"] == 100
    st_.get_quote.assert_not_called()


def test_quote_cai_para_stooq_quando_yfinance_erro():
    with patch.object(data, "yf_svc") as yf, \
         patch.object(data, "stooq") as st_:
        yf.get_quote.return_value = {"ticker": "X", "price": None, "error": True}
        st_.get_quote.return_value = {"ticker": "X", "price": 99, "error": False}
        q = data.quote("X")
    assert q["source"] == "stooq"
    assert q["price"] == 99


def test_quote_br_tenta_brapi_primeiro():
    with patch.object(data, "brapi") as br, \
         patch.object(data, "yf_svc") as yf, \
         patch.object(data, "stooq") as st_:
        br.get_quote.return_value = {"ticker": "PETR4", "price": 40, "error": False}
        q = data.quote("PETR4", br=True)
    assert q["source"] == "brapi"
    yf.get_quote.assert_not_called()


def test_quote_todas_falham_retorna_error():
    with patch.object(data, "yf_svc") as yf, \
         patch.object(data, "stooq") as st_:
        yf.get_quote.return_value = {"price": None, "error": True}
        st_.get_quote.return_value = {"price": None, "error": True}
        q = data.quote("ZZZ")
    assert q["error"] is True
    assert q["source"] == "none"

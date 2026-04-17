"""Testes dos utilitários de formatação."""
from utils import fmt_currency_brl, fmt_currency_usd, fmt_pct, fmt_points


def test_fmt_currency_brl_basico():
    assert fmt_currency_brl(1234.56) == "R$ 1.234,56"
    assert fmt_currency_brl(0)       == "R$ 0,00"
    assert fmt_currency_brl(1_000_000.5) == "R$ 1.000.000,50"


def test_fmt_currency_usd_basico():
    assert fmt_currency_usd(1234.56) == "$ 1,234.56"
    assert fmt_currency_usd(0)       == "$ 0.00"


def test_fmt_pct_sinais():
    s = fmt_pct(1.23)
    assert s.startswith("▲") and "1.23%" in s or "1,23%" in s
    n = fmt_pct(-2.5)
    assert n.startswith("▼")
    assert fmt_pct(0).startswith("▲")


def test_fmt_points_separador_br():
    assert fmt_points(12345.67) == "12.345,67"

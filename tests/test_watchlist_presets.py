"""Testes do catalogo de presets de watchlist."""

from services.watchlist_presets import (
    WATCHLIST_PRESETS,
    get_preset,
    get_preset_names,
)


def test_default_preset_exists_and_nonempty():
    out = get_preset("Default")
    assert isinstance(out, list)
    assert len(out) >= 5
    assert "PBR" in out  # default aprovado pelo usuario


def test_custom_preset_is_empty_placeholder():
    assert get_preset("Custom") == []


def test_get_preset_inexistente_returns_empty_list():
    assert get_preset("NaoExiste") == []


def test_get_preset_names_includes_all_known():
    names = get_preset_names()
    for must in ("Default", "Energy", "Brasil ADRs", "Volatility",
                 "Commodities", "Mag 7 + Index", "Financials US", "Custom"):
        assert must in names


def test_get_preset_returns_copy_not_reference():
    """Mutar o retorno nao deve afetar o catalogo."""
    a = get_preset("Default")
    a.append("FAKE")
    b = get_preset("Default")
    assert "FAKE" not in b

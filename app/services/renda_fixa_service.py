"""Renda Fixa Brasil — Tesouro Direto (CSV público) + proxy da curva DI.

Fontes:
- Tesouro Direto: https://www.tesourotransparente.gov.br/ckan/dataset/ (CSV PrecoTaxaTesouroDireto)
- DI futures: yfinance via data_service (cascade → stooq)
"""

import streamlit as st
import requests
import pandas as pd
from io import StringIO, BytesIO
from utils import CACHE_TTL
from services import data_service as data


_TD_URL = ("https://www.tesourotransparente.gov.br/ckan/dataset/"
           "df56aa42-484a-4a59-8184-7676580c81e3/resource/"
           "796d2059-14e9-44e3-80c9-2d9e30b405c1/download/"
           "PrecoTaxaTesouroDireto.csv")


@st.cache_data(ttl=CACHE_TTL * 4, persist="disk")
def get_tesouro_direto() -> pd.DataFrame:
    """Baixa e filtra o CSV público do Tesouro Direto.
    Retorna DataFrame com últimas taxas por título."""
    try:
        r = requests.get(_TD_URL, timeout=25,
                         headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        df = pd.read_csv(BytesIO(r.content), sep=";", decimal=",",
                         parse_dates=["Data Base", "Data Vencimento"],
                         dayfirst=True)
        if df.empty:
            return pd.DataFrame()
        # Pega a última data disponível
        last_date = df["Data Base"].max()
        df = df[df["Data Base"] == last_date].copy()

        # Só futuro + preço válido
        today = pd.Timestamp.today().normalize()
        df = df[df["Data Vencimento"] > today]
        df = df.sort_values(["Tipo Titulo", "Data Vencimento"]).reset_index(drop=True)
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=CACHE_TTL, persist="disk")
def get_di_curve() -> pd.DataFrame:
    """Curva DI aproximada via DI futures (DIF25, DIF26...) pela data_service.
    Retorna DataFrame com [vencimento, taxa]."""
    di_tickers = {
        "DI Jan/26": "DIF26.SA",
        "DI Jan/27": "DIF27.SA",
        "DI Jan/28": "DIF28.SA",
        "DI Jan/29": "DIF29.SA",
        "DI Jan/30": "DIF30.SA",
    }
    rows = []
    for label, ticker in di_tickers.items():
        q = data.quote(ticker)
        price = q.get("price")
        if price and price > 0:
            # PU base 100k → taxa a.a. aproximada (maturidade ~1..5 anos)
            # Para uma proxy visual básica: taxa implícita = (100000/PU - 1)*100
            try:
                taxa = (100_000 / price - 1) * 100
                if 0 < taxa < 30:  # sanity filter
                    rows.append({"vencimento": label, "taxa": round(taxa, 2)})
            except Exception:
                continue
    return pd.DataFrame(rows)

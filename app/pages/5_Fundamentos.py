import math
import streamlit as st
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

st.set_page_config(page_title="Fundamentos | QUAD", page_icon="🌍",
                   layout="wide", initial_sidebar_state="expanded")

from components.layout  import inject_css, render_sidebar, render_footer, page_header
from components.cards   import section_header
from services.macro_service import get_all_fundamentals

def _valid(v):
    return v is not None and not (isinstance(v, float) and math.isnan(v))

inject_css()
render_sidebar()
page_header("Fundamentos Países", "PIB, Inflação, Dívida e Taxa de Juros — dados FMI & Bancos Centrais")

# ── Styles ─────────────────────────────────────────────────────────────────────
st.markdown("""<style>
.fund-table { width:100%; border-collapse:collapse; font-size:0.84rem; }
.fund-table th { color:#666; font-size:0.62rem; text-transform:uppercase; letter-spacing:0.09em; padding:0.5rem 0.8rem; border-bottom:1px solid #2a2a2a; text-align:right; white-space:nowrap; }
.fund-table th:first-child { text-align:left; }
.fund-table td { padding:0.5rem 0.8rem; border-bottom:1px solid #181818; color:#E0E0E0; text-align:right; white-space:nowrap; vertical-align:middle; }
.fund-table td:first-child { text-align:left; }
.fund-table tbody tr:hover td { background:#1d1d1d; }
.f-country { font-weight:600; font-size:0.85rem; color:#F0F0F0; }
.f-code    { font-size:0.62rem; color:#555; margin-left:4px; }
.pill-hi   { background:rgba(200,35,43,0.15); color:#E05555; border:1px solid rgba(200,35,43,0.3); padding:2px 8px; border-radius:20px; font-weight:700; font-size:0.8rem; display:inline-block; }
.pill-lo   { background:rgba(38,162,105,0.15); color:#2ec27e; border:1px solid rgba(38,162,105,0.3); padding:2px 8px; border-radius:20px; font-weight:700; font-size:0.8rem; display:inline-block; }
.pill-mid  { color:#C0C0C0; font-size:0.83rem; }
.pill-na   { color:#3a3a3a; }
.bar-wrap  { display:inline-flex; align-items:center; gap:6px; justify-content:flex-end; }
.bar-track { background:#252525; border-radius:2px; height:3px; width:52px; display:inline-block; flex-shrink:0; }
.gdp-val   { font-size:0.82rem; color:#C0C0C0; }
.gdp-year  { font-size:0.6rem; color:#444; margin-left:3px; }
.hi-card   { background:#1A1A1A; border:1px solid #252525; border-radius:8px; padding:0.9rem 1rem; }
.hi-label  { font-size:0.62rem; color:#666; text-transform:uppercase; letter-spacing:0.1em; margin-bottom:0.3rem; }
.hi-flag   { font-size:1.1rem; margin-right:4px; }
.hi-name   { font-size:0.78rem; font-weight:700; color:#F0F0F0; }
.hi-val    { font-size:1.2rem; font-weight:700; color:#F0F0F0; margin-top:0.15rem; }
.hi-sub    { font-size:0.65rem; color:#555; margin-top:0.1rem; }
.cc-card   { background:#1A1A1A; border:1px solid #222; border-radius:8px; padding:0.85rem 0.9rem; height:100%; }
.cc-head   { font-size:0.88rem; font-weight:700; color:#F0F0F0; border-left:2px solid #C8232B; padding-left:0.45rem; margin-bottom:0.55rem; }
.cc-row    { display:flex; justify-content:space-between; align-items:center; margin-bottom:0.22rem; }
.cc-lbl    { font-size:0.63rem; color:#666; text-transform:uppercase; letter-spacing:0.06em; }
.cc-num    { font-size:0.82rem; font-weight:600; color:#D0D0D0; }
</style>""", unsafe_allow_html=True)

# ── Data ──────────────────────────────────────────────────────────────────────
with st.spinner("Carregando dados macroeconômicos…"):
    df = get_all_fundamentals()

if df.empty:
    st.error("Não foi possível carregar os dados. Tente novamente em instantes.")
    st.stop()

# ── Helpers ───────────────────────────────────────────────────────────────────
def _quartile_css(val, col_vals, lo_good=True):
    """Return pill CSS class based on quartile position."""
    if not _valid(val):
        return "pill-na"
    clean = sorted(v for v in col_vals if _valid(v))
    if len(clean) < 4:
        return "pill-mid"
    q25 = clean[len(clean) // 4]
    q75 = clean[int(len(clean) * 0.75)]
    if lo_good:
        return "pill-hi" if val >= q75 else ("pill-lo" if val <= q25 else "pill-mid")
    else:
        return "pill-hi" if val <= q25 else ("pill-lo" if val >= q75 else "pill-mid")

def _pill(val, col_vals, lo_good=True, decimals=1, suffix=""):
    if not _valid(val):
        return '<span class="pill-na">—</span>'
    css = _quartile_css(val, col_vals, lo_good)
    fmtd = f"{val:,.{decimals}f}{suffix}"
    return f'<span class="{css}">{fmtd}</span>'

def _bar_pill(val, col_vals, lo_good=True, decimals=1, suffix=""):
    """Pill with inline mini-bar showing relative magnitude."""
    if not _valid(val):
        return '<span class="pill-na">—</span>'
    clean = [v for v in col_vals if _valid(v)]
    pct   = int(val / max(clean) * 100) if clean and max(clean) > 0 else 0
    pct   = min(pct, 100)
    css   = _quartile_css(val, col_vals, lo_good)
    bar_color = "#E05555" if css == "pill-hi" else ("#2ec27e" if css == "pill-lo" else "#444")
    fmtd  = f"{val:,.{decimals}f}{suffix}"
    label = f'<span class="{css}">{fmtd}</span>' if css in ("pill-hi", "pill-lo") else f'<span class="pill-mid">{fmtd}</span>'
    bar   = (f'<span class="bar-track">'
             f'<span style="display:block;background:{bar_color};border-radius:2px;height:3px;width:{pct}%;"></span>'
             f'</span>')
    return f'<span class="bar-wrap">{bar}{label}</span>'

# ── Column lists for comparison ───────────────────────────────────────────────
gdp_vals   = df["PIB (USD)"].tolist()
infl_vals  = df["Inflação %"].tolist()
gross_vals = df["Dívida Bruta/PIB"].tolist()
net_vals   = df["Dívida Líq./PIB"].tolist()
rate_vals  = df["Taxa de Juros %"].tolist()

# ── Highlight winners ─────────────────────────────────────────────────────────
def _best(col, reverse=False):
    sub = df[df[col].apply(_valid)]
    if sub.empty:
        return None
    return sub.sort_values(col, ascending=reverse).iloc[0]

row_gdp   = _best("PIB (USD)",       reverse=True)   # highest GDP
row_infl  = _best("Inflação %",      reverse=False)  # lowest inflation
row_debt  = _best("Dívida Líq./PIB", reverse=False)  # lowest net debt
row_rate  = _best("Taxa de Juros %", reverse=False)  # lowest rate

def _hi_card(col, label, fmt_fn, sub_text, accent="#C8232B"):
    row = col
    if row is None:
        return f'<div class="hi-card"><div class="hi-label">{label}</div><div class="hi-val" style="color:#444;">—</div></div>'
    flag_name = row["País"]          # e.g. "🇺🇸 EUA"
    parts = flag_name.split(" ", 1)
    flag  = parts[0]
    name  = parts[1] if len(parts) > 1 else flag_name
    return (f'<div class="hi-card">'
            f'<div class="hi-label">{label}</div>'
            f'<div style="margin:0.3rem 0 0.2rem 0;"><span class="hi-flag">{flag}</span><span class="hi-name">{name}</span></div>'
            f'<div class="hi-val" style="color:{accent};">{fmt_fn(row)}</div>'
            f'<div class="hi-sub">{sub_text}</div>'
            f'</div>')

col_a, col_b, col_c, col_d = st.columns(4)
with col_a:
    st.markdown(_hi_card(row_gdp,  "Maior PIB",
        lambda r: f"US$ {r['PIB (USD)']:,.0f} bi", f"Ano {row_gdp['_pib_year']}", "#4A90D9"), unsafe_allow_html=True)
with col_b:
    st.markdown(_hi_card(row_infl, "Menor Inflação",
        lambda r: f"{r['Inflação %']:.1f}%", "Melhor controle de preços", "#2ec27e"), unsafe_allow_html=True)
with col_c:
    st.markdown(_hi_card(row_debt, "Menor Dívida Líq./PIB",
        lambda r: f"{r['Dívida Líq./PIB']:.1f}%", "Balanço fiscal mais saudável", "#2ec27e"), unsafe_allow_html=True)
with col_d:
    st.markdown(_hi_card(row_rate, "Menor Taxa de Juros",
        lambda r: f"{r['Taxa de Juros %']:.2f}%", "Crédito mais barato", "#2ec27e"), unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ══ COMPARISON TABLE ══════════════════════════════════════════════════════════
section_header("Tabela Comparativa", "Verde = melhor quartil · Vermelho = pior quartil · barras = magnitude relativa")

rows_html = ""
for i, (_, row) in enumerate(df.iterrows(), 1):
    gdp_bi  = row["PIB (USD)"]
    gdp_str = f'<span class="gdp-val">US$ {gdp_bi:,.0f} bi</span><span class="gdp-year">({row["_pib_year"]})</span>' if _valid(gdp_bi) else '<span class="pill-na">—</span>'

    flag_name = row["País"]
    parts = flag_name.split(" ", 1)
    flag  = parts[0]
    name  = parts[1] if len(parts) > 1 else flag_name

    infl_cell  = _pill(row["Inflação %"],       infl_vals,  lo_good=True,  decimals=1, suffix="%")
    gross_cell = _bar_pill(row["Dívida Bruta/PIB"], gross_vals, lo_good=True, decimals=1, suffix="%")
    net_cell   = _bar_pill(row["Dívida Líq./PIB"],  net_vals,  lo_good=True, decimals=1, suffix="%")
    rate_cell  = _pill(row["Taxa de Juros %"],  rate_vals,  lo_good=True,  decimals=2, suffix="%")

    stripe = "background:#161616;" if i % 2 == 0 else ""
    rows_html += (
        f'<tr style="{stripe}">'
        f'<td><span class="f-country">{flag} {name}</span></td>'
        f'<td>{gdp_str}</td>'
        f'<td>{infl_cell}</td>'
        f'<td>{gross_cell}</td>'
        f'<td>{net_cell}</td>'
        f'<td>{rate_cell}</td>'
        f'</tr>'
    )

st.markdown(f"""<table class="fund-table">
<thead><tr>
  <th>País</th>
  <th>PIB (USD bi)</th>
  <th>Inflação %</th>
  <th>Dívida Bruta/PIB ▸</th>
  <th>Dívida Líq./PIB ▸</th>
  <th>Taxa de Juros %</th>
</tr></thead>
<tbody>{rows_html}</tbody>
</table>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)
st.caption("Fontes: FMI DataMapper (PIB, Inflação¹, Dívida Bruta) · FMI WEO Out/2024 (Dívida Líquida) · FRED / BCB (Juros)  |  ¹ EUA: CPI YoY via FRED · Brasil: IPCA 12m via BCB · demais: estimativa anual FMI")

st.markdown("---")

# ══ COUNTRY CARDS (5 per row) ══════════════════════════════════════════════════
section_header("Detalhes por País", "Todos os indicadores por país")

def _cc_row(lbl, val_html):
    return f'<div class="cc-row"><span class="cc-lbl">{lbl}</span><span class="cc-num">{val_html}</span></div>'

chunks = [df.iloc[i:i+5] for i in range(0, len(df), 5)]
for chunk in chunks:
    cols = st.columns(5)
    for col, (_, row) in zip(cols, chunk.iterrows()):
        gdp_bi   = row["PIB (USD)"]
        gdp_disp = f"US$ {gdp_bi:,.0f} bi" if _valid(gdp_bi) else "—"
        infl_s   = f"{row['Inflação %']:.1f}%" if _valid(row["Inflação %"]) else "—"
        gross_s  = f"{row['Dívida Bruta/PIB']:.1f}%" if _valid(row["Dívida Bruta/PIB"]) else "—"
        net_s    = f"{row['Dívida Líq./PIB']:.1f}%" if _valid(row["Dívida Líq./PIB"]) else "—"
        rate_s   = f"{row['Taxa de Juros %']:.2f}%" if _valid(row["Taxa de Juros %"]) else "—"

        # color-code the rate value in the card
        r_css  = _quartile_css(row["Taxa de Juros %"], rate_vals, lo_good=True)
        r_color = "#E05555" if r_css == "pill-hi" else ("#2ec27e" if r_css == "pill-lo" else "#D0D0D0")

        flag_name = row["País"]
        with col:
            st.markdown(
                f'<div class="cc-card">'
                f'<div class="cc-head">{flag_name}</div>'
                + _cc_row("PIB", gdp_disp)
                + _cc_row("Inflação", infl_s)
                + _cc_row("Dív. Bruta/PIB", gross_s)
                + _cc_row("Dív. Líq./PIB", net_s)
                + f'<div class="cc-row"><span class="cc-lbl">Juros</span><span class="cc-num" style="color:{r_color};font-weight:700;">{rate_s}</span></div>'
                + f'</div>',
                unsafe_allow_html=True
            )

render_footer()

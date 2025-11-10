# prices.py
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objs as go
from datetime import datetime
from pathlib import Path
from itertools import islice

# --- Paramètres ---
START_DATE = pd.Timestamp("2020-01-01")   # >= 2020
DEFAULT_XLSX = Path("Prices") / "LPG prices.xlsx"

# --- Symbol lists ---
BUTANE_SYMBOLS = [
    'AAXDC00','PMAAK00','ABTNM01','ABTNM02','PMAAC00','ABTMA00','ATM0102','ATM0203',
    'ABTNB00','APRPF00','PMAAI00','AAWUF00','PTAAF10','PMAAF00','PMAAB00','PHAKG00',
    'AAWWM00','AAWWL00','FOCBA00','PHALA00','PHALF11','MTBEA00'
]
PROPANE_SYMBOLS = [
    'PMAAY00','AAWUD00','PMAAS00','APRPE00','PTAAM10','AAXIM00','PCMDM00','HPAJP00',
    'AAUXJ00','AAWWK00','PHAJD00','AEFOB00','AAOTM00','AAOTN00','PHAJC00'
]

# --- Styles par année ---
COLOR_MAP = {
    2025: "#000000",  # noir
    2024: "#d62728",  # rouge
    2023: "#2ca02c",  # vert
    2022: "#ffd300",  # jaune
    2021: "#6a3d9a",  # violet
    2020: "#7f7f7f",  # gris
}
BOLD_YEARS = {2025: 3.8, 2024: 3.4, 2023: 3.0}  # années mises en avant
THIN_WIDTH = 1.6
THIN_OPACITY = 0.55

@st.cache_data(show_spinner=False)
def load_excel(path_or_buffer):
    df = pd.read_excel(path_or_buffer, engine="openpyxl")
    df.columns = [str(c).strip().upper() for c in df.columns]
    return df

def combine_unit(subdf: pd.DataFrame) -> str:
    mom = subdf.get("MOM")
    cur = subdf.get("CURRENCY")
    def pick(s):
        try:
            return s.dropna().astype(str).replace({"nan":"", "None":""}).iloc[0]
        except Exception:
            return ""
    m = pick(mom) if mom is not None else ""
    c = pick(cur) if cur is not None else ""
    if m and c: return f"{m} / {c}"
    return m or c

def normalize_to_dummy_year(dt_series: pd.Series) -> pd.Series:
    def to_dummy(d):
        if pd.isna(d): return np.nan
        try:
            return datetime(2000, d.month, 28 if (d.month==2 and d.day==29) else d.day)
        except Exception:
            return datetime(2000, d.month, 1)
    return pd.to_datetime(dt_series).map(to_dummy)

def _band_2020_2024(df_desc: pd.DataFrame):
    """
    Enveloppe min–max 2020–2024 en surface pleine (gris clair) sur une grille journalière continue.
    """
    if df_desc.empty:
        return None

    dd = df_desc.copy()
    dd["ASSESSDATE"] = pd.to_datetime(dd["ASSESSDATE"])
    dd = dd[(dd["ASSESSDATE"] >= pd.Timestamp("2020-01-01")) &
            (dd["ASSESSDATE"] <  pd.Timestamp("2025-01-01"))]
    if dd.empty:
        return None

    dd["DUMMY_DATE"] = normalize_to_dummy_year(dd["ASSESSDATE"])
    dd["YEAR"] = dd["ASSESSDATE"].dt.year

    # Grille journalière complète
    grid = pd.date_range("2000-01-01", "2000-12-31", freq="D")

    series_per_year = {}
    for yr, g in dd.groupby("YEAR"):
        g = g.sort_values("DUMMY_DATE")
        s = g.groupby("DUMMY_DATE")["VALUE"].last()
        s = s.reindex(grid)
        s = s.interpolate(method="time", limit_direction="both")
        series_per_year[yr] = s

    if not series_per_year:
        return None

    wide = pd.DataFrame(series_per_year, index=grid)
    minv = wide.min(axis=1)
    maxv = wide.max(axis=1)

    lower = go.Scatter(
        x=minv.index, y=minv.values,
        mode="lines", line=dict(width=0),
        name="Range 2020–2024 (min)",
        showlegend=False
    )
    upper = go.Scatter(
        x=maxv.index, y=maxv.values,
        mode="lines", line=dict(width=0),
        fill="tonexty",
        fillcolor="rgba(128,128,128,0.20)",
        name="Range 2020–2024"
    )
    return [lower, upper]

def seasonal_figure(df_desc: pd.DataFrame, title: str):
    df_desc = df_desc.dropna(subset=["ASSESSDATE", "VALUE"]).copy()
    if df_desc.empty:
        return go.Figure()

    df_desc["ASSESSDATE"] = pd.to_datetime(df_desc["ASSESSDATE"])
    df_desc = df_desc[df_desc["ASSESSDATE"] >= START_DATE]
    if df_desc.empty:
        return go.Figure()

    df_desc["YEAR"] = df_desc["ASSESSDATE"].dt.year
    df_desc["DUMMY_DATE"] = normalize_to_dummy_year(df_desc["ASSESSDATE"])

    band_traces = _band_2020_2024(df_desc)

    traces = []
    for yr, g in df_desc.sort_values("DUMMY_DATE").groupby("YEAR"):
        color = COLOR_MAP.get(yr, "#bbbbbb")
        width = BOLD_YEARS.get(yr, THIN_WIDTH)
        opacity = 1.0 if yr in BOLD_YEARS else THIN_OPACITY
        traces.append(go.Scatter(
            x=g["DUMMY_DATE"],
            y=g["VALUE"],
            mode="lines",
            name=str(yr),
            line=dict(color=color, width=width),
            opacity=opacity
        ))

    unit = combine_unit(df_desc)
    layout = go.Layout(
        title=title,
        xaxis=dict(title="Seasonal (Jan → Dec)", tickformat="%b"),
        yaxis=dict(title=f"Value ({unit})" if unit else "Value"),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=50, r=20, t=60, b=40),
    )

    data = []
    if band_traces:
        data.extend(band_traces)
    data.extend(traces)

    return go.Figure(data=data, layout=layout)

def _filter_category(df: pd.DataFrame, category: str) -> pd.DataFrame:
    has_symbol = "SYMBOL" in df.columns
    if has_symbol:
        pool = BUTANE_SYMBOLS if category == "Butane" else PROPANE_SYMBOLS
        out = df[df["SYMBOL"].astype(str).isin(pool)].copy()
    else:
        temp = df.copy()
        temp["DESCRIPTION_UP"] = temp["DESCRIPTION"].astype(str).str.upper()
        mask = temp["DESCRIPTION_UP"].str.contains("BUTANE", na=False) if category=="Butane" \
               else temp["DESCRIPTION_UP"].str.contains("PROPANE", na=False)
        out = temp[mask].drop(columns=["DESCRIPTION_UP"])
    if "ASSESSDATE" in out.columns:
        out["ASSESSDATE"] = pd.to_datetime(out["ASSESSDATE"], errors="coerce")
        out = out[out["ASSESSDATE"] >= START_DATE]
    return out

def _chunk(iterable, size):
    it = iter(iterable)
    while True:
        batch = list(islice(it, size))
        if not batch:
            break
        yield batch

def _metrics_table_html(sub: pd.DataFrame) -> str:
    """
    Construit un mini tableau HTML de metrics (>=2020) dans le style demandé.
    Laisse '—' quand la donnée est insuffisante.
    """
    if sub.empty:
        return ""

    df = sub.copy()
    df["ASSESSDATE"] = pd.to_datetime(df["ASSESSDATE"], errors="coerce")
    df = df.dropna(subset=["ASSESSDATE", "VALUE"])
    df = df[df["ASSESSDATE"] >= START_DATE]
    if df.empty:
        return ""

    unit = combine_unit(df)
    unit_sfx = f" {unit}" if unit else ""

    # Série quotidienne continue (pour Δ1d/Δ7d/MoM robustes)
    s = (df.sort_values("ASSESSDATE")
            .set_index("ASSESSDATE")["VALUE"]
            .asfreq("D")
            .ffill())

    if s.dropna().empty:
        return ""
    last_date = s.last_valid_index()
    last_val  = s.loc[last_date]

    def get_shift(days):
        idx = last_date - pd.Timedelta(days=days)
        # aligné sur grille -> on a un point (ffill). Sinon renvoie NaN.
        try:
            return float(s.loc[idx])
        except KeyError:
            return np.nan

    prev1  = get_shift(1)
    prev7  = get_shift(7)
    prev30 = get_shift(30)

    d1  = last_val - prev1  if pd.notna(prev1)  else np.nan
    d7  = last_val - prev7  if pd.notna(prev7)  else np.nan
    mom = last_val - prev30 if pd.notna(prev30) else np.nan

    # YTD %
    start_y = pd.Timestamp(year=last_date.year, month=1, day=1)
    ytd_series = s.loc[start_y:last_date]
    first_ytd = ytd_series.dropna().iloc[0] if not ytd_series.dropna().empty else np.nan
    ytd_pct = ((last_val / first_ytd) - 1) * 100 if pd.notna(first_ytd) and first_ytd != 0 else np.nan

    # Moyenne du mois courant (sur toutes les années)
    month_name = last_date.strftime("%b")
    avg_month = df[df["ASSESSDATE"].dt.month == last_date.month]["VALUE"].mean()

    # Moyenne YTD (année courante)
    avg_ytd = df[df["ASSESSDATE"].dt.year == last_date.year]
    avg_ytd = avg_ytd[avg_ytd["ASSESSDATE"] <= last_date]["VALUE"].mean()

    # Fenêtre 52 semaines (percentile et z-score)
    win = s.loc[last_date - pd.Timedelta(days=364): last_date]
    if not win.dropna().empty:
        wmin, wmax = win.min(), win.max()
        denom = (wmax - wmin)
        pct52 = ((last_val - wmin) / denom * 100) if denom and denom != 0 else np.nan
        wmean, wstd = win.mean(), win.std(ddof=0)
        zscore = (last_val - wmean) / wstd if wstd and not np.isnan(wstd) else 0.0
    else:
        pct52, zscore = np.nan, np.nan

    def fmt_num(x):
        return "—" if pd.isna(x) else f"{x:,.2f}"

    def fmt_delta(x, as_pct=False):
        if pd.isna(x): return "—", ""
        if as_pct:
            text = f"{x:+.2f}%"
        else:
            text = f"{x:+.2f}"
        color_bg = "#eaf7e9" if x > 0 else ("#fdeaea" if x < 0 else "")
        color_tx = "#2e7d32" if x > 0 else ("#c62828" if x < 0 else "")
        style = f"background:{color_bg};color:{color_tx};" if color_bg else ""
        return text, style

    last_txt = fmt_num(last_val) + unit_sfx
    d1_txt,  d1_style  = fmt_delta(d1)
    d7_txt,  d7_style  = fmt_delta(d7)
    mom_txt, mom_style = fmt_delta(mom)
    ytd_txt, ytd_style = fmt_delta(ytd_pct, as_pct=True)
    avgm_txt = fmt_num(avg_month) + unit_sfx
    avgy_txt = fmt_num(avg_ytd)   + unit_sfx
    pct52_txt = "—" if pd.isna(pct52) else f"{pct52:.1f}%"
    z_txt = "—" if pd.isna(zscore) else f"{zscore:+.2f}"

    rows = [
        ("Last",          last_txt,  ""),
        ("Δ1d",           d1_txt,    d1_style),
        ("Δ7d",           d7_txt,    d7_style),
        ("MoM",           mom_txt,   mom_style),
        ("YTD %",         ytd_txt,   ytd_style),
        (f"Avg {month_name}", avgm_txt, ""),
        ("Avg YTD",       avgy_txt,  ""),
        ("Pct 52w",       pct52_txt, ""),
        ("Z-score",       z_txt,     ""),
    ]

    # Petit tableau HTML (2 colonnes) avec styles inline
    html = [
        "<table style='width:100%;border-collapse:collapse;font-size:12px;'>",
        "<thead><tr>",
        "<th style='text-align:left;border-bottom:1px solid #ddd;padding:4px;'>Metric</th>",
        "<th style='text-align:right;border-bottom:1px solid #ddd;padding:4px;'>Value</th>",
        "</tr></thead><tbody>"
    ]
    for metric, val, style in rows:
        html.append(
            f"<tr>"
            f"<td style='padding:4px;border-bottom:1px solid #f0f0f0;'>{metric}</td>"
            f"<td style='padding:4px;border-bottom:1px solid #f0f0f0;text-align:right;{style}'>{val}</td>"
            f"</tr>"
        )
    html.append("</tbody></table>")
    return "\n".join(html)



def _section(df: pd.DataFrame, title: str):
    # Titre stylisé plus grand
    st.markdown(
        f"<h2 style='font-size:28px; font-weight:700; margin-top:30px; margin-bottom:10px;'>{title}</h2>",
        unsafe_allow_html=True
    )
    if df.empty:
        st.info("Aucune donnée à afficher.")
        return

    all_desc = [str(x) for x in sorted(df["DESCRIPTION"].dropna().unique())]

    # 3 graphes par ligne
    for row_desc in _chunk(all_desc, 3):
        cols = st.columns(len(row_desc))
        for col, desc in zip(cols, row_desc):
            with col:
                sub = df[df["DESCRIPTION"].astype(str) == desc]

                # Graphique
                fig = seasonal_figure(sub, title=desc)
                st.plotly_chart(fig, use_container_width=True)

                # Tableau de metrics
                html = _metrics_table_html(sub)
                if html:
                    st.markdown(html, unsafe_allow_html=True)



def render():
    st.header("Prices – Seasonal Charts")

    # Chargement auto
    df = None
    if DEFAULT_XLSX.exists():
        try:
            df = load_excel(DEFAULT_XLSX)
            st.caption(f"Loaded: `{DEFAULT_XLSX}`")
        except Exception as e:
            st.error(f"Erreur de lecture `{DEFAULT_XLSX}` : {e}")

    if df is None:
        uploaded = st.file_uploader("Upload the Excel file (XLSX)", type=["xlsx"])
        if uploaded is None:
            st.info("Aucun fichier trouvé. Uploade ton Excel pour continuer.")
            return
        df = load_excel(uploaded)
        st.caption("Loaded uploaded file.")

    # Nettoyage : spike Propane Cracker Margin (PCMDM00 > 2000)
    if "SYMBOL" in df.columns and "VALUE" in df.columns:
        df = df[~((df["SYMBOL"] == "PCMDM00") & (df["VALUE"] > 2000))]

    required = ["DESCRIPTION","ASSESSDATE","VALUE"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        st.error(f"Colonnes manquantes : {', '.join(missing)}. Colonnes trouvées : {', '.join(df.columns)}")
        return

    # Sections : Butane puis Propane
    df_but = _filter_category(df, "Butane")
    df_pro = _filter_category(df, "Propane")

    _section(df_but, "Butane prices")
    st.markdown("---")
    _section(df_pro, "Propane prices")

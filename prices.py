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
    'AAUXJ00','AAWWK00','PHAJD00','AEFOB00','AAOTM00','AAOTN00','PHAJC00',
    'PMABA00',  # NEW: Propane NWE flat price
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

    # --- Title & legend layout to avoid overlap ---
    layout = go.Layout(
        title=dict(
            text=title,
            x=0.0, xanchor="left",
            y=0.98, yanchor="top",
            font=dict(size=16, color="#111", family="Arial, sans-serif")
        ),
        xaxis=dict(title="Seasonal (Jan → Dec)", tickformat="%b"),
        yaxis=dict(title=f"Value ({unit})" if unit else "Value"),
        hovermode="x unified",

        # Legend BELOW the plot; give extra bottom margin so it never collides
        legend=dict(
            orientation="h",
            x=0.0, xanchor="left",
            y=-0.20, yanchor="top",
            bgcolor="rgba(255,255,255,0.7)",
            bordercolor="rgba(0,0,0,0.05)",
            borderwidth=1,
            font=dict(size=10)
        ),

        # More headroom for the title and space at the bottom for the legend
        margin=dict(l=50, r=20, t=50, b=70),
    )

    data = []
    if band_traces:
        data.extend(band_traces)
    data.extend(traces)

    fig = go.Figure(data=data, layout=layout)
    # Keep legend entries tidy (years first, range last)
    fig.update_layout(legend_traceorder="normal")
    return fig

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


# ---------- utilitaire spread sym1 - sym2 ----------
def _compute_spread(df: pd.DataFrame, desc: str, sym_long: str, sym_short: str) -> pd.DataFrame:
    """
    Calcule un spread (sym_long - sym_short) sur la base de la colonne SYMBOL.
    Retourne un DataFrame avec DESCRIPTION / ASSESSDATE / VALUE (+ MOM/CURRENCY si dispo).
    """
    needed = {"SYMBOL", "ASSESSDATE", "VALUE"}
    if not needed.issubset(df.columns):
        return pd.DataFrame(columns=["DESCRIPTION", "ASSESSDATE", "VALUE"])

    d1 = df[df["SYMBOL"] == sym_long].copy()
    d2 = df[df["SYMBOL"] == sym_short].copy()
    if d1.empty or d2.empty:
        return pd.DataFrame(columns=["DESCRIPTION", "ASSESSDATE", "VALUE"])

    d1["ASSESSDATE"] = pd.to_datetime(d1["ASSESSDATE"], errors="coerce")
    d2["ASSESSDATE"] = pd.to_datetime(d2["ASSESSDATE"], errors="coerce")

    cols1 = ["ASSESSDATE", "VALUE"]
    for c in ("MOM", "CURRENCY"):
        if c in d1.columns:
            cols1.append(c)

    m = pd.merge(
        d1[cols1],
        d2[["ASSESSDATE", "VALUE"]],
        on="ASSESSDATE",
        how="inner",
        suffixes=("1", "2")
    ).dropna(subset=["VALUE1", "VALUE2"])

    if m.empty:
        return pd.DataFrame(columns=["DESCRIPTION", "ASSESSDATE", "VALUE"])

    m["VALUE"] = m["VALUE1"] - m["VALUE2"]
    m["DESCRIPTION"] = desc

    cols_out = ["DESCRIPTION", "ASSESSDATE", "VALUE"]
    for c in ("MOM", "CURRENCY"):
        if c in m.columns:
            cols_out.append(c)

    out = m[cols_out].copy()
    return out


# ---------- NEW : utilitaire pour les cracks ----------
def _compute_crack(df: pd.DataFrame, desc: str, sym_flat: str, factor: float) -> pd.DataFrame:
    """
    Calcule un crack en $/bbl :

        crack = (flat_mt / factor) - brent_bbl

    - flat_mt   : prix du produit (sym_flat) en $/mt
    - factor    : 10.6 (butane) ou 12.8 (propane)
    - brent_bbl : ICLL001 en $/bbl
    """

    needed = {"SYMBOL", "ASSESSDATE", "VALUE"}
    if not needed.issubset(df.columns):
        return pd.DataFrame(columns=["DESCRIPTION", "ASSESSDATE", "VALUE"])

    # --- jambe produit (flat en $/mt) ---
    d_flat = df[df["SYMBOL"] == sym_flat].copy()

    # --- Brent (ICLL001, $/bbl) ---
    d_brent = df[df["SYMBOL"] == "ICLL001"].copy()

    if d_flat.empty or d_brent.empty:
        return pd.DataFrame(columns=["DESCRIPTION", "ASSESSDATE", "VALUE"])

    # Nettoyage des dates
    d_flat["ASSESSDATE"] = pd.to_datetime(d_flat["ASSESSDATE"], errors="coerce")
    d_brent["ASSESSDATE"] = pd.to_datetime(d_brent["ASSESSDATE"], errors="coerce")

    d_flat = d_flat.dropna(subset=["ASSESSDATE", "VALUE"])
    d_brent = d_brent.dropna(subset=["ASSESSDATE", "VALUE"])

    # On garde juste ce qu'il faut et on renomme clairement
    d_flat = d_flat[["ASSESSDATE", "VALUE"]].rename(columns={"VALUE": "FLAT_MT"})
    d_brent = d_brent[["ASSESSDATE", "VALUE"]].rename(columns={"VALUE": "BRENT_BBL"})

    # Merge sur la date
    m = pd.merge(d_flat, d_brent, on="ASSESSDATE", how="inner").dropna()
    if m.empty:
        return pd.DataFrame(columns=["DESCRIPTION", "ASSESSDATE", "VALUE"])

    # Conversion du flat en $/bbl
    m["FLAT_BBL"] = m["FLAT_MT"] / factor

    # Crack en $/bbl
    m["VALUE"] = m["FLAT_BBL"] - m["BRENT_BBL"]
    m["DESCRIPTION"] = desc

    # On fixe explicitement l'unité en $/bbl pour les cracks
    m["MOM"] = "USD/bbl"
    m["CURRENCY"] = "USD"

    return m[["DESCRIPTION", "ASSESSDATE", "VALUE", "MOM", "CURRENCY"]].copy()




def _section(df: pd.DataFrame, title: str, priority_desc=None):
    # Titre stylisé plus grand
    st.markdown(
        f"<h2 style='font-size:28px; font-weight:700; margin-top:30px; margin-bottom:10px;'>{title}</h2>",
        unsafe_allow_html=True
    )
    if df.empty:
        st.info("Aucune donnée à afficher.")
        return

    # Liste de toutes les descriptions
    all_desc = [str(x) for x in sorted(df["DESCRIPTION"].dropna().unique())]

    # Réordonner pour mettre certaines descriptions en tête (spreads, cracks, etc.)
    if priority_desc:
        prio = [d for d in priority_desc if d in all_desc]
        rest = [d for d in all_desc if d not in prio]
        all_desc = prio + rest

    # 3 graphes par ligne, mais on garde toujours 3 colonnes
    for row_desc in _chunk(all_desc, 3):
        cols = st.columns(3)  # Toujours 3 colonnes pour garder la même largeur
        for i, desc in enumerate(row_desc):
            col = cols[i]
            with col:
                sub = df[df["DESCRIPTION"].astype(str) == desc]

                # Graphique
                fig = seasonal_figure(sub, title=desc)
                st.plotly_chart(fig, use_container_width=True)

                # Tableau de metrics
                html = _metrics_table_html(sub)
                if html:
                    st.markdown(html, unsafe_allow_html=True)
        # colonnes restantes (si 1 ou 2 graphes) => vides, donc même largeur


def render():
    st.header("Prices – Seasonal Charts")

    # --- Chargement auto du fichier Excel ---
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

    # --- Nettoyage : spike Propane Cracker Margin (PCMDM00 > 2000) ---
    if "SYMBOL" in df.columns and "VALUE" in df.columns:
        df = df[~((df["SYMBOL"] == "PCMDM00") & (df["VALUE"] > 2000))]

    # --- Vérification colonnes minimales ---
    required = ["DESCRIPTION", "ASSESSDATE", "VALUE"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        st.error(
            f"Colonnes manquantes : {', '.join(missing)}. "
            f"Colonnes trouvées : {', '.join(df.columns)}"
        )
        return

    # --- Séparation Propane / Butane (sections de base) ---
    df_but = _filter_category(df, "Butane")
    df_pro = _filter_category(df, "Propane")

    # ---------------------------------------------------------
    # Spreads M1/M2
    # ---------------------------------------------------------
    # Butane spreads
    but_spreads = [
        ("Butane Entreprise Mt Belvieu M1/M2", "PMAAI00", "AAWUF00"),
    ]
    for desc, s1, s2 in but_spreads:
        sp = _compute_spread(df, desc, s1, s2)
        if not sp.empty:
            df_but = pd.concat([df_but, sp], ignore_index=True)

    # Propane spreads
    pro_spreads = [
        ("Propane CIF NWE Large Cargo M1/M2", "AAHIK00", "AAHIM00"),
        ("Propane FOB Saudi Arabia CP M1/M2", "AAHHG00", "AAHHH00"),
        ("Propane Mt Belvieu M1/M2", "PMAAY00", "AAWUD00"),
        ("Propane CFR North Asia M1/M2", "AZWUA01", "AZWUA02"),
        ("Propane USGC M1/M2", "AAHYX00", "AAHYY00"),
    ]
    for desc, s1, s2 in pro_spreads:
        sp = _compute_spread(df, desc, s1, s2)
        if not sp.empty:
            df_pro = pd.concat([df_pro, sp], ignore_index=True)

    # ---------------------------------------------------------
    # Cracks (nouvelle définition)
    # crack = (flat / factor) - flat
    # Butane factor = 10.6 ; Propane factor = 12.8
    # ---------------------------------------------------------
    but_cracks = [
        ("Butane NWE cracks", "PMAAK00", 10.6),
    ]
    for desc, sym_flat, factor in but_cracks:
        cr = _compute_crack(df, desc, sym_flat, factor)
        if not cr.empty:
            df_but = pd.concat([df_but, cr], ignore_index=True)

    pro_cracks = [
        ("Propane NWE cracks", "PMABA00", 12.8),
    ]
    for desc, sym_flat, factor in pro_cracks:
        cr = _compute_crack(df, desc, sym_flat, factor)
        if not cr.empty:
            df_pro = pd.concat([df_pro, cr], ignore_index=True)

    # ---------------------------------------------------------
    # Priorité d’affichage : spreads puis cracks en haut
    # ---------------------------------------------------------
    priority_but = [d for d, _, _ in but_spreads] + [d for d, _, _ in but_cracks]
    priority_pro = [d for d, _, _ in pro_spreads] + [d for d, _, _ in pro_cracks]

    # Propane en premier, puis Butane
    _section(df_pro, "Propane prices", priority_desc=priority_pro)
    st.markdown("---")
    _section(df_but, "Butane prices", priority_desc=priority_but)

    # ---------------------------------------------------------
    # Sous-partie "Diffs"
    # ---------------------------------------------------------
    diff_specs = [
        ("Butane FOB ARA - Butane FOB NWE Large Cargo", "PMAAC00", "APRPF00"),
    ]
    diff_dfs = []
    for desc, s1, s2 in diff_specs:
        sp = _compute_spread(df, desc, s1, s2)
        if not sp.empty:
            diff_dfs.append(sp)

    if diff_dfs:
        df_diffs = pd.concat(diff_dfs, ignore_index=True)
        st.markdown("---")
        _section(df_diffs, "Diffs")

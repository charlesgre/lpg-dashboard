# tab_imports_exports_stocks.py
# Onglet Streamlit : Imports / Exports / Consumption / Production / Stocks – par pays

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go


# -------------------------------------------------------------------
# Config
# -------------------------------------------------------------------
FILENAME = "Imports-exports-stocks.xlsx"  # place le fichier à côté de app.py ou dans ./Imports-exports-stocks/
MONTH_ORDER = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Styles d'années demandés
SPECIAL_YEAR_COLOR = {
    2025: "black",
    2026: "black",
    2024: "red",
    2023: "green",
}
SPECIAL_YEAR_DASH = {
    2025: "solid",
    2026: "dash",   # pointillé
    2024: "solid",
    2023: "solid",
}
SPECIAL_YEAR_WIDTH = {
    2025: 2.8,
    2026: 2.8,
    2024: 2.8,
    2023: 2.8,
}
FADED_OPACITY = 0.35
DEFAULT_WIDTH = 1.6

RANGE_YEARS = [2021, 2022, 2023, 2024]  # bande min–max
RANGE_FILL = "rgba(180,180,180,0.25)"   # gris clair


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def _excel_path(app_dir: Path) -> Path:
    """Tente la racine du projet puis le sous-dossier 'Imports-exports-stocks'."""
    root = app_dir / FILENAME
    sub = app_dir / "Imports-exports-stocks" / FILENAME
    return root if root.exists() else sub


def _load_sheet(path: Path, sheet: str) -> pd.DataFrame:
    """Charge une feuille et ajoute les colonnes temporelles nécessaires."""
    df = pd.read_excel(path, sheet_name=sheet, header=2)
    if df.columns[0] != "Date":
        df = df.rename(columns={df.columns[0]: "Date"})
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).reset_index(drop=True)
    df["Year"] = df["Date"].dt.year.astype(int)
    df["Month"] = df["Date"].dt.month.astype(int)
    df["MonthName"] = pd.Categorical(
        df["Date"].dt.strftime("%b"), categories=MONTH_ORDER, ordered=True
    )
    return df


def _melt(df: pd.DataFrame) -> pd.DataFrame:
    """Passe en format long pour tracer facilement série × année."""
    value_cols = [c for c in df.columns if c not in ["Date", "Year", "Month", "MonthName"]]
    long_df = df.melt(
        id_vars=["Year", "Month", "MonthName"],
        value_vars=value_cols,
        var_name="Series",
        value_name="Value",
    )
    return long_df.dropna(subset=["Value"])


def _order_series(names: Iterable[str]) -> List[str]:
    """Ordre logique des séries."""
    key_words = [
        "inventory", "inventor", "stock",
        "imports", "exports",
        "consumption", "domestic sales", "sales",
        "production", "refinery", "blending",
    ]

    def key(s: str):
        s_low = s.lower()
        for i, kw in enumerate(key_words):
            if kw in s_low:
                return (i, s)
        return (len(key_words), s)

    return sorted(names, key=key)


def _add_range_band(fig: go.Figure, d: pd.DataFrame) -> None:
    """Ajoute la bande min–max pour RANGE_YEARS."""
    band = (
        d[d["Year"].isin(RANGE_YEARS)]
        .groupby("MonthName", observed=True)["Value"]
        .agg(["min", "max"])
        .reindex(MONTH_ORDER)
        .reset_index()
        .dropna()
    )
    if band.empty:
        return

    # Max (trace 1) – juste pour ancrer le tonexty
    fig.add_trace(
        go.Scatter(
            x=band["MonthName"],
            y=band["max"],
            line=dict(width=0),
            hoverinfo="skip",
            showlegend=True,
            name="Range 2021–2024",
        )
    )
    # Min (trace 2) – remplissage vers la précédente -> ruban
    fig.add_trace(
        go.Scatter(
            x=band["MonthName"],
            y=band["min"],
            line=dict(width=0),
            fill="tonexty",
            fillcolor=RANGE_FILL,
            hoverinfo="skip",
            showlegend=False,
            name="_range_min",
        )
    )


def _seasonal_fig(dlong: pd.DataFrame, series_name: str) -> go.Figure | None:
    """Construit le graphique saisonnier avec styles spécifiques + bande."""
    d = dlong[dlong["Series"] == series_name].sort_values(["Year", "Month"])
    if d.empty:
        return None

    # Figure de base
    fig = go.Figure()
    _add_range_band(fig, d)

    # Palette par défaut (servira pour les années "estompées")
    palette = px.colors.qualitative.Plotly + px.colors.qualitative.Safe + px.colors.qualitative.Pastel
    color_iter = iter(palette)

    # Tracer une courbe par année
    for yr, chunk in d.groupby("Year", sort=True):
        chunk = chunk.sort_values("Month")
        # style spécifique ou atténué
        if yr in SPECIAL_YEAR_COLOR:
            color = SPECIAL_YEAR_COLOR[yr]
            dash = SPECIAL_YEAR_DASH.get(yr, "solid")
            width = SPECIAL_YEAR_WIDTH.get(yr, 2.2)
            opacity = 1.0
        else:
            color = next(color_iter, "gray")
            dash = "solid"
            width = DEFAULT_WIDTH
            opacity = FADED_OPACITY

        fig.add_trace(
            go.Scatter(
                x=chunk["MonthName"],
                y=chunk["Value"],
                mode="lines+markers",
                name=str(yr),
                line=dict(color=color, width=width, dash=dash),
                opacity=opacity,
                marker=dict(size=6),
            )
        )

    fig.update_layout(
        title=series_name,
        margin=dict(l=10, r=10, t=40, b=10),
        legend_title_text="Année",
        xaxis_title="Mois",
        yaxis_title=None,
        hovermode="x unified",
    )
    return fig


# -------------------------------------------------------------------
# Render de l’onglet Streamlit
# -------------------------------------------------------------------
def render_trade_tab(tabs, app_dir: Path, tab_index: int = 3) -> None:
    """Rendu de l’onglet “Imports-Exports-Stocks” dans l’interface Streamlit."""
    with tabs[tab_index]:
        st.subheader("Imports • Exports • Consumption • Production • Stocks")

        xls_path = _excel_path(app_dir)
        if not xls_path.exists():
            st.error(f"Fichier Excel introuvable : {xls_path}")
            return

        sheets = pd.ExcelFile(xls_path).sheet_names
        region = st.selectbox("Région", sheets, index=0)

        df = _load_sheet(xls_path, region)
        dlong = _melt(df)
        all_series = _order_series(dlong["Series"].drop_duplicates().tolist())

        # Grille 2 colonnes (mets 3 si tu veux plus compact)
        cols_per_row = 2
        rows = (len(all_series) + cols_per_row - 1) // cols_per_row

        i = 0
        for _ in range(rows):
            cols = st.columns(cols_per_row)
            for c in cols:
                if i >= len(all_series):
                    break
                sname = all_series[i]
                fig = _seasonal_fig(dlong, sname)
                if fig is not None:
                    with c:
                        st.plotly_chart(fig, use_container_width=True)
                i += 1

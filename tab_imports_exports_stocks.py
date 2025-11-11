# tab_imports_exports_stocks.py
# Onglet Streamlit : Imports / Exports / Consumption / Production / Stocks – par pays

from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.express as px

# Ton fichier est dans le dossier "Imports-exports-stocks/Imports-exports-stocks.xlsx"
FILENAME = "Imports-exports-stocks.xlsx"

MONTH_ORDER = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

def _excel_path(app_dir: Path) -> Path:
    # essaie à la racine puis dans le sous-dossier
    root = app_dir / FILENAME
    sub = app_dir / "Imports-exports-stocks" / FILENAME
    return root if root.exists() else sub

def _load_sheet(path: Path, sheet: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet, header=2)
    # Col A = dates (souvent "Unnamed: 0")
    if df.columns[0] != "Date":
        df = df.rename(columns={df.columns[0]: "Date"})
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).reset_index(drop=True)
    df["Year"] = df["Date"].dt.year.astype(int)
    df["Month"] = df["Date"].dt.month.astype(int)
    df["MonthName"] = pd.Categorical(df["Date"].dt.strftime("%b"),
                                     categories=MONTH_ORDER, ordered=True)
    return df

def _melt(df: pd.DataFrame) -> pd.DataFrame:
    value_cols = [c for c in df.columns if c not in ["Date","Year","Month","MonthName"]]
    long_df = df.melt(id_vars=["Year","Month","MonthName"],
                      value_vars=value_cols, var_name="Series", value_name="Value")
    return long_df.dropna(subset=["Value"])

def _seasonal_fig(dlong: pd.DataFrame, series_name: str):
    d = dlong[dlong["Series"] == series_name].sort_values(["Year","Month"])
    if d.empty: 
        return None
    fig = px.line(d, x="MonthName", y="Value", color="Year", markers=True, title=series_name)
    fig.update_layout(
        margin=dict(l=10, r=10, t=40, b=10),
        legend_title_text="Année",
        xaxis_title="Mois",
        yaxis_title=None,
        hovermode="x unified",
    )
    return fig

def _order_series(names):
    # ordre logique
    key_words = ["inventory", "inventor", "stock",
                 "imports", "exports",
                 "consumption", "domestic sales", "sales",
                 "production", "refinery", "blending"]
    def k(s):
        s_low = s.lower()
        for i, kw in enumerate(key_words):
            if kw in s_low:
                return (i, s)
        return (len(key_words), s)
    return sorted(names, key=k)

def render_trade_tab(tabs, app_dir: Path, tab_index: int = 3):
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

        # grille 2 colonnes (mets 3 si tu veux plus compact)
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

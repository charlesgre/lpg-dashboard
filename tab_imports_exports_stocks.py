# tab_imports_exports_stocks.py
# Onglet: Imports / Exports / Consumption / Production / Stocks (Butane & Propane) – par pays
#
# À brancher dans app.py :
# from tab_imports_exports_stocks import layout as tab_trade_layout, register_callbacks as register_trade_callbacks
# ...
# tabs = dcc.Tabs([...,
#                  dcc.Tab(label="Imports-Exports-Stocks", value="tab_trade", children=tab_trade_layout)])
# register_trade_callbacks(app)

from functools import lru_cache
import pandas as pd
import plotly.express as px
from dash import dcc, html, Input, Output, callback

# --- Chemin vers ton fichier Excel (mets à jour si besoin) ---
EXCEL_PATH = "Imports-exports-stocks.xlsx"  # s'il est à la racine de ton projet / même dossier que app.py

# --- Chargement + préparation des données ---
@lru_cache(maxsize=1)
def load_workbook():
    # Les titres sont en ligne 3 => header=2 ; colonne A contient les dates
    xls = pd.ExcelFile(EXCEL_PATH)
    sheets = {}
    for sh in xls.sheet_names:
        df = pd.read_excel(EXCEL_PATH, sheet_name=sh, header=2)
        # Nettoyage colonnes
        if df.columns[0] != "Date":
            df = df.rename(columns={df.columns[0]: "Date"})
        # Conversion date
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["Date"]).reset_index(drop=True)

        # Découpe saisonnière : Année / Mois (1-12) / Nom du mois
        df["Year"] = df["Date"].dt.year.astype(int)
        df["Month"] = df["Date"].dt.month.astype(int)
        df["MonthName"] = pd.Categorical(
            df["Date"].dt.strftime("%b"),
            categories=["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
            ordered=True
        )
        sheets[sh] = df
    return sheets

def list_regions():
    return list(load_workbook().keys())

def melt_for_seasonal(df: pd.DataFrame) -> pd.DataFrame:
    """Transforme la feuille en format long pour tracer chaque série en saisonnier."""
    value_cols = [c for c in df.columns if c not in ["Date", "Year", "Month", "MonthName"]]
    long_df = df.melt(
        id_vars=["Year", "Month", "MonthName"],
        value_vars=value_cols,
        var_name="Series",
        value_name="Value"
    )
    # on enlève les colonnes vides
    long_df = long_df.dropna(subset=["Value"])
    return long_df

def build_seasonal_figure(long_df: pd.DataFrame, series_name: str):
    dsub = long_df[long_df["Series"] == series_name].copy()
    if dsub.empty:
        return px.line(title=series_name)  # placeholder
    fig = px.line(
        dsub.sort_values(["Year", "Month"]),
        x="MonthName", y="Value", color="Year",
        markers=True,
        title=series_name
    )
    fig.update_layout(
        margin=dict(l=10, r=10, t=50, b=10),
        legend_title_text="Année",
        xaxis_title="Mois",
        yaxis_title=None,
        hovermode="x unified"
    )
    return fig

# --- Layout ---
layout = html.Div(
    [
        html.Div(
            [
                html.Div("Région :", className="text-sm", style={"marginRight": "8px"}),
                dcc.Dropdown(
                    id="trade_region_dd",
                    options=[{"label": r, "value": r} for r in list_regions()],
                    value=list_regions()[0],
                    clearable=False,
                    style={"minWidth": 260},
                ),
            ],
            style={"display": "flex", "alignItems": "center", "gap": "8px", "marginBottom": "12px"},
        ),
        html.Div(
            id="trade_graphs_container",
            # grille fluide : 1 col mobile, 2 cols medium, 3 cols large
            style={
                "display": "grid",
                "gridTemplateColumns": "repeat(auto-fill, minmax(360px, 1fr))",
                "gap": "16px",
            },
        ),
    ],
    style={"padding": "12px"},
)

# --- Callbacks ---
def register_callbacks(app):
    @app.callback(
        Output("trade_graphs_container", "children"),
        Input("trade_region_dd", "value"),
        prevent_initial_call=False,
    )
    def _update_graphs(region):
        wb = load_workbook()
        df = wb.get(region)
        if df is None or df.empty:
            return [html.Div("Aucune donnée pour cette région.")]
        long_df = melt_for_seasonal(df)

        # Ordre des séries : regrouper par mots-clés usuels si présents
        # (Imports, Exports, Consumption, Production, Inventory/Stocks)
        series_all = long_df["Series"].drop_duplicates().tolist()

        keyword_order = [
            "Inventory", "Inventories", "Stock", "Stocks",
            "Imports", "Exports", "Consumption", "domestic sales",
            "Production", "production", "blending", "refinery",
        ]
        def sort_key(s):
            s_lower = s.lower()
            for i, k in enumerate(keyword_order):
                if k.lower() in s_lower:
                    return (i, s)
            return (len(keyword_order), s)
        series_all = sorted(series_all, key=sort_key)

        graphs = []
        for s in series_all:
            fig = build_seasonal_figure(long_df, s)
            graphs.append(dcc.Graph(figure=fig, config={"displayModeBar": False}))
        return graphs

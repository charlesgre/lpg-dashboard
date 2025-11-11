# tab_balances.py
# -*- coding: utf-8 -*-
from pathlib import Path
import re
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# ----------------------------------------------------------------------
# Emplacement du fichier (mêmes fallbacks que tab_hdd)
DEFAULT_BAL_XLSX = Path("Balances") / "2025-11_Global_LPG_NGLs_balances(1).xlsx"
BAL_FILE_CANDIDATE = "2025-11_Global_LPG_NGLs_balances(1).xlsx"

SHEET_NAME = "US by PADD and global LPG balances"

# Régions à afficher (et l'ordre)
REGIONS = ["PADD 1", "PADD 2", "PADD 3", "PADD 4", "PADD 5", "Total US"]

# On ne lit que A:Q comme demandé
USECOLS = "A:Q"

# ----------------------------------------------------------------------
_qpat = re.compile(r"^Q([1-4])\s*'?(\d{2})$", re.I)

def _resolve_xlsx(APP_DIR: Path) -> Path | None:
    """
    Cherche le fichier comme pour tab_hdd:
    - APP_DIR / Balances / <fichier>
    - APP_DIR / <fichier>
    - /mnt/data / <fichier>
    - /mnt/data / Balances / <fichier>
    - sinon, 1er fichier qui matche '2025-11_Global_LPG_NGLs_balances*.xlsx'
    """
    candidates = [
        APP_DIR / DEFAULT_BAL_XLSX,
        APP_DIR / BAL_FILE_CANDIDATE,
        Path("/mnt/data") / BAL_FILE_CANDIDATE,
        Path("/mnt/data") / "Balances" / BAL_FILE_CANDIDATE,
    ]
    for p in candidates:
        if p.exists():
            return p

    # fallback: glob dans Balances/ ou racine
    for root in [APP_DIR / "Balances", Path("/mnt/data") / "Balances", APP_DIR]:
        if root.exists():
            g = list(root.glob("2025-11_Global_LPG_NGLs_balances*.xlsx"))
            if g:
                return g[0]
    return None

def _is_quarter_label(x) -> bool:
    if pd.isna(x):
        return False
    return bool(_qpat.match(str(x).strip()))

def _parse_quarter_label(x):
    """'Q1 23' ou \"Q1'23\" -> (year=2023, quarter=1)"""
    m = _qpat.match(str(x).strip())
    if not m:
        return None
    q = int(m.group(1))
    yy = int(m.group(2))
    year = 2000 + yy if yy <= 99 else yy
    return (year, q)

def _to_number(x):
    """
    Convertit formats Excel fréquents:
      - nombres entre parenthèses -> négatif  (ex '(169)' -> -169)
      - tirets, '—', '--' -> NaN
      - retire les virgules séparateurs de milliers
    """
    if pd.isna(x):
        return pd.NA
    s = str(x).strip()
    if s in ("", "-", "—", "–", "--"):
        return pd.NA
    m = re.match(r"^\(\s*([0-9.,]+)\s*\)$", s)
    if m:
        s = "-" + m.group(1)
    s = s.replace(",", "")
    try:
        return float(s)
    except Exception:
        return pd.NA

# ----------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _load_us_by_padd(xlsx_path: Path):
    """
    Retourne un DataFrame tidy:
    columns = [Region, Product, Metric, QuarterLabel, Year, Quarter, Value]
    Metrics ∈ {"Balance","Demand","Supply"}
    """
    df = pd.read_excel(
        xlsx_path, sheet_name=SHEET_NAME, header=None, usecols=USECOLS, engine="openpyxl"
    )

    # aide pour lire la colonne A
    def _cell_a(i):
        v = df.iat[i, 0]
        return str(v).strip() if not pd.isna(v) else ""

    # repère les lignes 'Region' (col A)
    region_rows = [i for i in range(len(df)) if _cell_a(i) in REGIONS]

    tidy = []
    for rstart in region_rows:
        region = _cell_a(rstart)

        # trouver la ligne d'entêtes (quarters) juste après l'entête de région
        header_row = None
        for j in range(rstart, min(rstart + 6, len(df))):
            row = df.iloc[j, 1:]  # B:Q
            n_q = sum(_is_quarter_label(x) for x in row)
            if n_q >= max(6, int(0.5 * len(row))):
                header_row = j
                break
        if header_row is None:
            continue

        # colonnes de quarters
        quarters = df.iloc[header_row, 1:].tolist()  # B..Q
        qcols = [c for c, q in enumerate(quarters, start=1) if _is_quarter_label(q)]
        qlabels = [df.iat[header_row, c] for c in qcols]
        qmeta = [_parse_quarter_label(x) for x in qlabels]

        # lire les lignes jusqu'au prochain bloc
        i = header_row + 1
        while i < len(df):
            a = _cell_a(i)

            # fin de bloc si nouvelle région
            if a in REGIONS and i != rstart:
                break

            # fin si une ligne 'Total ...' démarre un sous-total
            if a and a.strip().lower().startswith("total"):
                break

            # ligne produit: nom en A, valeurs B:Q
            if a not in ("", "Demand", "Supply"):
                product = a

                # Balance
                row_bal = [_to_number(df.iat[i, c]) for c in qcols]
                for (year, q), lbl, val in zip(qmeta, qlabels, row_bal):
                    tidy.append([region, product, "Balance", str(lbl), year, q, val])

                # Demand (si présence ligne suivante)
                if i + 1 < len(df) and _cell_a(i + 1).lower() == "demand":
                    row_dem = [_to_number(df.iat[i + 1, c]) for c in qcols]
                    for (year, q), lbl, val in zip(qmeta, qlabels, row_dem):
                        tidy.append([region, product, "Demand", str(lbl), year, q, val])
                    i += 1

                # Supply (si présence ligne suivante)
                if i + 1 < len(df) and _cell_a(i + 1).lower() == "supply":
                    row_sup = [_to_number(df.iat[i + 1, c]) for c in qcols]
                    for (year, q), lbl, val in zip(qmeta, qlabels, row_sup):
                        tidy.append([region, product, "Supply", str(lbl), year, q, val])
                    i += 1

            i += 1

    tidy_df = pd.DataFrame(
        tidy, columns=["Region", "Product", "Metric", "QuarterLabel", "Year", "Quarter", "Value"]
    )
    # nettoyage & tri
    tidy_df["Value"] = pd.to_numeric(tidy_df["Value"], errors="coerce")
    tidy_df = tidy_df.dropna(subset=["Value"]).reset_index(drop=True)
    tidy_df["SortKey"] = tidy_df["Year"] * 10 + tidy_df["Quarter"]
    tidy_df = tidy_df.sort_values(["Region", "Product", "Metric", "SortKey"]).reset_index(drop=True)
    return tidy_df

# ----------------------------------------------------------------------
def render_balances_tab(tabs, APP_DIR: Path, tab_index: int) -> None:
    with tabs[tab_index]:
        st.header("Balances — US by PADD")

        xlsx = _resolve_xlsx(APP_DIR)
        if not xlsx:
            st.error(
                "Fichier Excel introuvable. Place-le dans "
                "`./Balances/2025-11_Global_LPG_NGLs_balances(1).xlsx` "
                "ou dans `/mnt/data/`."
            )
            st.stop()

        st.caption(f"📄 Fichier utilisé : {xlsx}")

        try:
            df = _load_us_by_padd(xlsx)
        except Exception as e:
            st.error(f"Erreur de lecture: {e}")
            st.stop()

        if df.empty:
            st.warning("Aucune donnée parsée dans la feuille 'US by PADD and global LPG balances' (A:Q).")
            st.stop()

        # --- UI ---
        c1, c2, c3 = st.columns([1.1, 1.2, 1.2])
        with c1:
            region = st.selectbox("Région", REGIONS, index=0)
        products_in_region = sorted(df.loc[df["Region"] == region, "Product"].unique().tolist())
        with c2:
            product = st.selectbox("Produit", products_in_region, index=0)
        with c3:
            metrics = st.multiselect(
                "Séries",
                ["Balance", "Demand", "Supply"],
                default=["Balance", "Demand", "Supply"],
            )

        d = df[(df["Region"] == region) & (df["Product"] == product) & (df["Metric"].isin(metrics))].copy()
        if d.empty:
            st.info("Pas de données pour cette sélection.")
            st.stop()

        # Ordre des quarters (libellés d'origine triés chrono)
        d = d.sort_values("SortKey")
        x = (
            d.drop_duplicates("QuarterLabel")[["QuarterLabel", "SortKey"]]
            .sort_values("SortKey")["QuarterLabel"]
            .tolist()
        )

        # --- Graph saisonnel (quarters sur l’axe X) ---
        fig = go.Figure()
        for m in metrics:
            sub = d[d["Metric"] == m]
            y = []
            for ql in x:
                val = sub.loc[sub["QuarterLabel"] == ql, "Value"]
                y.append(val.iloc[0] if not val.empty else None)
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines+markers", name=m))

        fig.update_layout(
            title=f"{region} — {product}: Balance / Demand / Supply (kb/d)",
            xaxis_title="Quarter",
            yaxis_title="kb/d",
            legend=dict(orientation="h"),
            margin=dict(l=40, r=40, t=60, b=40),
            height=480,
        )
        st.plotly_chart(fig, use_container_width=True)

        # Tableau des valeurs affichées
        pivot = (
            d.pivot_table(index="QuarterLabel", columns="Metric", values="Value", aggfunc="first")
            .reindex(x)
        )
        st.dataframe(pivot, use_container_width=True)

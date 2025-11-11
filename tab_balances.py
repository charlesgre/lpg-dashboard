# tab_balances.py
# -*- coding: utf-8 -*-
from pathlib import Path
import re
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# ----------------------------------------------------------------------
# Excel file location (same fallback logic as tab_hdd)
DEFAULT_BAL_XLSX = Path("Balances") / "2025-11_Global_LPG_NGLs_balances(1).xlsx"
BAL_FILE_CANDIDATE = "2025-11_Global_LPG_NGLs_balances(1).xlsx"

# ✅ Exact sheet name
SHEET_NAME = "US by PADD"

# Regions (and order)
REGIONS = ["PADD 1", "PADD 2", "PADD 3", "PADD 4", "PADD 5", "Total US"]

# Read only columns A:Q
USECOLS = "A:Q"

# ----------------------------------------------------------------------
_qpat = re.compile(r"^Q([1-4])\s*'?(\d{2})$", re.I)

def _resolve_xlsx(APP_DIR: Path) -> Path | None:
    """Locate the Excel file (same logic as tab_hdd)."""
    candidates = [
        APP_DIR / DEFAULT_BAL_XLSX,
        APP_DIR / BAL_FILE_CANDIDATE,
        Path("/mnt/data") / BAL_FILE_CANDIDATE,
        Path("/mnt/data") / "Balances" / BAL_FILE_CANDIDATE,
    ]
    for p in candidates:
        if p.exists():
            return p

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
    """'Q1 23' or "Q1'23" -> (year=2023, quarter=1)"""
    m = _qpat.match(str(x).strip())
    if not m:
        return None
    q = int(m.group(1))
    yy = int(m.group(2))
    year = 2000 + yy if yy <= 99 else yy
    return (year, q)

def _to_number(x):
    """
    Converts Excel-style number formats:
      - (169) → -169
      - dashes or blanks → NaN
      - removes thousand separators
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
    Returns a tidy DataFrame:
    columns = [Region, Product, Metric, QuarterLabel, Year, Quarter, Value]
    Metrics ∈ {"Balance", "Demand", "Supply"}
    """
    df = pd.read_excel(
        xlsx_path, sheet_name=SHEET_NAME, header=None, usecols=USECOLS, engine="openpyxl"
    )

    def _cell_a(i):
        v = df.iat[i, 0]
        return str(v).strip() if not pd.isna(v) else ""

    region_rows = [i for i in range(len(df)) if _cell_a(i) in REGIONS]

    tidy = []
    for rstart in region_rows:
        region = _cell_a(rstart)

        # Find the header row (quarter labels)
        header_row = None
        for j in range(rstart, min(rstart + 6, len(df))):
            row = df.iloc[j, 1:]  # B:Q
            n_q = sum(_is_quarter_label(x) for x in row)
            if n_q >= max(6, int(0.5 * len(row))):
                header_row = j
                break
        if header_row is None:
            continue

        quarters = df.iloc[header_row, 1:].tolist()  # B..Q
        qcols = [c for c, q in enumerate(quarters, start=1) if _is_quarter_label(q)]
        qlabels = [df.iat[header_row, c] for c in qcols]
        qmeta = [_parse_quarter_label(x) for x in qlabels]

        i = header_row + 1
        while i < len(df):
            a = _cell_a(i)
            if a in REGIONS and i != rstart:
                break
            if a and a.strip().lower().startswith("total"):
                break

            if a not in ("", "Demand", "Supply"):
                product = a

                # Balance
                row_bal = [_to_number(df.iat[i, c]) for c in qcols]
                for (year, q), lbl, val in zip(qmeta, qlabels, row_bal):
                    tidy.append([region, product, "Balance", str(lbl), year, q, val])

                # Demand
                if i + 1 < len(df) and _cell_a(i + 1).lower() == "demand":
                    row_dem = [_to_number(df.iat[i + 1, c]) for c in qcols]
                    for (year, q), lbl, val in zip(qmeta, qlabels, row_dem):
                        tidy.append([region, product, "Demand", str(lbl), year, q, val])
                    i += 1

                # Supply
                if i + 1 < len(df) and _cell_a(i + 1).lower() == "supply":
                    row_sup = [_to_number(df.iat[i + 1, c]) for c in qcols]
                    for (year, q), lbl, val in zip(qmeta, qlabels, row_sup):
                        tidy.append([region, product, "Supply", str(lbl), year, q, val])
                    i += 1

            i += 1

    tidy_df = pd.DataFrame(
        tidy, columns=["Region", "Product", "Metric", "QuarterLabel", "Year", "Quarter", "Value"]
    )
    tidy_df["Value"] = pd.to_numeric(tidy_df["Value"], errors="coerce")
    tidy_df = tidy_df.dropna(subset=["Value"]).reset_index(drop=True)
    tidy_df["SortKey"] = tidy_df["Year"] * 10 + tidy_df["Quarter"]
    tidy_df = tidy_df.sort_values(["Region", "Product", "Metric", "SortKey"]).reset_index(drop=True)
    return tidy_df

# ----------------------------------------------------------------------
def render_balances_tab(tabs, APP_DIR: Path, tab_index: int) -> None:
    with tabs[tab_index]:
        st.header("US LPG Balances — by PADD")

        xlsx = _resolve_xlsx(APP_DIR)
        if not xlsx:
            st.error(
                "Excel file not found. Please place it in "
                "`./Balances/2025-11_Global_LPG_NGLs_balances(1).xlsx` "
                "or in `/mnt/data/`."
            )
            st.stop()

        st.caption(f"📄 Loaded file: {xlsx}")

        try:
            df = _load_us_by_padd(xlsx)
        except Exception as e:
            st.error(f"Error reading Excel file: {e}")
            st.stop()

        if df.empty:
            st.warning("No data found in sheet 'US by PADD' (columns A:Q).")
            st.stop()

        # --- UI ---
        c1, c2, c3 = st.columns([1.1, 1.2, 1.0])
        with c1:
            region = st.selectbox("Region", REGIONS, index=0)
        products_in_region = sorted(df.loc[df["Region"] == region, "Product"].unique().tolist())
        with c2:
            product = st.selectbox("Product", products_in_region, index=0)
        with c3:
            metric = st.radio("Series", ["Balance", "Demand", "Supply"], index=0, horizontal=False)

        # Filter for single series
        d = df[(df["Region"] == region) & (df["Product"] == product) & (df["Metric"] == metric)].copy()
        if d.empty:
            st.info("No data for this selection.")
            st.stop()

        # Seasonal view: X = Q1..Q4, one line per year
        quarter_labels = ["Q1", "Q2", "Q3", "Q4"]
        pivot = (
            d.pivot_table(index="Year", columns="Quarter", values="Value", aggfunc="first")
             .sort_index()
        )

        fig = go.Figure()
        for year in pivot.index:
            yvals = [pivot.loc[year].get(q, None) for q in [1, 2, 3, 4]]
            fig.add_trace(go.Scatter(x=quarter_labels, y=yvals, mode="lines+markers", name=str(year)))

        fig.update_layout(
            title=f"{region} — {product} — {metric} (kb/d) • Seasonal by Quarter",
            xaxis_title="Quarter",
            yaxis_title="kb/d",
            legend=dict(orientation="h"),
            margin=dict(l=40, r=40, t=60, b=40),
            height=480,
        )
        st.plotly_chart(fig, use_container_width=True)

        # Table view: rows = quarters, columns = years
        table = (
            pivot.T.rename(index={1: "Q1", 2: "Q2", 3: "Q3", 4: "Q4"})
                  .reindex(quarter_labels)
        )
        st.dataframe(table, use_container_width=True)

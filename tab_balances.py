# tab_balances.py
# -*- coding: utf-8 -*-
from pathlib import Path
import re
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# ----------------------------------------------------------------------
# Excel file location (same fallback logic style as tab_hdd)
DEFAULT_BAL_XLSX = Path("Balances") / "2025-11_Global_LPG_NGLs_balances(1).xlsx"
BAL_FILE_CANDIDATE = "2025-11_Global_LPG_NGLs_balances(1).xlsx"

# ✅ Exact sheet names
SHEET_US_PADD = "US by PADD"
SHEET_GLOBAL  = "Global LPG balances"

# Regions for the PADD sheet (and order)
PADD_REGIONS = ["PADD 1", "PADD 2", "PADD 3", "PADD 4", "PADD 5", "Total US"]

# Read only columns A:Q
USECOLS = "A:Q"

# Custom colors by year
YEAR_COLORS = {
    2026: "blue",
    2025: "black",
    2024: "red",
    2023: "green",
}

# ----------------------------------------------------------------------
_qpat = re.compile(r"^Q([1-4])\s*'?(\d{2})$", re.I)

def _resolve_xlsx(APP_DIR: Path) -> Path | None:
    """Locate the Excel file (fallbacks similar to tab_hdd)."""
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
def _load_blocked_sheet(xlsx_path: Path, sheet_name: str):
    """Reads a balances sheet with the standard structure and returns the raw dataframe (no headers)."""
    df = pd.read_excel(
        xlsx_path, sheet_name=sheet_name, header=None, usecols=USECOLS, engine="openpyxl"
    )
    return df

def _tidy_from_structured_df(df: pd.DataFrame, region_list: list[str] | None = None):
    """
    Parse a sheet arranged by blocks:
      A = Region or row labels ('Demand', 'Supply', product names, 'Total ...')
      B:Q = Quarter columns (headers somewhere near the top of each region block)

    Returns tidy columns:
      [Region, Product, Metric, QuarterLabel, Year, Quarter, Value]
    """
    def _cell_a(i):
        v = df.iat[i, 0]
        return str(v).strip() if not pd.isna(v) else ""

    # If region list provided, use it; else infer from A col by finding likely region headers.
    if region_list:
        region_rows = [i for i in range(len(df)) if _cell_a(i) in region_list]
    else:
        # Heuristic: “region header” is a non-empty label followed (within a few rows) by a header row with quarter labels.
        candidate_idxs = [i for i in range(len(df)) if _cell_a(i) not in ("", "Demand", "Supply")]
        region_rows = []
        for i in candidate_idxs:
            # Search the next rows to see if a quarter header exists — then treat it as a region header
            header_row = None
            for j in range(i, min(i + 6, len(df))):
                row = df.iloc[j, 1:]
                n_q = sum(_is_quarter_label(x) for x in row)
                if n_q >= max(6, int(0.5 * len(row))):
                    header_row = j
                    break
            if header_row is not None:
                region_rows.append(i)

    tidy = []
    for rstart in region_rows:
        region = _cell_a(rstart)

        # find the quarter header row right after region
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

            # block ends when we hit a new region (only if region_list given) or a "Total ..." line or empty section
            if region_list and a in region_list and i != rstart:
                break
            # Even without region_list, if we detect another likely region start, stop
            if not region_list and a not in ("", "Demand", "Supply"):
                # Peek ahead: if a quarter header appears soon, treat as new region
                ahead_has_header = False
                for j in range(i, min(i + 6, len(df))):
                    rowj = df.iloc[j, 1:]
                    n_qj = sum(_is_quarter_label(x) for x in rowj)
                    if n_qj >= max(6, int(0.5 * len(rowj))):
                        ahead_has_header = True
                        break
                if ahead_has_header and i != rstart:
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

# Cached loaders for each sheet
@st.cache_data(show_spinner=False)
def _load_us_by_padd(xlsx_path: Path):
    df_raw = _load_blocked_sheet(xlsx_path, SHEET_US_PADD)
    return _tidy_from_structured_df(df_raw, region_list=PADD_REGIONS)

@st.cache_data(show_spinner=False)
def _load_global_balances(xlsx_path: Path):
    df_raw = _load_blocked_sheet(xlsx_path, SHEET_GLOBAL)
    # infer all regions; then we might overlap with "US" which we will keep
    tidy = _tidy_from_structured_df(df_raw, region_list=None)
    return tidy

# ----------------------------------------------------------------------
def _plot_seasonal_quarter(df_one_series: pd.DataFrame, title: str):
    """Seasonal plot: X = Q1..Q4, one line per year, with custom colors for 2026/25/24/23."""
    quarter_labels = ["Q1", "Q2", "Q3", "Q4"]
    pivot = (
        df_one_series.pivot_table(index="Year", columns="Quarter", values="Value", aggfunc="first")
        .sort_index()
    )

    fig = go.Figure()
    for year in pivot.index:
        yvals = [pivot.loc[year].get(q, None) for q in [1, 2, 3, 4]]
        color = YEAR_COLORS.get(year, None)
        fig.add_trace(
            go.Scatter(
                x=quarter_labels,
                y=yvals,
                mode="lines+markers",
                name=str(year),
                line=dict(color=color, width=2.5 if color else 1.8),
            )
        )

    fig.update_layout(
        title=title,
        xaxis_title="Quarter",
        yaxis_title="kb/d",
        legend=dict(orientation="h"),
        margin=dict(l=40, r=40, t=60, b=40),
        height=480,
    )
    return fig, pivot

# ----------------------------------------------------------------------
def render_balances_tab(tabs, APP_DIR: Path, tab_index: int) -> None:
    with tabs[tab_index]:
        st.header("LPG Balances — Global & US by PADD")

        xlsx = _resolve_xlsx(APP_DIR)
        if not xlsx:
            st.error(
                "Excel file not found. Please place it in "
                "`./Balances/2025-11_Global_LPG_NGLs_balances(1).xlsx` "
                "or in `/mnt/data/`."
            )
            st.stop()
        st.caption(f"📄 Loaded file: {xlsx}")

        # Load both datasets
        try:
            df_us = _load_us_by_padd(xlsx)       # PADD sheet
        except Exception as e:
            st.error(f"Error reading sheet '{SHEET_US_PADD}': {e}")
            st.stop()

        try:
            df_glob = _load_global_balances(xlsx)  # Global sheet
        except Exception as e:
            st.error(f"Error reading sheet '{SHEET_GLOBAL}': {e}")
            st.stop()

        if df_us.empty and df_glob.empty:
            st.warning("No data parsed in either sheet.")
            st.stop()

        # Build region lists:
        global_regions = sorted(df_glob["Region"].unique().tolist())
        # Make sure 'US' appears as a top-level region in the UI, even if not present in the global sheet
        regions_ui = list(global_regions)
        if "US" not in regions_ui:
            regions_ui.append("US")

        # --- UI ---
        c1, c2, c3, c4 = st.columns([1.2, 1.2, 1.0, 1.2])

        with c1:
            scope_region = st.selectbox("Region (Global balances + US)", regions_ui, index=regions_ui.index("US") if "US" in regions_ui else 0)

        # When selecting US, allow optional drill-down by PADD
        use_padd = False
        with c2:
            if scope_region == "US":
                use_padd = st.checkbox("Drill down by PADD", value=True)
            else:
                st.write("")  # spacing

        # Product and Series:
        if scope_region == "US" and use_padd:
            # Choose PADD
            with c3:
                sub_region = st.selectbox("PADD region", PADD_REGIONS, index=PADD_REGIONS.index("Total US"))
            # Products depend on selected sub-region in df_us
            products_in_region = sorted(df_us.loc[df_us["Region"] == sub_region, "Product"].unique().tolist())
        else:
            # Products from global dataset for the chosen region (or 'US' totals if present)
            products_in_region = sorted(df_glob.loc[df_glob["Region"] == scope_region, "Product"].unique().tolist())

        with c4:
            metric = st.radio("Series", ["Balance", "Demand", "Supply"], index=0, horizontal=False)

        # Product selection (separate column below to ensure options are computed)
        product = st.selectbox("Product", products_in_region, index=0, key="product_select_global_us")

        # --- Filtering data for plotting ---
        if scope_region == "US" and use_padd:
            dd = df_us[(df_us["Region"] == sub_region) & (df_us["Product"] == product) & (df_us["Metric"] == metric)].copy()
            title = f"{sub_region} — {product} — {metric} (kb/d) • Seasonal by Quarter"
        else:
            dd = df_glob[(df_glob["Region"] == scope_region) & (df_glob["Product"] == product) & (df_glob["Metric"] == metric)].copy()
            title = f"{scope_region} — {product} — {metric} (kb/d) • Seasonal by Quarter"

            # If user chose US but global sheet doesn't have US totals, offer a fallback by summing PADDs (Total US)
            if dd.empty and scope_region == "US" and not use_padd:
                total_us = (
                    df_us[df_us["Region"].isin(PADD_REGIONS)]
                    .groupby(["Product", "Metric", "Year", "Quarter"], as_index=False)["Value"].sum()
                )
                dd = total_us[(total_us["Product"] == product) & (total_us["Metric"] == metric)].copy()
                # Add synthetic labels required by plotting function
                dd["Region"] = "Total US"
                dd["QuarterLabel"] = dd["Quarter"].map({1: "Q1", 2: "Q2", 3: "Q3", 4: "Q4"})
                dd["SortKey"] = dd["Year"] * 10 + dd["Quarter"]
                title = f"Total US (from PADDs) — {product} — {metric} (kb/d) • Seasonal by Quarter"

        if dd.empty:
            st.info("No data for this selection.")
            st.stop()

        # Make sure it's chronologically ordered
        dd = dd.sort_values(["Year", "Quarter"])

        # Plot + pivot table
        fig, pivot = _plot_seasonal_quarter(dd, title)
        st.plotly_chart(fig, use_container_width=True)

        # Table view: rows = quarters, columns = years
        quarter_labels = ["Q1", "Q2", "Q3", "Q4"]
        table = (
            pivot.T.rename(index={1: "Q1", 2: "Q2", 3: "Q3", 4: "Q4"})
                  .reindex(quarter_labels)
        )
        st.dataframe(table, use_container_width=True)

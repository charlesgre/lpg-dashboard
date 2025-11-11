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

# ✅ Exact sheet names
SHEET_US_PADD = "US by PADD"
SHEET_GLOBAL  = "Global LPG balances"

# PADD regions (order)
PADD_REGIONS = ["PADD 1", "PADD 2", "PADD 3", "PADD 4", "PADD 5", "Total US"]

# Global regions wanted (display order)
GLOBAL_REGIONS_CANON = ["North America", "Europe", "FSU", "Middle East", "Asia Pacific", "China"]
# Accept these aliases in the sheet and normalize to the canonical names above
GLOBAL_REGION_ALIASES = {
    "North America": "North America",
    "Europe": "Europe",
    "FSU": "FSU",
    "Middle East": "Middle East",
    "Asia-Pacific": "Asia Pacific",
    "Asia Pacific": "Asia Pacific",
    "China": "China",
}

# Read only columns A:Q
USECOLS = "A:Q"

# Custom colors by year
YEAR_COLORS = {2026: "blue", 2025: "black", 2024: "red", 2023: "green"}

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
    return pd.read_excel(xlsx_path, sheet_name=sheet_name, header=None, usecols=USECOLS, engine="openpyxl")

def _tidy_from_structured_df(df: pd.DataFrame, region_list: list[str], *,
                             canonicalize=None, product_label: str | None = None):
    """
    Parse a balances sheet arranged by blocks:
      A: Region header row, then a header row with quarter labels (B:Q),
         then product line (or a single 'global' line), then Demand, Supply.
    Returns columns: [Region, Product, Metric, QuarterLabel, Year, Quarter, Value]
    """
    def _cell_a(i):
        v = df.iat[i, 0]
        return str(v).strip() if not pd.isna(v) else ""

    region_rows = [i for i in range(len(df)) if _cell_a(i) in region_list]

    tidy = []
    for rstart in region_rows:
        region_raw = _cell_a(rstart)
        region = canonicalize(region_raw) if canonicalize else region_raw

        # detect the header row (quarter labels) near region header
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

            # stop if we hit the next region header
            if a in region_list and i != rstart:
                break
            if a and a.strip().lower().startswith("total"):
                break

            # If a product label is provided (global sheet), we ignore the text in col A
            # and treat this line as the 'Balance' row if it isn't Demand/Supply/blank.
            if product_label is not None:
                if a not in ("", "Demand", "Supply"):
                    # Global balance line
                    row_bal = [_to_number(df.iat[i, c]) for c in qcols]
                    for (year, q), lbl, val in zip(qmeta, qlabels, row_bal):
                        tidy.append([region, product_label, "Balance", str(lbl), year, q, val])

                    if i + 1 < len(df) and _cell_a(i + 1).lower() == "demand":
                        row_dem = [_to_number(df.iat[i + 1, c]) for c in qcols]
                        for (year, q), lbl, val in zip(qmeta, qlabels, row_dem):
                            tidy.append([region, product_label, "Demand", str(lbl), year, q, val])
                        i += 1

                    if i + 1 < len(df) and _cell_a(i + 1).lower() == "supply":
                        row_sup = [_to_number(df.iat[i + 1, c]) for c in qcols]
                        for (year, q), lbl, val in zip(qmeta, qlabels, row_sup):
                            tidy.append([region, product_label, "Supply", str(lbl), year, q, val])
                        i += 1
            else:
                # PADD sheet parsing with product names
                if a not in ("", "Demand", "Supply"):
                    product = a
                    row_bal = [_to_number(df.iat[i, c]) for c in qcols]
                    for (year, q), lbl, val in zip(qmeta, qlabels, row_bal):
                        tidy.append([region, product, "Balance", str(lbl), year, q, val])

                    if i + 1 < len(df) and _cell_a(i + 1).lower() == "demand":
                        row_dem = [_to_number(df.iat[i + 1, c]) for c in qcols]
                        for (year, q), lbl, val in zip(qmeta, qlabels, row_dem):
                            tidy.append([region, product, "Demand", str(lbl), year, q, val])
                        i += 1

                    if i + 1 < len(df) and _cell_a(i + 1).lower() == "supply":
                        row_sup = [_to_number(df.iat[i + 1, c]) for c in qcols]
                        for (year, q), lbl, val in zip(qmeta, qlabels, row_sup):
                            tidy.append([region, product, "Supply", str(lbl), year, q, val])
                        i += 1

            i += 1

    tidy_df = pd.DataFrame(tidy, columns=["Region", "Product", "Metric", "QuarterLabel", "Year", "Quarter", "Value"])
    tidy_df["Value"] = pd.to_numeric(tidy_df["Value"], errors="coerce")
    tidy_df = tidy_df.dropna(subset=["Value"]).reset_index(drop=True)
    tidy_df["SortKey"] = tidy_df["Year"] * 10 + tidy_df["Quarter"]
    tidy_df = tidy_df.sort_values(["Region", "Product", "Metric", "SortKey"]).reset_index(drop=True)
    return tidy_df

# Cached loaders
@st.cache_data(show_spinner=False)
def _load_us_by_padd(xlsx_path: Path):
    df_raw = _load_blocked_sheet(xlsx_path, SHEET_US_PADD)
    return _tidy_from_structured_df(df_raw, region_list=PADD_REGIONS, product_label=None)

@st.cache_data(show_spinner=False)
def _load_global_balances(xlsx_path: Path):
    df_raw = _load_blocked_sheet(xlsx_path, SHEET_GLOBAL)
    # Accept both "Asia Pacific" and "Asia-Pacific" and normalize to "Asia Pacific"
    region_list = list(GLOBAL_REGION_ALIASES.keys())
    def _canon(name: str) -> str:
        return GLOBAL_REGION_ALIASES.get(name, name)
    # There is no product breakdown in this sheet -> single product label
    return _tidy_from_structured_df(df_raw, region_list=region_list, canonicalize=_canon, product_label="Global LPG")

# ----------------------------------------------------------------------
def _plot_seasonal_quarter(df_one_series: pd.DataFrame, title: str):
    """Seasonal plot: X = Q1..Q4, one line per year, with custom colors for 2026/25/24/23."""
    quarter_labels = ["Q1", "Q2", "Q3", "Q4"]
    pivot = df_one_series.pivot_table(index="Year", columns="Quarter", values="Value", aggfunc="first").sort_index()

    fig = go.Figure()
    for year in pivot.index:
        yvals = [pivot.loc[year].get(q, None) for q in [1, 2, 3, 4]]
        color = YEAR_COLORS.get(year, None)
        fig.add_trace(go.Scatter(x=quarter_labels, y=yvals, mode="lines+markers",
                                 name=str(year), line=dict(color=color, width=2.5 if color else 1.8)))
    fig.update_layout(title=title, xaxis_title="Quarter", yaxis_title="kb/d",
                      legend=dict(orientation="h"), margin=dict(l=40, r=40, t=60, b=40), height=480)
    return fig, pivot

# ----------------------------------------------------------------------
def render_balances_tab(tabs, APP_DIR: Path, tab_index: int) -> None:
    with tabs[tab_index]:
        st.header("LPG Balances — Global & US by PADD")

        xlsx = _resolve_xlsx(APP_DIR)
        if not xlsx:
            st.error("Excel file not found. Place it in ./Balances/2025-11_Global_LPG_NGLs_balances(1).xlsx or in /mnt/data/.")
            st.stop()
        st.caption(f"📄 Loaded file: {xlsx}")

        # Load data
        try:
            df_us = _load_us_by_padd(xlsx)
            df_glob = _load_global_balances(xlsx)
        except Exception as e:
            st.error(f"Error reading Excel: {e}")
            st.stop()

        # UI — region scope
        top_regions = ["US"] + GLOBAL_REGIONS_CANON
        c1, c2, c3, c4 = st.columns([1.2, 1.2, 1.0, 1.2])
        with c1:
            scope_region = st.selectbox("Region (Global balances + US)", top_regions, index=0)

        # Drilldown for US (PADD)
        use_padd = False
        with c2:
            if scope_region == "US":
                use_padd = st.checkbox("Drill down by PADD", value=True)
            else:
                st.write("")

        # Series selector
        with c4:
            metric = st.radio("Series", ["Balance", "Demand", "Supply"], index=0, horizontal=False)

        # Product selector logic:
        if scope_region == "US" and use_padd:
            with c3:
                sub_region = st.selectbox("PADD region", PADD_REGIONS, index=PADD_REGIONS.index("Total US"))
            products_in_region = sorted(df_us.loc[df_us["Region"] == sub_region, "Product"].unique().tolist())
            product = st.selectbox("Product", products_in_region, index=0, key="prod_us_padd")
            dd = df_us[(df_us["Region"] == sub_region) & (df_us["Product"] == product) & (df_us["Metric"] == metric)].copy()
            title = f"{sub_region} — {product} — {metric} (kb/d) • Seasonal by Quarter"
        elif scope_region == "US" and not use_padd:
            # Try global 'US' first (if ever present). If not, sum PADDs to Total US.
            dd = df_glob[(df_glob["Region"] == "US") & (df_glob["Product"] == "Global LPG") & (df_glob["Metric"] == metric)].copy()
            if dd.empty:
                total_us = (
                    df_us[df_us["Metric"] == metric]
                    .groupby(["Year", "Quarter"], as_index=False)["Value"].sum()
                    .assign(Region="Total US", Product="Global LPG")
                )
                # add labels needed by plot
                total_us["QuarterLabel"] = total_us["Quarter"].map({1: "Q1", 2: "Q2", 3: "Q3", 4: "Q4"})
                dd = total_us
                title = f"Total US (from PADDs) — {metric} (kb/d) • Seasonal by Quarter"
            else:
                title = f"US — Global LPG — {metric} (kb/d) • Seasonal by Quarter"
            st.selectbox("Product", ["Global LPG"], index=0, disabled=True, key="prod_us_total")
        else:
            # Global region (no product breakdown) → fixed 'Global LPG'
            st.selectbox("Product", ["Global LPG"], index=0, disabled=True, key="prod_global")
            dd = df_glob[(df_glob["Region"] == scope_region) & (df_glob["Product"] == "Global LPG") & (df_glob["Metric"] == metric)].copy()
            title = f"{scope_region} — Global LPG — {metric} (kb/d) • Seasonal by Quarter"

        if dd.empty:
            st.info("No data for this selection.")
            st.stop()

        dd = dd.sort_values(["Year", "Quarter"])
        fig, pivot = _plot_seasonal_quarter(dd, title)
        st.plotly_chart(fig, use_container_width=True)

        quarter_labels = ["Q1", "Q2", "Q3", "Q4"]
        table = pivot.T.rename(index={1: "Q1", 2: "Q2", 3: "Q3", 4: "Q4"}).reindex(quarter_labels)
        st.dataframe(table, use_container_width=True)

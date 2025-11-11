# tab_hdd.py
# -*- coding: utf-8 -*-
"""
TEMP & HDD tab – Regions (Europe / Asia / USA)

Excel structure:
- Historical sheet: "Historical temp & HDD"
  * Col A = Date
  * Col B..W = Temperatures (22 entities, headers on Excel row 3 like 'France temps')
  * Col X..AS = HDD (22 entities, headers on row 3 like 'France HDD')
- Forecast sheets: "<Country> forecast" (order may vary; may contain typos like 'forecats')
  * Col A = Date, Col B = Temperature (native units: USA=°F, Europe/Asia=°C)
"""

from pathlib import Path
import calendar
import hashlib
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import re

# ----------------------------------------------------------------------
# Settings
# ----------------------------------------------------------------------
DEFAULT_XLSX = Path("HDD") / "HDD Propane.xlsx"

EUROPE = [
    "France", "UK", "Netherlands", "Germany", "Poland",
    "Belgium", "Sweden", "Spain", "Finland", "Norway",
]
ASIA = ["Japan", "Korea"]
USA = [
    "North Dakota", "Minnesota", "Maine", "Vermont", "Wisconsin",
    "Montana", "New Hampshire", "Pennsylvania", "Michigan", "New York",
]
CANON_ORDER = EUROPE + ASIA + USA

# ----------------------------------------------------------------------
# Normalization helpers
# ----------------------------------------------------------------------
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).strip().lower())

def _clean_hist_header(h: str) -> str:
    """
    From 'France temps' / 'France HDD' -> 'France'
    From 'North Dakota temps' -> 'North Dakota'
    Also trims repeated spaces.
    """
    h = re.sub(r"\btemps\b", "", str(h), flags=re.I)
    h = re.sub(r"\bHDD\b",   "", h, flags=re.I)
    h = re.sub(r"\s+", " ", h).strip()
    return h

def _strip_forecast_tokens(s: str) -> str:
    """Remove any token starting with 'forec' (forecast/forecats/forecst...) then normalize."""
    s = re.sub(r"forec\w*", "", str(s), flags=re.I)
    return _norm(s)

def _c_to_f(s: pd.Series) -> pd.Series:
    """Convert Celsius to Fahrenheit."""
    return s * 9.0 / 5.0 + 32.0

# ----------------------------------------------------------------------
def render_tab(tabs, APP_DIR: Path, tab_index: int = 1) -> None:
    with tabs[tab_index]:
        st.header("Temperatures & HDD — by region and country/state")

        # ---------- Locate Excel ----------
        def _resolve() -> Path | None:
            for p in [APP_DIR / DEFAULT_XLSX, APP_DIR / "HDD Propane.xlsx", Path("/mnt/data") / "HDD Propane.xlsx"]:
                if p.exists():
                    return p
            return None

        xlsx = _resolve()
        if not xlsx:
            st.error("Excel file not found at ./HDD/HDD Propane.xlsx (or fallbacks).")
            st.stop()

        # ---------- Cache helpers ----------
        def _hash(p: Path) -> str:
            h = hashlib.sha256()
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            return h.hexdigest()

        @st.cache_data(show_spinner=False)
        def _load_hist(xlsx_path: Path, key: str):
            """
            Returns:
              df_hist: cleaned DataFrame
              temp_map: {DisplayName -> column}
              hdd_map : {DisplayName -> column}
              units   : {DisplayName -> "°C"/"°F"}
              entities_ordered: list of display names (intersection, ordered)
            """
            xls = pd.ExcelFile(xlsx_path)
            hist = None
            for s in xls.sheet_names:
                if s.strip().lower() == "historical temp & hdd":
                    hist = s; break
            if hist is None:
                raise RuntimeError("Sheet 'Historical temp & HDD' not found.")

            # Header row = Excel row 3
            df = pd.read_excel(xlsx_path, sheet_name=hist, header=2, engine="openpyxl").reset_index(drop=True)

            # Date column = first column
            date_col = df.columns[0]
            df = df.rename(columns={date_col: "Date"})
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce", dayfirst=True)

            cols = list(df.columns)
            if len(cols) < 45:
                raise RuntimeError("Historical sheet must have at least 45 columns (A + 22 temps + 22 HDD).")

            temp_cols = cols[1:23]   # B..W
            hdd_cols  = cols[23:45]  # X..AS

            # Build maps (display name -> actual col)
            temp_map, units_map = {}, {}
            for c in temp_cols:
                disp = _clean_hist_header(c)
                temp_map[disp] = c
                units_map[disp] = "°F" if disp in USA else "°C"

            hdd_map = {}
            for c in hdd_cols:
                disp = _clean_hist_header(c)
                hdd_map[disp] = c

            # Coerce numerics
            for c in temp_cols + hdd_cols:
                df[c] = pd.to_numeric(df[c], errors="coerce")
            df = df.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)

            # Robust intersection by normalized keys
            norm_temp = { _norm(k): k for k in temp_map.keys() }
            norm_hdd  = { _norm(k): k for k in hdd_map.keys() }
            common_norm = list(set(norm_temp.keys()) & set(norm_hdd.keys()))

            # Order by canonical list; if empty, fallback to whatever we found
            ordered = []
            for name in CANON_ORDER:
                nn = _norm(name)
                if nn in common_norm:
                    ordered.append(norm_temp[nn])
            if not ordered:  # fallback
                ordered = [norm_temp[n] for n in sorted(common_norm)]

            # Reduce maps to ordered entities
            temp_map = { e: temp_map[e] for e in ordered if e in temp_map }
            hdd_map  = { e: hdd_map[e]  for e in ordered if e in hdd_map }
            units_map = { e: units_map[e] for e in ordered if e in units_map }

            return df, temp_map, hdd_map, units_map, ordered

        @st.cache_data(show_spinner=False)
        def _find_fc_sheet(xlsx_path: Path, entity: str, key: str) -> str | None:
            """Find '<Country> forecast' robustly (tolerates 'forecats', 'forecst', etc.)."""
            target = _norm(entity)
            sheets = pd.ExcelFile(xlsx_path).sheet_names
            # exact match after stripping 'forec*'
            for s in sheets:
                if _strip_forecast_tokens(s) == target:
                    return s
            # substring fallback
            for s in sheets:
                if target in _strip_forecast_tokens(s):
                    return s
            return None

        @st.cache_data(show_spinner=False)
        def _load_fc(xlsx_path: Path, entity: str, key: str):
            s = _find_fc_sheet(xlsx_path, entity, key)
            if s is None:
                raise RuntimeError(f"No forecast sheet found for '{entity}' (expects '<Country> forecast').")

            probe = pd.read_excel(xlsx_path, sheet_name=s, header=None, usecols=[0, 1], engine="openpyxl")
            colA = probe.iloc[:, 0]

            def _is_date_like(x):
                try:
                    if isinstance(x, (int, float)) and 20000 <= float(x) <= 80000: return True
                    return pd.notna(pd.to_datetime(x, errors="coerce", dayfirst=True))
                except Exception:
                    return False

            start_idx0 = next((i for i, v in enumerate(colA[:80]) if _is_date_like(v)), None)
            if start_idx0 is None: start_idx0 = 1

            df = pd.read_excel(xlsx_path, sheet_name=s, header=None, skiprows=start_idx0, usecols=[0, 1], engine="openpyxl")
            df.columns = ["Date", "TempF"]

            s1 = pd.to_datetime(df["Date"], errors="coerce", dayfirst=True)
            if s1.isna().any():
                ser = pd.to_numeric(df["Date"], errors="coerce")
                mask = ser.notna()
                if mask.any():
                    s2 = pd.to_datetime(ser[mask], unit="D", origin="1899-12-30", errors="coerce")
                    s1.loc[mask] = s2
                if s1.isna().sum() > len(s1) * 0.5:
                    s3 = pd.to_datetime(ser, unit="s", origin="unix", errors="coerce")
                    s1 = s1.fillna(s3)

            df["Date"] = s1
            df["TempF"] = pd.to_numeric(df["TempF"], errors="coerce")
            df = df.dropna(subset=["Date", "TempF"]).drop_duplicates(subset=["Date"]).sort_values("Date").reset_index(drop=True)

            if not df.empty:
                last_day = df["Date"].max().normalize()
                df = df[(df["Date"] >= (last_day - pd.Timedelta(days=60))) & (df["Date"] <= (last_day + pd.Timedelta(days=31)))]
                # daily aggregation if hourly
                df = df.set_index("Date").resample("1D")["TempF"].mean().dropna().reset_index()

            return df, s, (start_idx0 + 1)

        # ---------- Load historical ----------
        key = _hash(xlsx)
        try:
            df_hist, temp_map, hdd_map, units_map, entities = _load_hist(xlsx, key)
        except Exception as e:
            st.error(str(e)); st.stop()

        if not entities:
            st.error("Historical data not found or no matching entities.")
            st.stop()

        # Build region pools that actually exist in file
        europe_avail = [e for e in EUROPE if e in entities]
        asia_avail   = [e for e in ASIA   if e in entities]
        usa_avail    = [e for e in USA    if e in entities]
        if not (europe_avail or asia_avail or usa_avail):
            europe_avail = entities  # fallback: show everything

        # ---------- UI ----------
        c1, c2, c3, c4 = st.columns([1, 1.2, 1, 1])
        with c1:
            region = st.selectbox("Region", ["Europe", "Asia", "USA"], index=0)
        pool = europe_avail if region == "Europe" else (asia_avail if region == "Asia" else usa_avail)
        if not pool:
            st.warning(f"No entities available in '{region}' from the workbook."); st.stop()

        with c2:
            entity = st.selectbox("Country / State", pool, index=0)
        with c3:
            mode = st.radio("Data type", ["Forecast", "History"], horizontal=True)
        with c4:
            smooth7 = st.checkbox("7-day smoothing (seasonal plots)", True)

        ticks = [pd.Timestamp(2021, m, 1).dayofyear for m in range(1, 13)]
        labels = [calendar.month_abbr[m] for m in range(1, 13)]
        unit = units_map.get(entity, "°C")  # native units

        # ---------- HISTORY ----------
        if mode == "History":
            if entity not in temp_map or entity not in hdd_map:
                st.error(f"'{entity}' not found in historical mappings."); st.stop()

            temp_col = temp_map[entity]
            df_t = df_hist[["Date", temp_col]].rename(columns={temp_col: "Temp"}).dropna()
            df_t["Year"] = df_t["Date"].dt.year
            df_t["DOY"]  = df_t["Date"].dt.dayofyear

            colors = {2025: ("black", 3.0, 1.0), 2024: ("red", 2.6, 1.0), 2023: ("green", 2.4, 1.0),
                      2022: ("#88c", 1.5, 0.35), 2021: ("#cc9", 1.5, 0.35), 2020: ("#9cc", 1.5, 0.35)}

            fig = go.Figure()
            for yr in sorted(df_t["Year"].unique()):
                ys = df_t[df_t["Year"] == yr].sort_values("DOY")
                if smooth7: ys = ys.assign(Temp=ys["Temp"].rolling(7, min_periods=1).mean())
                color, width, op = colors.get(yr, ("#bbb", 1.2, 0.3))
                fig.add_trace(go.Scatter(x=ys["DOY"], y=ys["Temp"], mode="lines",
                                         name=str(yr), line=dict(color=color, width=width), opacity=op))
            fig.update_layout(
                title=f"{entity} – Seasonal Temperatures (2020–2025)",
                xaxis=dict(title="Month", tickmode="array", tickvals=ticks, ticktext=labels),
                yaxis_title=f"Temperature ({unit})", legend=dict(orientation="h"),
                margin=dict(l=40, r=40, t=50, b=40), height=450
            )
            st.plotly_chart(fig, use_container_width=True)

            # HDD monthly: 2025 vs 2020–2024 average
            hdd_col = hdd_map[entity]
            d = df_hist[["Date", hdd_col]].rename(columns={hdd_col: "HDD"}).dropna()
            d["Year"] = d["Date"].dt.year; d["Month"] = d["Date"].dt.month
            monthly = d.groupby(["Year", "Month"])["HDD"].sum().unstack(0)
            for yr in range(2020, 2026):
                if yr not in monthly.columns: monthly[yr] = 0.0
            monthly = monthly.sort_index(axis=1)
            avg_2020_2024 = monthly.loc[:, 2020:2024].mean(axis=1)
            hdd_2025 = monthly.get(2025, pd.Series(index=avg_2020_2024.index, data=0.0))

            x = list(range(1, 13)); month_lbls = [calendar.month_abbr[m] for m in x]; w = 0.35
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(x=[xi - w/2 for xi in x], y=avg_2020_2024.values,
                                  name=f"{entity} Avg 2020–2024", marker_color="black", width=w))
            fig2.add_trace(go.Bar(x=[xi + w/2 for xi in x], y=hdd_2025.values,
                                  name=f"{entity} 2025", marker_color="red", width=w))
            fig2.update_layout(
                title=f"{entity} – Monthly HDD: 2025 vs Avg",
                xaxis=dict(title="Month", tickmode="array", tickvals=x, ticktext=month_lbls),
                yaxis_title="HDD (days)", barmode="group", legend=dict(orientation="h"),
                margin=dict(l=40, r=40, t=50, b=40), height=420
            )
            st.plotly_chart(fig2, use_container_width=True)

        # ---------- FORECAST ----------
        else:
            try:
                df_fc, sheet_used, start_row_excel = _load_fc(xlsx, entity, _hash(xlsx))
            except Exception as e:
                st.error(str(e)); st.stop()

            if df_fc.empty:
                st.error("Forecast data is empty or unusable."); st.stop()

            # --- NEW: conversion systématique °C -> °F pour les feuilles forecast des 10 États US listés ---
            if entity in USA:
                df_fc["TempF"] = _c_to_f(pd.to_numeric(df_fc["TempF"], errors="coerce"))
                st.caption("ℹ️ Conversion appliquée (°C → °F) pour la feuille de prévision de l'État US sélectionné.")

            df_fc["DOY"] = df_fc["Date"].dt.dayofyear
            start_fc, end_fc = df_fc["Date"].min(), df_fc["Date"].max()

            temp_col = temp_map.get(entity)
            if not temp_col:
                st.error(f"No historical temp column for '{entity}'"); st.stop()

            df_h = (df_hist[["Date", temp_col]].rename(columns={temp_col: "TempH"})
                    .dropna().sort_values("Date").reset_index(drop=True))
            df_h["Year"] = df_h["Date"].dt.year; df_h["DOY"] = df_h["Date"].dt.dayofyear

            hist_ref = (df_h[(df_h["Year"] >= 2020) & (df_h["Year"] <= 2024)]
                        .groupby("DOY")["TempH"].agg(["mean", "min", "max"])
                        .reindex(range(1, 367)).interpolate(limit_direction="both")
                        .rename(columns={"mean": "HistMean", "min": "HistMin", "max": "HistMax"})
                        .reset_index())
            df_cmp = df_fc.merge(hist_ref, on="DOY", how="left")

            unit_disp = units_map.get(entity, "°C")
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_cmp["Date"], y=df_cmp["HistMin"], mode="lines",
                                     line=dict(color="lightgray"), name="Hist Min (20–24)", showlegend=False))
            fig.add_trace(go.Scatter(x=df_cmp["Date"], y=df_cmp["HistMax"], mode="lines", fill="tonexty",
                                     line=dict(color="lightgray"), name="Hist Max (20–24)",
                                     fillcolor="rgba(128,128,128,0.25)"))
            fig.add_trace(go.Scatter(x=df_cmp["Date"], y=df_cmp["HistMean"], mode="lines",
                                     line=dict(color="black", dash="dash"), name="Mean 2020–2024"))
            fig.add_trace(go.Scatter(x=df_cmp["Date"], y=df_cmp["TempF"], mode="lines+markers",
                                     name="Forecast (daily)", line=dict(color="red", width=2.5)))
            fig.update_layout(
                title=f"{entity} – Forecast vs historical (same period)",
                xaxis=dict(tickformat="%d-%m", title=None),
                yaxis_title=f"Temperature ({unit_disp})",
                legend=dict(orientation="h"), margin=dict(l=40, r=40, t=50, b=40), height=480
            )
            st.plotly_chart(fig, use_container_width=True)

            mean_fc   = float(df_cmp["TempF"].mean())
            mean_hist = float(df_cmp["HistMean"].mean())
            anom      = mean_fc - mean_hist
            df_summary = pd.DataFrame({
                "Region": [("Europe" if entity in EUROPE else "Asia" if entity in ASIA else "USA")],
                "Country/State": [entity],
                "Forecast start": [start_fc.date()],
                "Forecast end":   [end_fc.date()],
                f"Mean forecast ({unit_disp})": [round(mean_fc, 2)],
                f"Mean hist. 20–24 ({unit_disp})": [round(mean_hist, 2)],
                f"Anomaly ({unit_disp})": [round(anom, 2)],
            })
            st.dataframe(df_summary, use_container_width=True)

            df_cmp["Anomaly"] = df_cmp["TempF"] - df_cmp["HistMean"]
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(x=df_cmp["Date"], y=df_cmp["Anomaly"], name=f"Anomaly ({unit_disp})"))
            fig2.add_hline(y=0, line_dash="dash", line_color="black")
            fig2.update_layout(
                title=f"{entity} – Daily anomaly (Forecast – 20–24 mean)",
                xaxis=dict(tickformat="%d-%m", title=None),
                yaxis_title=unit_disp, margin=dict(l=40, r=40, t=50, b=40), height=320
            )
            st.plotly_chart(fig2, use_container_width=True)

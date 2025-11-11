# app.py
# Streamlit dashboard for LPG market
# Run: streamlit run app.py

from pathlib import Path
import streamlit as st
import pandas as pd

import prices                     # existing module
import tab_hdd                    # HDD tab
import tab_balances               # Balances tab
import tab_imports_exports_stocks # Imports-Exports-Stocks tab
import tab_technicals             # NEW Technicals tab

st.set_page_config(page_title="LPG Market Dashboard", layout="wide")
st.title("LPG Market Dashboard")

APP_DIR = Path(__file__).parent

# 5 tabs: Prices (0) / Temp & HDD (1) / Balances (2) / Imports-Exports-Stocks (3) / Technicals (4)
tabs = st.tabs(["Prices", "Temp & HDD", "Balances", "Imports-Exports-Stocks", "Technicals"])

# Prices (index 0)
with tabs[0]:
    prices.render()

# Temp & HDD (index 1)
tab_hdd.render_tab(tabs, APP_DIR, tab_index=1)

# Balances (index 2)
tab_balances.render_balances_tab(tabs, APP_DIR, tab_index=2)

# Imports-Exports-Stocks (index 3)
tab_imports_exports_stocks.render_trade_tab(tabs, APP_DIR, tab_index=3)

# Technicals (index 4)
tab_technicals.render_technicals_tab(tabs, APP_DIR, tab_index=4)

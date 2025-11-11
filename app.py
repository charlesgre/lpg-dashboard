# app.py
# Streamlit dashboard for LPG market
# Run: streamlit run app.py

from pathlib import Path
import streamlit as st
import pandas as pd

import prices           # ton module existant
import tab_hdd          # onglet HDD
import tab_balances     # onglet Balances
import tab_imports_exports_stocks       # << NOUVEL onglet Imports-Exports-Stocks (à créer)

st.set_page_config(page_title="LPG Market Dashboard", layout="wide")
st.title("LPG Market Dashboard")

APP_DIR = Path(__file__).parent

# 4 onglets : Prices (0) / Temp & HDD (1) / Balances (2) / Imports-Exports-Stocks (3)
tabs = st.tabs(["Prices", "Temp & HDD", "Balances", "Imports-Exports-Stocks"])

# Onglet Prices (index 0)
with tabs[0]:
    prices.render()

# Onglet HDD (index 1)
tab_hdd.render_tab(tabs, APP_DIR, tab_index=1)

# Onglet Balances (index 2)
tab_balances.render_balances_tab(tabs, APP_DIR, tab_index=2)

# NOUVEL onglet Imports-Exports-Stocks (index 3)
tab_imports_exports_stocks.render_trade_tab(tabs, APP_DIR, tab_index=3)

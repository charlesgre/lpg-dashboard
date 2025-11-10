# app.py
# Streamlit dashboard for LPG market
# Run: streamlit run app.py

from pathlib import Path
import streamlit as st
import pandas as pd

import prices          # ton module existant
import tab_hdd         # notre onglet HDD

st.set_page_config(page_title="LPG Market Dashboard", layout="wide")
st.title("LPG Market Dashboard")

# 2 onglets : Prices (index 0) et Temp & HDD (index 1)
tabs = st.tabs(["Prices", "Temp & HDD"])

with tabs[0]:
    prices.render()

APP_DIR = Path(__file__).parent
# Rendre l’onglet HDD dans le 2e tab (index 1)
tab_hdd.render_tab(tabs, APP_DIR, tab_index=1)

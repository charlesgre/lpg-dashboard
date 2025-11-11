# tab_technicals.py
# Streamlit tab: Technical Indicators (price-based only)

from __future__ import annotations
from pathlib import Path
from typing import Tuple, Dict

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------
PRICES_FILE = "LPG prices.xlsx"
PRICES_SHEET = "Query1"  # Sheet containing price data

# -------------------------------------------------------------------
# Data loading
# -------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _load_prices(app_dir: Path) -> pd.DataFrame:
    """Load price data from Prices/LPG prices.xlsx"""
    p1 = app_dir / PRICES_FILE
    p2 = app_dir / "Prices" / PRICES_FILE
    path = p1 if p1.exists() else p2
    if not path.exists():
        raise FileNotFoundError(f"Excel file not found: {p1.name} or {p2}")

    df = pd.read_excel(path, sheet_name=PRICES_SHEET)
    df = df.rename(columns={"ASSESSDATE": "DATE", "VALUE": "CLOSE"})
    df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce")
    df = df.dropna(subset=["DATE", "CLOSE"]).astype({"CLOSE": "float"})
    df = df.sort_values(["SYMBOL", "DATE"]).reset_index(drop=True)
    return df[["SYMBOL", "DESCRIPTION", "DATE", "CLOSE", "UOM", "CURRENCY"]]


def _series_for_symbol(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    return df[df["SYMBOL"] == symbol].sort_values("DATE").reset_index(drop=True)


def _series_for_description(df: pd.DataFrame, desc: str) -> pd.DataFrame:
    return df[df["DESCRIPTION"] == desc].sort_values("DATE").reset_index(drop=True)

# -------------------------------------------------------------------
# Technical calculations (price only)
# -------------------------------------------------------------------
def sma(s, n): return s.rolling(n, min_periods=n).mean()
def ema(s, n): return s.ewm(span=n, adjust=False).mean()
def wma(s, n):
    w = np.arange(1, n + 1)
    return s.rolling(n).apply(lambda x: np.dot(x, w) / w.sum(), raw=True)

def macd(close, fast=12, slow=26, signal=9):
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = ema(macd_line, signal)
    return macd_line, signal_line

def rsi(close, n=14):
    delta = close.diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    roll_up = pd.Series(gain, index=close.index).ewm(alpha=1/n, adjust=False).mean()
    roll_down = pd.Series(loss, index=close.index).ewm(alpha=1/n, adjust=False).mean()
    rs = roll_up / (roll_down + 1e-12)
    return 100 - (100 / (1 + rs))

def roc(close, n=10): return close.pct_change(n) * 100
def stochastic(close, n=14, d=3):
    low_n = close.rolling(n).min()
    high_n = close.rolling(n).max()
    k = 100 * (close - low_n) / (high_n - low_n + 1e-12)
    dline = k.rolling(d).mean()
    return k, dline

def williams_r(close, n=14):
    low_n = close.rolling(n).min()
    high_n = close.rolling(n).max()
    return -100 * (high_n - close) / (high_n - low_n + 1e-12)

def cci(close, n=20, c=0.015):
    tp = close
    sma_tp = tp.rolling(n).mean()
    mad = (tp - sma_tp).abs().rolling(n).mean()
    return (tp - sma_tp) / (c * (mad + 1e-12))

def bollinger(close, n=20, k=2.0):
    mid = sma(close, n)
    std = close.rolling(n).std()
    upper = mid + k * std
    lower = mid - k * std
    return lower, mid, upper

def atr_proxy(close, n=14):
    tr = close.diff().abs()
    return tr.rolling(n).mean()

def donchian(close, n=20):
    upper = close.rolling(n).max()
    lower = close.rolling(n).min()
    return lower, upper

def keltner_proxy(close, n_ema=20, n_atr=14, m=2.0):
    mid = ema(close, n_ema)
    atr = atr_proxy(close, n_atr)
    upper = mid + m * atr
    lower = mid - m * atr
    return lower, mid, upper

# -------------------------------------------------------------------
# Short & detailed explanations
# -------------------------------------------------------------------
INFO_SHORT = {
    "SMA": "Simple Moving Average — smooths prices to show overall trend.",
    "EMA": "Exponential Moving Average — more weight on recent prices.",
    "WMA": "Weighted Moving Average — linear weighting from newest to oldest.",
    "MACD": "Difference between two EMAs to show trend strength and shifts.",
    "RSI": "Oscillator (0–100): overbought >70, oversold <30.",
    "ROC": "Rate of Change — % variation over n periods.",
    "Stochastic": "Position of price within its recent range (n periods).",
    "Williams %R": "Inverse of Stochastic, showing overbought/oversold zones.",
    "CCI": "Commodity Channel Index — deviation from its mean.",
    "Bollinger": "Bands = SMA ± k×std — volatility measure.",
    "Keltner": "EMA ± m×ATR (proxy) — volatility channel.",
    "Donchian": "Highest & lowest prices over a rolling window.",
    "ATR (proxy)": "Average True Range proxy — measures volatility magnitude.",
}

INFO_DETAILS = {
    "SMA": r"""
**Simple Moving Average (SMA)**  
Formula: \( SMA_n = \frac{1}{n}\sum_{i=0}^{n-1} P_{t-i} \)  
**Signals:** Price above → bullish bias; short/long SMA crossovers.  
**Limitations:** Lagging; whipsaws in sideways markets.
""",
    "EMA": r"""
**Exponential Moving Average (EMA)**  
Formula: \( EMA_t = \alpha P_t + (1-\alpha)EMA_{t-1} \), \( \alpha = \frac{2}{n+1} \)  
**Signals:** More reactive than SMA; common periods 12/26.  
**Limitations:** More sensitive to short-term noise.
""",
    "WMA": r"""
**Weighted Moving Average (WMA)**  
Linearly weighted average (recent data matters more).  
**Use:** Smoother trend with less lag than SMA.
""",
    "MACD": r"""
**Moving Average Convergence Divergence (MACD)**  
MACD = EMA(12) – EMA(26), Signal = EMA(9) of MACD.  
Histogram = MACD – Signal.  
**Signals:** Zero-line cross; MACD/Signal cross; divergences.  
**Limitations:** False signals in ranges.
""",
    "RSI": r"""
**Relative Strength Index (RSI)**  
\( RSI = 100 - \frac{100}{1 + RS} \), \( RS = \frac{avg(gains)}{avg(losses)} \).  
**Signals:** Overbought (>70), Oversold (<30); trendline breaks; divergences.  
**Limitations:** Can remain extreme in strong trends.
""",
    "ROC": r"""
**Rate of Change (ROC)**  
\( ROC_n = 100 \times \frac{P_t - P_{t-n}}{P_{t-n}} \).  
**Signals:** Acceleration/deceleration of momentum.  
**Limitations:** Sensitive to large historical moves.
""",
    "Stochastic": r"""
**Stochastic Oscillator (%K / %D)**  
\( \%K = 100 \times \frac{P_t - L_n}{H_n - L_n} \), %D = SMA(3) of %K.  
**Signals:** >80 overbought, <20 oversold; %K/%D cross; divergences.  
**Limitations:** Many false signals in non-trending markets.
""",
    "Williams %R": r"""
**Williams %R**  
\( \%R = -100 \times \frac{H_n - P_t}{H_n - L_n} \).  
**Signals:** Overbought above -20; oversold below -80.  
**Limitations:** Similar behavior to Stochastic but inverted scale.
""",
    "CCI": r"""
**Commodity Channel Index (CCI)**  
\( CCI = \frac{TP - SMA(TP)}{0.015 \times MeanDeviation(TP)} \)  
(Here TP≈close as proxy.)  
**Signals:** CCI > +100 → possible overbought; < -100 → oversold.  
**Limitations:** Volatile; use confirmation/smoothing.
""",
    "Bollinger": r"""
**Bollinger Bands**  
Upper/Lower = SMA(n) ± k×σ.  
**Signals:** Band squeeze → low vol & potential breakout; expansion → ongoing move.  
**Limitations:** Bands naturally widen in high volatility.
""",
    "Keltner": r"""
**Keltner Channel (proxy)**  
EMA(n) ± m×ATR(n). Here ATR is a close-to-close proxy.  
**Signals:** Breaks above/below confirm momentum; midline acts as dynamic MA.  
**Limitations:** Proxy lacks true H/L range.
""",
    "Donchian": r"""
**Donchian Channels**  
Upper = rolling max; Lower = rolling min (close-only proxy).  
**Signals:** Breakouts from channel often initiate trends.  
**Limitations:** Whipsaws during consolidations.
""",
    "ATR (proxy)": r"""
**Average True Range (ATR proxy)**  
Based on average absolute close-to-close changes.  
**Signals:** Rising ATR → increasing volatility; falling → calming market.  
**Limitations:** Ignores intraday highs/lows (proxy).
""",
}

# -------------------------------------------------------------------
# Plot functions
# -------------------------------------------------------------------
def _price_base_fig(df, title):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["DATE"], y=df["CLOSE"], name="Price", mode="lines"))
    fig.update_layout(title=title, margin=dict(l=10, r=10, t=40, b=10),
                      hovermode="x unified", xaxis_title="Date",
                      yaxis_title=f"Price ({df['UOM'].iloc[-1]} / {df['CURRENCY'].iloc[-1]})")
    return fig

def _overlay_ma(fig, df, kind, n):
    f = {"SMA": sma, "EMA": ema, "WMA": wma}[kind]
    ma = f(df["CLOSE"], n)
    fig.add_trace(go.Scatter(x=df["DATE"], y=ma, name=f"{kind} {n}", mode="lines"))

def _overlay_bands(fig, df, kind, **kw):
    if kind == "Bollinger":
        lo, mid, up = bollinger(df["CLOSE"], **kw)
        fig.add_trace(go.Scatter(x=df["DATE"], y=up, name="Upper", mode="lines"))
        fig.add_trace(go.Scatter(x=df["DATE"], y=mid, name="Mid", mode="lines"))
        fig.add_trace(go.Scatter(x=df["DATE"], y=lo, name="Lower", mode="lines"))
        fig.add_trace(go.Scatter(x=pd.concat([df["DATE"], df["DATE"][::-1]]),
                                 y=pd.concat([up, lo[::-1]]),
                                 fill="toself", fillcolor="rgba(180,180,255,0.15)",
                                 line=dict(width=0), hoverinfo="skip", showlegend=False))
    elif kind == "Keltner":
        lo, mid, up = keltner_proxy(df["CLOSE"], **kw)
        for y, name in zip([up, mid, lo], ["Upper", "Mid", "Lower"]):
            fig.add_trace(go.Scatter(x=df["DATE"], y=y, name=f"{kind} {name}", mode="lines"))
    elif kind == "Donchian":
        lo, up = donchian(df["CLOSE"], **kw)
        fig.add_trace(go.Scatter(x=df["DATE"], y=up, name="Upper", mode="lines"))
        fig.add_trace(go.Scatter(x=df["DATE"], y=lo, name="Lower", mode="lines"))

def _indicator_panel(df, indicator, params):
    x = df["DATE"]; close = df["CLOSE"]
    fig = go.Figure()
    if indicator == "MACD":
        macd_line, sig = macd(close, **params)
        hist = macd_line - sig
        fig.add_trace(go.Bar(x=x, y=hist, name="MACD hist"))
        fig.add_trace(go.Scatter(x=x, y=macd_line, name="MACD"))
        fig.add_trace(go.Scatter(x=x, y=sig, name="Signal"))
    elif indicator == "RSI":
        r = rsi(close, **params)
        fig.add_trace(go.Scatter(x=x, y=r, name="RSI"))
        fig.add_hline(y=70, line_dash="dash", line_color="red")
        fig.add_hline(y=30, line_dash="dash", line_color="green")
    elif indicator == "ROC":
        fig.add_trace(go.Scatter(x=x, y=roc(close, **params), name="ROC"))
    elif indicator == "Stochastic":
        k, dline = stochastic(close, **params)
        fig.add_trace(go.Scatter(x=x, y=k, name="%K"))
        fig.add_trace(go.Scatter(x=x, y=dline, name="%D"))
        fig.add_hline(y=80, line_dash="dash")
        fig.add_hline(y=20, line_dash="dash")
    elif indicator == "Williams %R":
        fig.add_trace(go.Scatter(x=x, y=williams_r(close, **params), name="%R"))
        fig.add_hline(y=-20, line_dash="dash")
        fig.add_hline(y=-80, line_dash="dash")
    elif indicator == "CCI":
        fig.add_trace(go.Scatter(x=x, y=cci(close, **params), name="CCI"))
        fig.add_hline(y=100, line_dash="dash")
        fig.add_hline(y=-100, line_dash="dash")
    elif indicator == "ATR (proxy)":
        fig.add_trace(go.Scatter(x=x, y=atr_proxy(close, **params), name="ATR"))
    fig.update_layout(margin=dict(l=10, r=10, t=30, b=10), hovermode="x unified")
    return fig

# -------------------------------------------------------------------
# UI
# -------------------------------------------------------------------
TREND = ["SMA", "EMA", "WMA", "MACD"]
MOMENTUM = ["RSI", "ROC", "Stochastic", "Williams %R", "CCI"]
VOL = ["Bollinger", "Keltner", "Donchian", "ATR (proxy)"]

def render_technicals_tab(tabs, app_dir: Path, tab_index: int = 4):
    with tabs[tab_index]:
        st.subheader("Technicals")

        # Load
        try:
            df_all = _load_prices(app_dir)
        except FileNotFoundError as e:
            st.error(str(e))
            return

        # Security selection
        col1, col2 = st.columns([1, 3])
        with col1:
            mode = st.radio("Select by", ["Description", "Symbol"], horizontal=True)
        with col2:
            if mode == "Description":
                opts = sorted(df_all["DESCRIPTION"].unique())
                sel = st.selectbox("Security", opts)
                df = _series_for_description(df_all, sel)
                label = sel
            else:
                opts = sorted(df_all["SYMBOL"].unique())
                sel = st.selectbox("Symbol", opts)
                df = _series_for_symbol(df_all, sel)
                label = f"{sel} — {df['DESCRIPTION'].iloc[0] if not df.empty else ''}"

        if df.empty:
            st.warning("No data for this selection.")
            return

        # Indicator selection
        colf1, colf2 = st.columns(2)
        with colf1:
            cat = st.selectbox("Category", ["1) Trend", "2) Momentum", "3) Volatility"])
        with colf2:
            if cat.startswith("1"):
                ind = st.selectbox("Indicator", TREND)
            elif cat.startswith("2"):
                ind = st.selectbox("Indicator", MOMENTUM)
            else:
                ind = st.selectbox("Indicator", VOL)

        # Short description + detailed expander
        st.info(INFO_SHORT.get(ind, "Technical indicator based on price."))
        with st.expander("More info"):
            st.markdown(INFO_DETAILS.get(ind, "_No additional info available._"))

        # Parameters
        params: Dict = {}
        if ind in {"SMA", "EMA", "WMA"}:
            n = st.slider("Period (n)", 2, 200, 20)
            params = {"n": n}
        elif ind == "MACD":
            fast = st.number_input("Fast", 2, 200, 12)
            slow = st.number_input("Slow", 2, 400, 26)
            signal = st.number_input("Signal", 2, 100, 9)
            params = {"fast": fast, "slow": slow, "signal": signal}
        elif ind in {"RSI", "ROC", "CCI", "ATR (proxy)", "Williams %R"}:
            n = st.slider("Period (n)", 2, 100, 14)
            params = {"n": n}
        elif ind == "Stochastic":
            n = st.slider("Lookback %K", 2, 100, 14)
            d = st.slider("Smoothing %D", 2, 20, 3)
            params = {"n": n, "d": d}
        elif ind == "Bollinger":
            n = st.slider("Period (n)", 2, 100, 20)
            k = st.slider("Std Dev (k)", 0.5, 5.0, 2.0, step=0.1)
            params = {"n": n, "k": k}
        elif ind == "Keltner":
            n_ema = st.slider("EMA (n)", 2, 100, 20)
            n_atr = st.slider("ATR (n)", 2, 100, 14)
            m = st.slider("Multiplier (m)", 0.5, 5.0, 2.0, step=0.1)
            params = {"n_ema": n_ema, "n_atr": n_atr, "m": m}
        elif ind == "Donchian":
            n = st.slider("Period (n)", 2, 200, 20)
            params = {"n": n}

        # Plot: price + overlays
        fig_price = _price_base_fig(df, f"{label} — {ind}")
        if ind in {"SMA", "EMA", "WMA"}:
            _overlay_ma(fig_price, df, ind, params["n"])
        elif ind in {"Bollinger", "Keltner", "Donchian"}:
            _overlay_bands(fig_price, df, ind, **params)
        st.plotly_chart(fig_price, use_container_width=True)

        # Indicator panel
        if ind in {"MACD", "RSI", "ROC", "Stochastic", "Williams %R", "CCI", "ATR (proxy)"}:
            fig_ind = _indicator_panel(df, ind, params)
            st.plotly_chart(fig_ind, use_container_width=True)

        st.caption("Indicators are computed on close-only series (no volume / H-L data).")

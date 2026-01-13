# trading.py
import alpaca_trade_api as tradeapi
import pandas as pd
from datetime import datetime, timedelta
import streamlit as st # 記得匯入 streamlit
from i18n import t

# 移除 config 匯入，改用 st.secrets
# import config 

@st.cache_resource
def get_api():
    # 🔥 修改重點：改從 Streamlit 的 Secrets 讀取金鑰
    # 這樣上傳到 GitHub 才不會洩漏密碼，也才能在雲端執行
    try:
        key_id = st.secrets["ALPACA_API_KEY"]
        secret_key = st.secrets["ALPACA_SECRET_KEY"]
        base_url = "https://paper-api.alpaca.markets" # Paper Trading 網址通常固定
    except:
        # 如果在本機跑，沒有設定 secrets，可以 fallback 到原本的 config (選用)
        import config
        key_id = config.ALPACA_API_KEY
        secret_key = config.ALPACA_SECRET_KEY
        base_url = config.BASE_URL

    return tradeapi.REST(key_id, secret_key, base_url)

def execute_order(api, symbol, side, qty=1, price=None):
    try:
        # 檢查是否已經有未成交的訂單
        existing_orders = api.list_orders(status='open', symbols=[symbol])
        if existing_orders:
            return f"⚠️ {symbol} 已有掛單，跳過。"
            
        if price:
            # 🔥 Limit Order (限價單) -> 支援夜間掛單
            api.submit_order(
                symbol=symbol,
                qty=qty,
                side=side,
                type='limit',
                limit_price=price,
                time_in_force='day'
            )
            return f"✅ 已掛單 (Limit): {side.upper()} {qty}張 @ ${price:.2f}"
        else:
            # Market Order (市價單)
            api.submit_order(
                symbol=symbol,
                qty=qty,
                side=side,
                type='market',
                time_in_force='day'
            )
            return f"✅ 成功下單 (Market): {side.upper()} {qty} 單位"

    except Exception as e:
        return f"❌ 下單失敗 {symbol}: {e}"

@st.cache_data(ttl=3600)
def get_all_assets(_api):
    try:
        assets = _api.list_assets(status='active', asset_class='us_equity')
        return [f"{asset.symbol} - {asset.name}" for asset in assets if asset.tradable]
    except: return []

@st.cache_data(ttl=300)
def get_stock_news(_api, symbol):
    try:
        raw_news = _api.get_news(symbol=symbol, limit=8)
        return [{'headline': n.headline, 'summary': n.summary, 'source': n.source, 'url': n.url, 'created_at': n.created_at} for n in raw_news]
    except: return []

@st.cache_data(ttl=60) 
def get_market_data(_api, symbol, days=700):
    try:
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        bars = _api.get_bars(symbol, tradeapi.rest.TimeFrame.Day, start=start_date, adjustment='raw').df
        if bars.empty: return pd.DataFrame()
        bars['SMA20'] = bars['close'].rolling(window=20).mean()
        bars['SMA50'] = bars['close'].rolling(window=50).mean()
        bars['SMA200'] = bars['close'].rolling(window=200).mean()
        delta = bars['close'].diff()
        gain = (delta.where(delta > 0, 0)).fillna(0)
        loss = (-delta.where(delta < 0, 0)).fillna(0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        rs = avg_gain / avg_loss
        bars['RSI'] = 100 - (100 / (1 + rs))
        if len(bars) > 300: bars = bars.tail(300)
        return bars
    except: return pd.DataFrame()

def get_signal(df, symbol=None):
    if df.empty: return t('error_data'), "warning"
    cash_etfs = ['SGOV', 'SHV', 'BIL', 'USFR']
    if symbol in cash_etfs: return "Cash", "info"

    last = df.iloc[-1]
    if last['SMA20'] > last['SMA200']: return "Buy", "success"
    elif last['SMA20'] < last['SMA200']: return "Sell", "error"
    else: return "Wait", "warning"

def get_orders_history(api, status='all', limit=50):
    """獲取歷史訂單紀錄"""
    try:
        # 獲取最近的訂單
        orders = api.list_orders(status=status, limit=limit, nested=True)
        data = []
        for o in orders:
            # 轉換時間格式
            created_at = o.created_at.strftime('%Y-%m-%d %H:%M') if hasattr(o, 'created_at') else ''
            filled_at = o.filled_at.strftime('%Y-%m-%d %H:%M') if o.filled_at else '-'
            
            data.append({
                "時間 (提交)": created_at,
                "時間 (成交)": filled_at,
                "代碼": o.symbol,
                "方向": "🟢 買入" if o.side == 'buy' else "🔴 賣出",
                "數量": int(o.qty) if o.qty else 0,
                "成交均價": float(o.filled_avg_price) if o.filled_avg_price else 0.0,
                "狀態": o.status,
                "類型": o.type,
                "ID": o.id
            })
        return pd.DataFrame(data)
    except Exception as e:
        return pd.DataFrame()

def cancel_order(api, order_id):
    """取消特定訂單"""
    try:
        api.cancel_order(order_id)
        return True
    except:
        return False
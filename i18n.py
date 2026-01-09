# i18n.py
import streamlit as st

TRANS = {
    'title': {'zh': '🚀 量化投資指揮中心', 'en': '🚀 AlgoTrading'},
    'total_assets': {'zh': '總資產', 'en': 'Total Equity'},
    'cash': {'zh': '現金', 'en': 'Cash'},
    'buying_power': {'zh': '購買力', 'en': 'Buying Power'},
    'market_status': {'zh': '市場狀態', 'en': 'Market Status'},
    'open': {'zh': '開盤', 'en': 'Open'},
    'closed': {'zh': '收盤', 'en': 'Closed'},
    'search_placeholder': {'zh': '🔍 搜尋美股 (例如: Apple...)', 'en': '🔍 Search Symbol (e.g., Apple...)'},
    'add_watchlist': {'zh': '☆ 加入清單', 'en': '☆ Add to Watchlist'},
    'remove_watchlist': {'zh': '⭐ 已關注 (移除)', 'en': '⭐ Following (Remove)'},
    'analyzing': {'zh': '正在分析', 'en': 'Analyzing'},
    'tech_signal': {'zh': '技術面信號', 'en': 'Tech Signal'},
    'ai_analysis': {'zh': '🧠 AI 深度分析 (Gemini)', 'en': '🧠 AI Deep Analysis (Gemini)'},
    'news_source': {'zh': '📰 以下是新聞來源 (點擊閱讀)：', 'en': '📰 News Sources (Click to read):'},
    'quiet': {'zh': '😴 這支標的最近很安靜，沒什麼新聞。', 'en': '😴 Quiet here. No recent news found.'},
    'error_data': {'zh': '無法獲取數據', 'en': 'Failed to fetch data'},
    'watchlist_title': {'zh': '👀 監控清單', 'en': '👀 Watchlist'},
    'scan_btn': {'zh': '📡 掃描信號', 'en': '📡 Scan Signals'},
    'scanning': {'zh': '掃描中...', 'en': 'Scanning...'},
    'positions': {'zh': '💼 持倉', 'en': '💼 Positions'},
    'no_positions': {'zh': '目前空手', 'en': 'No Open Positions'},
    'manage_list': {'zh': '管理清單', 'en': 'Manage List'},
    'gemini_keywords': {'zh': '🔑 **Gemini 提取關鍵字：**', 'en': '🔑 **Key Topics:**'},
    'report_title': {'zh': '**分析報告：**', 'en': '**Analysis Report:**'},
    'warning_title': {'zh': '**⚠️ 警示報告：**', 'en': '**⚠️ WARNING:**'},
    'legend_k': {'zh': 'K線', 'en': 'Candles'},
    'legend_sma20': {'zh': 'SMA20 (月)', 'en': 'SMA20 (Month)'},
    'legend_sma50': {'zh': 'SMA50 (季)', 'en': 'SMA50 (Quarter)'},
    'legend_sma200': {'zh': 'SMA200 (年)', 'en': 'SMA200 (Year)'},
    'overbought': {'zh': '(⚠️ 過熱)', 'en': '(⚠️ Overbought)'},
    'oversold': {'zh': '(❄️ 超賣)', 'en': '(❄️ Oversold)'},
    'healthy': {'zh': '(健康)', 'en': '(Healthy)'},
    'auto_trade_title': {'zh': '🤖 自動交易 (模擬)', 'en': '🤖 Auto-Trade (Paper)'},
    'run_strategy': {'zh': '⚡ 執行策略 (一鍵下單)', 'en': '⚡ Run Strategy (One-Click)'},
    'trade_log': {'zh': '📝 交易日誌', 'en': '📝 Trade Log'},
    'buy_msg': {'zh': '🔵 買進', 'en': '🔵 BUY'},
    'sell_msg': {'zh': '🔴 賣出', 'en': '🔴 SELL'},
    'skip_msg': {'zh': '⚪ 觀望', 'en': '⚪ WAIT'},
}

def t(key):
    """取得對應語言的字串，自動讀取 session_state"""
    lang = st.session_state.get('language', 'zh')
    return TRANS.get(key, {}).get(lang, key)
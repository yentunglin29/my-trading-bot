# brain.py
import requests
import json
import streamlit as st
from i18n import t

# 嘗試匯入 config，如果沒有也沒關係 (雲端環境可能沒有 config.py)
try:
    import config
except ImportError:
    config = None

@st.cache_data(ttl=600)
def call_gemini_analysis(symbol, full_name, news_text, tech_status, rsi_val, lang):
    api_key = None
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
    except:
        if config and hasattr(config, 'GEMINI_API_KEY'):
            api_key = config.GEMINI_API_KEY

    # 如果都找不到 Key，就報錯
    if not api_key:
        return "⚠️ Please set GEMINI_API_KEY in Secrets or config.py", "gray", []
    
    candidate_models = ["gemini-2.0-flash", "gemini-flash-latest", "gemini-2.5-flash", "gemini-2.0-flash-exp"]
    
    prompt_zh = f"""
    你是一位專業的華爾街交易員。請根據以下資訊分析 {symbol} ({full_name})。
    【技術面數據】趨勢：{tech_status}, RSI：{rsi_val}
    【新聞】{news_text}
    【要求】用繁體中文(台灣用語)回答。直接給三行：
    1. 中立客觀情緒 (例如：樂觀/悲觀/謹慎/誘多)
    2. 分析摘要(100字，白話解釋，若技術面空頭但新聞好請警告誘多)
    3. 關鍵字(3-5個英文單字，逗號隔開)
    """

    prompt_en = f"""
    You are a seasoned Wall Street trader. Analyze {symbol} ({full_name}).
    [Tech Data] Trend: {tech_status}, RSI: {rsi_val}
    [News] {news_text}
    [Req] Use trader jargon. Warn Bull Traps.
    [Format] 3 Lines:
    1. Sentiment
    2. Summary (100 words)
    3. Keywords (3-5 English words)
    """

    prompt_text = prompt_zh if lang == 'zh' else prompt_en
    payload = {"contents": [{"parts": [{"text": prompt_text}]}]}
    headers = {'Content-Type': 'application/json'}

    for model_name in candidate_models:
        # 🔥 修改重點 2：使用變數 api_key，而不是 config.GEMINI_API_KEY
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key.strip()}"
        try:
            response = requests.post(url, headers=headers, data=json.dumps(payload))
            if response.status_code == 200:
                result = response.json()
                try:
                    return result['candidates'][0]['content']['parts'][0]['text']
                except: continue
        except: continue
            
    return "⚠️ Gemini Connection Failed (Check API Key or Quota).", "gray", []

def generate_ai_report(symbol, full_name, news_list, df):
    lang = st.session_state.get('language', 'zh')
    tech_status = "Neutral"
    rsi_val = 50
    if not df.empty:
        last = df.iloc[-1]
        sma20, sma200 = last['SMA20'], last['SMA200']
        rsi_val = round(last['RSI'], 1)
        if sma20 > sma200: tech_status = "Bull"
        elif sma20 < sma200: tech_status = "Bear"
        if symbol in ['SGOV', 'SHV', 'BIL', 'USFR']: tech_status = "Cash"

    if not news_list: return t('quiet'), "gray", []
    news_text = "".join([f"- {n['headline']}\n" for n in news_list])
    
    raw_response = call_gemini_analysis(symbol, full_name, news_text, tech_status, rsi_val, lang)
    if isinstance(raw_response, tuple): return raw_response
    if isinstance(raw_response, str) and "⚠️" in raw_response: return raw_response, "gray", []

    try:
        lines = raw_response.strip().split('\n')
        lines = [l for l in lines if l.strip()]
        mood_line = lines[0]
        color = "info"
        if any(x in mood_line for x in ["樂觀", "Optimistic"]): color = "success"
        elif any(x in mood_line for x in ["悲觀", "Pessimistic"]): color = "error"
        elif any(x in mood_line for x in ["矛盾", "陷阱", "Trap", "謹慎"]): color = "warning"

        summary = lines[1].replace("分析摘要：", "").replace("Summary:", "").replace("2. ", "").strip()
        keywords_str = lines[2].replace("關鍵字：", "").replace("Keywords:", "").replace("3. ", "").strip()
        keywords = [k.strip() for k in keywords_str.split(',')]
        return summary, color, keywords
    except: return raw_response, "gray", []
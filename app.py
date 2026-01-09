# app.py
# 這是主程式，請執行: streamlit run app.py

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
import config
from i18n import t
import trading
import brain
import json
import os
import yfinance as yf
from pyngrok import ngrok

# # ================= 1. Ngrok 設定 (公開分享連結) =================


# # 只在第一次執行時啟動 tunnel
# if 'ngrok_url' not in st.session_state:
#     try:
#         # 建立一個連到 8501 port 的隨意門
#         public_url = ngrok.connect(8501, "http")
#         st.session_state.ngrok_url = public_url.public_url
#     except:
#         pass 

# if 'ngrok_url' in st.session_state:
#     st.sidebar.success(f"🌏 公開分享連結：\n{st.session_state.ngrok_url}")

# ================= 2. 存檔與讀檔函數 =================
def load_watchlist():
    """嘗試從 JSON 檔案讀取清單"""
    if os.path.exists(config.WATCHLIST_FILE):
        try:
            with open(config.WATCHLIST_FILE, 'r') as f:
                return json.load(f)
        except:
            return config.DEFAULT_WATCHLIST
    return config.DEFAULT_WATCHLIST

def save_watchlist(new_list):
    """把最新的清單寫入 JSON 檔案"""
    with open(config.WATCHLIST_FILE, 'w') as f:
        json.dump(new_list, f)

# ================= 3. 頁面初始化 =================
st.set_page_config(page_title="AlgoTrading 戰情室", layout="wide", page_icon="📈")

if 'language' not in st.session_state: st.session_state.language = 'zh'
if 'watchlist' not in st.session_state: st.session_state.watchlist = load_watchlist()

# ================= 4. 側邊欄 (導航與設定) =================
with st.sidebar:
    # --- 語言設定 ---
    st.header("🌐 Language")
    lang_choice = st.radio("Select", ["中文 (Traditional)", "English"], index=0 if st.session_state.language == 'zh' else 1)
    new_lang = 'zh' if "中文" in lang_choice else 'en'
    if new_lang != st.session_state.language:
        st.session_state.language = new_lang
        st.rerun()

    st.markdown("---")
    
    # --- 🔥 頁面導航模式 ---
    st.header("🧭 導航模式")
    page_mode = st.radio("請選擇功能：", ["📈 股票戰情室 (Dashboard)", "💰 期權策略 (Options)", "💼 我的資產 (Portfolio)"], index=0)

    # --- 監控清單 (共用) ---
    st.markdown("---")
    st.header(t('watchlist_title'))
    if st.session_state.watchlist:
        def on_change_watchlist():
            new_list = st.session_state.watchlist_ui
            st.session_state.watchlist = new_list
            save_watchlist(new_list)

        st.session_state.watchlist = st.multiselect(
            t('manage_list'), 
            options=st.session_state.watchlist, 
            default=st.session_state.watchlist,
            key='watchlist_ui',
            on_change=on_change_watchlist
        )
        
        # 只有在「股票戰情室」才顯示掃描按鈕
        if page_mode == "📈 股票戰情室 (Dashboard)":
            st.markdown("---")
            if st.button(t('scan_btn')):
                res = []
                api = trading.get_api()
                status = st.empty()
                status.text(t('scanning'))
                for ticker in st.session_state.watchlist:
                    d = trading.get_market_data(api, ticker, days=400)
                    if not d.empty:
                        last = d.iloc[-1]
                        s20, s200 = last['SMA20'], last['SMA200']
                        sig = "🔵 Cash" if ticker in ['SGOV'] else ("🟢 Bull" if s20 > s200 else ("🔴 Bear" if s20 < s200 else "⚪ Wait"))
                        res.append({"Sym": ticker, "Sig": sig, "Price": f"{last['close']:.1f}"})
                status.empty()
                st.dataframe(pd.DataFrame(res), hide_index=True)
    
    # --- 策略參數 (共用) ---
    st.markdown("---")
    st.header("⚙️ 策略參數")
    rsi_upper = st.slider("RSI 超買 (賣出/警戒)", 70, 90, 70)
    rsi_lower = st.slider("RSI 超賣 (買進/警戒)", 10, 30, 30)

    # --- 自動交易 (只在股票戰情室顯示) ---
    if page_mode == "📈 股票戰情室 (Dashboard)":
        st.markdown("---")
        st.header(t('auto_trade_title'))
        if 'trade_log' not in st.session_state: st.session_state.trade_log = []
        
        if st.button(t('run_strategy'), type="primary"):
            api = trading.get_api()
            st.session_state.trade_log = []
            progress = st.progress(0)
            status_txt = st.empty()
            
            # 獲取持倉
            current_positions = {p.symbol: int(p.qty) for p in api.list_positions()}
            
            watchlist = st.session_state.watchlist
            for i, ticker in enumerate(watchlist):
                status_txt.text(f"Scanning {ticker}...")
                progress.progress((i + 1) / len(watchlist))
                
                df = trading.get_market_data(api, ticker, days=500)
                signal, _ = trading.get_signal(df, ticker)
                
                action_msg = f"{ticker}: {t('skip_msg')}"
                if signal == "Buy" and ticker not in current_positions:
                    res = trading.execute_order(api, ticker, 'buy', qty=1)
                    action_msg = f"{ticker}: {t('buy_msg')} (1 unit) -> {res}"
                elif signal == "Sell" and ticker in current_positions:
                    qty = current_positions[ticker]
                    res = trading.execute_order(api, ticker, 'sell', qty=qty)
                    action_msg = f"{ticker}: {t('sell_msg')} ({qty} units) -> {res}"
                elif signal == "Cash":
                    action_msg = f"{ticker}: Cash Asset"
                
                st.session_state.trade_log.append(action_msg)
                time.sleep(0.5)
            
            status_txt.text("Done!")
            time.sleep(1)
            status_txt.empty()
            progress.empty()

        if st.session_state.trade_log:
            st.subheader(t('trade_log'))
            for log in st.session_state.trade_log: st.caption(log)
        
        # 持倉顯示
        st.markdown("---")
        st.subheader(t('positions'))
        api = trading.get_api()
        pos = api.list_positions()
        if pos:
            p_list = [{"Sym": p.symbol, "P/L": f"{float(p.unrealized_plpc)*100:.1f}%"} for p in pos]
            st.dataframe(pd.DataFrame(p_list), hide_index=True)
        else:
            st.caption(t('no_positions'))

# ================= 5. 主畫面邏輯 =================

# -----------------------------------------------
# 🅰️ 模式一：股票戰情室 (Dashboard)
# -----------------------------------------------
if page_mode == "📈 股票戰情室 (Dashboard)":
    st.title(t('title'))
    api = trading.get_api()
    account = api.get_account()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(t('total_assets'), f"${float(account.equity):,.0f}", f"{float(account.equity) - float(account.last_equity):+.0f}")
    c2.metric(t('cash'), f"${float(account.cash):,.0f}")
    c3.metric(t('buying_power'), f"${float(account.buying_power):,.0f}")
    c4.metric(t('market_status'), t('open') if api.get_clock().is_open else t('closed'))

    st.markdown("---")

    all_assets = trading.get_all_assets(api)
    col_search, _ = st.columns([2, 1])
    with col_search:
        selected_option = st.selectbox("🔍", [""] + all_assets, index=0, placeholder=t('search_placeholder'), label_visibility="collapsed")

    if selected_option:
        parts = selected_option.split(' - ')
        target_symbol = parts[0].strip()
        target_name = parts[1].strip() if len(parts) > 1 else ""
        
        col_title, col_btn = st.columns([0.8, 0.2])
        with col_title: st.header(f"📊 {target_symbol} {target_name}")
        with col_btn:
            st.write(""); st.write("")
            if target_symbol in st.session_state.watchlist:
                if st.button(t('remove_watchlist'), type="primary"):
                    st.session_state.watchlist.remove(target_symbol)
                    save_watchlist(st.session_state.watchlist)
                    st.rerun()
            else:
                if st.button(t('add_watchlist')):
                    st.session_state.watchlist.append(target_symbol)
                    save_watchlist(st.session_state.watchlist)
                    st.rerun()

        with st.spinner(f"{t('analyzing')} {target_symbol}..."):
            df = trading.get_market_data(api, target_symbol)
            if not df.empty:
                rsi = df.iloc[-1]['RSI']
                # 使用側邊欄設定的變數
                rsi_stat = t('healthy')
                if rsi > rsi_upper: rsi_stat = t('overbought')
                elif rsi < rsi_lower: rsi_stat = t('oversold')
                
                sig_txt, sig_col = trading.get_signal(df, target_symbol)
                
                if sig_col == "success": st.success(f"{t('tech_signal')}: {sig_txt} 🟢 | RSI: {rsi:.1f} {rsi_stat}")
                elif sig_col == "error": st.error(f"{t('tech_signal')}: {sig_txt} 🔴 | RSI: {rsi:.1f} {rsi_stat}")
                else: st.warning(f"{t('tech_signal')}: {sig_txt} ⚪ | RSI: {rsi:.1f} {rsi_stat}")

                fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_width=[0.2, 0.2, 0.6])
                fig.add_trace(go.Candlestick(x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name=t('legend_k')), row=1, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['SMA20'], line=dict(color='orange', width=1), name=t('legend_sma20')), row=1, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['SMA50'], line=dict(color='cyan', width=2), name=t('legend_sma50')), row=1, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['SMA200'], line=dict(color='blue', width=2), name=t('legend_sma200')), row=1, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='purple'), name='RSI'), row=2, col=1)
                
                # 使用側邊欄變數繪製 RSI 警戒線
                fig.add_hline(y=rsi_upper, line_dash="dash", line_color="red", row=2, col=1)
                fig.add_hline(y=rsi_lower, line_dash="dash", line_color="green", row=2, col=1)
                
                fig.add_trace(go.Bar(x=df.index, y=df['volume'], showlegend=False, marker_color='rgba(0,0,255,0.3)'), row=3, col=1)
                fig.update_layout(height=600, xaxis_rangeslider_visible=False, margin=dict(l=0,r=0,t=20,b=0))
                st.plotly_chart(fig, width='stretch')
                
                with st.expander("📖 圖表指標說明書 (SMA、RSI 是什麼？)"):
                    st.markdown("""
                    #### 1. 🕯️ K 線 (Candlestick) - 價格走勢
                    美股慣例：**🟢 綠漲 / 🔴 紅跌** - **實體 (粗)**：代表開盤價與收盤價的差距。
                    - **影線 (細)**：代表當天曾經去過的最高價與最低價。

                    #### 2. 📈 SMA 移動平均線 (均線) - 趨勢判斷
                    - **🟠 SMA20 (月線)**：短期趨勢。跌破通常代表短線轉弱。
                    - **🔵 SMA50 (季線)**：中期生命線。法人與大戶通常看這條。
                    - **🔵 SMA200 (年線)**：長期牛熊分界線。
                        - **股價 > 年線**：長多格局 (Bull)，適合做多。
                        - **股價 < 年線**：長空格局 (Bear)，建議空手或做空。

                    #### 3. 📊 RSI 相對強弱指標 - 抓轉折
                    - **範圍**：0 ~ 100。
                    - **⚠️ > 70 (過熱)**：買氣太強，隨時可能獲利回吐。
                    - **❄️ < 30 (超賣)**：恐慌過度，隨時可能反彈。
                    """)

                st.markdown("---")
                st.subheader(t('ai_analysis'))
                news = trading.get_stock_news(api, target_symbol)
                rpt, col, kws = brain.generate_ai_report(target_symbol, target_name, news, df)
                
                with st.container():
                    title = t('report_title') if col != "warning" else t('warning_title')
                    if col == "success": st.success(f"{title}\n\n{rpt}")
                    elif col == "error": st.error(f"{title}\n\n{rpt}")
                    elif col == "warning": st.warning(f"{title}\n\n{rpt}")
                    else: st.info(f"{title}\n\n{rpt}")
                    
                    st.write(t('gemini_keywords'))
                    tags = "".join([f"<span style='background-color:#eee; padding:4px 8px; margin:2px; border-radius:4px; color:#333'>{k}</span>" for k in kws])
                    st.markdown(tags, unsafe_allow_html=True)

                st.divider()
                st.caption(t('news_source'))
                for n in news[:5]:
                    with st.expander(f"{n['created_at'].strftime('%Y-%m-%d %H:%M')} | {n['headline']}"):
                        st.caption(f"Source: {n['source']}")
                        if n['summary']: st.write(n['summary'])
                        st.markdown(f"[Read More]({n['url']})")
            else:
                st.error(t('error_data'))

# -----------------------------------------------
# 🅱️ 模式二：期權策略 (Options) - 終極 AI 推薦版
# -----------------------------------------------
elif page_mode == "💰 期權策略 (Options)":
    st.title("💰 期權獵人 (Options Hunter)")
    st.caption("根據技術指標提供 Buy Call 或 Buy Put 建議 (資料來源: Yahoo Finance)")

    # 1. 選擇標的
    target = st.selectbox("🎯 請選擇標的", st.session_state.watchlist)
    
    if target:
        api = trading.get_api()
        # 獲取技術指標
        df = trading.get_market_data(api, target)
        
        if not df.empty:
            last_price = df.iloc[-1]['close']
            sma20 = df.iloc[-1]['SMA20']
            sma200 = df.iloc[-1]['SMA200']
            rsi = df.iloc[-1]['RSI']
            
            # 2. 策略判斷邏輯
            st.subheader(f"📊 {target} 現價: ${last_price:.2f}")
            col_s1, col_s2, col_s3 = st.columns(3)
            col_s1.metric("短期趨勢 (SMA20)", f"${sma20:.2f}", delta_color="normal")
            col_s2.metric("長期趨勢 (SMA200)", f"${sma200:.2f}", delta_color="normal")
            col_s3.metric("RSI 力道", f"{rsi:.1f}")

            # 核心判斷
            strategy_type = "WAIT" # CALL / PUT / WAIT
            strategy_text = "觀望 (Wait)"
            reason = "趨勢不明顯"
            color = "gray"
            
            # 簡單策略：黃金交叉 + RSI 健康 = Call
            if sma20 > sma200:
                if rsi < rsi_upper:
                    strategy_type = "CALL"
                    strategy_text = "🚀 建議：BUY CALL (看漲)"
                    reason = f"多頭排列 (SMA20 > 200) 且 RSI ({rsi:.1f}) 未過熱"
                    color = "green"
                else:
                    strategy_text = "⚠️ 警戒：過熱 (Overbought)"
                    reason = f"雖是多頭，但 RSI ({rsi:.1f}) 太高，小心回檔"
                    color = "orange"
            # 死亡交叉 + RSI 健康 = Put
            elif sma20 < sma200:
                if rsi > rsi_lower:
                    strategy_type = "PUT"
                    strategy_text = "📉 建議：BUY PUT (看跌)"
                    reason = f"空頭排列 (SMA20 < 200) 且 RSI ({rsi:.1f}) 未超賣"
                    color = "red"
                else:
                    strategy_text = "⚠️ 警戒：超賣 (Oversold)"
                    reason = f"雖是空頭，但 RSI ({rsi:.1f}) 太低，小心反彈"
                    color = "orange"

            st.markdown(f"""
            <div style="padding: 20px; border-radius: 10px; background-color: {'#e8f5e9' if color=='green' else '#ffebee' if color=='red' else '#fff3e0'}; border: 2px solid {color}; text-align: center;">
                <h2 style="color: {color}; margin:0;">{strategy_text}</h2>
                <p style="margin-top:10px; color: #555;">💡 原因：{reason}</p>
            </div>
            """, unsafe_allow_html=True)
            st.divider()

            # 3. 顯示期權鏈 (Option Chain)
            try:
                tk = yf.Ticker(target)
                _ = tk.info # 喚醒連線
                exps = tk.options
                
                if exps:
                    st.subheader("🗓️ 智慧選擇到期日")
                    
                    # 智慧選日演算法
                    from datetime import datetime
                    today = datetime.now().date()
                    
                    date_options = []
                    best_date_index = 0
                    min_diff_from_45 = 999 

                    for i, date_str in enumerate(exps):
                        exp_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                        dte = (exp_date - today).days
                        label = f"{date_str} (剩 {dte} 天)"
                        
                        risk_tag = ""
                        if dte < 7: risk_tag = "🔴 高風險"
                        elif 7 <= dte < 30: risk_tag = "🟠 中高風險"
                        elif 30 <= dte <= 60:
                            risk_tag = "🟢 最佳平衡"
                            diff = abs(dte - 45)
                            if diff < min_diff_from_45:
                                min_diff_from_45 = diff
                                best_date_index = i
                        else: risk_tag = "🔵 低風險"
                            
                        date_options.append(f"{label} | {risk_tag}")

                    selected_idx = st.selectbox("請選擇到期日 (AI 已為您預選最佳時機)", range(len(date_options)), format_func=lambda x: date_options[x], index=best_date_index)
                    selected_date = exps[selected_idx]
                    
                    # 抓取資料
                    opt = tk.option_chain(selected_date)
                    
                    # 根據策略決定要顯示 Call 還是 Put
                    if strategy_type == "CALL":
                        data = opt.calls
                        target_direction = "CALL"
                    elif strategy_type == "PUT":
                        data = opt.puts
                        target_direction = "PUT"
                    else:
                        # 如果是觀望或警告，預設顯示 Call 但不做推薦
                        data = opt.calls 
                        target_direction = "CALL"

                    # ----------------------------------------------------
                    # 🔥🔥🔥 AI 最佳 Strike 推薦算法 (Best Strike Algo) 🔥🔥🔥
                    # ----------------------------------------------------
                    if not data.empty and strategy_type in ["CALL", "PUT"]:
                        st.markdown("### 🤖 AI 推薦履約價 (Best Strike)")
                        
                        # 1. 找出 ATM (價平)：跟現價差距最小的
                        data['diff'] = abs(data['strike'] - last_price)
                        atm_row = data.sort_values('diff').iloc[0]
                        
                        # 2. 找出 ITM (價內) 和 OTM (價外)
                        # 注意：Call 和 Put 的方向是相反的
                        if target_direction == "CALL":
                            # Call ITM: Strike < Price (選履約價比現價低一點的)
                            itm_candidates = data[data['strike'] < last_price].sort_values('strike', ascending=False)
                            # Call OTM: Strike > Price (選履約價比現價高一點的)
                            otm_candidates = data[data['strike'] > last_price].sort_values('strike', ascending=True)
                        else: # PUT
                            # Put ITM: Strike > Price (選履約價比現價高一點的)
                            itm_candidates = data[data['strike'] > last_price].sort_values('strike', ascending=True)
                            # Put OTM: Strike < Price (選履約價比現價低一點的)
                            otm_candidates = data[data['strike'] < last_price].sort_values('strike', ascending=False)

                        itm_row = itm_candidates.iloc[0] if not itm_candidates.empty else atm_row
                        otm_row = otm_candidates.iloc[0] if not otm_candidates.empty else atm_row
                        
                        # 3. 顯示三張推薦卡片
                        c1, c2, c3 = st.columns(3)
                        
                        def show_card(col, title, row, desc, icon):
                            with col:
                                st.info(f"{icon} **{title}**")
                                st.write(f"履約價: **${row['strike']}**")
                                st.write(f"權利金: **${row['lastPrice']:.2f}**")
                                st.caption(f"{desc}")
                                st.caption(f"代碼: `{row['contractSymbol']}`")

                        show_card(c1, "保守型 (ITM)", itm_row, "勝率較高，價格較貴", "🛡️")
                        show_card(c2, "均衡型 (ATM)", atm_row, "🔥 AI 推薦：風險獲利最佳平衡", "⚖️")
                        show_card(c3, "積極型 (OTM)", otm_row, "以小博大，適合大行情", "🚀")

                        # 預設選中「均衡型」
                        default_contract = atm_row['contractSymbol']
                    
                    else:
                        default_contract = None

                    st.divider()

                    # 顯示完整表格 (給進階使用者看)
                    with st.expander(f"查看 {selected_date} 完整報價表", expanded=True):
                        # 簡單過濾與顯示
                        strike_min = last_price * 0.85
                        strike_max = last_price * 1.15
                        filtered_data = data[(data['strike'] > strike_min) & (data['strike'] < strike_max)]
                        
                        show_cols = ['contractSymbol', 'strike', 'lastPrice', 'bid', 'ask', 'volume', 'impliedVolatility']
                        existing_cols = [c for c in show_cols if c in filtered_data.columns]
                        
                        st.dataframe(filtered_data[existing_cols].style.format({
                            'lastPrice': '{:.2f}', 'bid': '{:.2f}', 'ask': '{:.2f}', 'impliedVolatility': '{:.2%}'
                        }), height=300)

                    # --- 📖 期權術語說明書 ---
                    with st.expander("📖 期權術語說明書 (新手必看)"):
                        st.markdown("""
                        - **ITM (價內)**: 比較貴，但已經有內在價值，比較安全。
                        - **ATM (價平)**: 履約價跟股價差不多，通常是交易最熱絡的。
                        - **OTM (價外)**: 很便宜，但如果到期前股價沒衝過去，就會歸零。
                        """)

                    st.divider()

                    # 🔥🔥🔥 4. 下單專區 (含損益平衡點計算) 🔥🔥🔥
                    st.subheader("⚡ 快速下單 (Paper Trading)")
                    
                    # 4.1 讓使用者選一個合約
                    contract_list = filtered_data['contractSymbol'].tolist() if 'filtered_data' in locals() else []
                    
                    # 嘗試保留使用者的選擇
                    default_idx = 0
                    if 'default_contract' in locals() and default_contract in contract_list:
                        default_idx = contract_list.index(default_contract)

                    if contract_list:
                        c1, c2 = st.columns([3, 1])
                        with c1:
                            target_contract = st.selectbox("📦 請選擇要交易的合約代碼", contract_list, index=default_idx)
                        with c2:
                            qty = st.number_input("張數", min_value=1, value=1)
                        
                        # 取得選中合約的詳細資料
                        selected_row = filtered_data[filtered_data['contractSymbol'] == target_contract].iloc[0]
                        limit_price = selected_row['lastPrice']          # 權利金 (單價)
                        strike_price = selected_row['strike']            # 履約價
                        est_cost = limit_price * 100 * qty               # 總成本

                        # ==========================================
                        # 🧮 自動算出：股價要漲到多少才賺錢？
                        # ==========================================
                        # 判斷是 Call 還是 Put
                        is_call = "C" in target_contract.split(str(int(strike_price)))[0] # 簡單判斷法
                        
                        if is_call:
                            # Call: 損益平衡點 = 履約價 + 權利金
                            breakeven = strike_price + limit_price
                            target_msg = f"股價需漲破 ${breakeven:.2f}"
                            color = "normal" # 綠色/黑色
                        else:
                            # Put: 損益平衡點 = 履約價 - 權利金
                            breakeven = strike_price - limit_price
                            target_msg = f"股價需跌破 ${breakeven:.2f}"
                            color = "inverse" # 紅色
                            
                        # 顯示儀表板
                        st.markdown("#### 💰 交易損益試算")
                        col_b1, col_b2, col_b3 = st.columns(3)
                        
                        # 1. 成本
                        col_b1.metric("💸 總投入成本 (Max Loss)", f"-${est_cost:.2f}", "最多就賠這樣", delta_color="inverse")
                        
                        # 2. 損益平衡點 (最重要的數字！)
                        col_b2.metric("🎯 獲利啟動價 (Breakeven)", f"${breakeven:.2f}", target_msg)
                        
                        # 3. 槓桿倍數 (額外資訊)
                        leverage = (last_price / limit_price) if limit_price > 0 else 0
                        col_b3.metric("🚀 預估槓桿", f"{leverage:.1f}x", f"股價漲1% 合約漲{leverage:.1f}%")

                        st.caption(f"ℹ️ 下單詳情: Limit Order @ ${limit_price:.2f} | 履約價: ${strike_price}")
                        
                        # ==========================================

                        # 4.3 下單按鈕
                        if st.button("🚀 送出訂單 (Buy Open)", type="primary"):
                            with st.spinner("下單中..."):
                                res = trading.execute_order(api, target_contract, 'buy', qty=qty, price=limit_price)
                                if "成功" in res or "已掛單" in res:
                                    st.success(res)
                                    st.balloons()
                                else:
                                    st.error(res)
                    else:
                        st.warning("⚠️ 目前篩選條件下無合約可選。")

                else:
                    st.warning("Yahoo Finance 暫時無法提供期權資料。")
            except Exception as e:
                st.error(f"無法讀取數據: {e}")

# -----------------------------------------------
# 🆎 模式三：我的資產 (Portfolio) - 含訂單管理
# -----------------------------------------------
elif page_mode == "💼 我的資產 (Portfolio)":
    st.title("💼 我的資產總覽 (Portfolio)")
    
    api = trading.get_api()
    
    # 1. 資金看板 (Account Summary)
    try:
        account = api.get_account()
        
        # 計算當日損益
        daily_pl = float(account.equity) - float(account.last_equity)
        daily_pl_pct = (daily_pl / float(account.last_equity)) * 100
        
        # 🔥 修改：顯示 Buying Power (購買力)
        st.markdown("### 🏦 資金狀態")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("💰 總資產 (Total Equity)", f"${float(account.equity):,.2f}")
        col2.metric("🔋 購買力 (Buying Power)", f"${float(account.buying_power):,.2f}", "還能買多少", delta_color="off")
        col3.metric("💵 現金 (Cash)", f"${float(account.cash):,.2f}")
        col4.metric("📈 今日損益 (Day P/L)", f"${daily_pl:,.2f}", f"{daily_pl_pct:.2f}%")
        
        st.divider()

        # 2. 訂單管理中心 (Orders) - 🔥 新增功能
        st.subheader("📋 訂單管理 (Orders)")
        
        # 2.1 ⏳ 掛單中 (Open Orders) - 也就是「等待交易」的單
        open_orders = api.list_orders(status='open')
        
        with st.expander("⏳ 掛單中 / 等待成交 (Open Orders)", expanded=True):
            if open_orders:
                o_data = []
                for o in open_orders:
                    # 判斷是買還是賣
                    side_emoji = "🟢 買進" if o.side == 'buy' else "🔴 賣出"
                    type_str = "限價 (Limit)" if o.type == 'limit' else "市價 (Market)"
                    price_str = f"${float(o.limit_price):.2f}" if o.limit_price else "市價"
                    
                    o_data.append({
                        "代碼": o.symbol,
                        "方向": side_emoji,
                        "類型": type_str,
                        "數量": int(o.qty),
                        "價格": price_str,
                        "狀態": "排隊中 (Accepted/Held)" if o.status in ['accepted', 'held', 'new'] else o.status,
                        "時間": o.created_at.strftime('%m-%d %H:%M')
                    })
                
                st.dataframe(pd.DataFrame(o_data), hide_index=True, use_container_width=True)
                
                # 取消訂單按鈕
                if st.button("❌ 取消所有掛單 (Cancel All)"):
                    api.cancel_all_orders()
                    st.success("已送出取消指令！")
                    time.sleep(1)
                    st.rerun()
            else:
                st.info("目前沒有正在等待的掛單。")

        # 2.2 ✅ 最近已成交 (Filled Orders) - 讓你知道買到了沒
        with st.expander("✅ 最近已成交紀錄 (Recent Fills)", expanded=False):
            # 抓取最近 10 筆已關閉(成交/取消)的訂單
            closed_orders = api.list_orders(status='closed', limit=10)
            if closed_orders:
                c_data = []
                for o in closed_orders:
                    if o.filled_at: # 只顯示真的有成交的
                        side_emoji = "🟢 買進" if o.side == 'buy' else "🔴 賣出"
                        avg_price = float(o.filled_avg_price) if o.filled_avg_price else 0
                        
                        c_data.append({
                            "代碼": o.symbol,
                            "方向": side_emoji,
                            "數量": int(o.filled_qty),
                            "成交價": f"${avg_price:.2f}",
                            "總金額": f"${(int(o.filled_qty) * avg_price):.2f}",
                            "時間": o.filled_at.strftime('%m-%d %H:%M')
                        })
                
                if c_data:
                    st.dataframe(pd.DataFrame(c_data), hide_index=True, use_container_width=True)
                else:
                    st.caption("最近沒有成交紀錄。")
            else:
                st.caption("查無歷史訂單。")

        st.divider()
        
        # 3. 持倉列表 (Positions) - 保持原本的功能
        st.subheader("📊 目前持倉 (Current Positions)")
        
        positions = api.list_positions()
        
        if positions:
            pos_data = []
            for p in positions:
                asset_type = "期權" if len(p.symbol) > 6 and any(c.isdigit() for c in p.symbol) else "股票"
                pl_val = float(p.unrealized_pl)
                pl_pct = float(p.unrealized_plpc) * 100
                
                pos_data.append({
                    "標的": p.symbol,
                    "類型": asset_type,
                    "數量": int(p.qty),
                    "成本": float(p.avg_entry_price),
                    "現價": float(p.current_price),
                    "損益 ($)": pl_val,
                    "報酬率 (%)": pl_pct
                })
            
            df_pos = pd.DataFrame(pos_data)
            
            st.dataframe(
                df_pos.style.format({
                    "成本": "${:.2f}", "現價": "${:.2f}", "損益 ($)": "${:+.2f}", "報酬率 (%)": "{:+.2f}%"
                }).applymap(lambda x: 'color: green' if x > 0 else 'color: red', subset=['損益 ($)', '報酬率 (%)']),
                height=400,
                use_container_width=True
            )
        else:
            st.info("📭 目前空手 (No Positions)")

    except Exception as e:
        st.error(f"讀取帳戶資料失敗: {e}")
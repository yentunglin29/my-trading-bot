# app.py

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
from i18n import t
import trading
import brain
import json
import os
import yfinance as yf

st.set_page_config(page_title="AlgoTrading 戰情室", layout="wide", page_icon="📈")

# ================= 🔐 安全登入檢查 (Security Check) =================
def check_password():
    """如果不對，回傳 False；如果對了，回傳 True"""
    # 如果已經登入過，直接放行
    if st.session_state.get('password_correct', False):
        return True

    # 顯示密碼輸入框
    st.title("🔒 請登入 (Login Required)")
    password = st.text_input("請輸入存取密碼", type="password")
    
    if st.button("登入"):
        # 比對 Secrets 裡的密碼
        if password == st.secrets["APP_PASSWORD"]:
            st.session_state['password_correct'] = True
            st.rerun()  # 密碼對了，重新整理畫面
        else:
            st.error("❌ 密碼錯誤")
    
    return False

# 🔥 如果密碼檢查沒通過，就直接在這裡「停住」，不執行後面的程式
if not check_password():
    st.stop()  # ⛔ 程式到此為止，駭客看不到後面的東西

# ================= 1. 初始化與設定 =================

# 這裡不再需要 Ngrok 的設定代碼

# ================= 2. 存檔與讀檔函數 =================
# 注意：在雲端上，WATCHLIST_FILE 會在每次重啟時重置。
# 如果要永久保存，需要連接資料庫，但目前先用簡單版即可。
WATCHLIST_FILE = "watchlist.json" 
DEFAULT_WATCHLIST = ["NVDA", "TSLA", "VOO", "PLTR", "SGOV"]

def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, 'r') as f: return json.load(f)
        except: return DEFAULT_WATCHLIST
    return DEFAULT_WATCHLIST

def save_watchlist(new_list):
    with open(WATCHLIST_FILE, 'w') as f: json.dump(new_list, f)

if 'language' not in st.session_state: st.session_state.language = 'zh'
if 'watchlist' not in st.session_state: st.session_state.watchlist = load_watchlist()

# ================= 3. 側邊欄 (導航與設定) =================
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
    # 修改 app.py 裡的導航選項
    st.header("🧭 導航模式")
    page_mode = st.radio("請選擇功能：", [
        "📈 股票戰情室 (Dashboard)", 
        "💰 期權策略 (Options)", 
        "🧪 回測實驗室 (Backtest)",
        "💼 我的資產 (Portfolio)",
        "📝 交易紀錄 (Log)"
    ], index=3)

    # --- 監控清單 ---
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
    
    # --- 策略參數 ---
    st.markdown("---")
    st.header("⚙️ 策略參數")
    rsi_upper = st.slider("RSI 超買 (賣出/警戒)", 70, 90, 70)
    rsi_lower = st.slider("RSI 超賣 (買進/警戒)", 10, 30, 30)

    # --- 自動交易 ---
    if page_mode == "📈 股票戰情室 (Dashboard)":
        st.markdown("---")
        st.header(t('auto_trade_title'))
        if 'trade_log' not in st.session_state: st.session_state.trade_log = []
        
        if st.button(t('run_strategy'), type="primary"):
            api = trading.get_api()
            st.session_state.trade_log = []
            progress = st.progress(0)
            status_txt = st.empty()
            
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
                
                st.session_state.trade_log.append(action_msg)
                time.sleep(0.5)
            
            status_txt.text("Done!")
            time.sleep(1)
            status_txt.empty()
            progress.empty()

        if st.session_state.trade_log:
            st.subheader(t('trade_log'))
            for log in st.session_state.trade_log: st.caption(log)
        
        # 持倉顯示 (簡易版)
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
                
                fig.add_hline(y=rsi_upper, line_dash="dash", line_color="red", row=2, col=1)
                fig.add_hline(y=rsi_lower, line_dash="dash", line_color="green", row=2, col=1)
                
                fig.add_trace(go.Bar(x=df.index, y=df['volume'], showlegend=False, marker_color='rgba(0,0,255,0.3)'), row=3, col=1)
                fig.update_layout(height=600, xaxis_rangeslider_visible=False, margin=dict(l=0,r=0,t=20,b=0))
                st.plotly_chart(fig, width='stretch')
                
                with st.expander("📖 圖表指標說明書"):
                    st.markdown("""
                    - **Candlestick**: 價格走勢。
                    - **SMA**: 平均線，用來判斷趨勢。
                    - **RSI**: 相對強弱，>70 太貴，<30 太便宜。
                    """)

                st.markdown("---")
                st.subheader(t('ai_analysis'))
                news = trading.get_stock_news(api, target_symbol)
                rpt, col, kws = brain.generate_ai_report(target_symbol, target_name, news, df)
                
                with st.container():
                    title = t('report_title') if col != "warning" else t('warning_title')
                    if col == "success": st.success(f"{title}\n\n{rpt}")
                    elif col == "error": st.error(f"{title}\n\n{rpt}")
                    else: st.info(f"{title}\n\n{rpt}")
                    
                    st.write(t('gemini_keywords'))
                    tags = "".join([f"<span style='background-color:#eee; padding:4px 8px; margin:2px; border-radius:4px; color:#333'>{k}</span>" for k in kws])
                    st.markdown(tags, unsafe_allow_html=True)

                st.divider()
                st.caption(t('news_source'))
                for n in news[:5]:
                    with st.expander(f"{n['created_at'].strftime('%Y-%m-%d %H:%M')} | {n['headline']}"):
                        st.markdown(f"[Read More]({n['url']})")
            else:
                st.error(t('error_data'))

# -----------------------------------------------
# 🆎 模式二：期權獵人 + 翻倍戰術 (Merged)
# -----------------------------------------------
elif page_mode == "💰 期權策略 (Options)":
    st.title("💰 期權獵人 (附帶翻倍戰術)")
    st.caption("結合趨勢分析、AI 履約價推薦，並支援「1/13 翻倍戰術」自動佈局。")

    # --- 1. 標的與趨勢分析 ---
    target = st.selectbox("🎯 請選擇標的", st.session_state.watchlist)
    
    if target:
        api = trading.get_api()
        df = trading.get_market_data(api, target)
        
        if not df.empty:
            last_price = df.iloc[-1]['close']
            sma20 = df.iloc[-1]['SMA20']
            sma200 = df.iloc[-1]['SMA200']
            rsi = df.iloc[-1]['RSI']
            
            st.subheader(f"📊 {target} 現價: ${last_price:.2f}")
            col_s1, col_s2, col_s3 = st.columns(3)
            col_s1.metric("短期趨勢", f"${sma20:.2f}")
            col_s2.metric("長期趨勢", f"${sma200:.2f}")
            col_s3.metric("RSI", f"{rsi:.1f}")

            # 策略信號判斷
            strategy_type = "WAIT"
            strategy_text = "觀望 (Wait)"
            reason = "趨勢不明顯"
            color = "gray"
            
            if sma20 > sma200:
                if rsi < rsi_upper:
                    strategy_type = "CALL"
                    strategy_text = "🚀 建議：BUY CALL (看漲)"
                    reason = f"多頭排列且 RSI 未過熱"
                    color = "green"
                else:
                    strategy_text = "⚠️ 警戒：過熱"
                    reason = "RSI 太高"
                    color = "orange"
            elif sma20 < sma200:
                if rsi > rsi_lower:
                    strategy_type = "PUT"
                    strategy_text = "📉 建議：BUY PUT (看跌)"
                    reason = f"空頭排列且 RSI 未超賣"
                    color = "red"
                else:
                    strategy_text = "⚠️ 警戒：超賣"
                    reason = "RSI 太低"
                    color = "orange"

            st.markdown(f"""
            <div style="padding: 20px; border-radius: 10px; background-color: {'#e8f5e9' if color=='green' else '#ffebee' if color=='red' else '#fff3e0'}; border: 2px solid {color}; text-align: center;">
                <h2 style="color: {color}; margin:0;">{strategy_text}</h2>
                <p style="margin-top:10px; color: #555;">💡 原因：{reason}</p>
            </div>
            """, unsafe_allow_html=True)
            st.divider()

            try:
                tk = yf.Ticker(target)
                exps = tk.options
                
                if exps:
                    # --- 2. 智慧選擇到期日 ---
                    st.subheader("🗓️ 智慧選擇到期日")
                    from datetime import datetime
                    today = datetime.now().date()
                    
                    date_options = []
                    best_date_index = 0
                    min_diff_from_45 = 999 

                    for i, date_str in enumerate(exps):
                        exp_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                        dte = (exp_date - today).days
                        label = f"{date_str} (剩 {dte} 天)"
                        risk_tag = "🔴 高風險" if dte < 7 else ("🟠 中高風險" if dte < 30 else ("🟢 最佳平衡" if dte <= 60 else "🔵 低風險"))
                        if 30 <= dte <= 60:
                            diff = abs(dte - 45)
                            if diff < min_diff_from_45:
                                min_diff_from_45 = diff
                                best_date_index = i
                        date_options.append(f"{label} | {risk_tag}")

                    selected_idx = st.selectbox("到期日", range(len(date_options)), format_func=lambda x: date_options[x], index=best_date_index)
                    selected_date = exps[selected_idx]
                    opt = tk.option_chain(selected_date)
                    
                    # 根據策略信號自動選擇 Call 或 Put
                    if strategy_type == "CALL":
                        data = opt.calls
                        target_direction = "CALL"
                    elif strategy_type == "PUT":
                        data = opt.puts
                        target_direction = "PUT"
                    else:
                        data = opt.calls
                        target_direction = "CALL" # 預設

                    if not data.empty:
                        # --- 3. AI 推薦履約價 ---
                        st.markdown("### 🤖 AI 推薦履約價")
                        data['diff'] = abs(data['strike'] - last_price)
                        atm_row = data.sort_values('diff').iloc[0]
                        
                        if target_direction == "CALL":
                            itm_candidates = data[data['strike'] < last_price].sort_values('strike', ascending=False)
                            otm_candidates = data[data['strike'] > last_price].sort_values('strike', ascending=True)
                        else:
                            itm_candidates = data[data['strike'] > last_price].sort_values('strike', ascending=True)
                            otm_candidates = data[data['strike'] < last_price].sort_values('strike', ascending=False)

                        itm_row = itm_candidates.iloc[0] if not itm_candidates.empty else atm_row
                        otm_row = otm_candidates.iloc[0] if not otm_candidates.empty else atm_row
                        
                        c1, c2, c3 = st.columns(3)
                        def show_card(col, title, row, desc, icon):
                            with col:
                                st.info(f"{icon} **{title}**")
                                st.write(f"Strike: **${row['strike']}**")
                                st.write(f"Ask: **${row['ask']:.2f}**") # 顯示 Ask 價格比較準確
                                st.caption(f"{desc}")
                                st.caption(f"Code: `{row['contractSymbol']}`")

                        show_card(c1, "保守型 (ITM)", itm_row, "勝率較高", "🛡️")
                        show_card(c2, "均衡型 (ATM)", atm_row, "AI 推薦", "⚖️")
                        show_card(c3, "積極型 (OTM)", otm_row, "以小博大", "🚀")
                        default_contract = atm_row['contractSymbol']
                        
                        # 準備下拉選單資料
                        strike_min = last_price * 0.85
                        strike_max = last_price * 1.15
                        filtered_data = data[(data['strike'] > strike_min) & (data['strike'] < strike_max)]
                        
                    else:
                        default_contract = None
                        st.warning("無資料")

                    st.divider()

                    # --- 4. 終極下單區 (結合實戰策略) ---
                    st.subheader("⚡ 執行交易 (Execution)")
                    
                    contract_list = filtered_data['contractSymbol'].tolist() if 'filtered_data' in locals() else []
                    default_idx = 0
                    if default_contract and default_contract in contract_list:
                        default_idx = contract_list.index(default_contract)

                    if contract_list:
                        # 選擇合約
                        c1, c2 = st.columns([3, 1])
                        with c1: 
                            target_contract = st.selectbox("📦 合約代碼", contract_list, index=default_idx)
                        
                        # 取得選中合約的詳細資料
                        selected_row = filtered_data[filtered_data['contractSymbol'] == target_contract].iloc[0]
                        limit_price = selected_row['ask'] # 使用 Ask 作為買入價
                        if limit_price == 0: limit_price = selected_row['lastPrice'] # 防呆

                        # === 🔥 策略選擇開關 ===
                        use_strategy = st.checkbox("🔥 啟用保底策略 (買入後，自動掛出一半部位翻倍賣單)", value=False)
                        
                        with c2: 
                            if use_strategy:
                                # 如果啟用策略，數量必須是雙數，且至少為 2
                                qty = st.number_input("張數 (自動調整為偶數)", min_value=2, value=2, step=2)
                                if qty % 2 != 0: qty += 1
                                st.caption(f"將會: 買 {qty} 張, 賣 {int(qty/2)} 張")
                            else:
                                qty = st.number_input("張數", min_value=1, value=1)
                        
                        # 損益試算
                        # === 取得 strike price 以計算損益平衡 ===
                        strike_price = selected_row['strike']
                        
                        # 計算損益平衡點 (Breakeven) - 這就是原本 "漲到多少就賺錢"
                        # 判斷是 Call 還是 Put
                        if target_direction == "CALL":
                             breakeven = strike_price + limit_price
                             breakeven_msg = f"股價需 > {breakeven:.2f}"
                             icon = "📈"
                        else: # PUT
                             breakeven = strike_price - limit_price
                             breakeven_msg = f"股價需 < {breakeven:.2f}"
                             icon = "📉"

                        # 損益試算數值
                        est_cost = limit_price * 100 * qty
                        target_sell_price = limit_price * 2.0
                        
                        st.markdown("#### 💰 交易試算")
                        c1, c2, c3, c4 = st.columns(4)
                        
                        c1.metric("💸 總成本", f"-${est_cost:.2f}")
                        
                        # 這是您要找回來的：
                        c2.metric("🚀 獲利啟動點", f"${breakeven:.2f}", breakeven_msg)

                        if use_strategy:
                            c3.metric("⚡ 翻倍賣出價", f"${target_sell_price:.2f}", "權利金 +100%")
                            c4.metric("🛡️ 戰術結果", "零成本", "剩餘部位免費")
                        else:
                            c3.metric("📦 買入權利金", f"${limit_price:.2f}")
                            c4.metric("⚖️ 交易模式", "一般買入")

                        # === 執行按鈕 ===
                        btn_text = f"🚀 執行翻倍戰術 (Buy {qty})" if use_strategy else "🚀 送出普通訂單"
                        if st.button(btn_text, type="primary"):
                            progress = st.progress(0)
                            status_box = st.empty()
                            
                            try:
                                # 1. 送出買單 (Limit Buy)
                                status_box.text(f"1/3 送出買單: {target_contract} x {qty} @ ${limit_price}...")
                                progress.progress(20)
                                
                                buy_order = api.submit_order(
                                    symbol=target_contract,
                                    qty=qty,
                                    side='buy',
                                    type='limit',
                                    limit_price=limit_price,
                                    time_in_force='day'
                                )
                                progress.progress(50)
                                
                                if use_strategy:
                                    # 2. 策略模式：等待成交並掛賣單
                                    status_box.text(f"2/3 訂單已送出，等待成交以執行策略... (ID: {buy_order.id})")
                                    
                                    # 簡易輪詢等待成交 (最多等 10 秒，避免卡死)
                                    filled = False
                                    real_avg_price = limit_price
                                    
                                    for _ in range(10):
                                        time.sleep(1)
                                        o = api.get_order(buy_order.id)
                                        if o.status == 'filled':
                                            filled = True
                                            real_avg_price = float(o.filled_avg_price)
                                            break
                                    
                                    if filled:
                                        progress.progress(80)
                                        # 3. 掛出翻倍賣單
                                        sell_qty = int(qty / 2)
                                        sell_price = round(real_avg_price * 2.0, 2)
                                        status_box.text(f"3/3 成交價 ${real_avg_price}。掛出保本賣單: {sell_qty}張 @ ${sell_price}...")
                                        
                                        api.submit_order(
                                            symbol=target_contract,
                                            qty=sell_qty,
                                            side='sell',
                                            type='limit',
                                            limit_price=sell_price,
                                            time_in_force='gtc' # 永久有效
                                        )
                                        progress.progress(100)
                                        st.balloons()
                                        st.success(f"✅ 戰術執行成功！\n買入均價: ${real_avg_price}\n已掛賣單: {sell_qty} 張 @ ${sell_price}")
                                    else:
                                        progress.progress(100)
                                        st.warning(f"⚠️ 買單已送出但尚未成交 (狀態: {o.status})。請稍後至「我的資產」手動設定自動停利。")
                                else:
                                    # 普通模式
                                    progress.progress(100)
                                    st.success(f"✅ 訂單已送出！ (狀態: {buy_order.status})")
                                    st.balloons()

                            except Exception as e:
                                st.error(f"交易失敗: {e}")

                else:
                    st.warning("Yahoo Finance 暫時無法提供數據。")
            except Exception as e:
                st.error(f"Error: {e}")

# -----------------------------------------------
# 🆎 模式三：我的資產 (Portfolio) - 含智慧自動賣出
# -----------------------------------------------
elif page_mode == "💼 我的資產 (Portfolio)":
    st.title("💼 我的資產總覽 (Portfolio)")
    
    api = trading.get_api()
    
    # 1. 資金看板
    try:
        account = api.get_account()
        daily_pl = float(account.equity) - float(account.last_equity)
        daily_pl_pct = (daily_pl / float(account.last_equity)) * 100
        
        st.markdown("### 🏦 資金狀態")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("💰 總資產", f"${float(account.equity):,.2f}")
        col2.metric("🔋 購買力", f"${float(account.buying_power):,.2f}")
        col3.metric("💵 現金", f"${float(account.cash):,.2f}")
        col4.metric("📈 今日損益", f"${daily_pl:,.2f}", f"{daily_pl_pct:.2f}%")
        
        st.divider()

        # 2. 訂單管理 (這裡很重要，可以看到你的自動單)
        st.subheader("📋 訂單管理 (Orders)")
        open_orders = api.list_orders(status='open')
        with st.expander("⏳ 掛單中 (已預約的自動賣單)", expanded=True):
            if open_orders:
                o_data = []
                for o in open_orders:
                    # 嘗試計算這張單是為了停利多少%
                    # 這需要知道持倉成本，這裡先簡單顯示
                    side_str = "🟢 買入" if o.side == 'buy' else "🔴 賣出"
                    limit_price = float(o.limit_price) if o.limit_price else 0
                    o_data.append({
                        "代碼": o.symbol,
                        "方向": side_str,
                        "數量": int(o.qty),
                        "目標價 (Limit)": f"${limit_price:.2f}",
                        "狀態": o.status, # held 代表夜間掛單，new/accepted 代表盤中
                        "有效期": o.time_in_force # gtc 代表永久有效
                    })
                st.dataframe(pd.DataFrame(o_data), hide_index=True, use_container_width=True)
                
                if st.button("❌ 取消所有掛單 (重設策略)"):
                    api.cancel_all_orders()
                    st.success("已取消所有掛單！")
                    time.sleep(1)
                    st.rerun()
            else:
                st.info("目前沒有掛單。")

# 3. 持倉列表 (修改版：分開顯示股票與期權)
        st.divider()
        st.subheader("📊 目前持倉 (Current Positions)")
        positions = api.list_positions()
        
        if positions:
            # 準備兩個清單分別存放
            stock_data = []
            option_data = []
            
            # 用來做下拉選單的列表 (維持原功能)
            sell_options = []
            
            for p in positions:
                # 判斷是否為期權 (長度>6且包含數字)
                is_option = len(p.symbol) > 6 and any(c.isdigit() for c in p.symbol)
                sell_options.append(f"{p.symbol}")
                
                # 建立顯示資料
                row = {
                    "代碼": p.symbol,
                    "數量": int(p.qty),
                    "成本": float(p.avg_entry_price),
                    "現價": float(p.current_price),
                    "損益 ($)": float(p.unrealized_pl),
                    "報酬率 (%)": float(p.unrealized_plpc) * 100
                }
                
                # 分類存入
                if is_option:
                    option_data.append(row)
                else:
                    stock_data.append(row)
            
            # --- 定義顯示表格樣式的函式 (避免重複寫程式碼) ---
            def show_position_table(data_list):
                st.dataframe(
                    pd.DataFrame(data_list).style.format({
                        "成本": "${:.2f}", "現價": "${:.2f}", 
                        "損益 ($)": "${:+.2f}", "報酬率 (%)": "{:+.2f}%"
                    }).applymap(lambda x: 'color: green' if x > 0 else 'color: red', subset=['損益 ($)', '報酬率 (%)']),
                    use_container_width=True,
                    hide_index=True # 隱藏索引欄位比較美觀
                )

            # --- A. 顯示股票持倉 ---
            if stock_data:
                st.markdown("#### 🏢 股票 (Stocks)")
                show_position_table(stock_data)
            else:
                # 如果沒有股票，也可以選擇不顯示或顯示提示
                # st.caption("無股票持倉") 
                pass

            # --- B. 顯示期權持倉 ---
            if option_data:
                st.divider() # 加個分隔線區隔
                st.markdown("#### 💰 期權 (Options)")
                show_position_table(option_data)
            else:
                pass

            # ==========================================
            # 🔥🔥🔥 4. 機器人：自動出場設定 (Auto Exit) 🔥🔥🔥
            # ==========================================
            st.markdown("---")
            st.subheader("🤖 自動停利設定 (Auto Take Profit)")
            st.caption("設定好目標後，系統會送出單，達標自動賣出。")
            
            c1, c2, c3 = st.columns([2, 1, 1])
            with c1:
                target_symbol = st.selectbox("📦 選擇持倉", [p.symbol for p in positions])
            
            # 找出選中持倉的成本
            target_pos = next(p for p in positions if p.symbol == target_symbol)
            avg_cost = float(target_pos.avg_entry_price)
            current_qty = int(target_pos.qty)

            with c2:
                # 選擇獲利目標 %
                profit_target = st.select_slider(
                    "🎯 獲利目標 (Take Profit)", 
                    options=[10, 20, 30, 50, 100, 200], 
                    value=30,
                    format_func=lambda x: f"+{x}%"
                )
            
            with c3:
                qty_to_sell = st.number_input("賣出數量", min_value=1, max_value=current_qty, value=current_qty)

            # 計算目標價格
            target_price = avg_cost * (1 + profit_target/100)
            
            # 期權價格通常有最小跳動單位 (0.01 或 0.05)，這裡簡單取小數點兩位
            target_price = round(target_price, 2)
            
            st.info(f"💡 策略邏輯：當 **{target_symbol}** 從成本 `${avg_cost:.2f}` 漲到 **`${target_price:.2f}`** (+{profit_target}%) 時，自動賣出 {qty_to_sell} 張。")

            if st.button(f"🚀 啟動自動停利 (Set & Forget)", type="primary"):
                with st.spinner("設定中..."):
                    try:
                        # 這種單子會一直掛在 Alpaca 伺服器上，直到成交或你取消，不用開電腦
                        api.submit_order(
                            symbol=target_symbol,
                            qty=qty_to_sell,
                            side='sell',
                            type='limit',
                            limit_price=target_price,
                            time_in_force='day'
                        )
                        st.success(f"✅ 設定成功！已掛出賣單 @ ${target_price:.2f}。")
                        st.balloons()
                        time.sleep(2)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ 設定失敗: {e}")
                        st.caption("提示：如果該標的已有其他掛單，請先到上方『取消所有掛單』再重新設定。")

        else:
            st.info("📭 目前空手，無可設定的資產。")

    except Exception as e:
        st.error(f"讀取帳戶資料失敗: {e}")


# ========================================================
# 交易紀錄 (Trade Log)
# ========================================================
elif page_mode == "📝 交易紀錄 (Log)":
    st.title("📝 交易紀錄簿 (Trade Log)")
    
    api = trading.get_api()
    
    # 過濾器
    col1, col2 = st.columns([3, 1])
    with col1:
        log_filter = st.radio("顯示類別", ["全部 (All)", "已成交 (Filled)", "掛單中 (Open)"], horizontal=True)
    with col2:
        if st.button("🔄 刷新紀錄"):
            st.rerun()
            
    status_map = {"全部 (All)": "all", "已成交 (Filled)": "closed", "掛單中 (Open)": "open"}
    target_status = status_map[log_filter]
    
    # 獲取資料
    with st.spinner("載入訂單資料中..."):
        df_orders = trading.get_orders_history(api, status=target_status)
    
    if not df_orders.empty:
        # 針對掛單中 (Open) 的訂單提供「取消」功能
        if target_status == 'open' or log_filter == "全部 (All)":
            st.info("💡 提示：勾選左側框框可選取，下方按鈕可取消掛單。")
            
            # 使用 DataEditor 讓使用者可以勾選 (Streamlit 新功能)
            # 這裡簡單一點，直接顯示表格，後面加按鈕
            
            for index, row in df_orders.iterrows():
                # 只對 Open 狀態顯示取消按鈕
                if row['狀態'] in ['new', 'accepted', 'partially_filled', 'held']:
                    c1, c2 = st.columns([5, 1])
                    with c1:
                        st.text(f"{row['時間 (提交)']} | {row['代碼']} | {row['方向']} {row['數量']} @ {row['類型']}")
                    with c2:
                        if st.button("❌ 取消", key=f"cancel_{row['ID']}"):
                            if trading.cancel_order(api, row['ID']):
                                st.success("已取消")
                                time.sleep(0.5)
                                st.rerun()
                            else:
                                st.error("取消失敗")
                    st.divider()
                else:
                    # 已成交或已取消的，顯示簡單列表
                    st.caption(f"{row['時間 (提交)']} | {row['代碼']} | {row['方向']} {row['數量']} | 均價: ${row['成交均價']} | {row['狀態']}")
        else:
            # 純顯示表格
            st.dataframe(df_orders, use_container_width=True, hide_index=True)
    else:
        st.info("📭 目前沒有相關的訂單紀錄。")

# ========================================================
# 🧪 回測實驗室 (Backtest Lab)
# ========================================================
elif page_mode == "🧪 回測實驗室 (Backtest)":
    st.title("🧪 策略回測實驗室 (Backtest Lab)")
    st.markdown("""
    **功能說明**：運用歷史數據驗證你的策略。
    
    這裡我們回測最經典的 **「趨勢跟隨 + RSI 濾網」** 策略，這是大多數量化策略的基石。
    * **買入訊號**：當股價站上短期均線 (SMA Short) 且 RSI 未過熱。
    * **賣出訊號**：當股價跌破長期均線 (SMA Long) 或 RSI 過高 (止盈)。
    """)

    # --- 1. 回測參數設定 ---
    st.sidebar.header("⚙️ 回測參數")
    my_backtest_list = st.session_state.watchlist if st.session_state.watchlist else ["NVDA", "TSLA", "PLTR", "AMD", "AAPL", "SPY", "QQQ"]
    # 標的與時間
    bc1, bc2 = st.columns(2)
    with bc1:
        backtest_symbol = st.selectbox("回測標的 (從監控清單)", my_backtest_list, index=0)
    with bc2:
        initial_capital = st.number_input("初始資金 ($)", value=10000, step=1000)

    # 策略參數
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        sma_short = st.number_input("短期均線 (進場)", value=20, min_value=5)
    with c2:
        sma_long = st.number_input("長期均線 (出場)", value=50, min_value=10)
    with c3:
        rsi_buy_max = st.number_input("RSI 上限 (買入濾網)", value=70, help="RSI 高於此值不買 (避免追高)")
    with c4:
        stop_loss_pct = st.number_input("停損 (%)", value=10.0, step=1.0) / 100

    days_back = st.slider("回測天數 (Days Lookback)", 100, 1000, 365)

    # --- 2. 執行回測 ---
    if st.button("🚀 開始回測 (Run Backtest)", type="primary"):
        status_text = st.empty()
        status_text.text("正在下載歷史數據...")
        
        try:
            # 下載數據
            df = trading.get_market_data(trading.get_api(), backtest_symbol, days=days_back+50) # 多抓一點算SMA
            
            if df.empty:
                st.error("❌ 無法獲取數據，請檢查標的或網絡。")
            else:
                status_text.text("計算技術指標...")
                
                # 計算策略指標
                df['SMA_S'] = df['close'].rolling(window=sma_short).mean()
                df['SMA_L'] = df['close'].rolling(window=sma_long).mean()
                # RSI 已經在 get_market_data 裡算好了，直接用 df['RSI']
                
                # 初始化回測變數
                cash = initial_capital
                position = 0 # 持股數量
                equity_curve = []
                trade_log = []
                entry_price = 0
                
                # 開始逐日模擬 (從資料足夠那天開始)
                start_idx = max(sma_long, 50) 
                
                status_text.text("正在逐日模擬交易...")
                
                for i in range(start_idx, len(df)):
                    today = df.iloc[i]
                    prev = df.iloc[i-1]
                    date = df.index[i].strftime('%Y-%m-%d')
                    price = today['close']
                    
                    action = "HOLD"
                    
                    # --- 賣出邏輯 (Sell Logic) ---
                    if position > 0:
                        # 1. 跌破長期均線 -> 趨勢反轉，賣出
                        if price < today['SMA_L']:
                            reason = f"跌破 SMA{sma_long}"
                            action = "SELL"
                        # 2. 停損 (Stop Loss)
                        elif price < entry_price * (1 - stop_loss_pct):
                            reason = f"觸發停損 (-{stop_loss_pct*100}%)"
                            action = "SELL"
                        
                        if action == "SELL":
                            cash += position * price
                            profit = (price - entry_price) * position
                            profit_pct = (price / entry_price) - 1
                            trade_log.append({
                                "日期": date, "動作": "🔴 賣出", "價格": price, 
                                "數量": position, "損益": profit, "報酬率": f"{profit_pct*100:.1f}%", "原因": reason
                            })
                            position = 0
                            entry_price = 0

                    # --- 買入邏輯 (Buy Logic) ---
                    elif position == 0:
                        # 策略：收盤價站上 短期均線 且 RSI 沒有過熱
                        if price > today['SMA_S'] and today['RSI'] < rsi_buy_max:
                            # 全倉買入 (模擬)
                            position = int(cash / price)
                            if position > 0:
                                cost = position * price
                                cash -= cost
                                entry_price = price
                                trade_log.append({
                                    "日期": date, "動作": "🔵 買入", "價格": price, 
                                    "數量": position, "損益": 0, "報酬率": "-", "原因": f"站上 SMA{sma_short}"
                                })

                    # 紀錄當日總資產
                    total_value = cash + (position * price)
                    equity_curve.append({"Date": df.index[i], "Equity": total_value})

                status_text.empty()
                
                # --- 3. 顯示結果報告 ---
                if not equity_curve:
                    st.warning("在此期間內沒有觸發任何交易。")
                else:
                    df_eq = pd.DataFrame(equity_curve).set_index("Date")
                    final_value = df_eq.iloc[-1]['Equity']
                    total_return = (final_value - initial_capital) / initial_capital
                    
                    # 計算買入持有 (Buy & Hold) 的績效作為對比
                    start_price = df.iloc[start_idx]['close']
                    end_price = df.iloc[-1]['close']
                    bh_return = (end_price - start_price) / start_price
                    
                    # 顯示 KPI
                    st.subheader("📊 回測績效報告")
                    k1, k2, k3, k4 = st.columns(4)
                    k1.metric("最終資產", f"${final_value:,.0f}")
                    k2.metric("策略報酬率", f"{total_return*100:.1f}%", 
                              delta=f"{(total_return - bh_return)*100:.1f}% vs Buy&Hold",
                              help="綠色代表戰勝大盤(買入持有)，紅色代表輸給大盤")
                    k3.metric("交易次數", f"{len([t for t in trade_log if t['動作']=='🔴 賣出'])}")
                    
                    # 勝率計算
                    wins = [t for t in trade_log if t['動作']=='🔴 賣出' and t['損益'] > 0]
                    total_trades = len([t for t in trade_log if t['動作']=='🔴 賣出'])
                    win_rate = len(wins) / total_trades if total_trades > 0 else 0
                    k4.metric("勝率 (Win Rate)", f"{win_rate*100:.0f}%")

                    # 繪製權益曲線
                    st.subheader("📈 資產成長曲線 (Equity Curve)")
                    
                    fig = make_subplots(specs=[[{"secondary_y": True}]])
                    
                    # 策略曲線
                    fig.add_trace(go.Scatter(
                        x=df_eq.index, y=df_eq['Equity'], 
                        name="策略回報 (Strategy)", line=dict(color='green', width=2)
                    ), secondary_y=False)
                    
                    # 股價曲線 (對照用)
                    df_bench = df.iloc[start_idx:].copy()
                    fig.add_trace(go.Scatter(
                        x=df_bench.index, y=df_bench['close'], 
                        name=f"{backtest_symbol} 股價", line=dict(color='gray', dash='dot')
                    ), secondary_y=True)
                    
                    fig.update_layout(title="你的策略 vs 股價走勢", hovermode="x unified")
                    fig.update_yaxes(title_text="總資產 ($)", secondary_y=False)
                    fig.update_yaxes(title_text="股價 ($)", secondary_y=True)
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # 交易明細
                    with st.expander("📝 查看詳細交易紀錄 (Trade Log)"):
                        st.dataframe(pd.DataFrame(trade_log))

        except Exception as e:
            st.error(f"回測發生錯誤: {e}")
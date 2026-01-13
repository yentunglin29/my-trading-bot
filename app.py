# app.py
# 這是主程式，請執行: streamlit run app.py

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
# import config # 雲端版不需要 config，改用 trading.py 裡的 secrets
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
        "⚡ 實戰策略 (Strategy)", 
        "⏰ 定時自動掛機 (Auto-Pilot)", 
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
# 🅱️ 模式二：期權策略 (Options)
# -----------------------------------------------
elif page_mode == "💰 期權策略 (Options)":
    st.title("💰 期權獵人 (Options Hunter)")
    st.caption("根據技術指標提供 Buy Call 或 Buy Put 建議 (資料來源: Yahoo Finance)")

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
                _ = tk.info
                exps = tk.options
                
                if exps:
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
                    
                    if strategy_type == "CALL":
                        data = opt.calls
                        target_direction = "CALL"
                    elif strategy_type == "PUT":
                        data = opt.puts
                        target_direction = "PUT"
                    else:
                        data = opt.calls
                        target_direction = "CALL"

                    if not data.empty and strategy_type in ["CALL", "PUT"]:
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
                                st.write(f"Price: **${row['lastPrice']:.2f}**")
                                st.caption(f"{desc}")
                                st.caption(f"Code: `{row['contractSymbol']}`")

                        show_card(c1, "保守型 (ITM)", itm_row, "勝率較高", "🛡️")
                        show_card(c2, "均衡型 (ATM)", atm_row, "AI 推薦", "⚖️")
                        show_card(c3, "積極型 (OTM)", otm_row, "以小博大", "🚀")
                        default_contract = atm_row['contractSymbol']
                    else:
                        default_contract = None

                    st.divider()
                    
                    with st.expander(f"查看 {selected_date} 完整報價表", expanded=True):
                        strike_min = last_price * 0.85
                        strike_max = last_price * 1.15
                        filtered_data = data[(data['strike'] > strike_min) & (data['strike'] < strike_max)]
                        st.dataframe(filtered_data[['contractSymbol', 'strike', 'lastPrice', 'bid', 'ask', 'volume', 'impliedVolatility']], height=300)

                    st.divider()

                    st.subheader("⚡ 快速下單 (Paper Trading)")
                    contract_list = filtered_data['contractSymbol'].tolist() if 'filtered_data' in locals() else []
                    default_idx = 0
                    if default_contract and default_contract in contract_list:
                        default_idx = contract_list.index(default_contract)

                    if contract_list:
                        c1, c2 = st.columns([3, 1])
                        with c1: target_contract = st.selectbox("📦 合約代碼", contract_list, index=default_idx)
                        with c2: qty = st.number_input("張數", min_value=1, value=1)
                        
                        selected_row = filtered_data[filtered_data['contractSymbol'] == target_contract].iloc[0]
                        limit_price = selected_row['lastPrice']
                        strike_price = selected_row['strike']
                        est_cost = limit_price * 100 * qty
                        
                        is_call = "C" in target_contract.split(str(int(strike_price)))[0]
                        if is_call:
                            breakeven = strike_price + limit_price
                            target_msg = f"漲破 ${breakeven:.2f}"
                        else:
                            breakeven = strike_price - limit_price
                            target_msg = f"跌破 ${breakeven:.2f}"
                            
                        st.markdown("#### 💰 損益試算")
                        cb1, cb2, cb3 = st.columns(3)
                        cb1.metric("💸 總成本", f"-${est_cost:.2f}")
                        cb2.metric("🎯 獲利啟動價", f"${breakeven:.2f}", target_msg)
                        
                        if st.button("🚀 送出訂單", type="primary"):
                            with st.spinner("下單中..."):
                                res = trading.execute_order(api, target_contract, 'buy', qty=qty, price=limit_price)
                                if "成功" in res or "已掛單" in res:
                                    st.success(res)
                                    st.balloons()
                                else:
                                    st.error(res)
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

        # 3. 持倉列表
        st.divider()
        st.subheader("📊 目前持倉 (Current Positions)")
        positions = api.list_positions()
        
        if positions:
            # 準備下拉選單的資料
            sell_options = []
            
            pos_data = []
            for p in positions:
                is_option = len(p.symbol) > 6 and any(c.isdigit() for c in p.symbol)
                sell_options.append(f"{p.symbol}")
                
                pos_data.append({
                    "代碼": p.symbol,
                    "類型": "期權" if is_option else "股票",
                    "數量": int(p.qty),
                    "成本": float(p.avg_entry_price),
                    "現價": float(p.current_price),
                    "損益 ($)": float(p.unrealized_pl),
                    "報酬率 (%)": float(p.unrealized_plpc) * 100
                })
            
            st.dataframe(
                pd.DataFrame(pos_data).style.format({
                    "成本": "${:.2f}", "現價": "${:.2f}", 
                    "損益 ($)": "${:+.2f}", "報酬率 (%)": "{:+.2f}%"
                }).applymap(lambda x: 'color: green' if x > 0 else 'color: red', subset=['損益 ($)', '報酬率 (%)']),
                use_container_width=True
            )

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
# 實戰策略 (Strategy) - 篩選與自動單
# ========================================================
elif page_mode == "⚡ 實戰策略 (Strategy)":
    st.title("⚡ 1/13 翻倍戰術 (Screen & Trade)")
    st.markdown("""
    **策略流程**：
    1. **篩選 (Screening)**：尋找 Ask Price 在 **$2.00 - $2.40** 的合約。
    2. **進場 (Entry)**：市價買入 **2** 張。
    3. **佈局 (Setup)**：成交後，自動掛出 **1 張翻倍賣單 (Limit Sell)** 保本。
    """)
    
    api = trading.get_api()
    
    # --- 步驟 1: 篩選器 ---
    st.subheader("1️⃣ 尋找標的 (Screening)")
    col_scr1, col_scr2, col_scr3 = st.columns([1, 1, 1])
    with col_scr1:
        # 優先使用你的監控清單。如果清單被刪光了，才用預設的避免報錯。
        my_options = st.session_state.watchlist if st.session_state.watchlist else ["AMD", "PLTR", "MARA", "COIN", "TSLA", "NVDA"]
        
        # 下拉選單現在會顯示你的清單內容
        scan_symbol = st.selectbox("標的股票 (從監控清單)", my_options, index=0)
    with col_scr2:
        price_min = st.number_input("最小價格 ($)", value=2.00, step=0.1)
    with col_scr3:
        price_max = st.number_input("最大價格 ($)", value=2.40, step=0.1)

    if st.button("🔍 掃描符合條件的期權 (Scan Options)"):
        with st.spinner(f"正在掃描 {scan_symbol} 的期權鏈... (資料來源: Yahoo Finance)"):
            try:
                tk = yf.Ticker(scan_symbol)
                exps = tk.options
                
                # 為了示範，我們只掃描最近的兩個到期日，節省時間
                scan_results = []
                for date in exps[:2]: 
                    opt = tk.option_chain(date)
                    calls = opt.calls
                    # 篩選條件：Ask 在區間內
                    mask = (calls['ask'] >= price_min) & (calls['ask'] <= price_max)
                    filtered = calls[mask].copy()
                    
                    for index, row in filtered.iterrows():
                        scan_results.append({
                            "到期日": date,
                            "合約代碼": row['contractSymbol'],
                            "行權價": row['strike'],
                            "Ask (買入價)": row['ask'],
                            "Bid (賣出價)": row['bid'],
                            "成交量": row['volume'],
                            "IV": row['impliedVolatility']
                        })
                
                if scan_results:
                    df_scan = pd.DataFrame(scan_results)
                    # 存入 session state 供下一步使用
                    st.session_state['scan_results'] = df_scan
                    st.success(f"找到 {len(df_scan)} 個符合條件的合約！")
                else:
                    st.warning("在此價格區間內找不到合約，請嘗試調整價格或更換標的。")
                    st.session_state['scan_results'] = pd.DataFrame()
            except Exception as e:
                st.error(f"掃描失敗: {e}")

    # --- 步驟 2 & 3: 執行交易 ---
    if 'scan_results' in st.session_state and not st.session_state['scan_results'].empty:
        st.divider()
        st.subheader("2️⃣ 選擇並執行 (Execute)")
        
        df_scan = st.session_state['scan_results']
        
        # 讓使用者選擇其中一個合約
        selected_idx = st.selectbox(
            "請選擇要交易的合約：", 
            df_scan.index, 
            format_func=lambda i: f"{df_scan.iloc[i]['到期日']} | Strike ${df_scan.iloc[i]['行權價']} | Ask ${df_scan.iloc[i]['Ask (買入價)']}"
        )
        
        target_contract = df_scan.iloc[selected_idx]
        symbol_code = target_contract['合約代碼']
        est_price = target_contract['Ask (買入價)']
        
        st.info(f"**準備交易**: 買入 **2** 張 `{symbol_code}` @ 約 ${est_price}")
        
        # 執行按鈕
        if st.button("🚀 立即執行 (Buy 2 & Auto-Limit 1)", type="primary"):
            status_box = st.empty()
            progress = st.progress(0)
            
            try:
                # 1. 下單買入 (改用 Limit 單，這樣盤後也能掛)
                status_box.text(f"1/3 正在送出買單 (Buy 2 @ Limit ${est_price})...")
                progress.progress(30)
                
                # 🔥 修改重點：改用 Limit Order，並設定價格為 Ask
                buy_order = api.submit_order(
                    symbol=symbol_code,
                    qty=2,
                    side='buy',
                    type='limit',          # <--- 改這裡
                    limit_price=est_price, # <--- 設定限價 (Ask)
                    time_in_force='day'
                )
                
                # 2. 等待成交
                status_box.text(f"2/3 訂單已送出，等待成交確認... (Order ID: {buy_order.id})")
                time.sleep(3) 
                
                # 檢查訂單狀態
                o = api.get_order(buy_order.id)
                
                if o.status == 'filled':
                    # === 情境 A: 立即成交 (盤中) ===
                    filled_price = float(o.filled_avg_price)
                    progress.progress(70)
                    
                    # 3. 掛出賣單 (Limit Sell 1 @ 2x)
                    target_sell_price = round(filled_price * 2.0, 2)
                    status_box.text(f"3/3 成交價 ${filled_price}。正在掛出保本賣單 @ ${target_sell_price}...")
                    
                    sell_order = api.submit_order(
                        symbol=symbol_code,
                        qty=1,
                        side='sell',
                        type='limit',
                        limit_price=target_sell_price,
                        time_in_force='gtc' # GTC = 永久有效
                    )
                    
                    progress.progress(100)
                    st.balloons()
                    st.success(f"✅ 策略執行成功！成交價 ${filled_price}")
                    st.markdown(f"""
                    - **已買入**: 2 張
                    - **已掛賣單**: 賣出 1 張 @ ${target_sell_price} (單號: `{sell_order.id}`)
                    """)
                    
                else:
                    # === 情境 B: 尚未成交 (盤後或排隊中) ===
                    progress.progress(100)
                    st.warning(f"⚠️ 買單已送出，但尚未成交 (目前狀態: `{o.status}`)。")
                    st.info(f"""
                    **原因可能是**：
                    1. 目前是休市時間 (美股期權交易時間為台灣 21:30 - 04:00)。
                    2. 設定的限價 (${est_price}) 太低，還沒排到。

                    **後續動作**：
                    因為買單還沒成交，**系統暫時無法掛出「賣單」** (因為你還沒有持倉)。
                    請等到開盤成交後，去 **「💼 我的資產」** 頁面使用 **「🤖 自動停利設定」** 補掛賣單即可。
                    """)
                
            except Exception as e:
                st.error(f"執行失敗: {e}")
                status_box.text("❌ 發生錯誤")

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
# 定時自動掛機 (Auto-Pilot) - V3 防斷線終極版
# ========================================================
elif page_mode == "⏰ 定時自動掛機 (Auto-Pilot)":
    st.title("⏰ 全自動掛機模式 (Sleep & Trade)")
    st.markdown("""
    **防斷線機制 (Auto-Resume)**：此版本會將設定存檔。即使網頁不小心重新整理，系統也會在 5 秒後自動恢復掛機。
    """)
    
    import datetime
    import pytz
    import json
    
    api = trading.get_api()
    STATE_FILE = "bot_state.json"

    # --- 函數：存取狀態 ---
    def save_state(running, symbol, time_str, budget, min_p, max_p, trend):
        with open(STATE_FILE, "w") as f:
            json.dump({
                "running": running,
                "symbol": symbol,
                "time": time_str,
                "budget": budget,
                "min": min_p,
                "max": max_p,
                "trend": trend
            }, f)

    def load_state():
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r") as f:
                    return json.load(f)
            except: pass
        return None

    # 讀取上次的設定 (如果有)
    state = load_state()
    default_running = state["running"] if state else False
    
    # --- 1. 策略設定 (Setup) ---
    st.subheader("1️⃣ 策略設定 (Setup)")
    
    # 預設值優先使用「存檔的紀錄」，沒有才用預設值
    my_options = st.session_state.watchlist if st.session_state.watchlist else ["AMD", "PLTR"]
    def_idx = 0
    if state and state["symbol"] in my_options:
        def_idx = my_options.index(state["symbol"])

    c1, c2, c3 = st.columns(3)
    with c1:
        target_symbol = st.selectbox("目標股票", my_options, index=def_idx)
    with c2:
        target_time_str = st.text_input("執行時間 (美東 ET)", value=state["time"] if state else "09:45")
    with c3:
        trend_filter = st.checkbox("✅ 只做多頭", value=state["trend"] if state else True)

    st.write("---")
    st.subheader("💰 資金管理")
    
    cm1, cm2, cm3 = st.columns(3)
    with cm1:
        total_budget = st.number_input("總預算 ($)", value=state["budget"] if state else 500, step=100)
    with cm2:
        min_ask = st.number_input("Ask 最小 ($)", value=state["min"] if state else 1.50)
    with cm3:
        max_ask = st.number_input("Ask 最大 ($)", value=state["max"] if state else 2.50)

    st.divider()

    # --- 邏輯核心：防斷線啟動 ---
    
    # 變數：決定是否要執行 Loop
    should_run = False
    
    # 情況 A: 使用者剛按下啟動
    if st.button("🔴 啟動掛機系統 (Start)", type="primary"):
        save_state(True, target_symbol, target_time_str, total_budget, min_ask, max_ask, trend_filter)
        st.rerun() # 強制刷新以進入狀態
    
    # 情況 B: 系統發現「上次是啟動狀態」 (可能是網頁重整了)
    elif default_running:
        st.warning("⚠️ 檢測到系統之前正在掛機 (可能是網頁剛重整)...")
        
        # 給使用者 5 秒鐘後悔的機會 (避免無限死循環)
        stop_col1, stop_col2 = st.columns([4, 1])
        with stop_col1:
            st.info("系統將在 **5 秒後** 自動恢復掛機監控...")
        with stop_col2:
            if st.button("🛑 取消掛機 (Stop)"):
                save_state(False, target_symbol, target_time_str, total_budget, min_ask, max_ask, trend_filter)
                st.success("已停止！")
                time.sleep(1)
                st.rerun()
                
        # 倒數 5 秒
        time.sleep(5)
        # 如果沒按取消，就繼續執行
        should_run = True

    # --- 正式進入掛機迴圈 ---
    if should_run:
        status_placeholder = st.empty()
        log_placeholder = st.empty()
        
        # 為了避免 UI 卡死無法操作，這裡顯示一個提示
        st.caption("💡 程式運行中。如需停止，請 **直接切換到側邊欄的其他頁面** 即可強行中斷。")
        
        tz_et = pytz.timezone('US/Eastern')
        now_et = datetime.datetime.now(tz_et)
        
        # 時間解析邏輯 (同 V2)
        try:
            t_hour, t_minute = map(int, target_time_str.split(':'))
            target_dt = now_et.replace(hour=t_hour, minute=t_minute, second=0, microsecond=0)
            if now_et > target_dt:
                target_dt += datetime.timedelta(days=1)
                
            log_txt = f"🚀 [自動恢復] 系統啟動！目標：{target_symbol}\n"
            log_txt += f"⏰ 鎖定時間：{target_dt.strftime('%Y-%m-%d %H:%M:%S')} ET\n"
            log_placeholder.text_area("系統日誌", log_txt, height=200)
            
            # --- 無限迴圈 (直到任務完成或切換頁面) ---
            while True:
                now = datetime.datetime.now(tz_et)
                remaining = target_dt - now
                
                if remaining.total_seconds() > 0:
                    status_placeholder.info(f"⏳ 監控中 | 倒數: {str(remaining).split('.')[0]} (網頁重整也能自動回來)")
                else:
                    # 時間到，執行策略 (同 V2)
                    log_txt += f"\n✅ 時間到達！開始執行...\n"
                    log_placeholder.text_area("系統日誌", log_txt, height=200)
                    status_placeholder.text("⚡ 執行中...")
                    
                    try:
                        # [Step A] 趨勢
                        if trend_filter:
                            bar = api.get_latest_bar(target_symbol)
                            if bar.c < bar.o:
                                log_txt += f"❌ 趨勢下跌 (${bar.c} < ${bar.o})，取消交易。\n"
                                log_placeholder.text_area("系統日誌", log_txt, height=200)
                                # 任務結束，修改存檔狀態為 False
                                save_state(False, target_symbol, target_time_str, total_budget, min_ask, max_ask, trend_filter)
                                break
                            log_txt += "✅ 趨勢符合 (多頭)。\n"

                        # [Step B] 掃描
                        tk = yf.Ticker(target_symbol)
                        exps = tk.options
                        found_contract = None
                        est_price = 0
                        
                        for date in exps[:2]:
                            if found_contract: break
                            opt = tk.option_chain(date)
                            candidates = opt.calls[(opt.calls['ask'] >= min_ask) & (opt.calls['ask'] <= max_ask)]
                            if not candidates.empty:
                                best_row = candidates.sort_values('volume', ascending=False).iloc[0]
                                found_contract = best_row['contractSymbol']
                                est_price = best_row['ask']
                        
                        if not found_contract:
                            log_txt += "❌ 找不到合約。\n"
                            log_placeholder.text_area("系統日誌", log_txt, height=200)
                            save_state(False, target_symbol, target_time_str, total_budget, min_ask, max_ask, trend_filter)
                            break

                        # [Step C] 下單
                        limit_buy = round(est_price + 0.05, 2)
                        cost_per = est_price * 100
                        qty = int(total_budget // cost_per)
                        if qty % 2 != 0: qty -= 1
                        
                        if qty < 2:
                            log_txt += "❌ 預算不足。\n"
                            break
                        
                        buy_order = api.submit_order(symbol=found_contract, qty=qty, side='buy', type='limit', limit_price=limit_buy, time_in_force='day')
                        
                        # [Step D] 等待成交
                        log_txt += "⏳ 等待成交...\n"
                        log_placeholder.text_area("系統日誌", log_txt, height=200)
                        filled = False
                        filled_price = 0
                        for _ in range(12):
                            time.sleep(5)
                            o = api.get_order(buy_order.id)
                            if o.status == 'filled':
                                filled = True
                                filled_price = float(o.filled_avg_price)
                                break
                        
                        if filled:
                            target_sell = round(filled_price * 2.0, 2)
                            api.submit_order(symbol=found_contract, qty=int(qty/2), side='sell', type='limit', limit_price=target_sell, time_in_force='gtc')
                            log_txt += f"🎉 任務完成！掛賣 ${target_sell}\n"
                            status_placeholder.success("執行完畢！")
                            st.balloons()
                        else:
                            api.cancel_order(buy_order.id)
                            log_txt += "⚠️ 未成交已取消。\n"
                            
                        log_placeholder.text_area("系統日誌", log_txt, height=200)
                        
                        # 任務結束，停止掛機狀態
                        save_state(False, target_symbol, target_time_str, total_budget, min_ask, max_ask, trend_filter)
                        break

                    except Exception as e:
                        log_txt += f"❌ 錯誤: {e}\n"
                        log_placeholder.text_area("系統日誌", log_txt, height=200)
                        save_state(False, target_symbol, target_time_str, total_budget, min_ask, max_ask, trend_filter)
                        break
                
                time.sleep(1)

        except Exception as e:
            st.error(f"系統錯誤: {e}")
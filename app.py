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
    st.header("🧭 導航模式")
    page_mode = st.radio("請選擇功能：", ["📈 股票戰情室 (Dashboard)", "💰 期權策略 (Options)", "💼 我的資產 (Portfolio)"], index=0)

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
# 🆎 模式三：我的資產 (Portfolio)
# -----------------------------------------------
elif page_mode == "💼 我的資產 (Portfolio)":
    st.title("💼 我的資產總覽")
    api = trading.get_api()
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

        st.subheader("📋 訂單管理 (Orders)")
        open_orders = api.list_orders(status='open')
        with st.expander("⏳ 掛單中 (Open Orders)", expanded=True):
            if open_orders:
                o_data = [{"Symbol": o.symbol, "Side": o.side, "Qty": o.qty, "Price": o.limit_price, "Status": o.status} for o in open_orders]
                st.dataframe(pd.DataFrame(o_data), hide_index=True)
                if st.button("❌ 取消所有掛單"):
                    api.cancel_all_orders()
                    st.rerun()
            else:
                st.info("無掛單")

        with st.expander("✅ 最近成交 (Filled)", expanded=False):
            closed_orders = api.list_orders(status='closed', limit=10)
            if closed_orders:
                c_data = [{"Symbol": o.symbol, "Side": o.side, "Qty": o.filled_qty, "Price": o.filled_avg_price, "Time": o.filled_at} for o in closed_orders if o.filled_at]
                st.dataframe(pd.DataFrame(c_data), hide_index=True)

        st.divider()
        st.subheader("📊 目前持倉")
        positions = api.list_positions()
        if positions:
            pos_data = [{"Symbol": p.symbol, "Qty": p.qty, "Cost": float(p.avg_entry_price), "Price": float(p.current_price), "P/L": float(p.unrealized_pl)} for p in positions]
            st.dataframe(pd.DataFrame(pos_data), hide_index=True)
        else:
            st.info("目前空手")

    except Exception as e:
        st.error(f"讀取失敗: {e}")
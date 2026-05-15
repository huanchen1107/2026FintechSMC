import sys
import re

with open('app.py', 'r') as f:
    content = f.read()

new_func_v9 = '''
def render_tradingview_chart(df, rec, snap):
    st.subheader("TradingView Advanced Dashboard")
    
    # ── Advanced Chart Settings ──
    col_set1, col_set2, col_set3 = st.columns([1, 1, 2])
    with col_set1:
        chart_theme = st.selectbox("Theme", ["dark", "light"], index=0, key="tv_theme")
    with col_set2:
        chart_height = st.slider("Chart Height", 400, 1000, 600, step=50, key="tv_height")
    with col_set3:
        show_watermark = st.checkbox("Enable Watermark", value=True, key="tv_watermark")

    with st.expander("🛠️ Drawing Tools Help & Hotkeys"):
        st.markdown("""
        - **Trendline**: `Alt + T`
        - **Horizontal Line**: `Alt + H`
        - **Ray**: `Alt + R`
        - **Undo**: `Ctrl/Cmd + Z`
        - **Delete Selected**: `Backspace` or `Delete`
        - **Note**: If the UI icons on the left are unresponsive, please use the **Hotkeys** above while the chart is focused.
        """)

    try:
        # 1. Prepare Data
        chart_df = df.copy()
        chart_df = chart_df.loc[:, ~chart_df.columns.duplicated()].copy()
        
        rename_map = {'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume', 'date': 'time'}
        chart_df = chart_df.rename(columns={k: v for k, v in rename_map.items() if k in chart_df.columns})
        
        chart_df['time'] = pd.to_datetime(chart_df['time'])
        if chart_df['time'].dt.tz is not None:
            chart_df['time'] = chart_df['time'].dt.tz_localize(None)
        
        chart_df = chart_df.sort_values('time').drop_duplicates(subset=['time']).reset_index(drop=True)
        
        is_intraday = False
        if len(chart_df) > 1:
            if (chart_df['time'].iloc[1] - chart_df['time'].iloc[0]).total_seconds() < 86400:
                is_intraday = True
        
        time_format = '%Y-%m-%d %H:%M:%S' if is_intraday else '%Y-%m-%d'
        chart_df['time'] = chart_df['time'].dt.strftime(time_format)
        
        for col in ['open', 'high', 'low', 'close']:
            chart_df[col] = pd.to_numeric(chart_df[col], errors='coerce')
        chart_df = chart_df.dropna(subset=['open', 'high', 'low', 'close'])

        # 2. Initialize Advanced Chart
        chart = StreamlitChart(width=1000, height=chart_height, toolbox=True)
        
        # Configuration
        bg_color = '#131722' if chart_theme == 'dark' else '#ffffff'
        text_color = '#d1d4dc' if chart_theme == 'dark' else '#131722'
        grid_color = '#1f222d' if chart_theme == 'dark' else '#f0f3fa'
        
        chart.layout(background_color=bg_color, text_color=text_color, font_size=12)
        chart.grid(vert_enabled=True, horz_enabled=True, color=grid_color)
        chart.legend(visible=True, font_size=14)
        
        if show_watermark:
            ticker_name = st.session_state.get("ticker", "STOCK")
            chart.watermark(ticker_name, color='rgba(180, 180, 255, 0.1)')

        # Set Data
        plot_df = chart_df[['time', 'open', 'high', 'low', 'close', 'volume']].copy()
        chart.set(plot_df)
        
        # 3. Add Dynamic Markers
        ret_data = st.session_state.get("model_ret", {})
        bt_trades_df = ret_data.get("test_backtest", {}).get("trades_df") if ret_data else None
        
        if bt_trades_df is not None and not bt_trades_df.empty:
            orig_times = pd.to_datetime(df['date']).dt.tz_localize(None)
            for _, t in bt_trades_df.iterrows():
                trade_t = pd.Timestamp(t['datetime']).tz_localize(None)
                idx = (orig_times - trade_t).abs().idxmin()
                match_dt = orig_times.iloc[idx]
                actual_time_str = match_dt.strftime(time_format)
                
                if t['type'] == 'BUY':
                    chart.marker(time=actual_time_str, position='belowBar', color='#22ab94', shape='arrowUp', text=f"BUY")
                else:
                    chart.marker(time=actual_time_str, position='aboveBar', color='#f7525f', shape='arrowDown', text=f"SELL")

        if 'ob' in chart_df.columns:
            for i, row in chart_df[chart_df['ob'] != 0].tail(20).iterrows():
                color = "#22ab94" if row['ob'] > 0 else "#f7525f"
                chart.marker(time=row['time'], position='belowBar' if row['ob'] > 0 else 'aboveBar', color=color, shape='square', text="OB")

        if 'fvg' in chart_df.columns:
            for i, row in chart_df[chart_df['fvg'] != 0].tail(10).iterrows():
                color = "#2962ff" if row['fvg'] > 0 else "#ff9800"
                chart.marker(time=row['time'], position='belowBar' if row['fvg'] > 0 else 'aboveBar', color=color, shape='circle', text="FVG")

        chart.load()
    except Exception as e:
        st.error(f"Advanced Chart Error: {e}")
        import traceback
        st.code(traceback.format_exc())
'''

pattern = r'def render_tradingview_chart\(df, rec, snap\):.*?chart\.load\(\)'
content = re.sub(pattern, new_func_v9, content, flags=re.DOTALL)

with open('app.py', 'w') as f:
    f.write(content)

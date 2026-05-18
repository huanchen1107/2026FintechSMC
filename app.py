import streamlit as st
if not hasattr(st, "fragment"):
    def fragment_fallback(func=None, *args, **kwargs):
        if func is None:
            return lambda f: f
        return func
    st.fragment = fragment_fallback
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as plotly_go
from pathlib import Path
from config import Config, ACTION_NAMES, ACTION_POSITION_RATIOS, ACTION_POSITION_RATIOS_DQN_ON_BUY
from train import run_training_pipeline
from train_v2 import run_training_pipeline_v2, run_evaluation_pipeline_v2
from recommend import recommend_strategy
from recommend_v2 import recommend_strategy_v2
from utils.data_utils import FEATURE_COLUMNS, prepare_data_for_chart, resample_ohlcv
from utils.data_utils_v2 import FEATURE_COLUMNS as FEATURE_COLUMNS_V2
from utils.data_utils_v2 import build_mtf_dataset, download_ohlcv_with_fallback
from utils.data_utils_v2 import download_and_build_mtf
from utils.data_utils_v2 import ensure_datetime_index, prepare_timeframe_features, resample_ohlcv, merge_asof_higher_tf, add_mtf_confluence_features, add_pd_validity_features, add_risk_reward_features_by_timeframe
from ai_comment import generate_ai_comment, generate_journal_ai_reply
from utils.ai_comment_cache import get_ai_comment, save_ai_comment
from utils.model_registry import list_models, load_model_by_id, delete_model_by_id, register_model
from utils.trade_pairs import reconstruct_trade_pairs, pairs_to_dataframe, append_trade_review, ensure_reviews_file
from lightweight_charts.widgets import StreamlitChart
from lightweight_charts.drawings import Box

STRATEGY_CHOICES = [
    {"label": "DQN Position", "mode": "dqn_position", "tag": "dqn-position"},
    {"label": "DQN-on-Buy with RR-box-Sell", "mode": "dqn_on_buy_rr_box_sell", "tag": "dqn-on-buy-rr-box-sell"},
    {"label": "Double DQN-on-Buy with RR-box-Sell with Priority Buffer Replay", "mode": "dqn_on_buy_rr_box_sell", "tag": "double-dqn-on-buy-rr-box-sell-priority-buffer-replay"},
]

# 設定頁面配置 (必須是第一個 Streamlit 指令)
st.set_page_config(page_title="SMC × DRL Trading Platform", layout="wide")

# 初始化設定
cfg = Config()

def load_data_raw(ticker, start_date, end_date):
    try:
        cache_df = load_raw_data_from_cache(ticker)
        if cache_df is not None and not cache_df.empty:
            cache_df = cache_df.copy()
            if "date" in cache_df.columns:
                cache_df["date"] = pd.to_datetime(cache_df["date"], errors="coerce")
                cache_df = cache_df.dropna(subset=["date"])
                start_ts = pd.to_datetime(start_date)
                end_ts = pd.to_datetime(end_date)
                cached_min = cache_df["date"].min()
                cached_max = cache_df["date"].max()
                if pd.notna(cached_min) and pd.notna(cached_max) and cached_min <= start_ts and cached_max >= end_ts:
                    return cache_df
        df = download_ohlcv_with_fallback(
            ticker=ticker,
            start=str(start_date),
            end=str(end_date),
            interval="1h",
            fallback_periods=("max", "730d", "365d", "180d", "90d", "60d"),
        )
        if df.empty:
            return None
        df = df.copy()
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        df.index.name = "date"
        df = df.reset_index()
        rename_map = {
            "Date": "date",
            "Datetime": "date",
            "index": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
        df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)
        if "date" not in df.columns:
            raise ValueError(f"Downloaded data is missing a date column. Columns: {list(df.columns)}")
        if pd.api.types.is_datetime64_any_dtype(df["date"]):
            if df["date"].dt.tz is not None:
                df["date"] = df["date"].dt.tz_convert("Asia/Taipei").dt.tz_localize(None)
            else:
                df["date"] = df["date"].dt.tz_localize("UTC").dt.tz_convert("Asia/Taipei").dt.tz_localize(None)
        save_raw_data_cache(ticker, df)
        return df
    except Exception as e:
        st.error(f"Failed to fetch data: {e}")
        return None

def process_data_for_chart(raw_df, interval, rolling_window):
    """Process data with smartmoneyconcepts for chart display."""
    df = raw_df.loc[:, ~raw_df.columns.duplicated()].copy()
    date_source = None
    for candidate in ["date", "datetime", "time"]:
        if candidate in df.columns:
            date_source = candidate
            break
    if date_source is not None:
        df["date"] = pd.to_datetime(df[date_source], errors="coerce")
    elif isinstance(df.index, pd.DatetimeIndex):
        df["date"] = pd.to_datetime(df.index, errors="coerce")
    else:
        raise ValueError("Chart data is missing a usable date column.")
    df = df.dropna(subset=["date"]).sort_values("date")
    df = df.set_index("date", drop=True)
    df.index.name = "date"
    resample_rules = {"1h": None, "4h": "4h", "1d": "D", "1wk": "W-MON"}
    rule = resample_rules.get(interval)
    if rule:
        df = df.resample(rule).agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna()
    df = df.reset_index()
    if "date" not in df.columns and "index" in df.columns:
        df.rename(columns={"index": "date"}, inplace=True)
    df["date"] = pd.to_datetime(df["date"], errors="coerce").astype("datetime64[ns]")
    if len(df) < rolling_window:
        st.warning(f"Current data count ({len(df)}) is less than rolling window ({rolling_window})")
    df = prepare_data_for_chart(df, rolling_window=rolling_window)
    return df

def compute_recommendation(ret, cfg):
    agent = ret["agent"]
    mtf_df = ret["mtf_df"]
    feature_mean = ret["feature_mean"]
    feature_std = ret["feature_std"]
    if ret.get("is_v2"):
        return recommend_strategy_v2(
            agent=agent, latest_mtf_raw=mtf_df, cfg=cfg,
            feature_cols=FEATURE_COLUMNS_V2, feature_mean=feature_mean, feature_std=feature_std
        )
    else:
        return recommend_strategy(
            agent=agent, latest_mtf_raw=mtf_df, cfg=cfg,
            feature_cols=FEATURE_COLUMNS, feature_mean=feature_mean, feature_std=feature_std
        )


def set_current_model_context(ret):
    model_record = ret.get("model_record") or {}
    model_id = model_record.get("model_id") or ret.get("model_path")
    st.session_state["current_model_id"] = model_id
    st.session_state["current_model_record"] = model_record
    if ret.get("recommendation"):
        st.session_state["recommendation"] = ret["recommendation"]
    else:
        try:
            st.session_state["recommendation"] = compute_recommendation(ret, cfg)
        except Exception:
            pass
    if ret.get("metrics"):
        st.session_state["model_metrics"] = ret["metrics"]


def save_current_trained_model(ret, cfg, strategy_mode):
    """Persist the current trained model as an explicit manual save."""
    agent = ret.get("agent")
    feature_mean = ret.get("feature_mean")
    feature_std = ret.get("feature_std")
    if agent is None or feature_mean is None or feature_std is None:
        return None, "missing_state"

    current_record = ret.get("model_record") or {}
    current_path = current_record.get("path")
    if current_path and Path(current_path).exists():
        return current_record, "already_saved"

    strategy_tag = getattr(cfg, "strategy_label_tag", None) or ("dqn-on-buy-rr-box-sell" if strategy_mode == "dqn_on_buy_rr_box_sell" else ("dqn-on-buy" if strategy_mode == "dqn_on_buy" else "dqn-position"))
    save_dir = cfg.outputs_dir / "models"
    save_dir.mkdir(parents=True, exist_ok=True)
    manual_path = save_dir / f"manual_mtf_dqn_model_v2_{strategy_tag}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.pth"
    agent.save(
        str(manual_path),
        feature_columns=FEATURE_COLUMNS_V2,
        feature_mean=feature_mean.to_dict() if hasattr(feature_mean, "to_dict") else dict(feature_mean),
        feature_std=feature_std.to_dict() if hasattr(feature_std, "to_dict") else dict(feature_std),
        config={k: v for k, v in cfg.__dict__.items() if not isinstance(v, type(cfg.project_dir))},
        action_position_ratios=ACTION_POSITION_RATIOS if strategy_mode == "dqn_position" else ACTION_POSITION_RATIOS_DQN_ON_BUY,
    )
    metrics = ret.get("metrics", {})
    model_record = register_model(
        cfg.outputs_dir,
        model_path=str(manual_path),
        ticker=cfg.ticker,
        sharpe=float(metrics.get("sharpe_ratio", 0.0) or 0.0),
        total_return=float(metrics.get("total_return", 0.0) or 0.0),
        max_drawdown=float(metrics.get("max_drawdown", 0.0) or 0.0),
        extra={"is_v2": True, "strategy_mode": strategy_mode, "strategy_label": strategy_tag, "manual_save": True},
    )
    ret["model_record"] = model_record
    ret["model_path"] = str(manual_path)
    return model_record, "saved"


def render_backtest_metrics(metrics):
    trade_pair_count = int(metrics.get("trade_pair_count", 0) or 0)
    win_count = int(metrics.get("win_count", 0) or 0)
    loss_count = int(metrics.get("loss_count", 0) or 0)
    auto_rr_fallback_used = bool(metrics.get("auto_rr_fallback_used", False))
    auto_rr_candidate_count = int(metrics.get("auto_rr_candidate_count", 0) or 0)
    win_rate = (win_count / trade_pair_count) if trade_pair_count else 0.0
    cols = st.columns(4)
    with cols[0]:
        st.metric("Trade Pairs", f"{trade_pair_count}")
    with cols[1]:
        st.metric("Wins", f"{win_count}")
    with cols[2]:
        st.metric("Losses", f"{loss_count}")
    with cols[3]:
        st.metric("Win Rate", f"{win_rate * 100:.1f}%")
    if auto_rr_fallback_used:
        st.caption(f"RR-threshold auto fallback used. Candidate trades: {auto_rr_candidate_count}.")
    elif trade_pair_count == 0:
        st.caption("No closed BUY/SELL pairs were reconstructed from this run.")
    else:
        st.caption(f"Win count + loss count = {win_count + loss_count} closed pairs.")


def sync_training_rr_threshold_shared() -> None:
    """Mirror Step 1 threshold into a shared session value used by Step 2."""
    raw_value = st.session_state.get("training_rr_threshold_input", st.session_state.get("rr_threshold_shared", 2.0))
    try:
        shared_value = float(raw_value)
    except Exception:
        shared_value = 2.0
    st.session_state["rr_threshold_shared"] = shared_value
    cfg.training_rr_threshold = shared_value


def render_mdp_model_summary():
    with st.container(border=True):
        st.markdown("#### MDP Model")
        st.markdown(
            """
            - **State**: latest 100 PD-valid steps of W1 / D1 / H4 / H1 SMC features, plus portfolio context and live RR features.
            - **Action**: DQN Position, DQN-on-Buy with RR-box-Sell, or Double DQN-on-Buy with RR-box-Sell.
            - **Transition**: rebalance to the selected target position, then advance one bar; buy-only modes auto-exit on H4 stop-loss or W1 take-profit.
            - **Reward**: step return, drawdown penalty, trade penalty, MTF confluence bonus, and higher-timeframe conflict penalty.
            - **Episode end**: when the dataset reaches the final bar.
            """
        )


def build_pd_arrays_from_raw(raw_df):
    interval_map = {"W1": "1wk", "D1": "1d", "H4": "4h", "H1": "1h"}
    rows = []
    for tf_name, interval in interval_map.items():
        try:
            tf_df = process_data_for_chart(raw_df, interval, cfg.rolling_window)
            if tf_df.empty:
                continue
            last = tf_df.iloc[-1]
            rows.append({
                "timeframe": tf_name,
                "swing_high": last.get("old_high", np.nan),
                "swing_low": last.get("old_low", np.nan),
                "fvg_mid": last.get("fvg_mid", np.nan),
                "fvg_top": last.get("fvg_top", np.nan),
                "fvg_bottom": last.get("fvg_bottom", np.nan),
                "ob_top": last.get("ob_top", np.nan),
                "ob_bottom": last.get("ob_bottom", np.nan),
                "close": last.get("close", np.nan),
            })
        except Exception:
            continue
    return pd.DataFrame(rows)


def _format_tag_tokens(tokens):
    tokens = [str(tok).strip() for tok in tokens if tok is not None and str(tok).strip()]
    return " / ".join(tokens) if tokens else "None"


def _build_swing_tag(row):
    tags = []
    tf_specs = [
        ("W1", "w1"),
        ("D1", "d1"),
        ("4H", "h4"),
        ("1H", "h1"),
    ]
    for label, prefix in tf_specs:
        lib_level = row.get(f"{prefix}_lib_swing_highlow", np.nan)
        if pd.notna(lib_level):
            try:
                lib_level = int(float(lib_level))
                if lib_level > 0:
                    tags.append(f"{label} Swing High")
                elif lib_level < 0:
                    tags.append(f"{label} Swing Low")
                continue
            except Exception:
                pass
        high = row.get(f"{prefix}_last_swing_high", np.nan)
        low = row.get(f"{prefix}_last_swing_low", np.nan)
        close = row.get("close", np.nan)
        if pd.notna(high) and pd.notna(close) and close >= high:
            tags.append(f"{label} Swing High")
        if pd.notna(low) and pd.notna(close) and close <= low:
            tags.append(f"{label} Swing Low")
    return _format_tag_tokens(tags)


def _build_fvg_tag(row):
    tags = []
    tf_specs = [
        ("W1", "w1"),
        ("D1", "d1"),
        ("4H", "h4"),
        ("1H", "h1"),
    ]
    for label, prefix in tf_specs:
        lib_fvg = row.get(f"{prefix}_lib_fvg", np.nan)
        if pd.notna(lib_fvg):
            try:
                lib_fvg = int(float(lib_fvg))
                if lib_fvg > 0:
                    tags.append(f"{label} UP")
                elif lib_fvg < 0:
                    tags.append(f"{label} Down")
                continue
            except Exception:
                pass
        bull = row.get(f"{prefix}_bullish_fvg", np.nan)
        bear = row.get(f"{prefix}_bearish_fvg", np.nan)
        if pd.notna(bull) and float(bull) > 0:
            tags.append(f"{label} UP")
        if pd.notna(bear) and float(bear) > 0:
            tags.append(f"{label} Down")
    return _format_tag_tokens(tags)


def _build_step1_hover_text(row):
    parts = []
    ts = row.get("timestamp", row.get("datetime", row.get("date", "")))
    if pd.notna(ts):
        parts.append(f"Time: {pd.Timestamp(ts).strftime('%Y-%m-%d %H:%M')}")
    if pd.notna(row.get("close_price", np.nan)):
        parts.append(f"Close: {float(row.get('close_price')):,.2f}")
    parts.append(f"Swing: {row.get('swing_tag', 'None')}")
    parts.append(f"FVG: {row.get('fvg_tag', 'None')}")
    parts.append(f"PD Valid: {int(row.get('pd_valid', 0) or 0)}")
    valid_keys = [k for k in row.index if isinstance(k, str) and ("_lib_" in k or k.endswith("_smc_bias") or k.endswith("_rr_ratio") or k.endswith("_rr_valid") or k.endswith("_liquidity_sweep_tag"))]
    for key in valid_keys:
        val = row.get(key)
        if pd.notna(val) and str(val) not in {"", "nan"}:
            parts.append(f"{key}: {val}")
    return "<br>".join(parts)


def _format_step1_display(df):
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    for ts_col in ("created_at", "updated_at"):
        if ts_col in out.columns:
            out[ts_col] = pd.to_datetime(out[ts_col], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")
    if "timestamp" in out.columns:
        out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M")
    if "close_price" in out.columns:
        close_col = out["close_price"]
        if isinstance(close_col, pd.DataFrame):
            close_col = close_col.iloc[:, 0]
        out["close_price"] = pd.to_numeric(close_col, errors="coerce").round(2)
    if "pd_valid" in out.columns:
        out["pd_valid"] = out["pd_valid"].fillna(0).astype(int)
    return out


def _step1_pd_excel_path():
    outputs_dir = Path(cfg.outputs_dir)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    return outputs_dir / "step1_pd_arrays.csv"


def _raw_data_cache_path(ticker: str) -> Path:
    outputs_dir = Path(cfg.outputs_dir)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    safe_ticker = ticker.replace("/", "_").replace(":", "_").replace(".", "_")
    return outputs_dir / f"raw_market_data_{safe_ticker}.csv"


def load_raw_data_from_cache(ticker: str):
    cache_path = _raw_data_cache_path(ticker)
    if not cache_path.exists():
        return None
    try:
        df = pd.read_csv(cache_path)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return df
    except Exception:
        return None


def save_raw_data_cache(ticker: str, df: pd.DataFrame) -> None:
    if df is None or df.empty:
        return
    cache_path = _raw_data_cache_path(ticker)
    out = df.copy()
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out.to_csv(cache_path, index=False)


def list_output_csv_files():
    outputs_dir = Path(cfg.outputs_dir)
    if not outputs_dir.exists():
        return []
    return sorted([p.name for p in outputs_dir.glob("*.csv")])


def ensure_step1_table_meta(df):
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    now_ts = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    if "id" not in out.columns:
        out.insert(0, "id", range(1, len(out) + 1))
    else:
        out["id"] = pd.to_numeric(out["id"], errors="coerce")
        missing = out["id"].isna()
        if missing.any():
            start_id = int(out["id"].dropna().max()) + 1 if out["id"].notna().any() else 1
            out.loc[missing, "id"] = range(start_id, start_id + int(missing.sum()))
        out["id"] = out["id"].astype(int)
    if "created_at" not in out.columns:
        out.insert(1, "created_at", now_ts)
    else:
        out["created_at"] = out["created_at"].fillna(now_ts)
    if "updated_at" not in out.columns:
        insert_at = 2 if "created_at" in out.columns else 1
        out.insert(insert_at, "updated_at", now_ts)
    else:
        out["updated_at"] = now_ts
    return out


def rebuild_step1_csv_from_source(csv_path):
    try:
        mtf_df, _, _ = download_and_build_mtf(cfg, progress_callback=None)
    except Exception:
        raw_cache = load_raw_data_from_cache(cfg.ticker)
        if raw_cache is None or raw_cache.empty:
            raise
        raw_cache = raw_cache.copy()
        if "date" not in raw_cache.columns:
            raise
        raw_cache["date"] = pd.to_datetime(raw_cache["date"], errors="coerce")
        raw_cache = raw_cache.dropna(subset=["date"]).sort_values("date")
        raw_cache = raw_cache.rename(columns={"date": "datetime"})
        raw_cache = raw_cache.set_index("datetime")
        h1_raw = raw_cache[["open", "high", "low", "close", "volume"]].copy()
        d1_raw = resample_ohlcv(h1_raw, "1d")
        mtf_df = build_mtf_dataset(h1_raw, d1_raw, cfg)
    out = mtf_df.copy()
    if "timestamp" not in out.columns:
        if "datetime" in out.columns:
            out["timestamp"] = pd.to_datetime(out["datetime"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M")
        elif isinstance(out.index, pd.DatetimeIndex):
            out["timestamp"] = pd.to_datetime(out.index, errors="coerce").strftime("%Y-%m-%d %H:%M")
        elif "date" in out.columns:
            out["timestamp"] = pd.to_datetime(out["date"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M")
    if "close" in out.columns and "close_price" not in out.columns:
        out["close_price"] = out["close"]
    out["swing_tag"] = out.apply(_build_swing_tag, axis=1)
    out["fvg_tag"] = out.apply(_build_fvg_tag, axis=1)
    if "pd_valid" not in out.columns:
        out["pd_valid"] = 1
    out = ensure_step1_table_meta(out)
    out.to_csv(csv_path, index=False)
    return out

# ── 圖表渲染 Fragment（切換時區不會觸發整頁 rerun）──
@st.fragment
def render_chart():
    """圖表 Fragment：內部自行讀取資料並建立 UI，確保 fragment rerun 時正常更新。"""
    raw_df = st.session_state.get("raw_df")
    if raw_df is None:
        st.info("Waiting for data to render chart...")
        return

    interval_map = {"W1": "1wk", "D1": "1d", "H4": "4h", "H1": "1h"}

    rec = st.session_state.get("recommendation", {})
    snap = rec.get("mtf_snapshot", {}) if rec else {}
    rr_options = []
    if "rr_details" in snap:
        rr_options = [tf.upper() for tf in ["w1", "d1", "h4", "h1"] if pd.notna(snap["rr_details"][tf.lower()]["entry"])]

    with st.expander("Chart Controls", expanded=False):
        ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([1, 1, 2])
        with ctrl_col1:
            chart_tf = st.selectbox("Timeframe", list(interval_map.keys()), index=2, key="chart_tf")
        with ctrl_col2:
            chart_engine = st.selectbox("Engine", ["Plotly (SMC Focus)", "TradingView (Performance)"], index=0, key="chart_engine")
        with ctrl_col3:
            show_rr = st.multiselect("Show MTF RRR Levels", rr_options, default=[], key="show_rr_levels")
        overlay_col1, overlay_col2, overlay_col3, overlay_col4 = st.columns(4)
        with overlay_col1:
            show_old_levels = st.checkbox("Old High / Low", value=True, key="show_old_levels")
        with overlay_col2:
            show_ob = st.checkbox("Order Blocks", value=True, key="show_ob_levels")
        with overlay_col3:
            show_fvg = st.checkbox("Fair Value Gaps", value=True, key="show_fvg_levels")
        with overlay_col4:
            show_liq = st.checkbox("Liquidity Sweeps", value=True, key="show_liq_levels")
        st.caption("Step 1: SMC Market Structure")

    interval_option = interval_map[chart_tf]

    with st.spinner(f"Aggregating {chart_tf} timeframe and calculating SMC features..."):
        try:
            df = process_data_for_chart(raw_df, interval_option, cfg.rolling_window)
        except Exception as e:
            st.error(f"Data conversion or SMC calculation failed: {e}")
            return

    if chart_engine == "Plotly (SMC Focus)":
        render_plotly_chart(df, rec, snap, show_rr, show_old_levels, show_ob, show_fvg, show_liq)
    else:
        render_tradingview_chart(df, rec, snap, show_old_levels, show_ob, show_fvg, show_liq)


def render_plotly_chart(df, rec, snap, show_rr, show_old_levels=True, show_ob=True, show_fvg=True, show_liq=True):
    fig = plotly_go.Figure()
    if df['date'].dtype == 'O': # Object/String
        date_col = df['date']
    else:
        # Check if interval is intraday
        if len(df) > 1 and (df['date'].iloc[1] - df['date'].iloc[0]).total_seconds() < 86400:
            date_col = df['date'].dt.strftime('%Y-%m-%d %H:%M')
        else:
            date_col = df['date'].dt.strftime('%Y-%m-%d')

    fig.add_trace(plotly_go.Candlestick(x=date_col, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='Candlesticks'))

    # Old Highs / Old Lows
    if show_old_levels and 'old_high' in df.columns:
        fig.add_trace(plotly_go.Scatter(x=date_col, y=df['old_high'], mode='lines', name='Old High (BSL)', line=dict(color='red', width=1, dash='dash')))
        fig.add_trace(plotly_go.Scatter(x=date_col, y=df['old_low'], mode='lines', name='Old Low (SSL)', line=dict(color='green', width=1, dash='dash')))

    # Order Block
    if show_ob and "ob" in df.columns:
        ob_pos_x, ob_pos_y, ob_neg_x, ob_neg_y = [], [], [], []
        for i, row in df[df['ob'] != 0].iterrows():
            x0 = date_col.iloc[i]
            x1 = date_col.iloc[-1] if i == len(df)-1 else date_col.iloc[min(i+10, len(df)-1)]
            y0 = row.get('ob_bottom', row['low'])
            y1 = row.get('ob_top', row['high'])
            if row['ob'] < 0:
                ob_neg_x.extend([x0, x0, x1, x1, None])
                ob_neg_y.extend([y0, y1, y1, y0, None])
            else:
                ob_pos_x.extend([x0, x0, x1, x1, None])
                ob_pos_y.extend([y0, y1, y1, y0, None])
        if ob_pos_x:
            fig.add_trace(plotly_go.Scatter(x=ob_pos_x, y=ob_pos_y, fill='toself', fillcolor='rgba(0, 255, 0, 0.2)', mode='lines', line=dict(width=0), name='+ OB (Bullish)'))
        if ob_neg_x:
            fig.add_trace(plotly_go.Scatter(x=ob_neg_x, y=ob_neg_y, fill='toself', fillcolor='rgba(255, 0, 0, 0.2)', mode='lines', line=dict(width=0), name='- OB (Bearish)'))

    # FVG
    if show_fvg and "fvg" in df.columns:
        fvg_pos_x, fvg_pos_y, fvg_neg_x, fvg_neg_y = [], [], [], []
        for i, row in df[df['fvg'] != 0].iterrows():
            x0 = date_col.iloc[i]
            x1 = date_col.iloc[-1] if i == len(df)-1 else date_col.iloc[min(i+3, len(df)-1)]
            y0 = row.get('fvg_bottom', row['low'])
            y1 = row.get('fvg_top', row['high'])
            if row['fvg'] < 0:
                fvg_neg_x.extend([x0, x0, x1, x1, None])
                fvg_neg_y.extend([y0, y1, y1, y0, None])
            else:
                fvg_pos_x.extend([x0, x0, x1, x1, None])
                fvg_pos_y.extend([y0, y1, y1, y0, None])
        if fvg_pos_x:
            fig.add_trace(plotly_go.Scatter(x=fvg_pos_x, y=fvg_pos_y, fill='toself', fillcolor='rgba(0, 191, 255, 0.2)', mode='lines', line=dict(width=0), name='+ FVG (Bullish Gap)'))
        if fvg_neg_x:
            fig.add_trace(plotly_go.Scatter(x=fvg_neg_x, y=fvg_neg_y, fill='toself', fillcolor='rgba(255, 165, 0, 0.2)', mode='lines', line=dict(width=0), name='- FVG (Bearish Gap)'))

    # Liquidity
    if show_liq and "liq_swept" in df.columns:
        liq_df = df[df['liq_swept'] != 0]
        if not liq_df.empty:
            fig.add_trace(plotly_go.Scatter(x=date_col.iloc[liq_df.index], y=liq_df['high'] * 1.01, mode='markers', name='Liquidity Swept', marker=dict(symbol='x', color='purple', size=8)))

    # ── DRL 測試集交易標記 ──
    ret_data = st.session_state.get("model_ret", {})
    bt_data = ret_data.get("test_backtest", {}) if ret_data else {}
    bt_trades_df = bt_data.get("trades_df") if bt_data else None

    if bt_trades_df is not None and not bt_trades_df.empty:
        def _nearest_candle(trade_dt):
            t = pd.Timestamp(trade_dt)
            diffs = (df['date'] - t).abs()
            idx = diffs.idxmin()
            return date_col.iloc[idx], df.loc[idx, 'low'], df.loc[idx, 'high']

        buy_rows = bt_trades_df[bt_trades_df['type'] == 'BUY']
        if not buy_rows.empty:
            bx, by, bc = [], [], []
            for _, t in buy_rows.iterrows():
                ds, low, _ = _nearest_candle(t['datetime'])
                bx.append(ds); by.append(low * 0.995)
                bc.append([str(t['datetime'])[:16], f"{t['price']:,.2f}", f"{t['value']:,.0f}", f"{t['cost']:,.2f}"])
            fig.add_trace(plotly_go.Scatter(
                x=bx, y=by, mode='markers+text', name='BUY Trade',
                marker=dict(symbol='circle', color='#00E676', size=9, line=dict(color='white', width=1)),
                text=['BUY'] * len(bx), textposition='top center',
                customdata=bc,
                hovertemplate='<b>BUY</b><br>Time: %{customdata[0]}<br>Price: %{customdata[1]}<br>Value: %{customdata[2]}<br>Fee: %{customdata[3]}<extra></extra>',
            ))

        sell_rows = bt_trades_df[bt_trades_df['type'] == 'SELL']
        if not sell_rows.empty:
            sx, sy, sc = [], [], []
            for _, t in sell_rows.iterrows():
                ds, _, high = _nearest_candle(t['datetime'])
                sx.append(ds); sy.append(high * 1.005)
                sc.append([str(t['datetime'])[:16], f"{t['price']:,.2f}", f"{t['value']:,.0f}", f"{t['cost']:,.2f}"])
            fig.add_trace(plotly_go.Scatter(
                x=sx, y=sy, mode='markers+text', name='SELL Trade',
                marker=dict(symbol='circle', color='#FF5252', size=9, line=dict(color='white', width=1)),
                text=['SELL'] * len(sx), textposition='bottom center',
                customdata=sc,
                hovertemplate='<b>SELL</b><br>Time: %{customdata[0]}<br>Price: %{customdata[1]}<br>Value: %{customdata[2]}<br>Fee: %{customdata[3]}<extra></extra>',
            ))

    # ── Draw MTF RRR Lines ──
    if show_rr and rec and "rr_details" in snap:
        last_date = date_col.iloc[-1]
        start_idx = max(0, len(df) - 30)
        start_date = date_col.iloc[start_idx]
        for tf_upper in show_rr:
            tf = tf_upper.lower()
            tf_rr = snap["rr_details"][tf]
            entry = tf_rr["entry"]
            sl = tf_rr["stop_loss"]
            tp = tf_rr["take_profit"]
            fig.add_trace(plotly_go.Scatter(x=[start_date, last_date], y=[entry, entry], mode='lines+text', name=f'{tf_upper} Entry', line=dict(color="white", width=2, dash="dashdot"), text=[f"{tf_upper} Entry: {entry:,.2f}", ""], textposition="top right", textfont=dict(color="white", size=10)))
            fig.add_trace(plotly_go.Scatter(x=[start_date, last_date], y=[sl, sl], mode='lines+text', name=f'{tf_upper} SL', line=dict(color="#FF5252", width=2, dash="dashdot"), text=[f"{tf_upper} SL: {sl:,.2f}", ""], textposition="bottom right", textfont=dict(color="#FF5252", size=10)))
            fig.add_trace(plotly_go.Scatter(x=[start_date, last_date], y=[tp, tp], mode='lines+text', name=f'{tf_upper} TP', line=dict(color="#00E676", width=2, dash="dashdot"), text=[f"{tf_upper} TP: {tp:,.2f}", ""], textposition="top right", textfont=dict(color="#00E676", size=10)))

    fig.update_layout(height=550, margin=dict(l=0, r=0, t=30, b=0), xaxis_rangeslider_visible=False, xaxis_type="category", title="Plotly SMC Price Action")
    fig.update_xaxes(type="category", nticks=10)
    st.plotly_chart(fig, use_container_width=True)











def render_tradingview_chart(df, rec, snap, show_old_levels=True, show_ob=True, show_fvg=True, show_liq=True):
    st.subheader("TradingView Advanced Dashboard")
    
    # ── Advanced Chart Settings ──
    col_set1, col_set2, col_set3 = st.columns([1, 1, 2])
    with col_set1:
        chart_theme = st.selectbox("Theme", ["light", "dark"], index=0, key="tv_theme")
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

        if 'ema20' not in chart_df.columns:
            chart_df['ema20'] = chart_df['close'].ewm(span=20, adjust=False).mean()
        if 'ema50' not in chart_df.columns:
            chart_df['ema50'] = chart_df['close'].ewm(span=50, adjust=False).mean()

        # 2. Initialize Advanced Chart
        try:
            chart = StreamlitChart(width=1000, height=chart_height, toolbox=True)
        except Exception as init_err:
            st.warning(f"TradingView chart unavailable in this session: {init_err}")
            st.caption("Plotly view remains available above. Restarting the app usually clears this widget issue.")
            return
        
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
        
        # Add EMA lines
        line20 = chart.create_line(name='EMA 20', color='rgba(41, 98, 255, 0.6)')
        line20.set(chart_df[['time', 'ema20']].rename(columns={'ema20': 'EMA 20'}))
        
        line50 = chart.create_line(name='EMA 50', color='rgba(255, 152, 0, 0.6)')
        line50.set(chart_df[['time', 'ema50']].rename(columns={'ema50': 'EMA 50'}))

        if show_old_levels and 'old_high' in chart_df.columns and 'old_low' in chart_df.columns:
            old_high = chart.create_line(name='Old High', color='rgba(255, 82, 82, 0.55)')
            old_high.set(chart_df[['time', 'old_high']].rename(columns={'old_high': 'Old High'}))
            old_low = chart.create_line(name='Old Low', color='rgba(0, 230, 118, 0.55)')
            old_low.set(chart_df[['time', 'old_low']].rename(columns={'old_low': 'Old Low'}))

        
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
                    chart.marker(time=actual_time_str, position='belowBar', color='#22ab94', shape='circle', text='BUY')
                else:
                    chart.marker(time=actual_time_str, position='aboveBar', color='#f7525f', shape='circle', text='SELL')

        last_chart_time = chart_df['time'].iloc[-1]

        if show_ob and {'ob', 'ob_top', 'ob_bottom'}.issubset(chart_df.columns):
            for _, row in chart_df[chart_df['ob'] != 0].tail(6).iterrows():
                top = float(row['ob_top']) if pd.notna(row['ob_top']) else float(row['high'])
                bottom = float(row['ob_bottom']) if pd.notna(row['ob_bottom']) else float(row['low'])
                if top < bottom:
                    top, bottom = bottom, top
                color = "rgba(34, 171, 148, 0.14)" if row['ob'] > 0 else "rgba(247, 82, 95, 0.14)"
                line_color = "#22ab94" if row['ob'] > 0 else "#f7525f"
                try:
                    Box(
                        chart,
                        str(row['time']),
                        bottom,
                        str(last_chart_time),
                        top,
                        round=False,
                        line_color=line_color,
                        fill_color=color,
                        width=1,
                        style='solid',
                    )
                except Exception:
                    pass

        if show_fvg and {'fvg', 'fvg_top', 'fvg_bottom'}.issubset(chart_df.columns):
            for _, row in chart_df[chart_df['fvg'] != 0].tail(6).iterrows():
                top = float(row['fvg_top']) if pd.notna(row['fvg_top']) else float(row['high'])
                bottom = float(row['fvg_bottom']) if pd.notna(row['fvg_bottom']) else float(row['low'])
                if top < bottom:
                    top, bottom = bottom, top
                color = "rgba(41, 98, 255, 0.12)" if row['fvg'] > 0 else "rgba(255, 152, 0, 0.12)"
                line_color = "#2962ff" if row['fvg'] > 0 else "#ff9800"
                try:
                    Box(
                        chart,
                        str(row['time']),
                        bottom,
                        str(last_chart_time),
                        top,
                        round=False,
                        line_color=line_color,
                        fill_color=color,
                        width=1,
                        style='solid',
                    )
                except Exception:
                    pass

        if show_liq and 'liq_swept' in chart_df.columns:
            for _, row in chart_df[chart_df['liq_swept'] != 0].iterrows():
                chart.marker(time=row['time'], position='aboveBar', color="#9c27b0", shape='diamond', text="LIQ")

        chart.load()
    except Exception as e:
        st.error(f"TradingView Chart Error: {e}")
        import traceback
        st.code(traceback.format_exc())




def render_trade_analysis():
    st.subheader("Step 4: Review Each Trading Pair")

    ret = st.session_state.get("model_ret")
    raw_df = st.session_state.get("raw_df")
    if not ret or raw_df is None:
        st.info("請先完成模型訓練以進行交易分析。")
        return

    trades_df = ret.get("test_backtest", {}).get("trades_df")
    if trades_df is None or trades_df.empty:
        st.warning("無交易紀錄。")
        return

    pairs = reconstruct_trade_pairs(trades_df, ticker=st.session_state.get("ticker", ""))
    pairs_df = pairs_to_dataframe(pairs)
    if pairs_df.empty:
        st.warning("查無完成的交易對 (BUY -> SELL)。")
        return

    reviews_path = Config().outputs_dir / "trade_reviews.csv"
    ensure_reviews_file(reviews_path)

    st.session_state.setdefault("selected_trade_pair_id", int(pairs_df.iloc[0]["pair_id"]))
    pair_options = pairs_df[["pair_id", "buy_trade_id", "sell_trade_id", "buy_time", "profit_pct", "pnl"]].copy()
    pair_options["label"] = pair_options.apply(
        lambda r: f"#{int(r['pair_id'])} | BUY {r['buy_trade_id']} -> SELL {r['sell_trade_id']} | {pd.Timestamp(r['buy_time']).strftime('%Y-%m-%d %H:%M')} | {r['profit_pct']*100:+.2f}%",
        axis=1,
    )

    # 1. 頁面分成左右兩欄：左邊放大型圖表與圖表控制，右邊放交易選擇與稽核 Inspector
    col_chart, col_panel = st.columns([3, 1])

    # ────────────────────────────────────────────────────────
    # 右邊欄位：Trade Inspector & Audit Panel
    # ────────────────────────────────────────────────────────
    with col_panel:
        st.markdown("### 🔍 Trade Inspector")
        label_list = pair_options["label"].tolist()
        default_pair_id = int(st.session_state.get("selected_trade_pair_id", int(pairs_df.iloc[0]["pair_id"])))
        default_label = pair_options.loc[pair_options["pair_id"] == default_pair_id, "label"]
        default_index = label_list.index(default_label.iloc[0]) if not default_label.empty else 0
        selected_label = st.selectbox(
            "Select Trade Pair",
            label_list,
            index=default_index,
        )
        selected_pair_id = int(selected_label.split(" | ")[0][1:])
        st.session_state["selected_trade_pair_id"] = selected_pair_id
        pair_row = pairs_df[pairs_df["pair_id"] == selected_pair_id].iloc[0]

        # 顯示三大亮點指標
        metric_col1, metric_col2 = st.columns(2)
        with metric_col1:
            st.metric("Profit %", f"{pair_row['profit_pct']*100:+.2f}%")
        with metric_col2:
            st.metric("PnL (TWD)", f"{pair_row['pnl']:+.2f}")
        st.metric("RL Agent Reward", f"{float(pair_row.get('training_reward', pair_row['profit_pct'] * 100.0)):+.2f}")

        # 詳細買賣與風報比數值卡片
        with st.container(border=True):
            st.markdown("**📌 Position Execution Details**")
            st.write(f"**Buy Price:** {pair_row['buy_price']:,.2f} TWD")
            st.write(f"**Sell Price:** {pair_row['sell_price']:,.2f} TWD")
            st.write(f"**H4 Stop Price:** {float(pair_row.get('rr_stop_loss_price', float('nan'))):,.2f}")
            st.write(f"**W1 Target Price:** {float(pair_row.get('rr_take_profit_price', float('nan'))):,.2f}")
            st.write(f"**R:R Basis:** {pair_row.get('rr_basis', 'N/A')}")
            st.caption(f"**Buy Reason:** {pair_row['buy_reason']}")
            st.caption(f"**Sell Reason:** {pair_row['sell_reason']}")

        # 稽核審查儲存
        review_state = st.radio("Was this trade correct?", ["Correct", "Wrong", "Unclear"], horizontal=True, key=f"review_state_{selected_pair_id}")
        review_note = st.text_area("Review Note", key=f"review_note_{selected_pair_id}", placeholder="輸入您對此交易的人工覆核意見...")
        if st.button("Save Review", key=f"save_review_{selected_pair_id}", use_container_width=True):
            append_trade_review(reviews_path, {
                "pair_id": int(pair_row["pair_id"]),
                "ticker": pair_row.get("ticker", st.session_state.get("ticker", "")),
                "buy_trade_id": str(pair_row.get("buy_trade_id", "")),
                "sell_trade_id": str(pair_row.get("sell_trade_id", "")),
                "buy_time": str(pd.Timestamp(pair_row["buy_time"])),
                "sell_time": str(pd.Timestamp(pair_row["sell_time"])),
                "buy_price": float(pair_row["buy_price"]),
                "sell_price": float(pair_row["sell_price"]),
                "profit_pct": float(pair_row["profit_pct"]),
                "pnl": float(pair_row["pnl"]),
                "training_reward": float(pair_row.get("training_reward", pair_row["profit_pct"] * 100.0)),
                "rr_stop_loss_price": float(pair_row.get("rr_stop_loss_price", float("nan"))),
                "rr_take_profit_price": float(pair_row.get("rr_take_profit_price", float("nan"))),
                "rr_stop_loss_time": str(pd.Timestamp(pair_row.get("rr_stop_loss_time", pair_row["buy_time"]))),
                "rr_take_profit_time": str(pd.Timestamp(pair_row.get("rr_take_profit_time", pair_row["buy_time"]))),
                "rr_basis": pair_row.get("rr_basis", ""),
                "buy_reason": pair_row.get("buy_reason", ""),
                "sell_reason": pair_row.get("sell_reason", ""),
                "is_correct": review_state,
                "review_note": review_note,
            })
            st.success("Review saved successfully.")

    # ────────────────────────────────────────────────────────
    # 左邊欄位：Plotly 蠟燭圖表與控制面版
    # ────────────────────────────────────────────────────────
    with col_chart:
        selected_pair = pairs_df[pairs_df["pair_id"] == st.session_state["selected_trade_pair_id"]].iloc[0]
        
        # 橫向控制開關 (Premium SaaS Dashboard 風格)
        col_c1, col_c2, col_c3, col_c4, col_c5 = st.columns([1.2, 1.0, 1.0, 1.0, 1.0])
        with col_c1:
            timeframe = st.selectbox("Chart Timeframe", ["W1", "D1", "H4", "H1"], index=3, key="pair_chart_timeframe")
        with col_c2:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            show_rr = st.checkbox("Show RRR Range", value=True, key="pair_show_rr")
        with col_c3:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            overlay_ob = st.checkbox("Order Blocks", value=True, key="pair_overlay_ob")
        with col_c4:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            overlay_fvg = st.checkbox("FVG", value=True, key="pair_overlay_fvg")
        with col_c5:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            overlay_liq = st.checkbox("Sweeps", value=True, key="pair_overlay_liq")

        overlay_old = st.checkbox("Show Old High/Low", value=True, key="pair_overlay_old")

        tf_rule = {"W1": "1W", "D1": "1D", "H4": "4h", "H1": "1h"}[timeframe]
        chart_source = raw_df.copy()
        chart_source["date"] = pd.to_datetime(chart_source["date"])
        chart_source = chart_source.sort_values("date").set_index("date")
        if timeframe != "H1":
            chart_source = resample_ohlcv(chart_source, tf_rule)
            chart_source = chart_source.reset_index().rename(columns={"index": "date"})
        else:
            chart_source = chart_source.reset_index()
        chart_source = prepare_data_for_chart(chart_source, rolling_window=100)

        buy_time = pd.Timestamp(selected_pair["buy_time"])
        sell_time = pd.Timestamp(selected_pair["sell_time"])
        padding = max((sell_time - buy_time) * 0.75, pd.Timedelta(days=10))
        t_start = buy_time - padding
        t_end = sell_time + padding
        chart_data = chart_source.copy()
        if chart_data.empty:
            st.error("無法取得該時段的圖表資料。")
            return

        entry_price = float(selected_pair["buy_price"])
        n_window = st.slider(
            "Price Window (+/- TWD)",
            min_value=10.0,
            max_value=1000.0,
            value=max(min(entry_price * 0.08, 1000.0), 10.0),
            step=10.0,
            key=f"pair_price_window_{selected_pair['pair_id']}",
        )
        visible_df = chart_data[(chart_data["date"] >= t_start) & (chart_data["date"] <= t_end)].copy()
        if visible_df.empty:
            visible_df = chart_data.copy()
        base_low = min(float(visible_df["low"].min()), entry_price - n_window)
        base_high = max(float(visible_df["high"].max()), entry_price + n_window)
        y_pad = max((base_high - base_low) * 0.05, 0.01)
        y_min = max(0.0, base_low - y_pad)
        y_max = base_high + y_pad

        fig = plotly_go.Figure()
        fig.add_trace(plotly_go.Candlestick(
            x=chart_data["date"],
            open=chart_data["open"] if "open" in chart_data.columns else chart_data["Open"],
            high=chart_data["high"] if "high" in chart_data.columns else chart_data["High"],
            low=chart_data["low"] if "low" in chart_data.columns else chart_data["Low"],
            close=chart_data["close"] if "close" in chart_data.columns else chart_data["Close"],
            name="Price",
            showlegend=False,
        ))
        if overlay_old and "old_high" in chart_data.columns:
            fig.add_trace(plotly_go.Scatter(x=chart_data["date"], y=chart_data["old_high"], mode="lines", line=dict(color="#00C853", width=1, dash="dot"), name="Old High"))
            fig.add_trace(plotly_go.Scatter(x=chart_data["date"], y=chart_data["old_low"], mode="lines", line=dict(color="#FF5252", width=1, dash="dot"), name="Old Low"))
        if overlay_ob and "ob_top" in chart_data.columns:
            ob_df = chart_data[chart_data["ob"] != 0]
            if not ob_df.empty:
                fig.add_trace(plotly_go.Scatter(x=ob_df["date"], y=ob_df["ob_top"], mode="markers", marker=dict(symbol="square", size=7, color="#FFD54F"), name="OB"))
        if overlay_fvg and "fvg_top" in chart_data.columns:
            fvg_bull = chart_data[chart_data["fvg"] > 0]
            fvg_bear = chart_data[chart_data["fvg"] < 0]
            if not fvg_bull.empty:
                fig.add_trace(plotly_go.Scatter(x=fvg_bull["date"], y=fvg_bull["fvg_top"], mode="markers", marker=dict(symbol="diamond", size=7, color="#00B0FF"), name="Bullish FVG"))
            if not fvg_bear.empty:
                fig.add_trace(plotly_go.Scatter(x=fvg_bear["date"], y=fvg_bear["fvg_bottom"], mode="markers", marker=dict(symbol="diamond", size=7, color="#FF9100"), name="Bearish FVG"))
        if overlay_liq and "liq_swept" in chart_data.columns:
            liq_df = chart_data[chart_data["liq_swept"] != 0]
            if not liq_df.empty:
                fig.add_trace(plotly_go.Scatter(x=liq_df["date"], y=liq_df["high"], mode="markers", marker=dict(symbol="x", size=8, color="#AA00FF"), name="Liquidity Sweep"))
        buy_price = float(selected_pair["buy_price"])
        sell_price = float(selected_pair["sell_price"])
        entry_price = buy_price
        pd_arrays = ret.get("pd_arrays")
        rr = ret.get("recommendation", {}).get("rr_details", {})
        h4_rr = rr.get("h4", {})
        w1_rr = rr.get("w1", {})
        pd_h1_low = np.nan
        pd_w1_high = np.nan
        if pd_arrays is not None and not pd_arrays.empty:
            h1_row = pd_arrays[pd_arrays["timeframe"] == "H1"]
            w1_row = pd_arrays[pd_arrays["timeframe"] == "W1"]
            if not h1_row.empty:
                pd_h1_low = h1_row.iloc[0].get("swing_low", np.nan)
            if not w1_row.empty:
                pd_w1_high = w1_row.iloc[0].get("swing_high", np.nan)
        trained_stop = float(selected_pair.get("rr_stop_loss_price", np.nan))
        trained_take = float(selected_pair.get("rr_take_profit_price", np.nan))
        stop_loss = trained_stop if pd.notna(trained_stop) else float(h4_rr.get("stop_loss", pd_h1_low if pd.notna(pd_h1_low) else buy_price - n_window * 0.5))
        take_profit = trained_take if pd.notna(trained_take) else float(w1_rr.get("take_profit", pd_w1_high if pd.notna(pd_w1_high) else buy_price + n_window * 0.5))
        stop_time = pd.Timestamp(selected_pair.get("rr_stop_loss_time", buy_time))
        take_time = pd.Timestamp(selected_pair.get("rr_take_profit_time", buy_time))
        rr_end_time = sell_time
        rr_success = sell_price >= take_profit
        rr_symbol = "V" if rr_success else "X"
        rr_symbol_color = "#00E676" if rr_success else "#FF5252"
        rr_basis_text = str(selected_pair.get("rr_basis", "") or "H4 stop / W1 target")
        st.caption(
            f"RR: Entry {entry_price:,.2f} | H4 Stop {stop_loss:,.2f} ({stop_time:%Y-%m-%d %H:%M}) | "
            f"W1 Target {take_profit:,.2f} ({take_time:%Y-%m-%d %H:%M}) | Exit {sell_price:,.2f} | Basis: {rr_basis_text}"
        )
        fig.add_shape(
            type="rect",
            x0=buy_time,
            x1=rr_end_time,
            y0=entry_price,
            y1=take_profit,
            fillcolor="rgba(76, 175, 80, 0.22)",
            line=dict(color="rgba(76, 175, 80, 0.22)", width=1),
            layer="below",
        )
        fig.add_shape(
            type="rect",
            x0=buy_time,
            x1=rr_end_time,
            y0=stop_loss,
            y1=entry_price,
            fillcolor="rgba(244, 67, 54, 0.20)",
            line=dict(color="rgba(244, 67, 54, 0.20)", width=1),
            layer="below",
        )
        fig.add_trace(plotly_go.Scatter(
            x=[buy_time, sell_time],
            y=[entry_price, entry_price],
            mode="lines",
            line=dict(color="#2196F3", width=2, dash="dash"),
            name="Entry",
        ))
        fig.add_trace(plotly_go.Scatter(
            x=[sell_time],
            y=[sell_price],
            mode="markers+text",
            marker=dict(symbol="circle", size=10, color="#FF5252", line=dict(width=2, color="white")),
            text=["EXIT"], textposition="bottom center", name="Exit",
        ))
        fig.add_annotation(x=buy_time, y=entry_price, text=f"BUY {entry_price:,.2f}", showarrow=False, yshift=16, font=dict(color="#2196F3", size=11))
        fig.add_annotation(x=sell_time, y=sell_price, text=f"SELL {sell_price:,.2f}", showarrow=False, yshift=-16, font=dict(color="#FF5252", size=11))
        fig.add_annotation(
            x=sell_time,
            y=max(take_profit, sell_price, entry_price) + (y_max - y_min) * 0.03,
            text=f"{rr_symbol} W1 Target" if rr_success else f"{rr_symbol} H4 Stop",
            showarrow=False,
            font=dict(color=rr_symbol_color, size=18),
        )
        if show_rr and ret.get("recommendation") and "rr_details" in ret["recommendation"]:
            rr = ret["recommendation"]["rr_details"]
            for tf in ["w1", "d1", "h4", "h1"]:
                tf_rr = rr.get(tf, {})
                entry = tf_rr.get("entry")
                sl = tf_rr.get("stop_loss")
                tp = tf_rr.get("take_profit")
                if pd.notna(entry):
                    fig.add_trace(plotly_go.Scatter(x=[t_start, t_end], y=[entry, entry], mode="lines", line=dict(color="white", width=1, dash="dash"), name=f"{tf.upper()} Entry"))
                if pd.notna(sl):
                    stop_name = "H4 Stop" if tf == "h4" else f"{tf.upper()} Stop"
                    fig.add_trace(plotly_go.Scatter(x=[t_start, t_end], y=[sl, sl], mode="lines", line=dict(color="#FF5252", width=1, dash="dash"), name=stop_name))
                if pd.notna(tp):
                    tp_name = "W1 Target" if tf == "w1" else f"{tf.upper()} Target"
                    fig.add_trace(plotly_go.Scatter(x=[t_start, t_end], y=[tp, tp], mode="lines", line=dict(color="#00E676", width=1, dash="dash"), name=tp_name))
        fig.update_layout(
            height=650,
            margin=dict(l=0, r=0, t=30, b=0),
            template="plotly_dark",
            xaxis_rangeslider_visible=True,
            hovermode="x unified",
            title=f"Trade #{int(selected_pair['pair_id'])} Review",
        )
        fig.update_xaxes(range=[t_start, t_end])
        fig.update_yaxes(range=[y_min, y_max])
        st.plotly_chart(fig, use_container_width=True)

    # ────────────────────────────────────────────────────────
    # 下方全寬區域：Trading Journal & AI Discussion 留言板
    # ────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 📔 Trading Journal & AI Discussion")

    col_journal_exp, col_journal_thread = st.columns([1, 2])
    with col_journal_exp:
        with st.container(border=True):
            st.markdown("#### 💡 SMC × DRL Core Logic")
            st.markdown(f"""
            * **移動停損停利 (Trailing Exits)**: 此環境採用動態時框計算出的停損與停利點 (`h4_rr_stop_loss_price` / `w1_rr_take_profit_price`)，因此出場門檻會隨行情推移呈**移動追蹤**態勢。
            * **DQN 長期預期回報勝出 (Expected Q-Value Overrides Bias)**: DQN 智能體以最大化長期投資組合價值為目標。即便當時的週線/日線趨勢偏向為空頭 (`-1`)，智能體若選擇 100% 持倉，代表它透過深度學習網絡計算出此處為**高勝率折價區/清算區**，具備極高的期望收益率。
            """)
            
    with col_journal_thread:
        # Helper to load and save trading journals
        def load_trade_journal() -> dict:
            import json
            journal_path = Config().outputs_dir / "trade_journal.json"
            if not journal_path.exists():
                return {}
            try:
                return json.loads(journal_path.read_text(encoding="utf-8"))
            except Exception:
                return {}

        def save_trade_journal(data: dict) -> None:
            import json
            journal_path = Config().outputs_dir / "trade_journal.json"
            journal_path.parent.mkdir(parents=True, exist_ok=True)
            journal_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        # 讀取當前交易對討論紀錄
        journal_db = load_trade_journal()
        pair_key = str(selected_pair_id)
        thread = journal_db.setdefault(pair_key, [])

        # 顯示歷史對話
        if thread:
            st.markdown("**討論歷程 (Journal Logs):**")
            for msg in thread:
                author = msg.get("author", "User")
                time_str = msg.get("timestamp", "")
                content = msg.get("content", "")
                if author == "User":
                    st.markdown(f"**🧑‍💻 User** ({time_str}):  \n{content}")
                else:
                    st.markdown(f"**🤖 AI Quant Coach** ({time_str}):  \n{content}")
                st.markdown("<hr style='margin: 0.5em 0; border: 0.5px solid #f0f2f6;'>", unsafe_allow_html=True)
        else:
            st.caption("尚無歷史討論筆記，您可以在下方輸入問題或心得開始記錄日誌！")

        # 留言文字輸入框與按鈕
        user_comment = st.text_area("新增日誌心得 / 向 AI 提問", key=f"journal_input_{selected_pair_id}", placeholder="例如：為什麼智能體會在此建倉？...", height=100)
        if st.button("提交討論日誌", key=f"submit_journal_{selected_pair_id}", use_container_width=True):
            if user_comment.strip():
                from datetime import datetime
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                # 新增使用者留言
                user_msg = {"timestamp": now_str, "author": "User", "content": user_comment}
                thread.append(user_msg)
                
                # 調用 AI 討論回覆
                with st.spinner("AI 導師正在深入剖析交易邏輯..."):
                    pair_info = {
                        "ticker": pair_row.get("ticker", st.session_state.get("ticker", "")),
                        "buy_time": str(pd.Timestamp(pair_row["buy_time"])),
                        "sell_time": str(pd.Timestamp(pair_row["sell_time"])),
                        "buy_price": float(pair_row["buy_price"]),
                        "sell_price": float(pair_row["sell_price"]),
                        "profit_pct": float(pair_row["profit_pct"]),
                        "rr_stop_loss_price": float(pair_row.get("rr_stop_loss_price", float("nan"))),
                        "rr_take_profit_price": float(pair_row.get("rr_take_profit_price", float("nan"))),
                        "rr_basis": pair_row.get("rr_basis", ""),
                        "buy_reason": pair_row.get("buy_reason", ""),
                        "sell_reason": pair_row.get("sell_reason", ""),
                    }
                    ai_reply_content = generate_journal_ai_reply(pair_info, user_comment, thread[:-1])
                    ai_msg = {"timestamp": now_str, "author": "AI Quant Coach", "content": ai_reply_content}
                    thread.append(ai_msg)
                    
                # 儲存更新後的歷程
                journal_db[pair_key] = thread
                save_trade_journal(journal_db)
                st.success("日誌已更新！")
                st.rerun()


def _render_log_html(log_messages):
    """共用的 log HTML 渲染函式。"""
    display_text = "\n".join(log_messages)
    return f"""
    <div style="background-color: #F8F9FA; color: #1A1A2E; padding: 12px 16px; border-radius: 8px; font-family: 'SF Mono', Consolas, monospace; font-size: 13px; height: 280px; display: flex; flex-direction: column-reverse; overflow-y: auto; border: 1px solid #E0E0E0;">
        <div style="white-space: pre-wrap;">{display_text}</div>
    </div>
    """


def main():
    if "raw_df" not in st.session_state and "ticker" not in st.session_state:
        st.session_state["auto_fetch"] = True
    # ── Header ──
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        :root {
            --bg: #f6f8fb;
            --panel: #ffffff;
            --panel-alt: #fbfcfe;
            --border: #dce3ec;
            --text: #162033;
            --muted: #667085;
            --accent: #2563eb;
            --accent-soft: rgba(37, 99, 235, 0.08);
        }
        html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; background: var(--bg); color: var(--text); }
        .stApp { background: linear-gradient(180deg, #f8fafc 0%, #f4f7fb 100%); }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 12px;
            box-shadow: 0 8px 22px rgba(15, 23, 42, 0.04);
            padding: 0.1rem 0.2rem;
        }
        section[data-testid="stSidebar"] {
            background: #f8fbff;
            border-right: 1px solid var(--border);
        }
        .stMetric {
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 0.8rem 0.9rem;
            box-shadow: 0 4px 10px rgba(15, 23, 42, 0.03);
        }
        .stButton > button {
            border-radius: 10px;
            border: 1px solid #cfd8e3;
            background: #fff;
            color: var(--text);
            font-weight: 600;
            padding: 0.55rem 0.9rem;
        }
        .stButton > button[kind="primary"] {
            background: var(--accent);
            color: white;
            border-color: var(--accent);
        }
        .stButton > button:hover {
            border-color: var(--accent);
            background: var(--accent-soft);
        }
        .stSelectbox label, .stMultiSelect label, .stRadio label, .stSlider label, .stTextInput label {
            color: var(--muted);
            font-size: 0.92rem;
        }
        h1, h2, h3, h4 { letter-spacing: 0; }
    </style>
    <div style="padding: 1.0rem 0 0.85rem 0; border-bottom: 1px solid #dbe3ee; margin-bottom: 1.2rem;">
        <div style="display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem;">
            <div style="flex: 1; text-align: center;">
                <h1 style="margin: 0; font-size: 2.4rem; font-weight: 700; color: #162033; font-family: 'Inter', sans-serif;">
                    SMC × DRL Trading Platform
                </h1>
                <p style="margin: 0.35rem 0 0 0; font-size: 0.92rem; color: #667085; font-family: 'Inter', sans-serif;">
                    Smart Money Concepts × Deep Reinforcement Learning — Multi-Timeframe Analysis & Strategy
                </p>
            </div>
            <div style="flex: 0 0 auto; padding-top: 0.15rem;">
                <a href="https://github.com/huanchen1107/2026FintechSMC" target="_blank">
                    <img src="https://img.shields.io/badge/GitHub-View%20Source-181717?style=for-the-badge&logo=github" alt="GitHub">
                </a>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if "active_tab" not in st.session_state:
        st.session_state["active_tab"] = "data"
    st.session_state.setdefault("rr_threshold_shared", float(getattr(cfg, "training_rr_threshold", 2.0)))
    st.session_state.setdefault("training_rr_threshold_input", float(st.session_state["rr_threshold_shared"]))
    cfg.training_rr_threshold = float(st.session_state.get("rr_threshold_shared", getattr(cfg, "training_rr_threshold", 2.0)))
    active_tab = st.session_state["active_tab"]

    nav_col, main_col = st.columns([1.15, 5.0], gap="large")
    with nav_col:
        st.markdown("#### Steps")
        st.markdown(
            """
            <style>
            div[data-testid="column"] .stButton > button {
                font-weight: 700 !important;
                font-size: 0.95rem !important;
                padding-top: 0.7rem !important;
                padding-bottom: 0.7rem !important;
                line-height: 1.1 !important;
                white-space: pre-line !important;
                text-align: center !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        nav_items = [
            ("Step 0", "Loading Data", "data"),
            ("Step 1", "SMC Features", "training"),
            ("Step 2", "Strategy Selection", "report"),
            ("Step 3", "AI Suggestion", "ai_comment"),
            ("Step 4", "Trading Pair Review", "analysis"),
        ]
        for label, subtitle, tab_id in nav_items:
            st.markdown(f"<div style='margin: 0 0 0.18rem 0; font-size: 0.76rem; color: #7a8699; text-align: center;'>{subtitle}</div>", unsafe_allow_html=True)
            btn_type = "primary" if active_tab == tab_id else "secondary"
            if st.button(label, use_container_width=True, key=f"tab_{tab_id}", type=btn_type):
                st.session_state["active_tab"] = tab_id
                st.rerun()
            st.markdown("<div style='height: 0.55rem;'></div>", unsafe_allow_html=True)
    with main_col:
        st.markdown('<div style="border-top: 1px solid #dbe3ee; margin: 0 0 1rem 0;"></div>', unsafe_allow_html=True)

        if active_tab == "data":
            st.markdown("#### Step 0: Data Loading Settings")
            st.caption("Load the maximum available 1H history for the selected ticker.")
            col_input1, col_input2, col_input3, col_btn1, col_btn2 = st.columns([2.5, 1.5, 1.5, 0.7, 1.0])
            with col_input1:
                ticker = st.text_input("Ticker (e.g. AAPL, 2330.TW)", value=st.session_state.get("ticker", "2330.TW"), key="ticker_input")
            if ticker and ticker != st.session_state.get("ticker") and ticker.strip() != "":
                st.session_state["auto_fetch"] = True
            with col_input2:
                start_date = st.date_input("Start Date", value=pd.to_datetime(st.session_state.get("start_date", cfg.start_date)), key="start_date_input")
            with col_input3:
                end_date = st.date_input("End Date", value=pd.to_datetime(st.session_state.get("end_date", cfg.end_date)), key="end_date_input")
            with col_btn1:
                start_btn = st.button("Fetch & Analyze", key="fetch_analyze")
            with col_btn2:
                reset_btn = st.button("Reset / Clear", key="reset_clear")

            if reset_btn:
                st.session_state.clear()
                st.rerun()

            date_diff = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days
            if date_diff > 730:
                st.warning(f"Date range is {date_diff} days, exceeding yfinance 1H intraday limit (approx. 730 days). Data might be incomplete.")

            if "data_range_warning" in st.session_state:
                st.warning(st.session_state["data_range_warning"])

            if start_btn or st.session_state.get("auto_fetch", False):
                st.session_state.pop("auto_fetch", None)
                if not ticker:
                    st.warning("Please enter a ticker symbol")
                    return
                st.session_state.pop("model_ret", None)
                with st.spinner(f"Fetching 1H data from {start_date} to {end_date}..."):
                    raw_df = load_data_raw(ticker, start_date, end_date)
                    if raw_df is not None:
                        actual_start = str(raw_df["date"].min().date())
                        actual_end = str(raw_df["date"].max().date())
                        st.session_state["raw_df"] = raw_df
                        st.session_state["ticker"] = ticker
                        st.session_state["start_date"] = actual_start
                        st.session_state["end_date"] = actual_end
                        save_raw_data_cache(ticker, raw_df)
                        try:
                            step1_csv_path = _step1_pd_excel_path()
                            with st.spinner("Updating Step 1 CSV from fetched market data..."):
                                rebuild_step1_csv_from_source(step1_csv_path)
                        except Exception as csv_err:
                            st.warning(f"Fetched market data, but Step 1 CSV refresh failed: {csv_err}")
                        if actual_start != str(start_date):
                            st.session_state["data_range_warning"] = (
                                f"{ticker} 實際資料從 **{actual_start}** 開始（請求 {start_date}）。"
                                f"訓練將使用實際可用範圍：{actual_start} ~ {actual_end}。"
                                f"若股票歷史不足 14 個月，訓練可能仍會失敗（W1 SMA-60 需要 60 週資料）。"
                            )
                        else:
                            st.session_state.pop("data_range_warning", None)
                        st.rerun()
                    else:
                        st.error("Failed to fetch stock data, please check ticker or date range.")
                        return

            if "raw_df" in st.session_state:
                st.success(
                    f"Loaded {st.session_state.get('ticker', ticker)} | "
                    f"{st.session_state.get('start_date', start_date)} → {st.session_state.get('end_date', end_date)}"
                )

            if "raw_df" in st.session_state:
                st.divider()
                render_chart()

            return

        # 先預先計算 recommendation，讓 render_chart 可以讀取到 RRR 資料
        ret = st.session_state.get("model_ret", {})
        if ret:
            try:
                st.session_state["recommendation"] = compute_recommendation(ret, cfg)
            except Exception:
                pass

        if "data_range_warning" in st.session_state:
            st.warning(st.session_state["data_range_warning"])

        if "raw_df" not in st.session_state:
            if active_tab != "data":
                st.info("Step 0: load data first.")
            return

        raw_df = st.session_state["raw_df"]
        ticker = st.session_state.get("ticker", "UNKNOWN")

    if "raw_df" not in st.session_state:
        st.info("Waiting for data and model training...")
        return

    raw_df = st.session_state["raw_df"]
    ticker = st.session_state.get("ticker", "UNKNOWN")

    # ── Content ──
    with main_col:
        if active_tab == "analysis":
            render_trade_analysis()

        if active_tab == "training":
            st.markdown("#### Step 1: SMC Features")
            st.caption("Step 1 reads the saved SMC CSV files from outputs/ and shows the selected file.")
            csv_files = list_output_csv_files()
            if not csv_files:
                st.warning("No CSV files found in outputs/. Generate the SMC table first.")
            else:
                selected_csv = st.selectbox("SMC CSV file", csv_files, index=csv_files.index("step1_pd_arrays.csv") if "step1_pd_arrays.csv" in csv_files else 0, key="pd_csv_select")
                csv_path = Path(cfg.outputs_dir) / selected_csv
                try:
                    pd_arrays = pd.read_csv(csv_path)
                    pd_arrays = ensure_step1_table_meta(pd_arrays)
                    try:
                        pd_arrays.to_csv(csv_path, index=False)
                    except Exception as save_err:
                        st.warning(f"Loaded CSV but could not persist metadata: {save_err}")
                    if "timestamp" not in pd_arrays.columns or pd_arrays["timestamp"].isna().all():
                        st.info("Rebuilding Step 1 CSV from source data to restore market timestamps...")
                        pd_arrays = rebuild_step1_csv_from_source(csv_path)
                except Exception as e:
                    st.warning(f"Failed to load CSV, rebuilding from source: {e}")
                    try:
                        pd_arrays = rebuild_step1_csv_from_source(csv_path)
                    except Exception as rebuild_err:
                        st.error(f"Failed to rebuild Step 1 CSV from source: {rebuild_err}")
                        pd_arrays = pd.DataFrame()
                if pd_arrays is not None and not pd_arrays.empty:
                    with st.container(border=True):
                        st.markdown("#### PD Arrays")
                        st.caption(f"CSV source: {csv_path}")
                        filter_col, table_col = st.columns([1, 4])
                        with filter_col:
                            tf_options = ["ALL", "W1", "D1", "4H", "1H"]
                            selected_tf = st.selectbox("Timeframe", tf_options, index=0, key="pd_tf_filter")
                            only_valid = st.checkbox("Valid only", value=False, key="pd_valid_only")
                            weekly_view = st.checkbox("Weekly structure view", value=False, key="pd_weekly_view")
                            compact_view = st.checkbox("Compact view", value=True, key="pd_compact_view")
                            max_rows = st.number_input("Rows to show", min_value=50, max_value=5000, value=300, step=50, key="pd_row_limit")
                            training_rr_threshold = st.number_input(
                                "Training H1/W1 RR >",
                                min_value=1.0,
                                max_value=10.0,
                                value=float(st.session_state.get("rr_threshold_shared", getattr(cfg, "training_rr_threshold", 2.0))),
                                step=0.1,
                                key="training_rr_threshold_input",
                                on_change=sync_training_rr_threshold_shared,
                            )
                            sync_training_rr_threshold_shared()
                            training_rr_threshold = float(st.session_state.get("rr_threshold_shared", getattr(cfg, "training_rr_threshold", 2.0)))
                            cfg.training_rr_threshold = training_rr_threshold
                            st.caption(f"Step 1 marks candles where H1/W1 RR >= {float(training_rr_threshold):.1f}.")
                            feature_options = [c for c in pd_arrays.columns if c not in ["id", "created_at", "updated_at"]]
                            default_features = [c for c in [
                                "timestamp", "close_price", "swing_tag", "fvg_tag", "pd_valid",
                                "w1_swing_high_version", "w1_swing_low_version",
                                "w1_swing_high_replaced", "w1_swing_low_replaced",
                                "w1_active_swing_high", "w1_active_swing_low",
                                "d1_swing_high_version", "d1_swing_low_version",
                                "d1_swing_high_replaced", "d1_swing_low_replaced",
                                "d1_active_swing_high", "d1_active_swing_low",
                                "h4_swing_high_version", "h4_swing_low_version",
                                "h4_swing_high_replaced", "h4_swing_low_replaced",
                                "h4_active_swing_high", "h4_active_swing_low",
                                "h1_swing_high_version", "h1_swing_low_version",
                                "h1_swing_high_replaced", "h1_swing_low_replaced",
                                "h1_active_swing_high", "h1_active_swing_low",
                                "w1_liquidity_sweep_tag", "d1_liquidity_sweep_tag", "h4_liquidity_sweep_tag", "h1_liquidity_sweep_tag",
                                "w1_smc_bias", "d1_smc_bias", "h4_smc_bias", "h1_smc_bias",
                            ] if c in feature_options]
                            selected_features = st.multiselect(
                                "Features",
                                feature_options,
                                default=default_features,
                                key="pd_feature_filter",
                            )
                        view_df = pd_arrays.copy()
                        if weekly_view:
                            weekly_cols = [c for c in [
                                "timestamp", "close_price", "pd_valid",
                                "w1_swing_tag", "w1_fvg_tag", "w1_liquidity_sweep_tag",
                                "w1_swing_high_version", "w1_swing_low_version",
                                "w1_swing_high_replaced", "w1_swing_low_replaced",
                                "w1_active_swing_high", "w1_active_swing_low",
                                "w1_smc_bias", "w1_rr_ratio", "w1_rr_valid",
                                "w1_last_swing_high", "w1_last_swing_low",
                                "w1_bos_bullish", "w1_bos_bearish",
                                "w1_choch_bullish", "w1_choch_bearish",
                                "w1_bullish_fvg", "w1_bearish_fvg",
                                "w1_bullish_ob_distance", "w1_bearish_ob_distance",
                            ] if c in view_df.columns]
                            if weekly_cols:
                                view_df = view_df[weekly_cols + [c for c in view_df.columns if c not in weekly_cols]]
                        chart_tf_map = {"W1": "1wk", "D1": "1d", "4H": "4h", "1H": "1h"}
                        chart_tf = chart_tf_map.get(selected_tf, "1h") if selected_tf != "ALL" else "1h"
                        try:
                            chart_df = process_data_for_chart(raw_df, chart_tf, cfg.rolling_window)
                            chart_df = chart_df.loc[:, ~chart_df.columns.duplicated()].copy()
                            chart_df["date"] = pd.to_datetime(chart_df["date"], errors="coerce").dt.tz_localize(None).astype("datetime64[ns]")
                            chart_df = chart_df.dropna(subset=["date", "open", "high", "low", "close"]).sort_values("date")
                            hover_source = view_df.copy()
                            if "timestamp" in hover_source.columns:
                                hover_source["date"] = pd.to_datetime(hover_source["timestamp"], errors="coerce").dt.tz_localize(None).astype("datetime64[ns]")
                            elif "date" in hover_source.columns:
                                hover_source["date"] = pd.to_datetime(hover_source["date"], errors="coerce").dt.tz_localize(None).astype("datetime64[ns]")
                            elif "datetime" in hover_source.columns:
                                hover_source["date"] = pd.to_datetime(hover_source["datetime"], errors="coerce").dt.tz_localize(None).astype("datetime64[ns]")
                            else:
                                hover_source["date"] = pd.NaT
                            hover_source = hover_source.dropna(subset=["date"]).sort_values("date")
                            hover_source = hover_source.drop(columns=[c for c in ["open", "high", "low", "close"] if c in hover_source.columns])
                            merged_hover = pd.merge_asof(
                                chart_df[["date", "open", "high", "low", "close"]].copy(),
                                hover_source.copy(),
                                left_on="date",
                                right_on="date",
                                direction="nearest",
                                tolerance=pd.Timedelta("1D"),
                            )
                            if "close_price" not in merged_hover.columns:
                                merged_hover["close_price"] = merged_hover["close"]
                            rr_threshold = float(st.session_state.get("training_rr_threshold", getattr(cfg, "training_rr_threshold", 2.0)))
                            rr_col = "h1_rr_ratio" if "h1_rr_ratio" in merged_hover.columns else ("rr_ratio" if "rr_ratio" in merged_hover.columns else None)
                            rr_valid_col = "h1_rr_valid" if "h1_rr_valid" in merged_hover.columns else ("rr_valid" if "rr_valid" in merged_hover.columns else None)
                            fig = plotly_go.Figure()
                            fig.add_trace(plotly_go.Candlestick(
                                x=merged_hover["date"],
                                open=merged_hover["open"],
                                high=merged_hover["high"],
                                low=merged_hover["low"],
                                close=merged_hover["close"],
                                name="Price",
                                showlegend=False,
                            ))
                            hover_text = merged_hover.apply(_build_step1_hover_text, axis=1)
                            fig.add_trace(plotly_go.Scatter(
                                x=merged_hover["date"],
                                y=merged_hover["close"],
                                mode="markers",
                                marker=dict(size=8, color="rgba(0,0,0,0)"),
                                hovertemplate="%{text}<extra></extra>",
                                text=hover_text,
                                showlegend=False,
                            ))
                            if rr_col is not None:
                                rr_mask = pd.to_numeric(merged_hover[rr_col], errors="coerce") >= rr_threshold
                                if rr_valid_col is not None:
                                    rr_mask = rr_mask & (pd.to_numeric(merged_hover[rr_valid_col], errors="coerce").fillna(0).astype(int) == 1)
                                rr_hits = merged_hover.loc[rr_mask, "date"].dropna()
                                y_min = float(pd.to_numeric(merged_hover["low"], errors="coerce").min())
                                y_max = float(pd.to_numeric(merged_hover["high"], errors="coerce").max())
                                for rr_dt in rr_hits:
                                    rr_x = pd.Timestamp(rr_dt).to_pydatetime()
                                    fig.add_trace(plotly_go.Scatter(
                                        x=[rr_x, rr_x],
                                        y=[y_min, y_max],
                                        mode="lines",
                                        line=dict(color="rgba(0, 200, 83, 0.65)", width=1, dash="dot"),
                                        hoverinfo="skip",
                                        showlegend=False,
                                    ))
                            fig.update_layout(
                                height=420,
                                margin=dict(l=0, r=0, t=20, b=0),
                                template="plotly_white",
                                hovermode="x unified",
                                xaxis_rangeslider_visible=True,
                            )
                            st.plotly_chart(fig, use_container_width=True)
                        except Exception as chart_err:
                            st.warning(f"Step 1 chart unavailable: {chart_err}")
                        with table_col:
                            if selected_tf != "ALL":
                                swing_series = view_df["swing_tag"].astype(str) if "swing_tag" in view_df.columns else pd.Series([""] * len(view_df), index=view_df.index)
                                fvg_series = view_df["fvg_tag"].astype(str) if "fvg_tag" in view_df.columns else pd.Series([""] * len(view_df), index=view_df.index)
                                label_map = {"W1": "Week", "D1": "Day", "4H": "4H", "1H": "1H"}
                                tf_label = label_map.get(selected_tf, selected_tf)
                                mask = swing_series.str.contains(tf_label, na=False) | fvg_series.str.contains(tf_label, na=False)
                                view_df = view_df[mask]
                            if only_valid and "pd_valid" in view_df.columns:
                                view_df = view_df[view_df["pd_valid"].fillna(0).astype(int) == 1]
                            if "timestamp" not in view_df.columns:
                                for candidate in ["datetime", "date", "time", "close_time"]:
                                    if candidate in view_df.columns:
                                        view_df["timestamp"] = pd.to_datetime(view_df[candidate], errors="coerce").dt.strftime("%Y-%m-%d %H:%M")
                                        break
                            fixed_cols = ["timestamp", "close_price", "swing_tag", "fvg_tag", "pd_valid"]
                            leading_cols = [c for c in fixed_cols if c in view_df.columns]
                            selected_core = [c for c in selected_features if c in view_df.columns and c not in leading_cols]
                            extra_cols = [c for c in view_df.columns if c not in leading_cols and c not in selected_core]
                            if weekly_view:
                                preferred = [c for c in [
                                    "timestamp", "close_price", "w1_swing_tag", "w1_fvg_tag", "w1_liquidity_sweep_tag",
                                    "w1_swing_high_version", "w1_swing_low_version",
                                    "w1_swing_high_replaced", "w1_swing_low_replaced",
                                    "w1_active_swing_high", "w1_active_swing_low",
                                    "w1_smc_bias", "w1_rr_ratio", "w1_rr_valid", "pd_valid",
                                    "w1_lib_swing_highlow", "w1_lib_swing_level",
                                    "w1_lib_fvg", "w1_lib_fvg_top", "w1_lib_fvg_bottom",
                                    "w1_lib_bos", "w1_lib_choch", "w1_lib_bos_level",
                                    "w1_lib_ob", "w1_lib_ob_top", "w1_lib_ob_bottom",
                                    "w1_lib_liquidity", "w1_lib_liquidity_level",
                                ] if c in view_df.columns]
                                selected_core = [c for c in preferred if c in view_df.columns]
                            if compact_view:
                                compact_priority = [
                                    "timestamp", "close_price", "swing_tag", "fvg_tag", "pd_valid",
                                    "w1_swing_high_version", "w1_swing_low_version",
                                    "w1_swing_high_replaced", "w1_swing_low_replaced",
                                    "w1_active_swing_high", "w1_active_swing_low",
                                    "d1_swing_high_version", "d1_swing_low_version",
                                    "d1_swing_high_replaced", "d1_swing_low_replaced",
                                    "d1_active_swing_high", "d1_active_swing_low",
                                    "h4_swing_high_version", "h4_swing_low_version",
                                    "h4_swing_high_replaced", "h4_swing_low_replaced",
                                    "h4_active_swing_high", "h4_active_swing_low",
                                    "h1_swing_high_version", "h1_swing_low_version",
                                    "h1_swing_high_replaced", "h1_swing_low_replaced",
                                    "h1_active_swing_high", "h1_active_swing_low",
                                    "w1_lib_swing_highlow", "w1_lib_swing_level",
                                    "w1_lib_fvg", "w1_lib_fvg_top", "w1_lib_fvg_bottom",
                                    "w1_lib_bos", "w1_lib_choch", "w1_lib_bos_level",
                                    "w1_lib_ob", "w1_lib_ob_top", "w1_lib_ob_bottom",
                                    "w1_lib_liquidity", "w1_lib_liquidity_level",
                                    "d1_lib_swing_highlow", "d1_lib_swing_level",
                                    "d1_lib_fvg", "d1_lib_fvg_top", "d1_lib_fvg_bottom",
                                    "d1_lib_bos", "d1_lib_choch", "d1_lib_bos_level",
                                    "d1_lib_ob", "d1_lib_ob_top", "d1_lib_ob_bottom",
                                    "d1_lib_liquidity", "d1_lib_liquidity_level",
                                    "h4_lib_swing_highlow", "h4_lib_swing_level",
                                    "h4_lib_fvg", "h4_lib_fvg_top", "h4_lib_fvg_bottom",
                                    "h4_lib_bos", "h4_lib_choch", "h4_lib_bos_level",
                                    "h4_lib_ob", "h4_lib_ob_top", "h4_lib_ob_bottom",
                                    "h4_lib_liquidity", "h4_lib_liquidity_level",
                                    "h1_lib_swing_highlow", "h1_lib_swing_level",
                                    "h1_lib_fvg", "h1_lib_fvg_top", "h1_lib_fvg_bottom",
                                    "h1_lib_bos", "h1_lib_choch", "h1_lib_bos_level",
                                    "h1_lib_ob", "h1_lib_ob_top", "h1_lib_ob_bottom",
                                    "h1_lib_liquidity", "h1_lib_liquidity_level",
                                ]
                                selected_core = [c for c in compact_priority if c in view_df.columns]
                            display_cols = leading_cols + selected_core + extra_cols
                            meta_first = [c for c in ["timestamp", "close_price", "swing_tag", "fvg_tag", "pd_valid"] if c in display_cols]
                            display_cols = meta_first + [c for c in display_cols if c not in meta_first]
                            if not display_cols:
                                display_cols = fixed_cols
                            display_df = view_df[[c for c in display_cols if c in view_df.columns]].copy()
                            if len(display_df) > int(max_rows):
                                display_df = display_df.tail(int(max_rows)).copy()
                            display_df = _format_step1_display(display_df)
                            display_df = display_df.loc[:, ~display_df.columns.duplicated()].copy()
                            rename_map = {
                                "timestamp": "Time",
                                "close_price": "Close",
                                "swing_tag": "Swing",
                                "fvg_tag": "FVG",
                                "pd_valid": "PD Valid",
                                "w1_swing_high_version": "W1 SH Ver",
                                "w1_swing_low_version": "W1 SL Ver",
                                "w1_swing_high_replaced": "W1 SH Repl",
                                "w1_swing_low_replaced": "W1 SL Repl",
                                "w1_active_swing_high": "W1 Active SH",
                                "w1_active_swing_low": "W1 Active SL",
                                "d1_swing_high_version": "D1 SH Ver",
                                "d1_swing_low_version": "D1 SL Ver",
                                "d1_swing_high_replaced": "D1 SH Repl",
                                "d1_swing_low_replaced": "D1 SL Repl",
                                "d1_active_swing_high": "D1 Active SH",
                                "d1_active_swing_low": "D1 Active SL",
                                "h4_swing_high_version": "H4 SH Ver",
                                "h4_swing_low_version": "H4 SL Ver",
                                "h4_swing_high_replaced": "H4 SH Repl",
                                "h4_swing_low_replaced": "H4 SL Repl",
                                "h4_active_swing_high": "H4 Active SH",
                                "h4_active_swing_low": "H4 Active SL",
                                "h1_swing_high_version": "H1 SH Ver",
                                "h1_swing_low_version": "H1 SL Ver",
                                "h1_swing_high_replaced": "H1 SH Repl",
                                "h1_swing_low_replaced": "H1 SL Repl",
                                "h1_active_swing_high": "H1 Active SH",
                                "h1_active_swing_low": "H1 Active SL",
                                "w1_lib_swing_highlow": "W1 Lib Swing",
                                "w1_lib_swing_level": "W1 Lib Level",
                                "w1_lib_fvg": "W1 Lib FVG",
                                "w1_lib_fvg_top": "W1 Lib FVG Top",
                                "w1_lib_fvg_bottom": "W1 Lib FVG Bottom",
                                "w1_lib_bos": "W1 Lib BOS",
                                "w1_lib_choch": "W1 Lib CHOCH",
                                "w1_lib_bos_level": "W1 Lib BOS Level",
                                "w1_lib_ob": "W1 Lib OB",
                                "w1_lib_ob_top": "W1 Lib OB Top",
                                "w1_lib_ob_bottom": "W1 Lib OB Bottom",
                                "w1_lib_liquidity": "W1 Lib Liquidity",
                                "w1_lib_liquidity_level": "W1 Lib Liquidity Level",
                                "d1_lib_swing_highlow": "D1 Lib Swing",
                                "d1_lib_swing_level": "D1 Lib Level",
                                "d1_lib_fvg": "D1 Lib FVG",
                                "d1_lib_fvg_top": "D1 Lib FVG Top",
                                "d1_lib_fvg_bottom": "D1 Lib FVG Bottom",
                                "d1_lib_bos": "D1 Lib BOS",
                                "d1_lib_choch": "D1 Lib CHOCH",
                                "d1_lib_bos_level": "D1 Lib BOS Level",
                                "d1_lib_ob": "D1 Lib OB",
                                "d1_lib_ob_top": "D1 Lib OB Top",
                                "d1_lib_ob_bottom": "D1 Lib OB Bottom",
                                "d1_lib_liquidity": "D1 Lib Liquidity",
                                "d1_lib_liquidity_level": "D1 Lib Liquidity Level",
                                "h4_lib_swing_highlow": "H4 Lib Swing",
                                "h4_lib_swing_level": "H4 Lib Level",
                                "h4_lib_fvg": "H4 Lib FVG",
                                "h4_lib_fvg_top": "H4 Lib FVG Top",
                                "h4_lib_fvg_bottom": "H4 Lib FVG Bottom",
                                "h4_lib_bos": "H4 Lib BOS",
                                "h4_lib_choch": "H4 Lib CHOCH",
                                "h4_lib_bos_level": "H4 Lib BOS Level",
                                "h4_lib_ob": "H4 Lib OB",
                                "h4_lib_ob_top": "H4 Lib OB Top",
                                "h4_lib_ob_bottom": "H4 Lib OB Bottom",
                                "h4_lib_liquidity": "H4 Lib Liquidity",
                                "h4_lib_liquidity_level": "H4 Lib Liquidity Level",
                                "h1_lib_swing_highlow": "H1 Lib Swing",
                                "h1_lib_swing_level": "H1 Lib Level",
                                "h1_lib_fvg": "H1 Lib FVG",
                                "h1_lib_fvg_top": "H1 Lib FVG Top",
                                "h1_lib_fvg_bottom": "H1 Lib FVG Bottom",
                                "h1_lib_bos": "H1 Lib BOS",
                                "h1_lib_choch": "H1 Lib CHOCH",
                                "h1_lib_bos_level": "H1 Lib BOS Level",
                                "h1_lib_ob": "H1 Lib OB",
                                "h1_lib_ob_top": "H1 Lib OB Top",
                                "h1_lib_ob_bottom": "H1 Lib OB Bottom",
                                "h1_lib_liquidity": "H1 Lib Liquidity",
                                "h1_lib_liquidity_level": "H1 Lib Liquidity Level",
                            }
                            display_df = display_df.rename(columns={k: v for k, v in rename_map.items() if k in display_df.columns})
                            display_df = display_df.loc[:, ~display_df.columns.duplicated()].copy()
                            display_df = display_df.reset_index(drop=True)
                            max_style_cells = 262144
                            cell_count = int(display_df.shape[0] * max(display_df.shape[1], 1))
                            metrics = st.columns(4)
                            with metrics[0]:
                                st.metric("Rows", len(display_df))
                            with metrics[1]:
                                st.metric("Valid", int(display_df["PD Valid"].fillna(0).astype(int).sum()) if "PD Valid" in display_df.columns else 0)
                            with metrics[2]:
                                st.metric("Cols", len(display_df.columns))
                            with metrics[3]:
                                st.metric("Mode", "Compact" if compact_view else "Full")
                            if cell_count <= max_style_cells:
                                def _step1_row_style(row):
                                    pdv = row.get("PD Valid", row.get("pd_valid", 1))
                                    if isinstance(pdv, pd.Series):
                                        pdv = pdv.iloc[0] if not pdv.empty else 1
                                    try:
                                        is_invalid = int(pdv) == 0
                                    except Exception:
                                        is_invalid = False
                                    return [
                                        "background-color: rgba(15, 23, 42, 0.06); color: #9ca3af;" if is_invalid else ""
                                        for _ in row
                                    ]
                                styled = display_df.style.apply(
                                    _step1_row_style,
                                    axis=1,
                                )
                                st.dataframe(styled, use_container_width=True, hide_index=True, height=420, column_order=list(display_df.columns))
                            else:
                                st.warning(f"Table too large for row styling ({cell_count} cells). Showing plain dataframe instead.")
                                st.dataframe(display_df, use_container_width=True, hide_index=True, height=420, column_order=list(display_df.columns))
                            if len(view_df) > len(display_df):
                                st.caption(f"Showing latest {len(display_df)} of {len(view_df)} rows from the selected CSV.")

                        with st.expander("Full raw PD columns", expanded=False):
                            raw_cols = [c for c in view_df.columns if c not in ["id", "created_at", "updated_at"]]
                            st.dataframe(
                                view_df[raw_cols].tail(int(max_rows)),
                                use_container_width=True,
                                hide_index=True,
                                height=260,
                            )

                        if weekly_view:
                            weekly_summary_cols = [c for c in [
                                "w1_last_swing_high", "w1_last_swing_low", "w1_bullish_fvg", "w1_bearish_fvg",
                                "w1_liquidity_sweep_bullish", "w1_liquidity_sweep_bearish", "w1_smc_bias",
                            ] if c in pd_arrays.columns]
                            if weekly_summary_cols:
                                latest_weekly = pd_arrays[weekly_summary_cols].tail(1).copy()
                                latest_weekly = latest_weekly.reset_index(drop=True)
                                st.markdown("#### Weekly Summary")
                                st.dataframe(latest_weekly, use_container_width=True, hide_index=True, height=160)

            with st.expander("MDP Model", expanded=False):
                st.markdown(
                    """
                    - **State**: latest 100 PD-valid steps of W1 / D1 / H4 / H1 SMC features, plus portfolio context and live RR features.
                    - **Action**: DQN Position, DQN-on-Buy with RR-box-Sell, or Double DQN-on-Buy with RR-box-Sell.
                    - **Transition**: rebalance to the selected target position, then advance one bar; buy-only modes auto-exit on H4 stop-loss or W1 take-profit.
                    - **Reward**: step return, drawdown penalty, trade penalty, MTF confluence bonus, and higher-timeframe conflict penalty.
                    - **Episode end**: when the dataset reaches the final bar.
                    """
                )

        # ── DRL × SMC Report Tab ──
        elif active_tab == "report":
            ret = st.session_state.get("model_ret", {})
            st.subheader("Step 2: DQN Analysis Results")
            report_log_status = st.empty()
            report_log_area = st.empty()
            training_rr_threshold = float(st.session_state.get("rr_threshold_shared", getattr(cfg, "training_rr_threshold", 2.0)))
            st.session_state["training_rr_threshold_input"] = training_rr_threshold
            cfg.training_rr_threshold = float(training_rr_threshold)
            with st.container(border=True):
                st.markdown("#### Model Source")
            strategy_label = st.selectbox(
                "Trading Strategy",
                [item["label"] for item in STRATEGY_CHOICES],
                index=2,
                key="report_strategy_mode",
            )
            strategy_meta = next(item for item in STRATEGY_CHOICES if item["label"] == strategy_label)
            strategy_mode = strategy_meta["mode"]
            strategy_tag = strategy_meta["tag"]
            cfg.strategy_mode = strategy_mode
            cfg.strategy_label_tag = strategy_tag
            report_mode = st.radio(
                "Model Mode",
                ["Train New Model", "Use saved model"],
                horizontal=True,
                key="report_model_mode",
            )
            saved_models = list_models(cfg.outputs_dir)
            selected_report_model_id = None
            if report_mode == "Train New Model":
                st.caption(f"Selected Strategy: {strategy_label}")
                train_mode_col1, train_mode_col2, train_mode_col3 = st.columns([1.1, 1.0, 1.0])
                with train_mode_col1:
                    train_mode = st.selectbox("Training Mode", ["Fixed Epochs", "Early Stop"], index=1, key="report_train_mode")
                with train_mode_col2:
                    episodes_override = st.number_input("Epochs", min_value=10, max_value=5000, value=int(getattr(cfg, "episodes", 50)), step=10, key="report_train_episodes")
                with train_mode_col3:
                    early_stop_patience = st.number_input("Patience", min_value=5, max_value=500, value=50, step=5, key="report_early_stop_patience")
                rr_threshold_col1, rr_threshold_col2 = st.columns([1.0, 1.0])
                with rr_threshold_col1:
                    st.metric("Training H1/W1 RR >", f"{training_rr_threshold:.1f}")
                with rr_threshold_col2:
                    st.caption("Edit the threshold in Step 1.")
                if train_mode == "Early Stop":
                    st.caption("Training will stop early when validation return stops improving.")
                train_col1, train_col2 = st.columns(2)
                with train_col1:
                    train_now = st.button("Train Selected Strategy", use_container_width=True, key="report_train_selected")
                with train_col2:
                    st.button("Clear Model", use_container_width=True, key="report_clear_model")

                if train_now:
                    if not ticker or ticker.strip() == "":
                        st.error("Please enter a Ticker (e.g., AAPL or 2330.TW) in the input box before training.")
                        return

                    report_log_status = st.empty()
                    report_log_area = st.empty()
                    report_log_status.info("Starting MTF DQN+SMC training...")
                    st.session_state["train_log"] = []

                    def update_log(msg):
                        st.session_state["train_log"].append(msg)
                        report_log_area.markdown(_render_log_html(st.session_state["train_log"]), unsafe_allow_html=True)

                    try:
                        train_cfg = Config()
                        train_cfg.ticker = ticker
                        train_cfg.start_date = st.session_state.get("start_date", cfg.start_date)
                        train_cfg.end_date = st.session_state.get("end_date", cfg.end_date)
                        train_cfg.strategy_mode = strategy_mode
                        train_cfg.strategy_label_tag = strategy_tag
                        train_cfg.episodes = int(episodes_override)
                        train_cfg.early_stop_enabled = train_mode == "Early Stop"
                        train_cfg.early_stop_patience = int(early_stop_patience)
                        train_cfg.early_stop_min_delta = float(getattr(cfg, "early_stop_min_delta", 0.001))
                        train_cfg.training_rr_threshold = float(st.session_state.get("rr_threshold_shared", training_rr_threshold))
                        ret = run_training_pipeline_v2(train_cfg, progress_callback=update_log)
                        st.session_state["model_ret"] = ret
                        set_current_model_context(ret)
                        st.session_state["current_model_source"] = "trained"
                        metrics = ret["metrics"]
                        final_msg = (
                            f"Training Completed! "
                            f"Test Return: {metrics.get('total_return', 0)*100:.1f}% | "
                            f"Best Train Return: {metrics.get('best_train_return', 0)*100:.1f}% | "
                            f"Best Val Return: {metrics.get('best_val_return', 0)*100:.1f}% | "
                            f"Sharpe: {metrics.get('sharpe_ratio', 0):.2f} | "
                            f"Replay Buffer: {metrics.get('replay_buffer_size', 0)} | "
                            f"Wins: {metrics.get('win_count', 0)} | "
                            f"Losses: {metrics.get('loss_count', 0)}"
                        )
                        update_log(final_msg)
                        rr_ctx = ret.get("recommendation", {}).get("rr_details", {}) if isinstance(ret, dict) else {}
                        if rr_ctx:
                            rr_cols = st.columns(4)
                            for idx, tf in enumerate(["w1", "h4", "d1", "h1"]):
                                with rr_cols[idx]:
                                    tf_rr = rr_ctx.get(tf, {})
                                    st.metric(f"{tf.upper()} RR", f"{float(tf_rr.get('rr_ratio', 0.0) or 0.0):.2f}")
                        report_log_status.success("Training saved successfully!")
                        st.session_state["active_tab"] = "report"
                        st.rerun()
                    except Exception as e:
                        report_log_status.error(f"Error during training: {e}")
                        import traceback
                        update_log(traceback.format_exc())
                        return

                current_ret = st.session_state.get("model_ret")
                if current_ret and current_ret.get("agent") is not None:
                    st.markdown("#### Current Trained Model")
                    current_record = current_ret.get("model_record") or {}
                    if current_record.get("model_id"):
                        st.caption(f"Saved model: {current_record['model_id']}")
                    if st.button("Save Current Trained Model", use_container_width=True, key="report_save_current_model"):
                        try:
                            saved_record, save_status = save_current_trained_model(current_ret, cfg, strategy_mode)
                            if save_status == "already_saved" and saved_record:
                                st.success(f"Current model is already saved as {saved_record.get('model_id')}")
                            elif save_status == "saved" and saved_record:
                                st.success(f"Saved current model as {saved_record.get('model_id')}")
                                st.session_state["current_model_record"] = saved_record
                                st.session_state["current_model_id"] = saved_record.get("model_id")
                                st.session_state["current_model_source"] = "trained"
                                st.rerun()
                            else:
                                st.error("Unable to save the current trained model.")
                        except Exception as e:
                            st.error(f"Save current model failed: {e}")

            elif report_mode == "Use saved model":
                if not saved_models:
                    st.warning("No saved models found yet. Train one first.")
                else:
                    selected_report_model_id = st.selectbox(
                        "Saved Models",
                        [f"{m['model_id']} | {m.get('strategy_label', m.get('strategy_mode', 'dqn_position'))} | Sharpe {m.get('sharpe', 0):.2f} | Return {m.get('total_return', 0):.2%}" for m in saved_models],
                        key="report_saved_model_select",
                    ).split(" | ")[0]
                    load_col1, load_col2, load_col3 = st.columns(3)
                    with load_col1:
                        if st.button("Load Selected Saved Model", use_container_width=True, key="report_load_saved_model"):
                            selected_meta = load_model_by_id(cfg.outputs_dir, selected_report_model_id)
                            if not selected_meta:
                                st.error("Selected model not found in registry.")
                            else:
                                try:
                                    eval_cfg = Config()
                                    eval_cfg.ticker = st.session_state.get("ticker", cfg.ticker)
                                    eval_cfg.start_date = st.session_state.get("start_date", cfg.start_date)
                                    eval_cfg.end_date = st.session_state.get("end_date", cfg.end_date)
                                    eval_cfg.strategy_mode = selected_meta.get("strategy_mode", cfg.strategy_mode)
                                    eval_cfg.strategy_label_tag = selected_meta.get("strategy_label", strategy_tag)
                                    eval_cfg.training_rr_threshold = float(st.session_state.get("rr_threshold_shared", training_rr_threshold))
                                    st.session_state["train_log"] = [f"Loading saved model: {selected_report_model_id}"]
                                    report_log_area.markdown(_render_log_html(st.session_state["train_log"]), unsafe_allow_html=True)
                                    def load_update_log(msg):
                                        st.session_state["train_log"].append(msg)
                                        report_log_area.markdown(_render_log_html(st.session_state["train_log"]), unsafe_allow_html=True)
                                    ret = run_evaluation_pipeline_v2(
                                        eval_cfg,
                                        selected_meta["path"],
                                        model_record=selected_meta,
                                        progress_callback=load_update_log,
                                    )
                                    st.session_state["model_ret"] = ret
                                    set_current_model_context(ret)
                                    st.session_state["current_model_source"] = "saved"
                                    rr_ctx = ret.get("recommendation", {}).get("rr_details", {}) if isinstance(ret, dict) else {}
                                    if rr_ctx:
                                        rr_cols = st.columns(4)
                                        for idx, tf in enumerate(["w1", "h4", "d1", "h1"]):
                                            with rr_cols[idx]:
                                                tf_rr = rr_ctx.get(tf, {})
                                                st.metric(f"{tf.upper()} RR", f"{float(tf_rr.get('rr_ratio', 0.0) or 0.0):.2f}")
                                    st.session_state["active_tab"] = "report"
                                    st.rerun()
                                except Exception as e:
                                    try:
                                        report_log_status.error(f"Error loading saved model: {e}")
                                    except UnboundLocalError:
                                        st.error(f"Error loading saved model: {e}")
                                    import traceback
                                    err_text = traceback.format_exc()
                                    if "update_log" in locals():
                                        update_log(err_text)
                                    else:
                                        st.text_area("Error details", err_text, height=220)
                                    return
                    with load_col2:
                        if st.button("Run Backtest Only", use_container_width=True, key="report_backtest_only_saved_model"):
                            selected_meta = load_model_by_id(cfg.outputs_dir, selected_report_model_id)
                            if not selected_meta:
                                st.error("Selected model not found in registry.")
                            else:
                                try:
                                    eval_cfg = Config()
                                    eval_cfg.ticker = st.session_state.get("ticker", cfg.ticker)
                                    eval_cfg.start_date = st.session_state.get("start_date", cfg.start_date)
                                    eval_cfg.end_date = st.session_state.get("end_date", cfg.end_date)
                                    eval_cfg.strategy_mode = selected_meta.get("strategy_mode", cfg.strategy_mode)
                                    eval_cfg.strategy_label_tag = selected_meta.get("strategy_label", strategy_tag)
                                    eval_cfg.training_rr_threshold = float(st.session_state.get("rr_threshold_shared", training_rr_threshold))
                                    st.session_state["train_log"] = [f"Backtesting saved model: {selected_report_model_id}"]
                                    report_log_area.markdown(_render_log_html(st.session_state["train_log"]), unsafe_allow_html=True)

                                    def backtest_update_log(msg):
                                        st.session_state["train_log"].append(msg)
                                        report_log_area.markdown(_render_log_html(st.session_state["train_log"]), unsafe_allow_html=True)

                                    ret = run_evaluation_pipeline_v2(
                                        eval_cfg,
                                        selected_meta["path"],
                                        model_record=selected_meta,
                                        progress_callback=backtest_update_log,
                                    )
                                    st.session_state["model_ret"] = ret
                                    set_current_model_context(ret)
                                    st.session_state["current_model_source"] = "backtest"
                                    rr_ctx = ret.get("recommendation", {}).get("rr_details", {}) if isinstance(ret, dict) else {}
                                    if rr_ctx:
                                        rr_cols = st.columns(4)
                                        for idx, tf in enumerate(["w1", "h4", "d1", "h1"]):
                                            with rr_cols[idx]:
                                                tf_rr = rr_ctx.get(tf, {})
                                                st.metric(f"{tf.upper()} RR", f"{float(tf_rr.get('rr_ratio', 0.0) or 0.0):.2f}")
                                    st.session_state["active_tab"] = "report"
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Backtest failed: {e}")
                                    import traceback
                                    st.text_area("Error details", traceback.format_exc(), height=220)
                                    return
                    with load_col3:
                        if st.button("Delete Selected Model", use_container_width=True, key="report_delete_saved_model"):
                            removed = delete_model_by_id(cfg.outputs_dir, selected_report_model_id)
                            if removed:
                                st.success(f"Deleted model: {selected_report_model_id}")
                                st.session_state.pop("model_ret", None)
                                st.session_state.pop("current_model_id", None)
                                st.session_state.pop("current_model_record", None)
                                st.session_state.pop("recommendation", None)
                                st.rerun()
                            else:
                                st.error("Selected model not found.")
            else:
                st.info("Select Train New Model or Use saved model.")

        if not ret:
            st.info("Waiting for model training or saved-model loading...")
            return

        report_placeholder = st.empty()
        report_placeholder.info("Running strategy inference...")
        try:
            recommendation = st.session_state.get("recommendation")
            if not recommendation:
                recommendation = compute_recommendation(ret, cfg)

            rr = recommendation["risk_reward_plan"]
            snap = recommendation["mtf_snapshot"]
            metrics = ret["metrics"]

            report_placeholder.empty()

            r1, r2, r3, r4 = st.columns(4)
            with r1:
                st.markdown(f"""
##### Recommendation
* **Close**: {recommendation['latest_close']:,.2f}
* **Action**: **{recommendation['best_action_name']}**
* **Direction**: {recommendation['trade_direction']}
* **Position**: {recommendation['target_position_ratio']:.0%}
                """)
            with r2:
                st.markdown(f"""
##### MTF SMC
* W1 bias: {snap['w1_smc_bias']:.0f}
* D1 bias: {snap['d1_smc_bias']:.0f}
* H4 bias: {snap['h4_smc_bias']:.0f}
* H1 bias: {snap['h1_smc_bias']:.0f}
* Confluence: {snap['mtf_confluence_score']:.1f}
* Conflict: {'Yes' if snap['mtf_conflict'] else 'No'}
                """)
            with r3:
                st.markdown(f"""
##### Backtest
* Return: {metrics.get('total_return', 0)*100:.1f}%
* Drawdown: {metrics.get('max_drawdown', 0)*100:.1f}%
* Sharpe: {metrics.get('sharpe_ratio', 0):.2f}
* Profit Factor: {metrics.get('profit_factor', 0):.2f}
                """)
            with r4:
                if rr.get("risk_reward_valid"):
                    st.markdown(f"""
##### Current Target RRR
* Entry: {rr['entry_price']:,.2f}
* Stop Loss: {rr['stop_loss_price']:,.2f}
* Take Profit: {rr['take_profit_price']:,.2f}
* RR Ratio: **{rr['risk_reward_ratio']:.2f}**
* Basis: {rr.get('take_profit_basis', '')}
                    """)
                else:
                    st.markdown("##### Current Target RRR\n*No valid RRR*")

            st.markdown("#### Backtest Trade Outcome")
            render_backtest_metrics(metrics)
            bt = ret.get("test_backtest", {}) if isinstance(ret, dict) else {}
            bt_trades = bt.get("trades_df") if isinstance(bt, dict) else None
            if bt_trades is not None and not bt_trades.empty:
                st.markdown("##### Reconstructed BUY/SELL Pairs")
                pair_rows = reconstruct_trade_pairs(bt_trades, ticker=st.session_state.get("ticker", ""))
                pair_df = pairs_to_dataframe(pair_rows)
                if not pair_df.empty:
                    preview_cols = [
                        "pair_id", "buy_time", "sell_time", "buy_price", "sell_price",
                        "profit_pct", "rr_stop_loss_price", "rr_take_profit_price", "rr_basis",
                    ]
                    preview_cols = [c for c in preview_cols if c in pair_df.columns]
                    st.dataframe(pair_df[preview_cols], use_container_width=True, hide_index=True, height=220)
                else:
                    st.info("No closed BUY/SELL pairs could be reconstructed from this backtest.")
            else:
                st.info("No backtest trade records available for this model.")

            if "rr_details" in snap:
                st.markdown("---")
                st.markdown("#### MTF Risk Reward Analysis")
                rr_cols = st.columns(4)
                for i, tf in enumerate(["w1", "d1", "h4", "h1"]):
                    with rr_cols[i]:
                        tf_rr = snap["rr_details"][tf]
                        st.markdown(f"##### {tf.upper()} Level")
                        if pd.notna(tf_rr["entry"]):
                            st.markdown(f"""
* **Entry**: {tf_rr['entry']:,.2f}
* **Stop Loss**: {tf_rr['stop_loss']:,.2f}
* **Take Profit**: {tf_rr['take_profit']:,.2f}
* **RR Ratio**: **{tf_rr['rr_ratio']:.2f}**
* **Basis**: {tf_rr['basis']}
                            """)
                        else:
                            st.markdown("*No valid setup*")

            logs_df = ret.get("logs_df")
            if logs_df is not None and not logs_df.empty:
                st.markdown("---")
                st.markdown("#### Training / Testing Curves")
                loss_fig = plotly_go.Figure()
                if "train_return" in logs_df.columns:
                    loss_fig.add_trace(plotly_go.Scatter(
                        x=logs_df["episode"], y=logs_df["train_return"] * 100,
                        mode="lines", name="Train Return %", line=dict(color="#2563eb", width=2)
                    ))
                if "val_return" in logs_df.columns:
                    loss_fig.add_trace(plotly_go.Scatter(
                        x=logs_df["episode"], y=logs_df["val_return"] * 100,
                        mode="lines", name="Val Return %", line=dict(color="#10b981", width=2)
                    ))
                if "avg_loss" in logs_df.columns:
                    loss_fig.add_trace(plotly_go.Scatter(
                        x=logs_df["episode"], y=logs_df["avg_loss"],
                        mode="lines", name="Training Loss", line=dict(color="#2563eb", width=2)
                    ))
                if "test_loss" in logs_df.columns:
                    loss_fig.add_trace(plotly_go.Scatter(
                        x=logs_df["episode"], y=logs_df["test_loss"],
                        mode="lines", name="Testing Loss Proxy", line=dict(color="#f59e0b", width=2)
                    ))
                loss_fig.update_layout(
                    height=320,
                    margin=dict(l=0, r=0, t=20, b=0),
                    template="plotly_white",
                    hovermode="x unified",
                    legend=dict(orientation="h"),
                )
                st.plotly_chart(loss_fig, use_container_width=True)

                summary_col1, summary_col2 = st.columns(2)
                with summary_col1:
                    st.metric("Best Train Return", f"{metrics.get('best_train_return', 0) * 100:.1f}%")
                with summary_col2:
                    st.metric("Best Val Return", f"{metrics.get('best_val_return', 0) * 100:.1f}%")

        except Exception as e:
            st.error(f"Inference failed: {e}")

    # ── AI 評語 Tab ──
    if active_tab == "ai_comment":
        ret = st.session_state.get("model_ret", {})
        if not ret:
            st.info("請先完成模型訓練，才能使用 AI 評語功能。")
            return

        st.subheader("Step 3: Generate AI Comments")

        model_id = st.session_state.get("current_model_id")
        cached_comment = get_ai_comment(cfg.outputs_dir, model_id) if model_id else None
        if cached_comment and not st.session_state.get("ai_comment"):
            st.session_state["ai_comment"] = cached_comment

        recommendation = st.session_state.get("recommendation")
        if not recommendation:
            try:
                recommendation = compute_recommendation(ret, cfg)
                st.session_state["recommendation"] = recommendation
            except Exception as e:
                st.error(f"無法計算推薦指標：{e}")
                return

        metrics = ret.get("metrics", {})

        perf_col1, perf_col2, perf_col3, perf_col4 = st.columns(4)
        with perf_col1:
            st.metric("Total Return", f"{metrics.get('total_return', 0) * 100:.1f}%")
        with perf_col2:
            st.metric("Max Drawdown", f"{metrics.get('max_drawdown', 0) * 100:.1f}%")
        with perf_col3:
            st.metric("Sharpe", f"{metrics.get('sharpe_ratio', 0):.2f}")
            with perf_col4:
                st.metric("Profit Factor", f"{metrics.get('profit_factor', 0):.2f}")

        st.markdown("#### Testing Outcome")
        render_backtest_metrics(metrics)
        st.metric("Replay Buffer Size", f"{int(metrics.get('replay_buffer_size', 0) or 0)}")

        recommendation = st.session_state.get("recommendation")
        rr_details = recommendation.get("rr_details", {}) if isinstance(recommendation, dict) else {}
        if rr_details:
            st.caption("RR bias: prefer W1 take-profit first, keep H4 stop-loss as the protection level.")
            rr_cols = st.columns(4)
            for idx, tf in enumerate(["w1", "h4", "d1", "h1"]):
                with rr_cols[idx]:
                    tf_rr = rr_details.get(tf, {})
                    st.metric(f"{tf.upper()} RR", f"{float(tf_rr.get('rr_ratio', 0.0) or 0.0):.2f}")

        btn_label = "🔄 重新生成" if st.session_state.get("ai_comment") else "✨ 生成 AI 評語"
        col_btn, _ = st.columns([1, 5])
        with col_btn:
            gen_btn = st.button(btn_label, use_container_width=True)

        if gen_btn:
            with st.spinner("AI 分析中，請稍候..."):
                try:
                    comment = generate_ai_comment(recommendation, metrics)
                    st.session_state["ai_comment"] = comment
                    if model_id:
                        save_ai_comment(cfg.outputs_dir, model_id, comment)
                except Exception as e:
                    st.error(f"AI 評語生成失敗：{e}")

        if st.session_state.get("ai_comment"):
            with st.container(border=True):
                st.markdown(st.session_state["ai_comment"])

if __name__ == '__main__':
    main()

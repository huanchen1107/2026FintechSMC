import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

import pandas as pd
import numpy as np
from fastapi import FastAPI, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import Config
from train_v2 import run_evaluation_pipeline_v2
from utils.model_registry import list_models, load_model_by_id
from utils.trade_pairs import reconstruct_trade_pairs, pairs_to_dataframe, append_trade_review
from ai_comment import generate_journal_ai_reply

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fastapi_app")

app = FastAPI(title="SMC × DRL Trading Dashboard API")

# Add CORS Middleware to allow browser debugging
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global in-memory cache for evaluation outputs
global_eval_data = {
    "model_id": None,
    "pairs": [],
    "metrics": {},
    "raw_ohlcv": [],
}

class SelectModelRequest(BaseModel):
    model_id: str

class SaveReviewRequest(BaseModel):
    pair_id: int
    review_state: str
    review_note: str

class SubmitJournalRequest(BaseModel):
    user_comment: str

class RunPipelineRequest(BaseModel):
    ticker: str
    start_date: str
    end_date: str
    strategy_mode: str
    episodes: int
    early_stop_patience: int

def serialize_trade_pair(pair) -> dict:
    """Safely serialize trade pair fields to standard JSON types."""
    return {
        "pair_id": int(pair.pair_id),
        "ticker": str(pair.ticker),
        "buy_trade_id": str(pair.buy_trade_id),
        "sell_trade_id": str(pair.sell_trade_id),
        "buy_time": str(pair.buy_time),
        "sell_time": str(pair.sell_time),
        "buy_price": float(pair.buy_price),
        "sell_price": float(pair.sell_price),
        "profit_pct": float(pair.profit_pct),
        "pnl": float(pair.pnl),
        "training_reward": float(pair.training_reward),
        "rr_stop_loss_price": float(pair.rr_stop_loss_price) if not np.isnan(pair.rr_stop_loss_price) else None,
        "rr_take_profit_price": float(pair.rr_take_profit_price) if not np.isnan(pair.rr_take_profit_price) else None,
        "rr_stop_loss_time": str(pair.rr_stop_loss_time) if pd.notna(pair.rr_stop_loss_time) else None,
        "rr_take_profit_time": str(pair.rr_take_profit_time) if pd.notna(pair.rr_take_profit_time) else None,
        "rr_basis": str(pair.rr_basis),
        "buy_reason": str(pair.buy_reason),
        "sell_reason": str(pair.sell_reason),
    }

def run_evaluation_for_model(model_id: str) -> bool:
    """Helper to run the V2 evaluation pipeline on a specific model."""
    try:
        cfg = Config()
        outputs_dir = cfg.outputs_dir
        selected_meta = load_model_by_id(outputs_dir, model_id)
        if not selected_meta:
            logger.error(f"Model ID {model_id} not found in registry.")
            return False

        # Load environment overrides
        eval_cfg = Config()
        eval_cfg.strategy_mode = selected_meta.get("strategy_mode", cfg.strategy_mode)
        eval_cfg.strategy_label_tag = selected_meta.get("strategy_label", "dqn-position")
        
        logger.info(f"Running dynamic backtest evaluation for model: {model_id}...")
        eval_ret = run_evaluation_pipeline_v2(
            eval_cfg,
            selected_meta["path"],
            model_record=selected_meta
        )
        
        # Extract trade pairs
        trades_df = eval_ret.get("test_backtest", {}).get("trades_df")
        if trades_df is None or trades_df.empty:
            logger.warning("No trade trades occurred in backtest evaluation.")
            global_eval_data["pairs"] = []
        else:
            pairs = reconstruct_trade_pairs(trades_df, ticker=selected_meta.get("ticker", "2330.TW"))
            global_eval_data["pairs"] = [serialize_trade_pair(p) for p in pairs]
        
        # Extract metrics
        bt_metrics = eval_ret.get("test_backtest", {}).get("metrics", {})
        # Merge model score metrics
        global_eval_data["metrics"] = {
            "sharpe": float(selected_meta.get("sharpe", 0.0)),
            "total_return": float(selected_meta.get("total_return", 0.0)),
            "max_drawdown": float(selected_meta.get("max_drawdown", 0.0)),
            "win_rate": float(bt_metrics.get("win_rate", 0.0)),
            "total_trades": int(bt_metrics.get("total_trades", len(global_eval_data["pairs"]))),
            "created_at": str(selected_meta.get("created_at", "")),
        }
        
        # Load Raw Candlesticks from output CSV
        csv_path = outputs_dir / "raw_market_data_2330_TW.csv"
        if csv_path.exists():
            df_ohlcv = pd.read_csv(csv_path)
            # Standardize column types
            df_ohlcv["date"] = pd.to_datetime(df_ohlcv["date"])
            # Format to lightweight charts format: time as epoch seconds
            records = []
            for _, row in df_ohlcv.iterrows():
                records.append({
                    "time": int(row["date"].timestamp()),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"])
                })
            global_eval_data["raw_ohlcv"] = sorted(records, key=lambda x: x["time"])
        else:
            logger.warning("raw_market_data_2330_TW.csv not found, candlestick loading skipped.")
            global_eval_data["raw_ohlcv"] = []

        global_eval_data["model_id"] = model_id
        logger.info("Dynamic model evaluation completed successfully.")
        return True
    except Exception as e:
        logger.exception(f"Error evaluating model {model_id}: {e}")
        return False

# Bootloader to load best model at start
@app.on_event("startup")
async def startup_event():
    cfg = Config()
    models = list_models(cfg.outputs_dir)
    if models:
        best_model_id = models[0]["model_id"]
        logger.info(f"Startup: loading best registered model: {best_model_id}")
        run_evaluation_for_model(best_model_id)
    else:
        logger.warning("Startup: No models registered in outputs/models/model_registry.json yet.")

@app.get("/api/models")
async def get_models():
    """List all trained model files available in the model registry."""
    cfg = Config()
    models = list_models(cfg.outputs_dir)
    return JSONResponse(content=models)

@app.post("/api/select_model")
async def select_model(payload: SelectModelRequest):
    """Switch active evaluation context to the selected model."""
    success = run_evaluation_for_model(payload.model_id)
    if not success:
        raise HTTPException(status_code=404, detail="Failed to load or evaluate model.")
    return {"status": "success", "model_id": payload.model_id}

@app.get("/api/trade_pairs")
async def get_trade_pairs():
    """Fetch complete reconstructed buying/selling trade pairs."""
    return JSONResponse(content={
        "model_id": global_eval_data["model_id"],
        "pairs": global_eval_data["pairs"]
    })

@app.get("/api/chart_data")
async def get_chart_data():
    """Fetch epoch-second standard hourly candlestick data for the charting container."""
    return JSONResponse(content={
        "model_id": global_eval_data["model_id"],
        "ohlcv": global_eval_data["raw_ohlcv"]
    })

@app.get("/api/metrics")
async def get_metrics():
    """Fetch standard DQN backtest performance metrics."""
    return JSONResponse(content={
        "model_id": global_eval_data["model_id"],
        "metrics": global_eval_data["metrics"]
    })

@app.get("/api/journal/{pair_id}")
async def get_journal(pair_id: str):
    """Fetch full discussion thread chat logs for a specific position pair."""
    cfg = Config()
    journal_path = cfg.outputs_dir / "trade_journal.json"
    if not journal_path.exists():
        return JSONResponse(content=[])
    try:
        db = json.loads(journal_path.read_text(encoding="utf-8"))
        thread = db.get(pair_id, [])
        return JSONResponse(content=thread)
    except Exception as e:
        logger.error(f"Error loading trade journal: {e}")
        return JSONResponse(content=[])

@app.post("/api/journal/{pair_id}")
async def submit_journal(pair_id: str, payload: SubmitJournalRequest):
    """Append a user trade question, generate Gemini feedback, and return updated logs."""
    cfg = Config()
    journal_path = cfg.outputs_dir / "trade_journal.json"
    
    # 1. Find corresponding trade pair info
    pair_info = None
    for p in global_eval_data["pairs"]:
        if str(p["pair_id"]) == pair_id:
            pair_info = p
            break
            
    if not pair_info:
        raise HTTPException(status_code=404, detail="Trade pair not found in active backtest.")

    # 2. Load existing log thread
    db = {}
    if journal_path.exists():
        try:
            db = json.loads(journal_path.read_text(encoding="utf-8"))
        except Exception:
            db = {}
            
    thread = db.setdefault(pair_id, [])
    
    # 3. Append user message
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    user_msg = {
        "timestamp": now_str,
        "author": "User",
        "content": payload.user_comment.strip()
    }
    thread.append(user_msg)
    
    # 4. Invoke Google Gemini Coach via direct REST client
    try:
        # Format mapping parameters
        coach_pair_info = {
            "ticker": pair_info.get("ticker", "2330.TW"),
            "buy_time": pair_info.get("buy_time"),
            "sell_time": pair_info.get("sell_time"),
            "buy_price": pair_info.get("buy_price"),
            "sell_price": pair_info.get("sell_price"),
            "profit_pct": pair_info.get("profit_pct"),
            "rr_stop_loss_price": pair_info.get("rr_stop_loss_price") or float('nan'),
            "rr_take_profit_price": pair_info.get("rr_take_profit_price") or float('nan'),
            "rr_basis": pair_info.get("rr_basis", ""),
            "buy_reason": pair_info.get("buy_reason", ""),
            "sell_reason": pair_info.get("sell_reason", ""),
        }
        
        # Pass conversation context up to previous turns (thread excluding the new comment)
        ai_reply = generate_journal_ai_reply(coach_pair_info, payload.user_comment, thread[:-1])
    except Exception as e:
        logger.exception("Failed generating Gemini reply")
        ai_reply = f"❌ AI Quant Coach Reply Error: {str(e)}"
        
    ai_msg = {
        "timestamp": now_str,
        "author": "AI Quant Coach",
        "content": ai_reply
    }
    thread.append(ai_msg)
    
    # 5. Save thread to database
    db[pair_id] = thread
    journal_path.write_text(json.dumps(db, indent=2, ensure_ascii=False), encoding="utf-8")
    
    return JSONResponse(content=thread)

@app.post("/api/save_review/{pair_id}")
async def save_review(pair_id: str, payload: SaveReviewRequest):
    """Save manual audits and custom notes to trade_reviews.csv database."""
    try:
        cfg = Config()
        reviews_path = cfg.outputs_dir / "trade_reviews.csv"
        
        # Find corresponding trade pair info
        pair_info = None
        for p in global_eval_data["pairs"]:
            if str(p["pair_id"]) == pair_id:
                pair_info = p
                break
                
        if not pair_info:
            raise HTTPException(status_code=404, detail="Trade pair not found in active backtest.")

        review_item = {
            "pair_id": int(pair_info["pair_id"]),
            "ticker": str(pair_info["ticker"]),
            "buy_trade_id": str(pair_info["buy_trade_id"]),
            "sell_trade_id": str(pair_info["sell_trade_id"]),
            "buy_time": str(pair_info["buy_time"]),
            "sell_time": str(pair_info["sell_time"]),
            "buy_price": float(pair_info["buy_price"]),
            "sell_price": float(pair_info["sell_price"]),
            "profit_pct": float(pair_info["profit_pct"]),
            "pnl": float(pair_info["pnl"]),
            "training_reward": float(pair_info["training_reward"]),
            "rr_stop_loss_price": float(pair_info["rr_stop_loss_price"]) if pair_info["rr_stop_loss_price"] else float("nan"),
            "rr_take_profit_price": float(pair_info["rr_take_profit_price"]) if pair_info["rr_take_profit_price"] else float("nan"),
            "rr_stop_loss_time": str(pair_info["rr_stop_loss_time"]) if pair_info["rr_stop_loss_time"] else str(pair_info["buy_time"]),
            "rr_take_profit_time": str(pair_info["rr_take_profit_time"]) if pair_info["rr_take_profit_time"] else str(pair_info["buy_time"]),
            "rr_basis": str(pair_info["rr_basis"]),
            "buy_reason": str(pair_info["buy_reason"]),
            "sell_reason": str(pair_info["sell_reason"]),
            "is_correct": str(payload.review_state),
            "review_note": str(payload.review_note),
        }
        
        append_trade_review(reviews_path, review_item)
        return {"status": "success", "message": "Manual audit review saved successfully."}
    except Exception as e:
        logger.exception("Failed saving trade review")
        raise HTTPException(status_code=500, detail=f"Failed saving review: {str(e)}")

@app.post("/api/run_pipeline")
async def run_pipeline(payload: RunPipelineRequest):
    """Run the entire DRL training pipeline end-to-end and register the new model."""
    try:
        from train_v2 import run_training_pipeline_v2
        from utils.data_utils_v2 import FEATURE_COLUMNS as FEATURE_COLUMNS_V2
        from config import ACTION_POSITION_RATIOS, ACTION_POSITION_RATIOS_DQN_ON_BUY
        from utils.model_registry import register_model

        cfg = Config()
        cfg.ticker = payload.ticker
        cfg.start_date = payload.start_date
        cfg.end_date = payload.end_date
        cfg.strategy_mode = payload.strategy_mode
        cfg.episodes = payload.episodes
        cfg.early_stop_enabled = True
        cfg.early_stop_patience = payload.early_stop_patience

        logger.info(f"Starting DRL Pipeline for {cfg.ticker} from {cfg.start_date} to {cfg.end_date}...")
        
        # 1. Trigger training (downloads data if needed via the SQLite cache implicitly)
        ret = run_training_pipeline_v2(cfg)
        
        # 2. Save the trained model
        agent = ret.get("agent")
        feature_mean = ret.get("feature_mean")
        feature_std = ret.get("feature_std")
        
        if not agent:
            raise ValueError("Training pipeline did not return an agent.")

        save_dir = cfg.outputs_dir / "models"
        save_dir.mkdir(parents=True, exist_ok=True)
        manual_path = save_dir / f"api_mtf_dqn_model_v2_{payload.strategy_mode}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.pth"
        
        agent.save(
            str(manual_path),
            feature_columns=FEATURE_COLUMNS_V2,
            feature_mean=feature_mean.to_dict() if hasattr(feature_mean, "to_dict") else dict(feature_mean),
            feature_std=feature_std.to_dict() if hasattr(feature_std, "to_dict") else dict(feature_std),
            config={k: v for k, v in cfg.__dict__.items() if not isinstance(v, type(cfg.project_dir))},
            action_position_ratios=ACTION_POSITION_RATIOS if payload.strategy_mode == "dqn_position" else ACTION_POSITION_RATIOS_DQN_ON_BUY,
        )
        
        metrics = ret.get("metrics", {})
        model_record = register_model(
            cfg.outputs_dir,
            model_path=str(manual_path),
            ticker=cfg.ticker,
            sharpe=float(metrics.get("sharpe_ratio", 0.0) or 0.0),
            total_return=float(metrics.get("total_return", 0.0) or 0.0),
            max_drawdown=float(metrics.get("max_drawdown", 0.0) or 0.0),
            extra={"is_v2": True, "strategy_mode": payload.strategy_mode, "strategy_label": payload.strategy_mode, "manual_save": True},
        )
        
        # 3. Load the new model into the active dashboard state!
        run_evaluation_for_model(model_record["model_id"])
        
        return {"status": "success", "model_id": model_record["model_id"]}
    except Exception as e:
        logger.exception("Pipeline failed")
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {str(e)}")

# Mount static folder
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serve the sleek SPA frontend dashboard."""
    index_path = Path("static/index.html")
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="index.html not found inside static folder.")
    return index_path.read_text(encoding="utf-8")

if __name__ == "__main__":
    import uvicorn
    # Start on port 8080
    uvicorn.run(app, host="127.0.0.1", port=8080)

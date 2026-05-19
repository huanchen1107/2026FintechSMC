import requests
import streamlit as st
import os
from dotenv import load_dotenv
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai_comment")

# Load environment variables from .env using absolute path resolution
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(dotenv_path=env_path, override=True)


def _build_prompt(recommendation: dict, metrics: dict) -> str:
    snap = recommendation.get("mtf_snapshot", {})
    rr = recommendation.get("risk_reward_plan", {})
    rr_details = snap.get("rr_details", {})

    def fmt(val, decimals=2):
        if val is None:
            return "N/A"
        try:
            return f"{val:,.{decimals}f}"
        except Exception:
            return str(val)

    def rr_block(tf: str) -> str:
        d = rr_details.get(tf, {})
        entry = d.get("entry")
        if entry is None or (hasattr(entry, "__float__") and entry != entry):
            return "（無有效設置）"
        return (
            f"進場：{fmt(entry)} / 停損：{fmt(d.get('stop_loss'))} / "
            f"止盈：{fmt(d.get('take_profit'))} / RR：{fmt(d.get('rr_ratio'))}"
        )

    conflict_str = "是" if snap.get("mtf_conflict") else "否"
    rr_valid = rr.get("risk_reward_valid", False)
    current_rrr_block = (
        f"- 進場價：{fmt(rr.get('entry_price'))}\n"
        f"- 停損價：{fmt(rr.get('stop_loss_price'))}\n"
        f"- 止盈價：{fmt(rr.get('take_profit_price'))}\n"
        f"- 風報比：{fmt(rr.get('risk_reward_ratio'))}\n"
        f"- 計算依據：{rr.get('take_profit_basis', 'N/A')}"
        if rr_valid else "（無有效風報比）"
    )

    return f"""你是一位專業的量化交易分析師，擅長 Smart Money Concepts (SMC) 與強化學習回測策略分析。
請根據以下指標，給出專業的交易評語，並建議下一步行動。

## 當前交易訊號

- 最新收盤價：{fmt(recommendation.get('latest_close'))}
- 建議動作：{recommendation.get('best_action_name', 'N/A')}
- 交易方向：{recommendation.get('trade_direction', 'N/A')}
- 建議倉位：{recommendation.get('target_position_ratio', 0):.0%}

## MTF SMC 多時框偏向分析

- W1（週線）偏向：{snap.get('w1_smc_bias', 0):.0f}（+1 看多 / -1 看空 / 0 中性）
- D1（日線）偏向：{snap.get('d1_smc_bias', 0):.0f}
- H4（4小時）偏向：{snap.get('h4_smc_bias', 0):.0f}
- H1（1小時）偏向：{snap.get('h1_smc_bias', 0):.0f}
- 多時框共識分數：{snap.get('mtf_confluence_score', 0):.2f}（範圍 -1 ~ +1）
- 方向衝突：{conflict_str}

## 回測績效指標

- 總報酬：{metrics.get('total_return', 0) * 100:.1f}%
- 最大回撤：{metrics.get('max_drawdown', 0) * 100:.1f}%
- 夏普比率：{metrics.get('sharpe_ratio', 0):.2f}
- 獲利因子：{metrics.get('profit_factor', 0):.2f}

## 當前目標風報比（RRR）

{current_rrr_block}

## 多時框風報比分析

### W1 週線級別
- {rr_block('w1')}

### D1 日線級別
- {rr_block('d1')}

### H4 四小時級別
- {rr_block('h4')}

### H1 一小時級別
- {rr_block('h1')}

---

請依照以下格式以**繁體中文**回覆：

### 📊 指標綜合評語
（對以上所有指標的整體解讀，包含多時框偏向是否一致、回測績效是否可信、風報比是否合理）

### ⚠️ 風險提示
（指出當前最主要的風險因素，例如：時框衝突、回撤偏高、共識分數偏低等）

### 🎯 建議下一步行動
（具體建議：進場 / 觀望 / 減倉等，並說明理由）

### 💡 理由說明
（結合以上指標，解釋為何給出此建議）
"""


def _generate_with_gemini_api(prompt: str):
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        gemini_key = st.secrets.get("GEMINI_API_KEY", "")
    if gemini_key:
        gemini_key = gemini_key.strip().strip('"').strip("'")
        if gemini_key == "AIzaSyDtraUgiv__LAvtPPQh4h5muQeP3eTkSMI" or not gemini_key:
            return None
        
        logger.info(f"Detected GEMINI_API_KEY (len={len(gemini_key)}). Calling Google AI Studio directly...")
        # Use gemini-2.5-flash as the standard, extremely fast, completely free model
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
        try:
            resp = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt}]}]
                },
                timeout=60
            )
            resp.raise_for_status()
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            return text
        except Exception as e:
            logger.error(f"Gemini API Direct call failed: {str(e)}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Gemini API Details: {e.response.text}")
    return None


def generate_ai_comment(recommendation: dict, metrics: dict) -> str:
    prompt = _build_prompt(recommendation, metrics)
    
    # 優先嘗試官方 Gemini API
    gemini_result = _generate_with_gemini_api(prompt)
    if gemini_result is not None:
        return gemini_result
        
    # 否則退回使用 OpenRouter API
    api_key = os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("MODEL", "open_router/google/gemini-2.0-flash-exp:free")
    
    if not api_key:
        # 嘗試從 streamlit secrets 讀取 (相容 Streamlit Cloud)
        api_key = st.secrets.get("OPENROUTER_API_KEY", "")
        
    if api_key:
        api_key = api_key.strip().strip('"').strip("'")
        logger.info(f"Loaded OPENROUTER_API_KEY for comment (len={len(api_key)})")
    
    if not api_key:
        return "❌ 未設定 OPENROUTER_API_KEY，且無有效 GEMINI_API_KEY。請在 `.env` 中加入 API Key。"
    
    # 處理 OpenRouter 模型名稱 (移除 open_router/ 前綴，如果有的話)
    actual_model = model.replace("open_router/", "")
    
    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://github.com/huanchen1107/2026FintechSMC", # Optional
                "X-Title": "SMC DRL Trading Platform", # Optional
            },
            json={
                "model": actual_model,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        if hasattr(e, "response") and e.response is not None:
            try:
                err_text = e.response.text
                logger.error(f"OpenRouter API Error: {err_text}")
                if e.response.status_code == 401:
                    return "❌ **AI 討論回覆生成失敗：401 Unauthorized (金鑰已失效)**\n\n偵測到您的 `OPENROUTER_API_KEY` 或 `GEMINI_API_KEY` 已失效或被撤銷。\n\n**💡 解決方法：**\n1. 請前往 [Google AI Studio](https://aistudio.google.com/) 免費申請一個全新的 Gemini API 金鑰。\n2. 開啟專案根目錄的 `.env` 檔案，填入：\n   `GEMINI_API_KEY=\"您的全新金鑰\"`\n3. 系統將會直接使用官方高速管道，完全免費、更穩定，且不再依賴 OpenRouter！"
                return f"❌ AI 評語生成失敗：{e.response.status_code} - {err_text}"
            except Exception:
                pass
        return f"❌ AI 評語生成失敗：{str(e)}"


def generate_journal_ai_reply(pair_info: dict, user_comment: str, history: list) -> str:
    # 格式化歷史對話
    history_str = ""
    for idx, h in enumerate(history):
        history_str += f"- [{h.get('timestamp')}] {h.get('author')}: {h.get('content')}\n"
        
    prompt = f"""你是一位卓越的量化交易導師與 SMC (Smart Money Concepts) 專家。
我們正在審查一筆強化學習 DQN 智能體在回測中完成的交易對 (Trade Pair)。

## 交易對基本資訊
- Agent model ID: {pair_info.get('model_id', 'N/A')}
- Position pair ID: {pair_info.get('pair_id', 'N/A')}
- Ticker: {pair_info.get('ticker')}
- 進場時間：{pair_info.get('buy_time')} / 價格：{pair_info.get('buy_price')}
- 出場時間：{pair_info.get('sell_time')} / 價格：{pair_info.get('sell_price')}
- 報酬率：{pair_info.get('profit_pct', 0)*100:.2f}%
- 停損設點：{pair_info.get('rr_stop_loss_price')}
- 停利設點：{pair_info.get('rr_take_profit_price')}
- R:R 計算依據：{pair_info.get('rr_basis')}
- 買入原因 (RL Agent Rationale): {pair_info.get('buy_reason')}
- 賣出原因 (RL Agent Rationale): {pair_info.get('sell_reason')}

## 核心交易邏輯回顧 (SMC × DRL 特性)
1. **動態/移動出場 (Trailing SL/TP)**: 智能體使用的停損/停利點是基於當前時間步 (Current Step) 滾動計算的，因此會在行情的推動下呈移動/追蹤態勢。
2. **Q-Value 超越常規偏向 (DQN Q-value overrides standard bias)**: DQN 智能體以最大化長期回報為目標。若在多時框 Bias 為空頭 (-1) 時建倉 100%，是因為它透過深度網絡學習到此處是高勝率的折價積累區/清算區。

## 歷史討論紀錄
{history_str or "（目前無歷史討論）"}

## 使用者最新問題/意見
"{user_comment}"

請針對使用者的問題，給予極度專業、條理清晰且富有洞察力的回答，共同探討這筆交易的優劣。使用繁體中文回覆。
"""

    # 優先嘗試官方 Gemini API
    gemini_result = _generate_with_gemini_api(prompt)
    if gemini_result is not None:
        return gemini_result

    # 否則退回使用 OpenRouter API
    api_key = os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("MODEL", "open_router/google/gemini-2.0-flash-exp:free")
    
    if not api_key:
        api_key = st.secrets.get("OPENROUTER_API_KEY", "")
        
    if api_key:
        api_key = api_key.strip().strip('"').strip("'")
        logger.info(f"Loaded OPENROUTER_API_KEY for Q&A reply (len={len(api_key)})")
    
    if not api_key:
        return "❌ 未設定 OPENROUTER_API_KEY，且無有效 GEMINI_API_KEY。請在 `.env` 中加入 API Key。"
        
    actual_model = model.replace("open_router/", "")
    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://github.com/huanchen1107/2026FintechSMC",
                "X-Title": "SMC DRL Trading Platform",
            },
            json={
                "model": actual_model,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        if hasattr(e, "response") and e.response is not None:
            try:
                err_text = e.response.text
                logger.error(f"OpenRouter API Error: {err_text}")
                if e.response.status_code == 401:
                    return "❌ **AI 討論回覆生成失敗：401 Unauthorized (金鑰已失效)**\n\n偵測到您的 `OPENROUTER_API_KEY` 或 `GEMINI_API_KEY` 已失效或被撤銷。\n\n**💡 解決方法：**\n1. 請前往 [Google AI Studio](https://aistudio.google.com/) 免費申請一個全新的 Gemini API 金鑰。\n2. 開啟專案根目錄的 `.env` 檔案，填入：\n   `GEMINI_API_KEY=\"您的全新金鑰\"`\n3. 系統將會直接使用官方高速管道，完全免費、更穩定，且不再依賴 OpenRouter！"
                return f"❌ AI 討論回覆生成失敗：{e.response.status_code} - {err_text}"
            except Exception:
                pass
        return f"❌ AI 討論回覆生成失敗：{str(e)}"

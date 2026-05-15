# 📈 SMC × DRL Trading Platform Tutorial

Welcome to the comprehensive guide for the **SMC × DRL Trading Platform**. This project is a state-of-the-art quantitative trading assistant that combines **Smart Money Concepts (SMC)** with **Deep Reinforcement Learning (DRL)** to provide actionable trading insights across multiple timeframes.

---

## 1. Project Overview: What is it?

This platform is designed to bridge the gap between institutional trading logic (SMC) and automated decision-making (DRL). It doesn't just look at simple technical indicators; it analyzes the "footprints" of large institutions (Smart Money) to find high-probability trade setups.

### Core Objectives:
*   **Automated Feature Extraction**: Use SMC to identify liquidity pools, gaps, and institutional order blocks.
*   **Adaptive Decision Making**: Use a Deep Q-Network (DQN) to learn when to increase or decrease position sizes based on market structure.
*   **Risk Management**: Automatically calculate Risk-Reward Ratios (RRR) to ensure every trade has a mathematical edge.
*   **AI Interpretation**: Leverage LLMs to summarize complex quantitative data into human-readable advice.

---

## 2. The Engine: Smart Money Concepts (SMC)

Instead of standard RSI or MACD, this project uses the `smartmoneyconcepts` library to transform raw price action into institutional features:

*   **Order Blocks (OB)**: Areas where large institutions have previously placed significant orders, often leading to price reversals.
*   **Fair Value Gaps (FVG)**: Imbalances in price movement where liquidity was "skipped," often acting as magnets for future price action.
*   **Liquidity Sweeps**: Identifying "stop-hunts" where price temporarily breaks a key level to grab liquidity before reversing.
*   **Market Structure**: Tracking Break of Structure (BOS) and Change of Character (CHoCH) to determine the current trend bias.

---

## 3. The Brain: Deep Reinforcement Learning (DRL)

The "Brain" of the system is a **Deep Q-Network (DQN)**. Unlike traditional backtesting which follows rigid rules, DRL *learns* the optimal strategy through trial and error.

### The State Space (What the AI sees):
The AI doesn't just see the current price. It sees:
1.  **SMC Features**: FVG status, OB proximity, and Liquidity markers.
2.  **Multi-Timeframe (MTF) Context**: The bias (Bullish/Bearish) from Weekly (W1), Daily (D1), and 4-Hour (H4) charts.
3.  **Portfolio Status**: Current cash, shares held, and unrealized PnL.

### The Action Space (What the AI does):
The agent manages **Position Ratios**:
*   `0%`: Stay in Cash.
*   `25%`: Small Exposure.
*   `50%`: Moderate Exposure.
*   `100%`: Full Exposure.

### The Reward Function (How it learns):
The AI is rewarded for:
*   **Profits**: Positive returns.
*   **MTF Alignment**: Bonus rewards for trading in the same direction as the higher timeframe trend.
*   **Risk Mitigation**: Penalties for high drawdowns or trading against the major trend (Conflict Penalty).

---

## 4. Multi-Timeframe (MTF) Strategy

The project excels at "Top-Down Analysis":
1.  **Weekly (W1)**: Determines the "Master Trend."
2.  **Daily (D1)**: Identifies the "Major Swing Direction."
3.  **4-Hour (H4)**: Locates "Institutional Interest Zones."
4.  **1-Hour (H1)**: The "Execution Timeframe" where the DRL agent makes its moves.

The **Confluence Score** measures how many timeframes agree. A high positive score (+1) indicates a strong bullish consensus across all timeframes.

---

## 5. Risk-Reward Ratio (RRR) Calculation

Even with a great signal, a trade is only viable if the math makes sense. The system automatically calculates:
*   **Entry**: Based on the current price or the nearest OB/FVG.
*   **Stop Loss (SL)**: Placed below the recent "Swing Low" or "Liquidity Level."
*   **Take Profit (TP)**: Calculated using an ATR-based multiplier or the next major institutional zone.
*   **RR Ratio**: Minimum requirement (default 1.5) must be met for a "Recommendation" to be valid.

---

## 6. How to Use the Platform

### Step 1: Data Acquisition
Enter a ticker (e.g., `AAPL` or `2330.TW`) and a date range. Click **Fetch & Analyze**. The system will download 1H data and compute SMC features for all four timeframes.

### Step 2: Training the Agent
Click the **DQN Training** button. You will see a real-time log of the agent "playing" the market. It will go through 25+ episodes of the historical data, learning from its mistakes.

### Step 3: Reviewing the Report
Once trained, the **DRL × SMC Report** will show:
*   The recommended action for the *current* moment.
*   A summary of the backtest results (Sharpe Ratio, Max Drawdown).
*   The specific RRR plan (Entry/SL/TP).

### Step 4: AI Commentary
Go to the **AI Comment** tab. The system will send all the quantitative data to an LLM (via OpenRouter), which will then provide a professional human-readable summary and "Next Steps" advice.

---

## 7. Technical Setup (Quick Start)

If you are running this locally:
1.  **Start the App**: Run `./start_app.sh`.
2.  **API Keys**: Ensure your `OPENROUTER_API_KEY` is set in the `.env` file for the AI comments to work.
3.  **Venv**: The project uses a dedicated virtual environment (`.venv`) for stability.

---

> **Disclaimer**: This tool is for research and educational purposes. Trading involves significant risk. Never risk more than you can afford to lose.

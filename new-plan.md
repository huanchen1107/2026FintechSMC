I want to continue implement, add some database for model that save the trained model 現在每次都要重新訓練，我想如果使用訓練過的模型就把它存起來下次就直接運用要是想要再重新訓練的話需要有一個重新訓練的button所有的可以使用舊的或新的限制有一個下拉視窗可以選擇要重新訓練還是要使用舊模型最多存兩個表現比較好的模式不會有一個儲存這次訓練的模型

2. 想再實現一個功能維護一個buy 跟sell pair 記錄每次交易的成果並說明原因，所以我應該是放在圖表的右邊當我回顧交易歷史紀律的時候成對的買賣就會同一隊買賣就會出現在左邊的圖裡面說明這次的表現和下單的原因這樣我就可以以一組一組買賣來對照，看他是不是有正確然後記錄他們是否正確

可以，這兩個功能很適合做成 V3：Model Registry + Trade Pair Review System。

我看了 repo：目前已經有 train_v2.py 會把模型固定存成 outputs/mtf_dqn_model_v2.pth，所以每次會覆蓋舊模型；而交易配對工具 group_trades_into_pairs() 已經存在，但原因還是 placeholder。 ￼  ￼

你要加的功能可以這樣設計

1. 模型資料庫 / Model Registry

新增：

utils/model_registry.py
outputs/models/
outputs/models/model_registry.json

模型最多保留 2 個表現最好的：

[
  {
    "model_id": "AAPL_20260515_1430",
    "ticker": "AAPL",
    "path": "outputs/models/AAPL_20260515_1430.pth",
    "sharpe": 1.42,
    "return": 0.18,
    "max_drawdown": -0.07,
    "created_at": "2026-05-15 14:30"
  }
]

Streamlit UI 加：

model_mode = st.selectbox(
    "Model Mode",
    ["Use saved model", "Retrain new model"]
)

selected_model = st.selectbox(
    "Saved Models",
    available_models
)

if st.button("Retrain Model"):
    ret = run_training_pipeline_v2(cfg)
    save_if_top2(ret)

邏輯：

Use saved model
→ 載入 .pth
→ 直接 recommend / backtest / AI comment

Retrain new model
→ 執行訓練
→ 產生新模型
→ 根據 Sharpe / Return / Drawdown 排名
→ 只保留 top 2

重點是不要只看 return，建議排序分數：

score = sharpe + total_return - abs(max_drawdown)


⸻

2. Buy / Sell Pair Review System

你 repo 已有 utils/analysis_utils.py，裡面已經能把 BUY/SELL 配成一組。 ￼

下一步要升級成：

Trade Pair #1
Buy Time
Sell Time
Buy Price
Sell Price
PnL
Profit %
Buy Reason
Sell Reason
Correct / Wrong
Review Note

新增資料表：

outputs/trade_reviews.csv

欄位：

pair_id,ticker,buy_time,sell_time,buy_price,sell_price,profit_pct,pnl,buy_reason,sell_reason,is_correct,review_note

右側 UI：

left, right = st.columns([3, 1])

with left:
    render_chart_with_selected_trade_pair()

with right:
    selected_pair = st.selectbox("Trade Pair", pair_ids)

    st.metric("Profit %", profit_pct)
    st.write("Buy Reason:", buy_reason)
    st.write("Sell Reason:", sell_reason)

    is_correct = st.radio("Was this trade correct?", ["Correct", "Wrong", "Unclear"])
    note = st.text_area("Review Note")

    if st.button("Save Review"):
        save_trade_review(...)

你要的效果就是：

右邊選一組 buy/sell
→ 左邊圖表自動 zoom 到那一段
→ 顯示買點、賣點、PnL 區間
→ 右邊寫原因與人工判斷
→ 存入交易紀律紀錄


⸻

建議開發順序

第一階段先做：

1. model_registry.py
2. app.py 加下拉選單：Use saved / Retrain
3. 訓練後只保留 top 2 model

第二階段做：

4. trade_reviews.csv
5. 右側 Trade Pair Review Panel
6. 點選 pair 後左圖 highlight 該交易區間

第三階段再加：

7. AI 自動解釋 buy/sell reason
8. 統計哪一種 setup 最容易賺錢
9. Correct / Wrong 變成紀律學習資料庫

核心概念：

模型資料庫解決「不要每次重訓」；交易配對資料庫解決「每一筆交易能不能被回顧、解釋、修正」。
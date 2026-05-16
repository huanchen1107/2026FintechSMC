# Plan 2.1: Save Model + Trade Pair Review

## Objective
Add two persistent systems to the SMC × DRL platform:

1. a model registry so trained models are saved, reused, and limited to the best two
2. a trade pair review system so each BUY/SELL pair can be reviewed, labeled, and explained

This removes the current behavior where every training run overwrites the previous model and every trade is hard to review after the fact.

## Problem Statement

The current workflow has two gaps:

- the trained model is saved to a single fixed path, so retraining destroys the previous model
- completed BUY/SELL trades exist in analysis, but they do not have a durable review record or a clean UI for explanation and correction

The new plan should make it possible to:

- load an existing trained model without retraining
- retrain on demand from the UI
- keep only the two best models based on performance
- inspect each BUY/SELL pair as a single review unit
- save human feedback on whether the trade was correct

## Part 1: Model Registry

### Goal
Persist trained models and their metrics so the app can reuse the best saved model instead of always retraining.

### Files to add

- `utils/model_registry.py`
- `outputs/models/`
- `outputs/models/model_registry.json`

### Registry fields

Each saved model entry should include:

- `model_id`
- `ticker`
- `path`
- `sharpe`
- `total_return`
- `max_drawdown`
- `created_at`

Example:

```json
[
  {
    "model_id": "AAPL_20260515_1430",
    "ticker": "AAPL",
    "path": "outputs/models/AAPL_20260515_1430.pth",
    "sharpe": 1.42,
    "total_return": 0.18,
    "max_drawdown": -0.07,
    "created_at": "2026-05-15 14:30"
  }
]
```

### Registry behavior

- save a new model after training
- rank models by a score based on performance
- keep only the top 2 models
- allow the UI to select a saved model for inference
- allow retraining from the UI when the user wants a new run

Suggested ranking score:

```text
score = sharpe + total_return - abs(max_drawdown)
```

### Required helper functions

In `utils/model_registry.py`, implement helpers such as:

- `list_models()`
- `save_model_if_top2(...)`
- `load_model(model_id)`
- `get_best_model()`

## Part 2: Model Selection UI

### Goal
Let the user choose between using a saved model and retraining a new one.

### UI behavior

Add a Streamlit control like:

```python
model_mode = st.selectbox(
    "Model Mode",
    ["Use saved model", "Retrain new model"]
)
```

If the user chooses `Use saved model`:

- show a dropdown of available saved models
- load the selected `.pth`
- skip training
- run recommendation/backtest using the loaded model

If the user chooses `Retrain new model`:

- run the training pipeline
- save the resulting model into the registry
- refresh the available model list

### Training integration

The training pipeline should return metrics needed for the registry:

- `sharpe`
- `total_return`
- `max_drawdown`
- model path

The training code should not overwrite the only saved model.

## Part 3: Trade Pair Review System

### Goal
Store each completed BUY/SELL pair as a reviewable record, including the reasons for the trade and the human judgment of whether the trade was correct.

### Files to add

- `outputs/trade_reviews.csv`
- a new utility module for pair creation if needed

### Review fields

Each review row should include:

- `pair_id`
- `ticker`
- `buy_time`
- `sell_time`
- `buy_price`
- `sell_price`
- `profit_pct`
- `pnl`
- `buy_reason`
- `sell_reason`
- `is_correct`
- `review_note`

Example CSV header:

```text
pair_id,ticker,buy_time,sell_time,buy_price,sell_price,profit_pct,pnl,buy_reason,sell_reason,is_correct,review_note
```

### Pairing behavior

The app should reconstruct trade pairs from the BUY/SELL event stream and keep them in a review-friendly format.

Each pair should show:

- buy time
- sell time
- buy price
- sell price
- PnL
- profit percentage
- buy reason
- sell reason
- human review status

## Part 4: Trade Pair Review UI

### Goal
Add a split-screen review panel where the user can inspect and annotate one BUY/SELL pair at a time.

### Layout

- left side: chart with the selected trade pair highlighted
- right side: pair list, metrics, reason text, and review form

### Suggested UI structure

```python
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
```

### Interaction behavior

When the user selects a pair:

- the chart should zoom to that trade window
- buy and sell markers should be highlighted
- the selected trade should be visually distinct from the rest of the series
- the right panel should show the trade explanation and review controls

## Part 5: Implementation Order

### Phase 1

1. add `utils/model_registry.py`
2. update the training flow to return metrics
3. add the model mode dropdown in `app.py`
4. save only the top 2 models

### Phase 2

5. add `outputs/trade_reviews.csv`
6. implement trade pair reconstruction
7. add the trade pair review panel
8. connect the selected pair to chart zoom and highlight

### Phase 3

9. add AI-generated buy/sell reason text if needed
10. add reporting for common profitable setups
11. use the review labels as a dataset for discipline tracking

## Notes

- `utils/analysis_utils.py` is already deleted in this branch, so the trade pairing logic should be recreated in a fresh utility module if needed.
- The model registry should not depend on a single fixed `.pth` filename.
- The review system should persist the human decision, not just show it in the UI.


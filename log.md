# 2026-05-20 Fixing Step 4

Recovery tag target: `2026-5-20-fixing-step4`

## Restored Version Context

- Restored the FastAPI app from the `step0-to-step4-ok-2026.5.18` line of work.
- Kept the current FastAPI dashboard flow instead of returning to Streamlit.
- Restarted the app on `http://127.0.0.1:8080/` after each backend/frontend fix.

## Fixes Applied

- Step 1 now sends `training_rr_threshold` from the `Replay Buffer RR > N` control to `/api/run_pipeline`.
- `/api/chart_data` now includes `rr_points` for 1H, 4H, 1D, and 1W chart responses.
- RR>N chart guides are drawn as green dotted vertical lines when `rr_valid == 1` and `rr_ratio >= threshold`.
- Step 4 review mode shows chart, position list, position parameters, audit form, and AI Quant Coach together.
- Step 4 selecting a position focuses the chart on that buy/sell window and loads that pair's discussion.
- Journal discussions are scoped by saved agent model and pair: `model_id::pair::pair_id`.
- AI journal submissions include `model_id`; stale model submissions are rejected with HTTP 409.
- AI journal prompts include the exact saved agent model ID and position pair ID.
- The AI Quant Coach discussion panel scrolls inside the card and wraps long AI replies.
- Added a dedicated `Trading Pair for Discussion` dropdown inside the AI Quant Coach panel so the user can select a specific trading pair for discussion without relying only on the right-side position cards.

## Files Changed

- `main_api.py`
- `ai_comment.py`
- `static/index.html`
- `static/app.js`
- `static/styles.css`
- `log.md`

## Verification Notes

- `python -m py_compile main_api.py ai_comment.py`
- `node --check static/app.js`
- Verified `/api/trade_pairs` returns the active saved model and pair list.
- Verified `/api/journal/{pair_id}?model_id={model_id}` returns the model-scoped discussion thread.
- Verified stale journal post with a wrong model id returns `409`.
- Verified `/api/chart_data?interval=1h` returns RR point data.

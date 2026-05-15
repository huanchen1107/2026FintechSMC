#!/bin/bash
# 啟動 SMC × DRL 交易平台

# 檢查虛擬環境
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# 啟動 Streamlit
echo "🚀 正在啟動 SMC × DRL 交易平台..."
streamlit run app.py

#!/bin/bash
# Unified Claude Code Launcher (Interactive)
# Author: Antigravity

PROXY_DIR="$HOME/free-claude-code"
DEFAULT_PORT=8082
CC_SWITCH_PORT=18080

# Fix terminal input to avoid ^M on Enter
stty icrnl 2>/dev/null || true

echo "========================================="
echo "🤖 Claude Code Unified Launcher"
echo "========================================="
echo "1) Start Local Proxy & Claude (8082) [Default]"
echo "2) Connect to existing Proxy (8082)"
echo "3) Connect to CC Switch (18080)"
echo "4) Exit"
echo "-----------------------------------------"
printf "Select proxy option [1-4, Default: 1]: "
IFS= read -r choice
choice=$(printf '%s' "$choice" | tr -dc '0-9')
choice=${choice:-1}

case $choice in
    1) START_PROXY=true; PORT=$DEFAULT_PORT ;;
    2) START_PROXY=false; PORT=$DEFAULT_PORT ;;
    3) START_PROXY=false; PORT=$CC_SWITCH_PORT ;;
    *) echo "Exiting..."; exit 0 ;;
esac

echo ""
echo "-----------------------------------------"
echo "📝 Select Model for this Session"
echo "-----------------------------------------"
echo "1) DeepSeek Chat (via OpenRouter => Not free)"
echo "2) DeepSeek V4 Flash (Free) [Default]"
echo "3) Llama 3.3 70B (Free)"
echo "4) Qwen3 Coder (Free)"
echo "5) Trinity Large Thinking (Free + 🧠 Thinking)"
echo "6) Skip (Use Proxy Default)"
echo "-----------------------------------------"
printf "Select model option [1-6, Default: 2]: "
IFS= read -r model_choice
model_choice=$(printf '%s' "$model_choice" | tr -dc '0-9')
model_choice=${model_choice:-2}

case $model_choice in
    1) MODEL_ID="anthropic/open_router/deepseek/deepseek-chat";    THINKING=false ;;
    2) MODEL_ID="anthropic/open_router/deepseek/deepseek-v4-flash:free"; THINKING=false ;;
    3) MODEL_ID="anthropic/open_router/meta-llama/llama-3.3-70b-instruct:free"; THINKING=false ;;
    4) MODEL_ID="anthropic/open_router/qwen/qwen3-coder:free";     THINKING=false ;;
    5) MODEL_ID="anthropic/open_router/arcee-ai/trinity-large-thinking:free"; THINKING=true ;;
    *) MODEL_ID=""; THINKING=false ;;
esac

if [ "$START_PROXY" = true ]; then
    echo ""
    echo "🧠 啟動 Free Claude Code Proxy..."
    [ ! -d "$PROXY_DIR" ] && echo "❌ 找不到代理伺服器目錄" && exit 1

    # Sync .env and apply thinking setting
    cp ".env" "$PROXY_DIR/.env"
    # Update ENABLE_MODEL_THINKING in the proxy .env
    if grep -q "^ENABLE_MODEL_THINKING" "$PROXY_DIR/.env"; then
        sed -i "" "s/^ENABLE_MODEL_THINKING=.*/ENABLE_MODEL_THINKING=$THINKING/" "$PROXY_DIR/.env"
    else
        echo "ENABLE_MODEL_THINKING=$THINKING" >> "$PROXY_DIR/.env"
    fi

    lsof -ti :$PORT | xargs kill -9 2>/dev/null
    (cd "$PROXY_DIR" && uv run python server.py --port $PORT >> /tmp/freecc_proxy.log 2>&1) &
    PROXY_PID=$!
    echo "⏳ 等待代理伺服器就緒..."
    while ! curl -s "http://localhost:$PORT/health" > /dev/null; do sleep 1; done
    echo "✅ 代理伺服器已就緒 (Port $PORT)"
    trap "echo '🛑 關閉代理伺服器...'; kill $PROXY_PID 2>/dev/null" EXIT
fi

unset ANTHROPIC_API_KEY OPENROUTER_API_KEY GEMINI_API_KEY OPENAI_API_KEY DEEPSEEK_API_KEY
unset ANTHROPIC_MODEL ANTHROPIC_DEFAULT_SONNET_MODEL ANTHROPIC_DEFAULT_HAIKU_MODEL ANTHROPIC_DEFAULT_OPUS_MODEL

export ANTHROPIC_BASE_URL="http://localhost:$PORT"
export ANTHROPIC_API_KEY="sk-ant-api03-1234567890123456789012345678901234567890123456789012345678901234567890123456789012345"
export CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1
export CLAUDE_CODE_SKIP_LOGIN=1
export CLAUDE_CODE_USE_KEY_FROM_ENV=1

FINAL_ARGS=("--bare")
[ -n "$MODEL_ID" ] && FINAL_ARGS+=("--model" "$MODEL_ID")
FINAL_ARGS+=("$@")

echo ""
echo "🚀 啟動 Claude Code (Gateway: $ANTHROPIC_BASE_URL)..."
[ -n "$MODEL_ID" ] && echo "📦 Model: $MODEL_ID | Thinking: $THINKING"
echo "-----------------------------------------"
npx -y @anthropic-ai/claude-code "${FINAL_ARGS[@]}"

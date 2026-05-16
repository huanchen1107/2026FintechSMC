#!/bin/bash

# =========================================================
# Step 1: 環境檢查 (Environment Check)
# =========================================================
echo "=============================="
echo "Step 1: 環境檢查 (Environment Check)"
echo "=============================="
PASS=true

check_cmd() {
    if command -v "$1" &>/dev/null; then
        echo "  ✅ $1 → $(command -v $1)"
    else
        echo "  ❌ $1 → 未安裝！請執行: $2"
        PASS=false
    fi
}

echo ""
echo "📦 依賴工具："
check_cmd "uv"   "brew install uv"
check_cmd "node" "brew install node"
check_cmd "npx"  "brew install node"
check_cmd "curl" "brew install curl"
check_cmd "git"  "brew install git"

echo ""
echo "🧭 AI Agent Rules："
[ -f "CLAUDE.md" ] && echo "  ✅ CLAUDE.md root instructions found" || echo "  ⚠️  CLAUDE.md not found"
[ -f ".cursor/rules/karpathy-guidelines.mdc" ] && echo "  ✅ Cursor Karpathy rule found" || echo "  ⚠️  .cursor/rules/karpathy-guidelines.mdc not found"
[ -f ".agents/skills/karpathy-guidelines/SKILL.md" ] && echo "  ✅ Codex Karpathy skill found" || echo "  ⚠️  .agents/skills/karpathy-guidelines/SKILL.md not found"

echo ""
echo "🔑 API Keys (.env)："
if [ -f ".env" ]; then
    source .env 2>/dev/null
    [ -n "$OPENROUTER_API_KEY" ] && echo "  ✅ OPENROUTER_API_KEY 已設定 (${OPENROUTER_API_KEY:0:8}...)" || { echo "  ❌ OPENROUTER_API_KEY 未設定"; PASS=false; }
    [ -n "$DEEPSEEK_API_KEY" ]   && echo "  ✅ DEEPSEEK_API_KEY 已設定 (${DEEPSEEK_API_KEY:0:8}...)"     || echo "  ⚠️  DEEPSEEK_API_KEY 未設定 (optional)"
    [ -n "$OPENAI_API_KEY" ]     && echo "  ✅ OPENAI_API_KEY 已設定"                                     || echo "  ⚠️  OPENAI_API_KEY 未設定 (optional)"
else
    echo "  ❌ .env 檔案不存在！請建立並填入 API Key"
    PASS=false
fi

echo ""
echo "📁 Proxy 目錄："
PROXY_DIR="$HOME/free-claude-code"
[ -d "$PROXY_DIR" ]           && echo "  ✅ $PROXY_DIR 存在"  || { echo "  ❌ $PROXY_DIR 不存在！請 clone free-claude-code"; PASS=false; }
[ -f "$PROXY_DIR/server.py" ] && echo "  ✅ server.py 存在"   || { echo "  ❌ server.py 不存在";                             PASS=false; }
[ -f "$PROXY_DIR/.env" ]      && echo "  ✅ proxy .env 存在"  || echo "  ⚠️  proxy .env 不存在 (cc.sh 會自動複製)"

echo ""
echo "🔌 Port 狀態："
if lsof -ti :8082 &>/dev/null; then
    echo "  ⚠️  Port 8082 已被佔用 PID=$(lsof -ti :8082 | tr '\n' ' ')"
else
    echo "  ✅ Port 8082 可用"
fi

echo ""
echo "🌐 網路連線："
HTTP=$(curl -s --max-time 5 -o /dev/null -w "%{http_code}" "https://openrouter.ai/api/v1/models" -H "Authorization: Bearer ${OPENROUTER_API_KEY:-test}")
[[ "$HTTP" =~ ^[24] ]] && echo "  ✅ OpenRouter API 可連線 (HTTP $HTTP)" || echo "  ❌ OpenRouter API 連線失敗 (HTTP $HTTP)"

echo ""
if [ "$PASS" = true ]; then
    echo "✅ 環境檢查通過！繼續下一步..."
else
    echo "❌ 環境有問題，請修正後再執行 ./startup.sh"
    exit 1
fi

# =========================================================
# Step 2: 拉取最新進度 (Git Pull)
# =========================================================
echo ""
echo "=============================="
echo "Step 2: 拉取最新進度 (Git Pull)"
echo "=============================="
git pull origin main || echo "⚠️ 同步失敗，跳過此步驟。"

# =========================================================
# Step 3: 閱讀開發日誌 (Read Dev Log)
# =========================================================
echo ""
echo "=============================="
echo "Step 3: 閱讀開發日誌 (Read Dev Log)"
echo "=============================="
LATEST_LOG=$(ls -t *開發日誌*.md 2>/dev/null | head -n 1)
if [ -n "$LATEST_LOG" ]; then
    cat "$LATEST_LOG"
else
    echo "⚠️ 找不到開發日誌檔案！"
fi
echo ""
echo "🤖 嗨，AI 助手！請閱讀上方的開發日誌，並總結目前的進度，然後告訴我接下來可以開始哪些任務 (Tasks to start)。"

# =========================================================
# Step 4: 啟動 Claude Code (Launch)
# =========================================================
echo ""
echo "=============================="
echo "Step 4: 啟動 Claude Code (Launch)"
echo "=============================="
if [ -f "cc.sh" ]; then
    bash cc.sh
else
    echo "❌ 找不到 cc.sh，請確認檔案是否存在。"
fi

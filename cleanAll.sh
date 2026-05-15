#!/bin/bash

# =================================================================
# cleanAll.sh - Project Initialization & Cleanup Script
# =================================================================

PROJECT_NAME=${1:-$(basename "$PWD")}
TODAY=$(date +"%Y.%m.%d")
DEV_LOG="${TODAY}開發日誌.md"

echo "🧹 Starting project cleanup for: $PROJECT_NAME"

# 1. Handle Development Logs
echo "📝 Initializing development log: $DEV_LOG"
# Remove existing dev logs to avoid clutter, or just ensure today's is fresh
find . -maxdepth 1 -name "*開發日誌.md" ! -name "$DEV_LOG" -delete

cat <<EOF > "$DEV_LOG"
# $TODAY 開發日誌

> **⚠️ 備忘錄（$TODAY）**
> CC Switch 目前無法正常運作，暫停使用。
> 本專案目前僅使用 **\`free-claude-code\` 本地代理**搭配 \`.env\` 中設定的 API Key 運作。
> 請勿嘗試透過 CC Switch 連線，直接執行 \`./cc.sh\` 即可。

## 今日重點紀錄
1. **專案初始化**：執行 cleanAll.sh 完成環境重置。
2. **新專案啟動**：準備開始 $PROJECT_NAME 的開發工作。

## 技術結論
- (待填寫)
EOF

# 2. Reset Core Markdown Files
echo "📄 Resetting core markdown files..."

cat <<EOF > README.md
# $PROJECT_NAME

> **⚠️ MEMO ($TODAY)**: CC Switch is currently **not working**. Do not use it.
> This project runs exclusively via the **\`free-claude-code\` local proxy** with API keys configured in \`.env\`.
> Simply run \`./cc.sh\` to start.

## 🚀 Quick Start

\`\`\`bash
./startup.sh   # Initialize project + launch Claude Code
./ending.sh    # Commit, push, and finalize session
\`\`\`

## 🤖 How it Works

\`startup.sh\` → reads \`project_initial.md\` → launches \`cc.sh\` → interactive menu:

\`\`\`
1) Start Local Proxy & Claude (8082) [Default]   ← starts free-claude-code proxy
2) Connect to existing Proxy (8082)
3) Connect to CC Switch (18080)
4) Exit

Model options:
1) DeepSeek Chat (Not free)
2) DeepSeek V4 Flash (Free) [Default]
3) Llama 3.3 70B (Free)
4) Qwen3 Coder (Free)
5) Trinity Large Thinking (Free + 🧠 Thinking)
\`\`\`

## 📁 Project Structure

\`\`\`
.
├── cc.sh              # Unified launcher (proxy + model selection)
├── startup.sh         # Session start: reads project goals + launches cc.sh
├── ending.sh          # Session end: update logs + commit + push
├── .env               # API keys (gitignored)
├── $DEV_LOG  # Daily dev log
└── user/dialog.md     # Auto-reconstructed conversation history
\`\`\`

## 🛠 Prerequisites

- \`uv\` — Python package manager (\`brew install uv\`)
- \`npx\` / Node.js — for Claude Code CLI
- \`free-claude-code\` proxy at \`~/free-claude-code/\`
- OpenRouter API key in \`.env\`
EOF

echo "# Project Initial" > project_initial.md
echo "(Describe your new project goals here)" >> project_initial.md

echo "# Skill List" > skill_list.md
echo "- (Add installed skills here)" >> skill_list.md

echo "# Free Claude Code Proxy Readme" > freecc_readme.md

# 3. Clean subdirectories
echo "📁 Cleaning user and Tutorial directories..."
mkdir -p user Tutorial
echo "# User Conversation Dialog History" > user/dialog.md
echo "# Tutorial 1: Getting Started" > Tutorial/Tutorial_1.md

# 4. Finalizing
chmod +x startup.sh ending.sh cc.sh cleanAll.sh

echo "✅ Cleanup complete. $PROJECT_NAME is ready for a fresh start!"
echo "👉 Run ./startup.sh to begin your session."

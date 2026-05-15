#!/bin/bash
echo "🛑 準備結束目前的工作階段..."
echo ""

# =========================================================
# 1. 驗證與同步專案核心文件
# =========================================================
echo "================================================="
echo "📋 步驟 1：驗證核心文件"
echo "================================================="
echo ""

# Check dev log exists and show last update
LATEST_LOG=$(ls -t *開發日誌*.md 2>/dev/null | head -n 1)
if [ -n "$LATEST_LOG" ]; then
    echo "✅ 開發日誌：$LATEST_LOG"
    echo "   最後修改：$(date -r "$LATEST_LOG" '+%Y-%m-%d %H:%M:%S')"
else
    echo "❌ 找不到開發日誌！請建立今日日誌再繼續。"
fi

# Check README exists
if [ -f "README.md" ]; then
    echo "✅ README.md：存在"
    echo "   最後修改：$(date -r README.md '+%Y-%m-%d %H:%M:%S')"
else
    echo "❌ 找不到 README.md！"
fi
echo ""

# =========================================================
# 2. 提醒 AI 更新開發日誌 & 對話紀錄
# =========================================================
echo "================================================="
echo "🤖 步驟 2：AI 更新開發日誌 & 對話紀錄"
echo "================================================="
echo ""
echo "嗨，AI 助手！請確認以下文件已更新後再繼續："
echo "   ✅ 開發日誌 (*開發日誌*.md) — 加入今日所有有意義的除錯、優化與結論"
echo "   ✅ README.md — 確保反映最新的工作流與使用說明"
echo "   ✅ Tutorials/ — 若有新任務，請更新對應教學文件"
echo ""
echo "正在自動重建 user/dialog.md 對話紀錄..."
python3 reconstruct_dialog.py 2>/dev/null || echo "⚠️ reconstruct_dialog.py 執行失敗"
echo ""
read -r -p "✅ 所有文件已確認更新完畢？按 Enter 繼續推送至 GitHub..."
echo ""

# =========================================================
# 3. Git 備份
# =========================================================
echo "================================================="
echo "📦 步驟 3：Git 備份推送至 GitHub"
echo "================================================="
git add .
git commit -m "Auto-commit: 結束工作階段 $(date +%Y-%m-%d)" || echo "（無新變更）"
git push origin main || echo "⚠️ 推送失敗：請確認 git remote 設定。"
echo ""
echo "✅ 完成備份與同步！下次請執行 ./startup.sh 開始新工作階段。"

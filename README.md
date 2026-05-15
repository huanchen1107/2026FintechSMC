# 2026FintechSMC

> **⚠️ MEMO (2026.05.15)**: CC Switch is currently **not working**. Do not use it.
> This project runs exclusively via the **`free-claude-code` local proxy** with API keys configured in `.env`.
> Simply run `./cc.sh` to start.

## 🚀 Quick Start

```bash
./startup.sh   # Initialize project + launch Claude Code
./ending.sh    # Commit, push, and finalize session
```

## 🤖 How it Works

`startup.sh` → reads `project_initial.md` → launches `cc.sh` → interactive menu:

```
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
```

## 📁 Project Structure

```
.
├── cc.sh              # Unified launcher (proxy + model selection)
├── startup.sh         # Session start: reads project goals + launches cc.sh
├── ending.sh          # Session end: update logs + commit + push
├── .env               # API keys (gitignored)
├── 2026.05.15開發日誌.md  # Daily dev log
└── user/dialog.md     # Auto-reconstructed conversation history
```

## 🛠 Prerequisites

- `uv` — Python package manager (`brew install uv`)
- `npx` / Node.js — for Claude Code CLI
- `free-claude-code` proxy at `~/free-claude-code/`
- OpenRouter API key in `.env`

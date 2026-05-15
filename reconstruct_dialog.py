import json
import os
import glob

# Try to find the latest overview.txt in the brain folder
brain_path = "/Users/huango/.gemini/antigravity/brain/"
log_files = glob.glob(os.path.join(brain_path, "*/.system_generated/logs/overview.txt"))

if not log_files:
    print("Error: Could not find any overview.txt in the brain folder.")
    exit(1)

# Sort by modification time to get the most recent session
latest_log = max(log_files, key=os.path.getmtime)
print(f"Reading logs from: {latest_log}")

# Output to user directory to keep project root clean
output_path = "user/dialog.md"

with open(latest_log, 'r') as f:
    lines = f.readlines()

dialog_md = "# 完整對話紀錄 (Full Session History)\n\n"
dialog_md += f"本文件由系統日誌自動生成。來源：{latest_log}\n\n---\n\n"

for line in lines:
    try:
        entry = json.loads(line)
        source = entry.get("source")
        content = entry.get("content", "")
        
        # Redact sensitive keys
        import re
        patterns = [
            (r'sk-or-v1-[a-f0-9]{64}', '[REDACTED_OPENROUTER_KEY]'),
            (r'sk-proj-[a-zA-Z0-9_-]{100,}', '[REDACTED_OPENAI_KEY]'),
            (r'AIzaSy[a-zA-Z0-9_-]{33}', '[REDACTED_GEMINI_KEY]')
        ]
        for pattern, replacement in patterns:
            content = re.sub(pattern, replacement, content)

        if source == "USER_EXPLICIT":
            if "<USER_REQUEST>" in content:
                content = content.split("<USER_REQUEST>")[1].split("</USER_REQUEST>")[0].strip()
            dialog_md += f"### 👤 User ({entry['created_at']})\n\n{content}\n\n"
        elif source == "MODEL":
            if content:
                dialog_md += f"### 🤖 AI ({entry['created_at']})\n\n{content}\n\n"
        
        dialog_md += "---\n\n"
    except Exception:
        continue

# Ensure user directory exists
os.makedirs(os.path.dirname(output_path), exist_ok=True)

with open(output_path, 'w') as f:
    f.write(dialog_md)

print(f"Successfully updated {output_path} with {len(lines)} log entries.")

#!/bin/bash

# =================================================================
# initial.sh - New Project Bootstrap & GitHub Integration
# =================================================================

# 1. Verification
if ! command -v gh &> /dev/null; then
    echo "❌ Error: GitHub CLI (gh) is not installed. Please install it first."
    exit 1
fi

# 2. User Input
echo "🚀 Welcome to the Project Initializer!"
read -p "Enter the name for your new GitHub repository: " REPO_NAME

if [ -z "$REPO_NAME" ]; then
    echo "❌ Error: Repository name cannot be empty."
    exit 1
fi

# 3. Disconnect from Template
echo "🔗 Disconnecting from template repository..."
rm -rf .git

# 4. Initialize New Git
echo "📂 Initializing new Git repository..."
git init -b main

# 5. Clean Workspace
if [ -f "./cleanAll.sh" ]; then
    echo "🧹 Running cleanup..."
    ./cleanAll.sh "$REPO_NAME"
else
    echo "⚠️ Warning: cleanAll.sh not found. Skipping internal cleanup."
fi

# 6. Initial Commit (Required for --push)
echo "📦 Making initial commit..."
git add .
git commit -m "Initial commit from template"

# 7. Create GitHub Repository
echo "🌐 Creating repository on GitHub: $REPO_NAME"
gh repo create "$REPO_NAME" --public --source=. --remote=origin --push

if [ $? -eq 0 ]; then
    echo "✅ Success! Project '$REPO_NAME' is now live on GitHub."
    echo "🔗 Remote: $(git remote get-url origin)"
    echo "👉 You can now run ./startup.sh to begin."
else
    echo "❌ Error: Failed to create or push to the new repository."
    echo "Please check if you are logged in to gh (run 'gh auth login') or if the repo already exists."
fi

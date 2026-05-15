---
name: repo-templater
description: Create a new GitHub repository based on the current project template. Use this skill whenever the user wants to "template" the project, "clone" it to a new GitHub repo, or start a new repository using this codebase as a starting point. It will guide the user through selecting an owner and repository name.
---

# Repo Templater

This skill handles the end-to-end process of creating a new GitHub repository and pushing the current codebase to it as a template.

## Prerequisites
- GitHub CLI (`gh`) must be installed and authenticated.

## Workflow

### 1. Gather Configuration
Use `AskUserQuestion` to obtain the following details from the user:
- **GitHub Owner**: The username or organization (e.g., `huanchen1107`).
- **Repository Name**: The name for the new repository.
- **Visibility**: Public or Private (Default: Public).

### 2. Validation
- Run `gh auth status` to ensure the session is active.
- If the user is not logged in, output:
  > [!WARNING]
  > You are not logged into GitHub CLI. Please run `gh auth login` in your terminal and then try again.
- STOP if authentication fails.

### 3. Execution
Create the repository and push the current code:
```bash
gh repo create [OWNER]/[REPO_NAME] --[VISIBILITY] --source=. --remote=origin --push
```

### 4. Verification
- Confirm the successful push and provide the URL: `https://github.com/[OWNER]/[REPO_NAME]`.
- Ask if the user wants to open the new repository in their browser.

## Success Criteria
- [ ] Repository created on GitHub.
- [ ] Local files pushed to the new `origin`.
- [ ] User provided with the final URL.

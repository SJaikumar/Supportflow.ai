# GitHub Submission Checklist

## Required repository files

- [ ] `app.py` — Streamlit entry point
- [ ] `supportflow/` — agents, services, UI, database models, worker, images
- [ ] `knowledge_base/` — four sample company documents
- [ ] `requirements.txt` — Python packages to install
- [ ] `.env.example` — safe environment variable template (NO actual key)
- [ ] `.gitignore` — excludes `.env`, `.venv`, database and uploads
- [ ] `.streamlit/config.toml` — UI theme settings
- [ ] `README.md` — description, setup, features and demo walkthrough
- [ ] `tests/` — automated tests
- [ ] `docs/` — architecture, testing, walkthrough and this checklist
- [ ] `screenshots/` — **real screenshots of working app must be added by the student**
- [ ] `scripts/check_ai_connection.py` — optional connectivity diagnostic

## Before making the repository public

- [ ] Run `python -m pytest -q`; fix failures.
- [ ] Run `python -m streamlit run app.py`; verify UI.
- [ ] Capture a **Resolved** ticket, an **Escalated** ticket, and **Ticket Log** screenshots.
- [ ] Capture two more relevant test scenarios (human approval, policy citations).
- [ ] Optional: show named escalation assignment and ticket closure.
- [ ] Ensure `.env`, local SQLite database, `.venv`, uploaded images and API keys are not tracked.
- [ ] Avoid publishing real customer names, emails, financial details or uploaded images.
- [ ] Ensure `git status --short` does not include any runtime/private files.
- [ ] Preview README on GitHub and verify links/images.
- [ ] Copy the repository URL into the assignment submission.

## What NOT to upload

**Never upload:** `.env`, private API keys, `.venv/`, `__pycache__/`, `data/` (database/uploads), private customer logs, credential files, local FAISS indexes, sample invoices containing real identifiers or old intermediate patch ZIPs.

## PowerShell commands to publish

1. Create an **empty** repository on GitHub (do not auto-create a README or `.gitignore`).
2. Open PowerShell at the folder containing `app.py`:

```powershell
cd C:\SupportFlow
# Run only if this folder is not already a Git repository:
git init -b main
git add .
git status --short
git commit -m "Initial SupportFlow AI submission"
git remote add origin https://github.com/YOUR_USERNAME/supportflow-ai.git
git push -u origin main
```

Replace `YOUR_USERNAME` with your own GitHub user or organization name. GitHub may ask you to authenticate using the browser or credential manager.

**If you already have a Git repository**, do not rerun `git init` or blindly re-add a remote. Inspect `git remote -v` and use the existing repository.

**Security check before `git add .`:** Inspect files with `git status` and review `.gitignore`. If `.env` was committed previously, adding it to `.gitignore` does **not** remove it from Git history. Rotate any exposed key and remove the sensitive data from the repository history before publication.

## Submission communication

The assignment requests sharing the GitHub URL and example screenshots with the course group/community. Prefer screenshots from a successful live run, not static mockups.

## Release-specific notes

Use the **Stage 4.6 final package** for the submitted code. If your VS Code folder has more recent local edits, copy them into the final submission folder and rerun `python -m pytest -q` before uploading. The ZIP is not a linked Git repository and does not automatically update your GitHub account.

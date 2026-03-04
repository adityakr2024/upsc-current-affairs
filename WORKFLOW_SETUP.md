# ⚠️ IMPORTANT: Manual Step Required for GitHub Actions

## Why this file exists

When uploading files to GitHub via the **web interface (drag and drop)**,
folders and files starting with `.` (like `.github/`) are often **silently skipped**.
This means the automation workflow will NOT exist and nothing will run.

You must create the workflow file manually on GitHub. Follow these steps exactly.

---

## Step-by-Step: Create the Workflow on GitHub

### 1. Go to your repository on GitHub

Open `https://github.com/YOUR_USERNAME/YOUR_REPO_NAME`

### 2. Click "Add file" → "Create new file"

### 3. In the filename box, type this EXACTLY:

```
.github/workflows/daily.yml
```

GitHub will auto-create the folders when you type the slashes.

### 4. Copy and paste this ENTIRE content into the editor:

```yaml
name: Daily UPSC Current Affairs

on:
  schedule:
    - cron: '30 0 * * *'
  workflow_dispatch:

permissions:
  contents: write

jobs:
  generate-current-affairs:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install system fonts
        run: |
          sudo apt-get update -q
          sudo apt-get install -y fonts-noto fonts-noto-extra fonts-liberation fonts-dejavu

      - name: Install Python dependencies
        run: pip install -r requirements.txt

      - name: Run daily current affairs pipeline
        env:
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          EMAIL_ADDRESS: ${{ secrets.EMAIL_ADDRESS }}
          EMAIL_PASSWORD: ${{ secrets.EMAIL_PASSWORD }}
          EMAIL_TO: ${{ secrets.EMAIL_TO }}
          SITE_URL: ${{ secrets.SITE_URL }}
        run: |
          cd scripts
          python main.py

      - name: Commit and push website data
        run: |
          git config --local user.email "github-actions[bot]@users.noreply.github.com"
          git config --local user.name "github-actions[bot]"
          git add docs/
          git diff --staged --quiet || git commit -m "Daily Current Affairs $(date +'%Y-%m-%d')"
          git push
```

### 5. Scroll down and click "Commit new file"

---

## Verify it worked

After committing, go to the **Actions** tab of your repository.
You should see "Daily UPSC Current Affairs" listed as a workflow.

Click it → click "Run workflow" → "Run workflow" (green button) to test manually.

---

## Alternative: Use Git command line (easier if you have it)

If you have Git installed on your computer, just run:

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO_NAME
cd YOUR_REPO_NAME
# Copy all project files here including the .github folder
git add -A
git commit -m "Initial setup"
git push
```

Git CLI handles hidden files/folders automatically.

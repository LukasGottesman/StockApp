# Rules for StockApp project

## Workflow - Git
- After every functional code change, always automatically run git add, git commit and git push without asking. Git is already set up and connected.
- **BEFORE** every `git add`, verify with `git diff --cached --name-only` that no sensitive file is being added (see Forbidden Files section).

---

## Security Rules (MANDATORY)

These rules apply to ALL future development of this project. Violating them can lead to leakage of personal and financial user data.

### 1. No credentials in code
- **NEVER** add passwords, API keys, tokens or any access credentials directly into source code.
- Always use `st.secrets["KEY_NAME"]` to access sensitive values.
- For local development, secrets are read from `.streamlit/secrets.toml`.
- On Streamlit Cloud, secrets are set in Settings -> Secrets.
- If code needs a new secret, add only `st.secrets["NEW_KEY"]` in the code and notify the user to set the value in Streamlit Secrets and in `.streamlit/secrets.toml`.

### 2. No financial/personal data in repository
- **NEVER** create, modify or commit files containing user financial data.
- All financial data (CSV exports from brokers) are loaded EXCLUSIVELY via `st.file_uploader` - they stay only in memory (RAM) and disappear after closing the browser.
- For local development, CSV files may exist on disk but MUST NOT be committed to Git.

### 3. Forbidden files for Git
The following file types MUST NEVER be committed to the git repository:
- `*.csv` - financial exports
- `*.xlsx`, `*.xls` - financial exports
- `*.json` (except `package.json`, `package-lock.json`) - cache and data files
- `.env` - environment variables
- `.streamlit/secrets.toml` - local secrets
- `*_cache.json` - cache files
- Any file containing personal data, account numbers, or investment data

### 4. Pre-commit checks
Before every `git add` and `git commit`:
1. Verify that `.gitignore` covers all sensitive file formats
2. Check `git diff` for hardcoded credentials (passwords, keys, tokens)
3. Check `git status` for tracked sensitive files

### 5. Error handling and logging
- **NEVER** log or display secret values, passwords, or financial data content in error messages.
- In `st.error()` show only the error type and general description, never specific data.
- `print()` statements in production must not contain sensitive data (portfolio values, tickers with quantities).

### 6. Input validation
- Validate all user inputs (tickers, numbers, dates) before processing.
- Limit ticker symbols to alphanumeric characters, dots and dashes (max 10 characters).
- Verify numbers (quantities, prices) are within reasonable ranges.

### 7. Dependencies
- In `requirements.txt`, specify concrete package versions (e.g. `streamlit==1.35.0`), not just names without versions, to prevent supply-chain attacks.
- Before adding a new dependency, verify it is a legitimate, actively maintained package.

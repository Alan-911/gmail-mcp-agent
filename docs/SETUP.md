# Setup Guide — Gmail MCP Agent

Follow these steps to authorize and run your autonomous Gmail assistant.

### 1. Prerequisites
- Python 3.11+
- A [Google Cloud Project](https://console.cloud.google.com/)
- An [Anthropic API Key](https://console.anthropic.com/) (Claude 3 Haiku for cost-efficiency)

### 2. Google Cloud API Credentials
1. Go to the **Google Cloud Console** > **APIs & Services** > **Dashboard**.
2. Enable the **Gmail API**.
3. Go to **Credentials** > **Create Credentials** > **OAuth Client ID**.
4. Configure the **OAuth Consent Screen** (Internal or External).
5. Application Type: **Desktop App**.
6. Name: `Gmail MCP Agent`.
7. Download the `credentials.json` file and place it in the project root.

### 3. Local Environment Setup
1. Clone the repo.
2. Create a `.env` file:
   ```env
   ANTHROPIC_API_KEY=sk-ant-xxx
   POLL_INTERVAL_SECONDS=60
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### 4. Authorize Your Account
1. Run the script:
   ```bash
   python agent.py
   ```
2. A browser window will open. Log in to your Gmail account and grant permissions.
3. This creates a `token.json` file in your root folder for future sessions.

### 5. Running the Agent & Dashboard
1. The `agent.py` script starts the background daemon.
2. To see the data visualized, start the FastAPI dashboard:
   ```bash
   uvicorn dashboard:app --reload --port 5000
   ```
3. The dashboard endpoints (`/api/log`, `/api/stats`) now serve your recently classified emails.

### 6. Classification Categories
By default, the agent uses these labels (folder `MCP/` in Gmail):
- `Action Required` (Important items)
- `Projects` (Work-related threads)
- `Newsletters` (Low-priority reading)
- `Cold Outreach` (Potential spam or sales pitches)
- `Spam/Social` (General noise)
- `Auto-Archive` (Thread cleanup)

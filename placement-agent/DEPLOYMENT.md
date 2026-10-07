# Deployment Guide

This guide covers setting up, deploying, and maintaining the **Trident Auto Placement Agent** on Windows.

---

## Option A: Docker (Recommended)

Running via Docker Compose manages the PostgreSQL database and application agent container seamlessly without requiring local Python or PostgreSQL installations.

### Step-by-Step Instructions

1. **Install Docker Desktop for Windows**
   - Download and install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/).
   - Ensure the WSL 2 backend is enabled in Docker settings.

2. **Configure Environment Variables**
   - Copy `.env.example` to `.env`:
     ```powershell
     Copy-Item .env.example .env
     ```
   - Open `.env` and fill in your credentials (`GEMINI_API_KEY`, `GMAIL_SENDER`, `GMAIL_APP_PASSWORD`, `GMAIL_RECIPIENT`).
   - For Docker, keep the default database URL:
     ```env
     DATABASE_URL=postgresql+asyncpg://placement_agent:placement_agent@db:5432/placement_agent
     ```

3. **Launch Containers**
   - Start the database and agent service in detached mode:
     ```powershell
     docker-compose up -d
     ```

4. **Verify Health Status**
   - Query the health endpoint:
     ```powershell
     curl http://localhost:8000/api/health
     ```
   - Expected response:
     ```json
     {"status": "ok", "service": "trident-placement-agent", "timestamp": "..."}
     ```

5. **View Live Logs**
   - Follow logs from the running placement agent container:
     ```powershell
     docker-compose logs -f agent
     ```

6. **Trigger a Manual Run**
   - Execute an immediate crawl and evaluation cycle:
     ```powershell
     curl -X POST http://localhost:8000/api/run-now
     ```

---

## Option B: Direct (Windows, Python 3.12)

If you prefer running directly on your Windows host machine with Python 3.12:

### Step-by-Step Instructions

1. **Create and Activate Virtual Environment**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. **Install Dependencies**
   ```powershell
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**
   - Create `.env` from `.env.example`.
   - Update `DATABASE_URL` to point to your local PostgreSQL instance:
     ```env
     DATABASE_URL=postgresql+asyncpg://placement_agent:placement_agent@localhost:5432/placement_agent
     ```

4. **Validate Setup**
   - Run the preflight environment checker:
     ```powershell
     python scripts/check_setup.py
     ```

5. **Run Database Migrations**
   ```powershell
   alembic upgrade head
   ```

6. **Start the Application Server**
   ```powershell
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

---

## Gmail App Password Setup

Gmail blocks basic password login. You must generate a dedicated 16-character **Google App Password**.

1. **Enable 2-Step Verification**
   - Go to your [Google Account Security](https://myaccount.google.com/security).
   - Under **How you sign in to Google**, ensure **2-Step Verification** is turned ON.

2. **Navigate to App Passwords**
   - Search for **App passwords** in the top search bar, or navigate to:
     `https://myaccount.google.com/apppasswords`

3. **Generate App Password**
   - Enter an app name (e.g. `Trident Placement Agent`).
   - Click **Create**.
   - Google will display a 16-character passcode in a yellow banner (e.g., `abcd efgh ijkl mnop`).

4. **Add to `.env`**
   - Paste the password into `.env`:
     ```env
     GMAIL_APP_PASSWORD=abcd efgh ijkl mnop
     ```
     *(Spaces are automatically handled, or you can remove them: `abcdefghijklmnop`)*.

---

## Running as a Windows Service (Optional)

To keep the agent running in the background across Windows reboots, use **NSSM** (Non-Sucking Service Manager):

1. **Download NSSM**
   - Download the latest binary from [nssm.cc](https://nssm.cc/download) and extract `nssm.exe`.

2. **Install Service**
   - Open PowerShell as Administrator:
     ```powershell
     nssm install PlacementAgent "E:\tridentauto\placement-agent\.venv\Scripts\uvicorn.exe" "main:app --host 0.0.0.0 --port 8000"
     nssm set PlacementAgent AppDirectory "E:\tridentauto\placement-agent"
     ```

3. **Start Service**
   ```powershell
   nssm start PlacementAgent
   ```

4. **Check Service Status**
   ```powershell
   nssm status PlacementAgent
   ```

---

## Environment Variable Reference

| Variable | Description | Example / Default |
| :--- | :--- | :--- |
| `DATABASE_URL` | PostgreSQL asyncpg connection string | `postgresql+asyncpg://user:pass@localhost:5432/db` |
| `GEMINI_API_KEY` | Google Gemini API key for structured data extraction | `AIzaSy...` |
| `GMAIL_SENDER` | Sending Gmail address | `notifications@gmail.com` |
| `GMAIL_APP_PASSWORD` | 16-character Google App Password | `xxxx xxxx xxxx xxxx` |
| `GMAIL_RECIPIENT` | Candidate receiving email alerts | `jeebanmohanty45@gmail.com` |
| `CHECK_INTERVAL_MINUTES` | Frequency of automated portal crawls in minutes | `30` |
| `APP_ENV` | Application environment (`production` or `development`) | `production` |
| `LOG_LEVEL` | Logging verbosity (`INFO`, `DEBUG`, `WARN`, `ERROR`) | `INFO` |

---

## Troubleshooting

### 1. Connection Refused (Database)
- **Symptom**: `asyncpg.exceptions.CannotConnectNowError` or `Connection refused`.
- **Solution**:
  - If using Docker: check if the `db` service is healthy via `docker-compose ps`.
  - If running directly: ensure PostgreSQL service is running on `localhost:5432` and credentials in `.env` match.

### 2. Authentication Failed (Gmail SMTP)
- **Symptom**: `smtplib.SMTPAuthenticationError: (535, b'5.7.8 Username and Password not accepted')`.
- **Solution**:
  - Do NOT use your regular Google account password.
  - Generate a new 16-character **App Password** from `https://myaccount.google.com/apppasswords`.
  - Ensure 2-Step Verification is enabled on the sending Google account.

### 3. No Posts Found / Network Timeout
- **Symptom**: `fetch_listing_page.done count=0` or `httpx.ConnectTimeout`.
- **Solution**:
  - Verify your machine has internet access to `https://trident.ac.in`.
  - Run `python -c "import httpx; print(httpx.get('https://trident.ac.in').status_code)"` to test connectivity.

### 4. LLM Extraction Failed
- **Symptom**: `llm_extractor.error` in logs with fallback partial extractions.
- **Solution**:
  - Verify your `GEMINI_API_KEY` at [Google AI Studio](https://aistudio.google.com/).
  - Ensure your API key quota has not been exceeded.

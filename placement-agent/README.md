# Trident Auto Placement Agent

Automated placement portal monitor for Trident Academy of Technology students. Scrapes the official placement notice portal every 30 minutes, leverages Google Gemini AI to extract structured eligibility criteria, evaluates eligibility using a deterministic rules engine, and sends high-priority Gmail alerts with direct apply links.

## Features

- **Automated Portal Monitoring**: Periodically polls the Trident placement portal and detects new or updated notices.
- **AI-Powered Extraction**: Uses Google Gemini to convert unstructured notices, attachments, and PDFs into structured eligibility schemas.
- **Deterministic Eligibility Engine**: Purely rule-based verification for Branch (CSE/IT), Graduation Batch (2027), Minimum CGPA, and Backlog restrictions — never silently drops a real opportunity.
- **Gmail HTML Alerts**: Sends rich email notifications with company details, salary/CTC, deadlines, and a direct apply button.
- **PostgreSQL Deduplication**: Guarantees zero duplicate emails via SHA-256 content hashing and idempotent database tracking.
- **FastAPI HTTP Interface**: Health checks, manual pipeline trigger, and post inspection endpoints.
- **Container Ready**: Full Docker and `docker-compose` support for reproducible deployments.

## Architecture

```
Trident Portal → fetcher.py → change_detector.py → pdf_extractor.py
                                                           ↓
                                              llm_extractor.py (Gemini)
                                                           ↓
                                              rules_engine.py (CSE check)
                                                           ↓
                                              email_sender.py (Gmail SMTP)
                                                           ↓
                                              PostgreSQL (audit log)
```

## Quick Start

### Prerequisites
- Python 3.12+
- PostgreSQL 16+
- Google Gemini API Key
- Gmail Account with an App Password configured

### Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your database, Gemini API key, and Gmail credentials

# 3. Run with Docker (Recommended)
docker-compose up -d

# OR run directly
uvicorn main:app --reload
```

## Configuration

### `candidate.yaml`
Specifies the student profile used by the deterministic eligibility engine:
- `branch`: Allowed branch aliases (e.g., `["CSE", "Computer Science and Engineering", "CS"]`).
- `graduation_year`: Expected year of passing (e.g., `2027`).
- `cgpa`: Current candidate CGPA (e.g., `8.26`).
- `active_backlogs`: Number of uncleared backlogs (e.g., `0`).

### Environment Variables (`.env`)
| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string (`postgresql+asyncpg://user:pass@localhost:5432/db`) |
| `GEMINI_API_KEY` | Google AI Studio API key |
| `GMAIL_SENDER` | Email address sending the alerts |
| `GMAIL_APP_PASSWORD` | 16-character Google App Password |
| `GMAIL_RECIPIENT` | Candidate's destination email address |
| `CHECK_INTERVAL_MINUTES` | Frequency of portal scraping runs (default: `30`) |

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Service health check and current timestamp |
| `POST` | `/api/run-now` | Manually triggers the placement pipeline |
| `GET` | `/api/posts` | Lists recent placement posts with eligibility status |
| `GET` | `/api/posts/{id}` | Returns complete detail for a specific post |

## Testing

```bash
pytest tests/ -v
```

## Gmail App Password Setup

1. Open **Google Account** → **Security** → **2-Step Verification** (must be enabled first).
2. Scroll down to **App Passwords**.
3. Generate a new App Password named `Trident Placement Agent`.
4. Copy the 16-character password and set it as `GMAIL_APP_PASSWORD` in your `.env` file.

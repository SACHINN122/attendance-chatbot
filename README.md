# Kairon: NSUT Smart Attendance Assistant 🎓

An intelligent attendance analytics chatbot for NSUT that predicts leave eligibility and provides insights into your attendance patterns using web scraping and conversational AI.

The logged-in workspace now combines chat with an interactive dashboard:
- subject, semester, date-range, status, and search filters
- overall metrics, subject comparison bars, cumulative attendance trend, subject table, and date-wise records
- authenticated profile header with portal name, roll number, and captured student photo when the portal exposes it
- chat commands for summary, subject-wise details, absences, risk/safe subjects, profile, website surfaces, and shortcut help

---

## 🎯 Why This Architecture?

### Why Playwright over Selenium?
- **Performance:** Playwright is 2-3x faster than Selenium for modern web apps
- **Better Frame Handling:** Seamlessly navigates complex frame structures (like the NSUT portal's banner/data frames)
- **Built-in Captcha Support:** Easy screenshot capture for headless automation
- **Multi-language:** Works with Python, Node.js, Java, .NET (we use Python)
- **Sync & Async:** We use sync API for simplicity; async available for scaling

### Why Captcha Required?
The NSUT portal enforces CAPTCHA to prevent automated abuse. Our flow:
1. User submits roll number + password
2. Backend loads the NSUT login form (framed)
3. Playwright captures the CAPTCHA image & sends to frontend
4. User solves CAPTCHA in the UI
5. Backend submits CAPTCHA + credentials → scrapes attendance data
6. Results cached for 5 minutes to avoid repeated logins

### Architecture Overview
```
┌─────────────┐                    ┌──────────────────┐
│   Frontend  │◄──── JSON API ────►│  Flask Backend   │
│  (HTML/JS)  │                    │  (app.py)        │
└─────────────┘                    └──────────────────┘
                                            │
                                    ┌───────▼────────┐
                                    │   Scraper      │
                                    │ (playwright,   │
                                    │  beautifulsoup)│
                                    └────────────────┘
                                            │
                                            ▼
                                    ┌──────────────────┐
                                    │ NSUT Portal      │
                                    │ (framed structure)
                                    └──────────────────┘
```

---

## 📦 Project Structure

```
Kairon/
├── README.md                    # This file
├── requirements.txt             # Project dependencies
├── .env                         # Credentials (DO NOT COMMIT)
│
├── backend/
│   ├── app.py                   # Flask API routes
│   ├── scraper.py               # Web scraper (Playwright/BeautifulSoup)
│   ├── chatbot.py               # Chatbot Q&A engine
│   ├── playwright_manager.py    # Playwright lifecycle manager
│   ├── logging_config.py        # Structured logging setup
│   ├── requirements.txt         # Backend-specific dependencies
│   └── data/                    # Cached attendance JSON files
│
├── frontend/
│   ├── index.html               # Main UI
│   ├── style.css                # Styling
│   └── js/
│       └── app.js               # Frontend logic
│
├── css/
│   └── main.css                 # Shared CSS
│
└── .venv/                       # Python virtual environment (gitignored)
```

---

## 🚀 Getting Started

### Prerequisites
- Python 3.12+
- macOS / Linux / Windows (with WSL2)

### 1️⃣ Clone & Navigate to Project

```bash
cd /Volumes/algsoch/sachin/Kairon
```

### 2️⃣ Create & Activate Virtual Environment

```bash
# Create a Python 3.12 virtual environment
python3.12 -m venv .venv

# Activate it
source .venv/bin/activate

# On Windows:
# .venv\Scripts\activate
```

### 3️⃣ Bootstrap pip (if needed)

```bash
# Ensure pip is installed in the venv
.venv/bin/python -m ensurepip --upgrade
.venv/bin/python -m pip install --upgrade pip setuptools wheel
```

### 4️⃣ Install Dependencies

```bash
# Install all project requirements
.venv/bin/python -m pip install -r requirements.txt

# Download Playwright browsers (required for scraping)
.venv/bin/python -m playwright install chromium
```

### 5️⃣ Set Up Credentials

Create a `.env` file in the project root:

```bash
cat > .env << 'EOF'
roll_no=YOUR_ROLL_NUMBER
password=YOUR_PASSWORD
EOF
```

**⚠️ WARNING:** Do NOT commit `.env` to Git. It's already in `.gitignore`.

### 6️⃣ Run the Server

```bash
cd backend
../.venv/bin/python app.py
```

You should see:

```
 * Serving Flask app 'app'
 * Debug mode: on
 * Running on http://127.0.0.1:5000
```

### 7️⃣ Open in Browser

Navigate to **http://127.0.0.1:5000** and log in with your NSUT credentials.

---

## 🔑 API Endpoints

All endpoints return JSON. Requires `session_id` (except login/cache check).

### POST `/api/login`
**Start login flow.** Frontend sends roll number + password; backend captures CAPTCHA.

**Request:**
```json
{
  "rollno": "2024ABC0000",
  "password": "your_password"
}
```

`semester` is intentionally not required. The scraper reads the authenticated attendance form and tries likely year/semester filters internally.

**Response (Success):**
```json
{
  "success": true,
  "session_id": "uuid-string",
  "captcha_base64": "data:image/png;base64,..."
}
```

**Next Step:** User solves CAPTCHA & calls `/api/captcha`.

---

### POST `/api/captcha`
**Submit CAPTCHA solution & scrape attendance.**

**Request:**
```json
{
  "session_id": "uuid-string",
  "captcha": "ABC123"
}
```

**Response (Success):**
```json
{
  "success": true,
  "message": "Login successful! I've fetched your attendance data..."
}
```

---

### POST `/api/chat`
**Chat with the attendance assistant.** Try:
- `"HI"` → Full attendance dashboard
- `"SW"` → Subject-wise list, then enter a number for details
- `"TOTAL"` → Overall attendance and total absent classes
- `"ABSENT"` → Subject-wise absences, plus exact dates when v2 day-wise data exists
- `"SAFE"` → Subjects where the student can skip classes while staying above 75%
- `"RISK"` → Borderline or below-threshold subjects
- `"PROFILE"` → Authenticated student profile summary in the local app
- `"CALENDAR"` → Portal marks such as GH/TL/CS/MB
- `"WEBSITE"` → Authenticated website sections discovered after login
- `"MEMEC303"` → Details for one subject by code/name

**Request:**
```json
{
  "session_id": "uuid-string",
  "message": "PROFILE"
}
```

**Response:**
```json
{
  "assistant_version": "data-analysis-assistant-v2",
  "reply": "**Student profile from attendance portal data**\n\n- Name: **Example Student**\n- Roll no: **20...000**\n- Degree: **B.Tech.**\n- Department: **MECHANICAL ENGINEERING**\n- Semester: **3**\n- Academic year: **2025-26**\n- Portal photo: **available**"
}
```

Public docs use redacted sample identifiers. Do not paste a real roll number, encrypted portal URL, student ID, or portal screenshot into README/PR text.

---

### POST `/api/check_cache`
**Load previous attendance data from local cache.** Skip CAPTCHA if cached.

**Request:**
```json
{
  "rollno": "2024ABC0000"
}
```

**Response (if cache exists):**
```json
{
  "success": true,
  "session_id": "new-uuid",
  "message": "Loaded from cache",
  "assistant_version": "data-analysis-assistant-v2",
  "cache_schema_version": 2,
  "cache_needs_refresh": false
}
```

---

### POST `/api/analysis`
**Get raw attendance analysis (JSON).**

**Request:**
```json
{
  "session_id": "uuid-string"
}
```

**Response:**
```json
{
  "success": true,
  "analysis": {
    "schema_version": 2,
    "student": {
      "name": "Example Student",
      "rollno": "2024ABC0000",
      "department": "MECHANICAL ENGINEERING",
      "degree": "B.Tech.",
      "photo_available": true
    },
    "attendance": [
      {
        "subject": "Strength of Materials",
        "code": "MEMEC303",
        "attended": 37,
        "total": 49,
        "absent": 12,
        "percentage": 75.51,
        "status_75": "borderline",
        "status_65": "safe",
        "absent_dates": ["2025-08-01", "2025-08-04"]
      }
    ],
    "insights": {
      "overall_percentage": 82.51,
      "total_attended": 217,
      "total_classes": 263,
      "total_absent": 46
    }
  }
}
```

---

## 📝 Server Logs

The server logs all endpoint access with request/response details:

```
[INFO] POST /api/login | Status: 200 | Duration: 8.45s
[INFO] POST /api/captcha | Status: 200 | Duration: 15.32s
[INFO] POST /api/chat | Status: 200 | Duration: 0.12s
[ERROR] POST /api/login | Status: 401 | Reason: Invalid credentials
```

---

## 🧪 Testing

### Mock Mode (No CAPTCHA, No NSUT Portal Needed)

Edit `backend/app.py`, in the `login()` function, change:

```python
scraper = AttendanceScraper(use_mock=False)
```

to:

```python
scraper = AttendanceScraper(use_mock=True)
```

Then restart the server. Mock logins return instant results without contacting NSUT.

### Run Tests (Pytest)

```bash
cd backend
../.venv/bin/python -m pytest test_scraper.py -v
```

---

## 🔧 Development

### File Structure for Features

1. **New scraper logic?** → Add to `backend/scraper.py` → `AttendanceScraper` class
2. **New chatbot features?** → Add to `backend/chatbot.py` → `ChatbotEngine` class
3. **New API route?** → Add to `backend/app.py` → Register with `@app.route()`
4. **Frontend logic?** → Edit `frontend/js/app.js`

### Enable Debug Logging

Set in `backend/app.py`:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

## 🐛 Troubleshooting

### "ModuleNotFoundError: No module named 'bs4'"
- Activate venv: `source .venv/bin/activate`
- Reinstall deps: `.venv/bin/python -m pip install -r requirements.txt`

### "Playwright browser failed to start"
- Run: `.venv/bin/python -m playwright install chromium`
- Verify: `.venv/bin/python -c "from playwright.sync_api import sync_playwright; sync_playwright().start()"`

### "Could not find the login form"
- NSUT portal may be down or changed structure
- Check: Visit https://www.imsnsit.org/imsnsit/ manually
- Debug screenshot saved as `debug_menu_final.png` in `backend/` (on error)

### "Session expired" (401 error)
- Sessions last 5 minutes
- Re-login from scratch: POST to `/api/login` again

### Port 5000 Already in Use
```bash
# Kill process using port 5000
lsof -i :5000 | grep LISTEN | awk '{print $2}' | xargs kill -9

# Or use different port in app.py:
# app.run(port=5001)
```

---

## 📊 Architecture Diagram

See diagram below (generated with Mermaid)

---

## 📚 Key Concepts

### Session Management
Each user gets a unique `session_id` UUID. The server maintains active sessions for 5 minutes before cleanup.

### Caching
Attendance data is cached per user (rollno) in `backend/data/<rollno>.json`. Check cache before re-scraping.

### Day-Wise Attendance
After initial scrape, the bot clicks on subject links to fetch per-day attendance records (Present/Absent for each date).

### Attendance Thresholds
- **75%:** Default threshold (most strict) — minimum for eligibility
- **65%:** Extended threshold (more lenient) — backup option

---

## 🚀 Render Deployment Guide

Because the app uses **Playwright** to open the NSUT portal in a hidden Chromium browser, Render needs a build step that installs Chromium and a start command that binds Gunicorn to Render's assigned port.

Since the Flask backend automatically serves the frontend files, **you only need to deploy a single Web Service!**

The easiest path is the provided `render.yaml` Blueprint. Use the manual settings below when you want to configure the Web Service yourself from the Render dashboard.

### Blueprint Deployment

1. Go to your [Render Dashboard](https://dashboard.render.com/).
2. Click **New** -> **Blueprint**.
3. Connect your GitHub repository.
4. Select the repository containing `render.yaml`.
5. Click **Apply**.

### Manual Web Service Configuration

If you do not use Blueprint, create **New** -> **Web Service** and use these values:

| Render field | Value |
| --- | --- |
| Runtime | `Python 3` |
| Root Directory | Leave empty, or set to repository root |
| Build Command | `cd backend && pip install --upgrade pip && pip install -r requirements.txt && python -m playwright install chromium` |
| Start Command | `cd backend && gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 1 --timeout 180` |
| Health Check Path | `/api/config` |

Add these environment variables in **Environment**:

| Key | Value |
| --- | --- |
| `PLAYWRIGHT_BROWSERS_PATH` | `0` |
| `PYTHON_VERSION` | `3.10.0` |
| `HOST` | `0.0.0.0` |
| `roll_no` | Your test roll number, only if you want the login form prefilled |
| `password` | Your portal password, only as a Render secret |
| `ATTENDANCE_YEAR` | Optional preferred academic year, for example `2025-26` |
| `ATTENDANCE_SEMESTER` | Optional preferred semester, for example `4` |
| `CAPTCHA_SOLVER` | Optional: `runanywhere` or `tesseract` |
| `RUNANYWHERE_CAPTCHA_URL` | Required only when `CAPTCHA_SOLVER=runanywhere` |
| `RUNANYWHERE_API_KEY` | Required only when your Runanywhere endpoint needs an API key |

Render supplies `PORT` automatically; do not hard-code it. Keep `backend/data/`, `backend/scrape/`, `.env`, screenshots, and debug HTML out of git because they are local runtime artifacts and may contain portal data.

*Note: The first deployment can take 2-4 minutes because Chromium is downloaded during the build.*

---

## 📄 License

MIT License. See LICENSE file (if present).

---

## ✉️ Support

For issues, check logs or raise an issue in the repository.

**Happy learning!** 🚀

---

## ✨ Features
- **Raw HTML Parsing**: Bypasses the portal's complex frameset architecture and CSS `display: none` restrictions to reliably extract links.
- **Captcha Streaming**: Captures the NSUT captcha image and streams it to the modern UI for human-in-the-loop solving.
- **Local Caching**: Saves your deep-scraped day-wise data to `backend/data/` locally so you only have to log in once!
- **Intelligent Predictions**: Calculates "Safe to Skip" and "Needed Classes" based on dynamic 75% and 65% thresholds.

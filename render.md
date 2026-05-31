# Render Deployment Notes

This file explains how the Render deployment is wired and what happens when a new deploy starts.

## Blueprint Overview

```mermaid
flowchart TD
    A["GitHub repository"] --> B["Render Blueprint"]
    B --> C["render.yaml at repo root"]
    C --> D["Python Web Service"]
    D --> E["Build command"]
    D --> F["Start command"]
    D --> G["Environment variables"]

    E --> E1["pip install -r backend/requirements.txt"]
    E --> E2["python -m playwright install --with-deps chromium"]

    F --> F1["cd backend"]
    F --> F2["gunicorn app:app --bind 0.0.0.0:$PORT"]

    G --> G1["PYTHON_VERSION"]
    G --> G2["PLAYWRIGHT_BROWSERS_PATH"]
    G --> G3["roll_no and password as secrets"]
```

## Request Flow On Render

```mermaid
sequenceDiagram
    autonumber
    participant Student as "Student browser"
    participant Render as "Render Web Service"
    participant Flask as "Flask app"
    participant Playwright as "Playwright Chromium"
    participant Portal as "NSUT IMS portal"
    participant Cache as "Runtime cache directory"

    Student->>Render: "Open Render URL"
    Render->>Flask: "GET /"
    Flask-->>Student: "Frontend assets"
    Student->>Flask: "POST /api/check_cache"
    Flask->>Cache: "Read backend/data/<roll>.json"
    alt "Cache exists"
        Cache-->>Flask: "analysis payload"
        Flask-->>Student: "Dashboard + assistant session"
    else "Fresh login needed"
        Student->>Flask: "POST /api/login"
        Flask->>Playwright: "Launch Chromium"
        Playwright->>Portal: "Open login page"
        Portal-->>Playwright: "CAPTCHA image"
        Playwright-->>Flask: "CAPTCHA data URL"
        Flask-->>Student: "CAPTCHA challenge"
        Student->>Flask: "POST /api/captcha"
        Flask->>Playwright: "Submit CAPTCHA and scrape"
        Playwright->>Portal: "Read profile, menu, attendance, courses, timetable"
        Playwright-->>Flask: "analysis payload"
        Flask->>Cache: "Write latest cache"
        Flask-->>Student: "Dashboard + assistant session"
    end
```

## Current `render.yaml`

```mermaid
flowchart LR
    A["type: web"] --> B["runtime: python"]
    B --> C["plan: free"]
    C --> D["buildCommand"]
    D --> E["startCommand"]
    E --> F["healthCheckPath: /api/config"]
    F --> G["envVars"]
    G --> H["PYTHON_VERSION=3.12.4"]
    G --> I["PLAYWRIGHT_BROWSERS_PATH=/opt/render/project/playwright"]
    G --> J["HOST=0.0.0.0"]
    G --> K["roll_no sync:false"]
    G --> L["password sync:false"]
```

## Environment Variables

| Key | Required | Value | Notes |
|:---|:---:|:---|:---|
| `PYTHON_VERSION` | Yes | `3.12.4` | Pins Render Python runtime. |
| `PLAYWRIGHT_BROWSERS_PATH` | Yes | `/opt/render/project/playwright` | Keeps the Chromium browser install in a stable Render project path. |
| `HOST` | Yes | `0.0.0.0` | Lets Gunicorn expose the Flask app. |
| `PORT` | Provided by Render | Render value | Used by Gunicorn in the start command. |
| `roll_no` | Yes | secret | Portal roll number. Do not commit. |
| `password` | Yes | secret | Portal password. Do not commit. |
| `CAPTCHA_SOLVER` | Optional | `tesseract` or `runanywhere` | Manual CAPTCHA entry still works without it. |
| `RUNANYWHERE_CAPTCHA_URL` | Optional | endpoint URL | Used only when `CAPTCHA_SOLVER=runanywhere`. |
| `RUNANYWHERE_API_KEY` | Optional | secret | Bearer token for a compatible solver endpoint. |

## Deploy Steps

```mermaid
flowchart TD
    A["Push branch to GitHub"] --> B["Open Render Dashboard"]
    B --> C["New Blueprint"]
    C --> D["Select repository"]
    D --> E["Render reads render.yaml"]
    E --> F["Enter sync:false secrets"]
    F --> G["Apply Blueprint"]
    G --> H["Build dependencies and Chromium"]
    H --> I["Start Gunicorn"]
    I --> J["Health check GET /api/config"]
    J --> K{"Healthy?"}
    K -->|Yes| L["App is live"]
    K -->|No| M["Inspect Render logs"]
```

## Runtime Notes

- Render starts the web service with `gunicorn app:app` from the `backend/` directory.
- Flask serves both the API and the static frontend.
- The app uses Render's `PORT` environment variable in the Gunicorn bind address.
- Local cache files created on Render are runtime data. They should not be committed to git.
- Free instances may sleep when inactive, so the first request after idle can be slower.
- If runtime logs show `Playwright browser failed to start`, rebuild with `python -m playwright install --with-deps chromium` and keep the same `PLAYWRIGHT_BROWSERS_PATH` value during build and runtime.

## Failure Map

```mermaid
flowchart TD
    A["Deploy or runtime failure"] --> B{"Where did it fail?"}
    B -->|Build| C["Check pip install and Playwright browser install"]
    B -->|Start| D["Check Gunicorn command and PORT binding"]
    B -->|Health check| E["Check /api/config response"]
    B -->|Login| F["Check portal availability, credentials, and CAPTCHA flow"]
    B -->|Scrape| G["Check backend/scrape session artifacts"]
    B -->|Cache| H["Check backend/data write permissions"]

    C --> I["Render build logs"]
    D --> J["Render runtime logs"]
    E --> J
    F --> K["Portal debug HTML and screenshots"]
    G --> K
    H --> J
```

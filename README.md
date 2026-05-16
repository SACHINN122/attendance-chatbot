# NSUT Attendance Chatbot V2

A smart, automated attendance scraper and chatbot interface for the NSUT student portal. 

It uses Playwright to natively navigate the portal, bypass captcha, and mathematically extract day-wise attendance data (bypassing all frontend CSS/JS hiding tricks), providing intelligent leave predictions through a beautiful glassmorphism UI.

---

## 🛠️ Local Setup

Since the frontend is directly served by the Flask backend, you only need to run one server!

1. **Install Python dependencies:**
   Navigate to the `backend` folder and run:
   ```bash
   pip install -r requirements.txt
   ```

2. **Install Playwright Browsers:**
   This is required for the bot to navigate the portal in the background:
   ```bash
   playwright install chromium
   ```

3. **Start the App:**
   ```bash
   python app.py
   ```
   Open `http://127.0.0.1:5000` in your browser.

---

## 🚀 Render Deployment Guide

Because the app uses **Playwright** (which requires a hidden Chromium browser to run), deploying it requires a specific configuration. 

Since the Flask backend automatically serves the frontend files, **you only need to deploy a single Web Service!**

The easiest way to deploy to Render is using the provided `render.yaml` file. 

### Step 1: Push to GitHub
Make sure all your code (including `render.yaml`, `requirements.txt`, and the frontend/backend folders) is pushed to a GitHub repository.

### Step 2: Deploy on Render
1. Go to your [Render Dashboard](https://dashboard.render.com/).
2. Click **New** -> **Blueprint**.
3. Connect your GitHub repository.
4. Render will automatically detect the `render.yaml` file and configure everything for you (Build Commands, Start Commands, and Environment Variables).
5. Click **Apply**!

*Note: The first deployment might take 2-4 minutes because it has to download and install the Chromium browser in the cloud.*

---

### Alternative: Manual Render Deployment
If you prefer not to use Blueprint, create a **New Web Service** with these settings:

- **Environment**: `Python 3`
- **Root Directory**: `.` (leave empty or set to root)
- **Build Command**: 
  ```bash
  cd backend && pip install -r requirements.txt && playwright install chromium
  ```
- **Start Command**: 
  ```bash
  cd backend && gunicorn app:app
  ```

**Environment Variables:**
You MUST add this exact environment variable, otherwise Render will delete the downloaded browser after the build step!
- Key: `PLAYWRIGHT_BROWSERS_PATH`
- Value: `0`

---

## ✨ Features
- **Raw HTML Parsing**: Bypasses the portal's complex frameset architecture and CSS `display: none` restrictions to reliably extract links.
- **Captcha Streaming**: Captures the NSUT captcha image and streams it to the modern UI for human-in-the-loop solving.
- **Local Caching**: Saves your deep-scraped day-wise data to `backend/data/` locally so you only have to log in once!
- **Intelligent Predictions**: Calculates "Safe to Skip" and "Needed Classes" based on dynamic 75% and 65% thresholds.

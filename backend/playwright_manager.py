"""Playwright browser manager for the Kairon scraper.

Keeps a single Playwright instance and browser to avoid repeated
start/stop overhead and provides safe startup/teardown helpers.
"""
from playwright.sync_api import sync_playwright
import threading

_playwright = None
_browser = None
_last_error = None
_lock = threading.Lock()


def get_browser():
    """Return a launched browser instance or None on failure."""
    global _playwright, _browser, _last_error
    with _lock:
        if _playwright is None:
            try:
                _playwright = sync_playwright().start()
            except Exception as exc:
                _last_error = f"Could not start Playwright runtime: {exc}"
                _playwright = None
                return None

        if _browser is None:
            try:
                _browser = _playwright.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                )
                _last_error = None
            except Exception as exc:
                _last_error = str(exc)
                _browser = None
                return None

    return _browser


def get_browser_error():
    """Return the most recent Playwright launch failure."""
    return _last_error


def stop_browser():
    """Stop and clean up Playwright/browser resources."""
    global _playwright, _browser
    with _lock:
        try:
            if _browser:
                _browser.close()
        except Exception:
            pass
        try:
            if _playwright:
                _playwright.stop()
        except Exception:
            pass
        _browser = None
        _playwright = None

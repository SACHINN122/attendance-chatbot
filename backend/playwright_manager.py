"""Playwright browser manager for the Kairon scraper.

Keeps a single Playwright instance and browser to avoid repeated
start/stop overhead and provides safe startup/teardown helpers.
"""
from playwright.sync_api import sync_playwright
import threading

_playwright = None
_browser = None
_lock = threading.Lock()


def get_browser():
    """Return a launched browser instance or None on failure."""
    global _playwright, _browser
    with _lock:
        if _playwright is None:
            try:
                _playwright = sync_playwright().start()
            except Exception:
                _playwright = None
                return None

        if _browser is None:
            try:
                _browser = _playwright.chromium.launch(headless=True)
            except Exception:
                _browser = None
                return None

    return _browser


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

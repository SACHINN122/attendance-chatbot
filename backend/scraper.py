import base64
import math
import uuid
import time
import threading
import os
import json
import re
import urllib.request
import urllib.error
from urllib.parse import urljoin
from datetime import datetime
from bs4 import BeautifulSoup

from playwright_manager import get_browser, get_browser_error, stop_browser

# Global dictionary to store active sessions waiting for captcha
active_sessions = {}
PORTAL_BASE_URL = "https://www.imsnsit.org/imsnsit/"

class AttendanceScraper:
    def __init__(self, use_mock=False):
        self.use_mock = use_mock
        self.cached_analysis = None
        self._last_attendance_payload = {}
        self._last_portal_catalog = {}
        self.debug_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scrape")
        os.makedirs(self.debug_root, exist_ok=True)

    def _session_debug_dir(self, session_id):
        debug_dir = os.path.join(self.debug_root, session_id)
        os.makedirs(debug_dir, exist_ok=True)
        return debug_dir

    def _write_debug_text(self, debug_dir, name, text):
        try:
            path = os.path.join(debug_dir, name)
            with open(path, "w", encoding="utf-8", errors="ignore") as f:
                f.write(text if isinstance(text, str) else str(text))
        except:
            pass

    def _write_debug_json(self, debug_dir, name, data):
        try:
            path = os.path.join(debug_dir, name)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=True)
        except:
            pass

    def _visible_text(self, html):
        soup = BeautifulSoup(html or "", "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return soup.get_text(" ", strip=True)

    def _normalize_portal_url(self, href, base_url=None):
        if not href:
            return None
        href = href.strip()
        if href.lower().startswith("javascript:"):
            return href
        return urljoin(base_url or PORTAL_BASE_URL, href)

    def _find_frame_by_name(self, page, frame_name):
        if not frame_name:
            return None
        for frame in page.frames:
            if frame.name == frame_name:
                return frame
        return None

    def _find_login_frame(self, page):
        for frame in page.frames:
            try:
                has_uid = frame.locator("input[name='uid']").count() > 0
                has_captcha = frame.locator("input[name='cap']").count() > 0
                has_image = frame.locator("img#captchaimg, img[id*='captcha'], img[src*='captcha']").count() > 0
                if has_uid and has_captcha and has_image:
                    return frame
            except:
                pass
        return None

    def _write_login_form_state(self, debug_dir, name, frame):
        try:
            state = frame.evaluate("""
                () => {
                    const valueLen = (id) => {
                        const el = document.getElementById(id);
                        return el && typeof el.value === 'string' ? el.value.length : null;
                    };
                    const captcha = document.querySelector('img#captchaimg, img[id*="captcha"], img[src*="captcha"]');
                    return {
                        url: window.location.href,
                        uid_len: valueLen('uid'),
                        pwd_len: valueLen('pwd'),
                        cap_len: valueLen('cap'),
                        hrand: document.getElementById('HRAND_NUM')?.value || null,
                        captcha_src: captcha?.getAttribute('src') || null
                    };
                }
            """)
            self._write_debug_json(debug_dir, name, state)
        except Exception as e:
            self._write_debug_json(debug_dir, name, {"error": str(e)})

    def _snapshot_page(self, page, debug_dir, prefix):
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        try:
            page.screenshot(path=os.path.join(debug_dir, f"{prefix}_{ts}.png"), full_page=True)
        except:
            pass
        try:
            self._write_debug_text(debug_dir, f"{prefix}_{ts}.html", page.content())
        except:
            pass

    def _snapshot_frames(self, page, debug_dir, prefix):
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        frame_meta = []
        for idx, frame in enumerate(page.frames):
            frame_name = frame.name or f"unnamed_{idx}"
            safe_name = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in frame_name)
            try:
                html = frame.content()
                self._write_debug_text(debug_dir, f"{prefix}_{ts}_{idx}_{safe_name}.html", html)
                frame_meta.append({"index": idx, "name": frame_name, "status": "ok"})
            except Exception as e:
                frame_meta.append({"index": idx, "name": frame_name, "status": "error", "error": str(e)})
        self._write_debug_json(debug_dir, f"{prefix}_{ts}_frames.json", frame_meta)

    def _cleanup_old_sessions(self, exclude_session_id=None):
        current_time = time.time()
        to_delete = []
        for sid, data in active_sessions.items():
            if exclude_session_id and sid == exclude_session_id:
                continue
            if current_time - data["timestamp"] > 900:  # 15 minutes
                to_delete.append(sid)
                
        for sid in to_delete:
            try:
                active_sessions[sid]["context"].close()
            except:
                pass
            del active_sessions[sid]

    def has_session(self, session_id):
        return session_id in active_sessions

    def close_session(self, session_id):
        if session_id in active_sessions:
            try:
                active_sessions[session_id]["context"].close()
            except:
                pass
            try:
                del active_sessions[session_id]
            except:
                pass

    def get_session_debug_dir(self, session_id):
        if session_id in active_sessions:
            return active_sessions[session_id].get("debug_dir")
        return None

    def _get_fresh_captcha_base64(self, frame):
        try:
            captcha_element = frame.locator("img#captchaimg, img[id*='captcha'], img[src*='captcha']")
            if captcha_element.count() == 0:
                return None
            captcha_bytes = captcha_element.first.screenshot()
            return f"data:image/png;base64,{base64.b64encode(captcha_bytes).decode('utf-8')}"
        except:
            return None

    def _get_fresh_captcha_from_page(self, page):
        """Capture latest captcha image by scanning all current frames."""
        try:
            for frame in page.frames:
                try:
                    captcha_element = frame.locator("img#captchaimg, img[id*='captcha'], img[src*='captcha']")
                    if captcha_element.count() > 0:
                        captcha_bytes = captcha_element.first.screenshot()
                        return f"data:image/png;base64,{base64.b64encode(captcha_bytes).decode('utf-8')}"
                except:
                    pass
        except:
            pass
        return None

    def _captcha_src(self, frame):
        try:
            captcha_element = frame.locator("img#captchaimg, img[id*='captcha'], img[src*='captcha']")
            if captcha_element.count() == 0:
                return None
            return captcha_element.first.get_attribute("src")
        except:
            return None

    def _trigger_captcha_refresh(self, frame):
        """Ask the portal itself to generate a new CAPTCHA for the login frame."""
        before_src = self._captcha_src(frame)
        did_trigger = False

        try:
            did_trigger = bool(frame.evaluate("""
                () => {
                    if (typeof refreshcaptcha1 === 'function') {
                        refreshcaptcha1();
                        return true;
                    }
                    const refreshImage = Array.from(document.images).find((img) => {
                        const title = (img.getAttribute('title') || '').toLowerCase();
                        const src = (img.getAttribute('src') || '').toLowerCase();
                        return title.includes('refresh') || src.includes('refresh');
                    });
                    if (refreshImage) {
                        refreshImage.click();
                        return true;
                    }
                    return false;
                }
            """))
        except:
            did_trigger = False

        if not did_trigger:
            try:
                refresh_icon = frame.locator("img[title*='Refresh'], img[src*='refresh']")
                if refresh_icon.count() > 0:
                    refresh_icon.first.click(force=True, timeout=2000)
                    did_trigger = True
            except:
                pass

        # The portal refresh function updates through a hidden iframe, so wait for
        # the login frame to settle before re-screenshotting the image.
        for _ in range(20):
            time.sleep(0.25)
            after_src = self._captcha_src(frame)
            if before_src and after_src and after_src != before_src:
                return True

        return did_trigger

    def _refresh_captcha_and_get_base64(self, page, frame=None, debug_dir=None, prefix=None):
        login_frame = frame or self._find_login_frame(page)
        if login_frame:
            self._trigger_captcha_refresh(login_frame)
            if debug_dir and prefix:
                self._write_login_form_state(debug_dir, f"{prefix}_form_state.json", login_frame)
                self._snapshot_page(page, debug_dir, prefix)
            return self._get_fresh_captcha_base64(login_frame)

        if debug_dir and prefix:
            self._snapshot_page(page, debug_dir, prefix)
        return self._get_fresh_captcha_from_page(page)

    def refresh_captcha(self, session_id):
        """Return latest captcha image for an active session without submitting login."""
        if session_id not in active_sessions:
            return {"success": False, "message": "Session expired. Please login again."}

        session_data = active_sessions[session_id]
        page = session_data["page"]
        debug_dir = session_data.get("debug_dir") or self._session_debug_dir(session_id)
        session_data["debug_dir"] = debug_dir
        session_data["timestamp"] = time.time()
        self._cleanup_old_sessions(exclude_session_id=session_id)

        captcha_base64 = self._refresh_captcha_and_get_base64(
            page,
            frame=self._find_login_frame(page),
            debug_dir=debug_dir,
            prefix="captcha_refreshed"
        )
        if not captcha_base64:
            self._snapshot_page(page, debug_dir, "captcha_refresh_failed")
            return {"success": False, "message": "Could not refresh CAPTCHA from portal."}

        return {"success": True, "captcha_base64": captcha_base64}

    def start_login(self, rollno, password):
        """Starts browser, fills credentials, returns captcha base64."""
        if self.use_mock:
            return {"success": True, "session_id": "mock_session", "captcha_base64": "mock_base64"}

        try:
            b = get_browser()
            if b is None:
                detail = get_browser_error()
                hint = (
                    "Playwright browser failed to start. On Render, rebuild with "
                    "`python -m playwright install --with-deps chromium` and keep "
                    "`PLAYWRIGHT_BROWSERS_PATH` identical during build and runtime."
                )
                raise Exception(f"{hint} Detail: {detail}" if detail else hint)

            context = b.new_context()
            page = context.new_page()
            
            # Go to the root page to initialize session properly
            page.goto("https://www.imsnsit.org/imsnsit/")
            
            # Wait a moment for frames to load
            time.sleep(2)
            
            # Click Student Login link to load the login form in the banner frame
            for frame in page.frames:
                try:
                    if frame.locator("text='Student Login'").count() > 0:
                        frame.locator("text='Student Login'").click()
                        time.sleep(2)
                        break
                except:
                    pass
            
            # Search across all frames for the login form
            login_frame = None
            for _ in range(120): # Check up to 2 minutes
                login_frame = self._find_login_frame(page)
                if login_frame:
                    break
                time.sleep(1)
                
            if not login_frame:
                raise Exception("Could not find the login form. The portal might be down or loading slowly.")
                
            try:
                # Force fill skips strict visibility/clickability checks that cause timeouts
                login_frame.locator("input[name='uid']").fill(rollno, force=True, timeout=5000)
                login_frame.locator("input[name='pwd']").fill(password, force=True, timeout=5000)
            except Exception as e:
                raise Exception(f"Found the login frame but couldn't fill credentials. Error: {str(e)}")
            
            # Capture captcha image
            captcha_element = login_frame.locator("img#captchaimg")
            if captcha_element.count() == 0:
                raise Exception("Could not locate captcha image on the login form.")

            captcha_bytes = captcha_element.screenshot()
            captcha_base64 = base64.b64encode(captcha_bytes).decode('utf-8')
            
            session_id = str(uuid.uuid4())
            debug_dir = self._session_debug_dir(session_id)
            self._snapshot_page(page, debug_dir, "01_after_login_form_fill")
            self._snapshot_frames(page, debug_dir, "01_after_login_form_fill")
            self._write_login_form_state(debug_dir, "01_login_form_state.json", login_frame)

            try:
                captcha_debug_path = os.path.join(debug_dir, "captcha_initial.png")
                captcha_element.first.screenshot(path=captcha_debug_path)
            except:
                pass

            active_sessions[session_id] = {
                "context": context,
                "page": page,
                "login_frame": login_frame,
                "rollno": rollno,
                "password": password,
                "timestamp": time.time(),
                "debug_dir": debug_dir,
                "attempts": 0,
            }
            
            self._cleanup_old_sessions()
            
            return {
                "success": True, 
                "session_id": session_id, 
                "captcha_base64": f"data:image/png;base64,{captcha_base64}"
            }
        except Exception as e:
            if 'context' in locals():
                context.close()
            return {"success": False, "message": str(e)}

    def submit_captcha_and_scrape(self, session_id, captcha_text=None, auto_ocr=False):
        """
        Submits captcha, navigates to attendance, scrapes table.
        
        Args:
            session_id: Session ID from start_login
            captcha_text: User-provided CAPTCHA solution (optional if auto_ocr=True)
            auto_ocr: If True, attempt automatic CAPTCHA solving via OCR
        """
        if self.use_mock:
             return {"success": True, "message": "Logged in with mock data"}
             
        if session_id not in active_sessions:
            return {"success": False, "message": "Session expired. Please try logging in again."}

        active_sessions[session_id]["timestamp"] = time.time()
        self._cleanup_old_sessions(exclude_session_id=session_id)
        session_data = active_sessions[session_id]
        page = session_data["page"]
        context = session_data["context"]
        rollno = session_data.get("rollno", "")
        password = session_data.get("password", "")
        debug_dir = session_data.get("debug_dir") or self._session_debug_dir(session_id)
        session_data["debug_dir"] = debug_dir
        session_data["timestamp"] = time.time()
        session_data["attempts"] = int(session_data.get("attempts", 0)) + 1
        attempt_no = session_data["attempts"]
        self._write_debug_json(debug_dir, f"attempt_{attempt_no}_input.json", {
            "auto_ocr": bool(auto_ocr),
            "captcha_text_len": len(captcha_text or ""),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        })
        self._snapshot_page(page, debug_dir, f"02_before_captcha_attempt_{attempt_no}")
        self._snapshot_frames(page, debug_dir, f"02_before_captcha_attempt_{attempt_no}")
        
        try:
            # STEP 1: Find CAPTCHA input and fill it
            login_frame = self._find_login_frame(page)
            
            if not login_frame:
                raise Exception("Could not find CAPTCHA field. Session may have expired.")
            
            # Try OCR if auto_ocr=True and captcha_text is empty
            if auto_ocr and not captcha_text:
                try:
                    captcha_text = self._ocr_captcha_from_page(page, login_frame)
                    if captcha_text:
                        print(f"[OCR] Detected CAPTCHA via OCR: '{captcha_text}'")
                        self._write_debug_text(debug_dir, f"attempt_{attempt_no}_ocr_text.txt", captcha_text)
                    else:
                        self._snapshot_page(page, debug_dir, f"03_ocr_failed_attempt_{attempt_no}")
                        return {"success": False, "message": "OCR failed to read CAPTCHA. Please enter manually."}
                except Exception as e:
                    self._write_debug_text(debug_dir, f"attempt_{attempt_no}_ocr_error.txt", str(e))
                    return {"success": False, "message": f"OCR error: {str(e)}"}
            
            if not captcha_text:
                return {
                    "success": False,
                    "message": "CAPTCHA text required",
                    "retryable": True,
                    "captcha_base64": self._get_fresh_captcha_base64(login_frame),
                }
            
            # Re-fill all fields right before submit to avoid portal-side value resets.
            if rollno:
                login_frame.locator("input[name='uid']").click(click_count=3)
                login_frame.locator("input[name='uid']").fill(str(rollno), force=True)
            if password:
                login_frame.locator("input[name='pwd']").click(click_count=3)
                login_frame.locator("input[name='pwd']").fill(str(password), force=True)

            login_frame.locator("input[name='cap']").click(click_count=3)
            login_frame.locator("input[name='cap']").fill(str(captcha_text), force=True)
            self._write_login_form_state(debug_dir, f"03_before_submit_form_state_attempt_{attempt_no}.json", login_frame)
            
            # Submit using portal's own validation function first.
            try:
                submitted = login_frame.evaluate("""
                    () => {
                        if (typeof Login === 'function') {
                            return Login() !== false;
                        }
                        const form = document.forms['f1'];
                        if (form) {
                            form.submit();
                            return true;
                        }
                        const loginButton = document.getElementById('login');
                        if (loginButton) {
                            loginButton.click();
                            return true;
                        }
                        return false;
                    }
                """)
                if not submitted:
                    self._write_login_form_state(debug_dir, f"03_submit_rejected_form_state_attempt_{attempt_no}.json", login_frame)
                    raise Exception("Portal rejected the login form before submit.")
            except Exception as e:
                # A fast frame navigation can destroy the JS context right after
                # form.submit(); in that case the submit already happened.
                nav_started = any(
                    marker in str(e).lower()
                    for marker in ["execution context was destroyed", "frame was detached", "navigation"]
                )
                if not nav_started:
                    try:
                        login_frame.locator("input[type='submit'][value='Login']").click(force=True)
                    except:
                        raise Exception("Could not submit Login form")

            self._snapshot_page(page, debug_dir, f"04_after_captcha_submit_attempt_{attempt_no}")
            self._snapshot_frames(page, debug_dir, f"04_after_captcha_submit_attempt_{attempt_no}")
            
            # STEP 2: Wait for frame-level login result. The root frameset often
            # stays loaded while child frames continue navigating.
            login_state, login_detail = self._wait_for_login_outcome(page, timeout=30)
            self._write_debug_json(debug_dir, f"05_login_outcome_attempt_{attempt_no}.json", {
                "state": login_state,
                "detail": login_detail,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            })

            if login_state == "authenticated":
                self._snapshot_page(page, debug_dir, f"05_login_success_attempt_{attempt_no}")
                self._snapshot_frames(page, debug_dir, f"05_login_success_attempt_{attempt_no}")
            elif login_state == "invalid":
                fresh_captcha = self._refresh_captcha_and_get_base64(
                    page,
                    frame=self._find_login_frame(page),
                    debug_dir=debug_dir,
                    prefix=f"05_invalid_captcha_refreshed_attempt_{attempt_no}"
                )
                self._snapshot_page(page, debug_dir, f"05_invalid_captcha_attempt_{attempt_no}")
                return {
                    "success": False,
                    "message": "Invalid CAPTCHA or wrong credentials",
                    "retryable": True,
                    "captcha_base64": fresh_captcha,
                }
            elif login_state == "login":
                fresh_captcha = self._refresh_captcha_and_get_base64(
                    page,
                    frame=self._find_login_frame(page),
                    debug_dir=debug_dir,
                    prefix=f"05_login_screen_refreshed_attempt_{attempt_no}"
                )
                self._snapshot_page(page, debug_dir, f"05_login_screen_still_visible_attempt_{attempt_no}")
                return {
                    "success": False,
                    "message": "Login did not complete. CAPTCHA may be invalid or expired. Please refresh CAPTCHA and retry.",
                    "retryable": True,
                    "captcha_base64": fresh_captcha,
                }
            else:
                fresh_captcha = self._refresh_captcha_and_get_base64(
                    page,
                    frame=self._find_login_frame(page),
                    debug_dir=debug_dir,
                    prefix=f"05_login_pending_refreshed_attempt_{attempt_no}"
                )
                self._snapshot_page(page, debug_dir, f"05_login_pending_attempt_{attempt_no}")
                return {
                    "success": False,
                    "message": "Login response did not finish loading. Please retry with the refreshed CAPTCHA.",
                    "retryable": True,
                    "captcha_base64": fresh_captcha,
                }
            
            self._ensure_activity_menu_loaded(page, debug_dir, attempt_no)
            portal_catalog = self._extract_portal_catalog(page)
            self._last_portal_catalog = portal_catalog
            self._write_debug_json(debug_dir, f"06_portal_catalog_attempt_{attempt_no}.json", portal_catalog)

            # STEP 3: Find "My Attendance" link (critical - frames may have changed)
            attendance_link = self._find_attendance_link(page)
            if not attendance_link:
                self._snapshot_frames(page, debug_dir, f"06_attendance_link_not_found_attempt_{attempt_no}")
                return {
                    "success": False,
                    "message": "Logged in, but the portal did not expose 'My Attendance' even after opening My Activities. A feedback/notice page may be blocking the activity menu.",
                    "retryable": True,
                    "captcha_base64": self._get_fresh_captcha_from_page(page),
                }

            my_attendance_href = attendance_link["href"]
            self._write_debug_text(debug_dir, f"06_attendance_href_attempt_{attempt_no}.txt", my_attendance_href)
            self._write_debug_json(debug_dir, f"06_attendance_link_attempt_{attempt_no}.json", attendance_link)
            
            # Navigate to attendance page
            try:
                self._open_attendance_link(page, attendance_link)
            except Exception as e:
                raise Exception(f"Could not navigate to attendance page: {str(e)[:80]}")

            self._snapshot_page(page, debug_dir, f"07_after_attendance_nav_attempt_{attempt_no}")
            self._snapshot_frames(page, debug_dir, f"07_after_attendance_nav_attempt_{attempt_no}")

            invalid_detail = self._invalid_operation_detail(page)
            if invalid_detail:
                self._write_debug_json(debug_dir, f"07_invalid_operation_attempt_{attempt_no}.json", invalid_detail)
                self._ensure_activity_menu_loaded(page, debug_dir, attempt_no, force=True)
                fresh_attendance_link = self._find_attendance_link(page, max_attempts=5)
                self._write_debug_json(
                    debug_dir,
                    f"07_attendance_link_retry_attempt_{attempt_no}.json",
                    fresh_attendance_link or {"found": False}
                )
                if fresh_attendance_link:
                    self._open_attendance_link(page, fresh_attendance_link)
                    self._snapshot_page(page, debug_dir, f"07_after_attendance_retry_attempt_{attempt_no}")
                    self._snapshot_frames(page, debug_dir, f"07_after_attendance_retry_attempt_{attempt_no}")
                    invalid_detail = self._invalid_operation_detail(page)

                if invalid_detail:
                    self._write_debug_json(debug_dir, f"07_invalid_operation_after_retry_attempt_{attempt_no}.json", invalid_detail)
                    raise Exception(
                        "Portal rejected the My Attendance link with Invalid operation232. "
                        "Login succeeded, but the authenticated attendance navigation was refused by the portal."
                    )
            
            # STEP 4: Find form and submit year/optional semester
            content_frame = self._find_attendance_form_frame(page, max_attempts=30)
            if not content_frame:
                self._snapshot_page(page, debug_dir, f"08_missing_form_attempt_{attempt_no}")
                raise Exception("Could not find attendance form after opening My Attendance")
            
            # STEP 5: Submit the portal's year/semester filters and parse results.
            content_frame, html_content, attendance_data = self._load_attendance_records(
                page,
                content_frame,
                debug_dir,
                attempt_no,
                rollno,
            )
            
            if not attendance_data:
                self._snapshot_page(page, debug_dir, f"10_no_records_attempt_{attempt_no}")
                raise Exception("No attendance records found")

            self._write_debug_json(debug_dir, f"11_attendance_data_attempt_{attempt_no}.json", attendance_data)
            
            # STEP 6: Deep scrape day-wise data
            for subject in attendance_data:
                href = subject.get("details_link")
                if href and "newPopup" in href:
                    try:
                        js_code = href.replace('JavaScript:', '').replace('javascript:', '')
                        with page.expect_popup() as popup_info:
                            content_frame.locator("body").evaluate(f"() => {{ {js_code} }}")
                        
                        popup = popup_info.value
                        popup.wait_for_load_state()
                        popup_html = popup.content()
                        self._write_debug_text(debug_dir, f"popup_{subject.get('subject','unknown')}_{attempt_no}.html", popup_html)
                        subject["day_wise"] = self._parse_day_wise_html(popup_html)
                        popup.close()
                    except:
                        subject.setdefault("day_wise", [])
                else:
                    subject.setdefault("day_wise", [])
            
            attendance_payload = getattr(self, "_last_attendance_payload", {}) or {}
            self.cached_analysis = self._compute_full_analysis(
                attendance_data,
                attendance_payload=attendance_payload,
                portal_catalog=portal_catalog,
            )
            self._write_debug_json(debug_dir, f"12_final_analysis_attempt_{attempt_no}.json", self.cached_analysis)
            self.close_session(session_id)
            return {"success": True, "message": "✓ Attendance synced!"}
            
        except Exception as e:
             # Keep session for retries by default unless context is unusable.
             self._write_debug_text(debug_dir, f"error_attempt_{attempt_no}.txt", str(e))
             self._snapshot_page(page, debug_dir, f"99_error_attempt_{attempt_no}")
             return {
                 "success": False,
                 "message": str(e),
                 "retryable": True,
                 "captcha_base64": self._get_fresh_captcha_from_page(page) or (self._get_fresh_captcha_base64(login_frame) if 'login_frame' in locals() and login_frame else None),
             }
    
    def _find_frame_with_selector(self, page, selector, max_attempts=30):
        """Find a frame containing the given selector (with retry)"""
        for attempt in range(max_attempts):
            try:
                for frame in page.frames:
                    try:
                        if frame.locator(selector).count() > 0:
                            return frame
                    except:
                        pass
            except:
                pass
            time.sleep(1)
        return None

    def _find_frame_with_selectors(self, page, selectors, max_attempts=30):
        """Find a frame containing all requested selectors."""
        for attempt in range(max_attempts):
            try:
                for frame in page.frames:
                    try:
                        if all(frame.locator(selector).count() > 0 for selector in selectors):
                            return frame
                    except:
                        pass
            except:
                pass
            time.sleep(1)
        return None

    def _find_attendance_form_frame(self, page, max_attempts=30):
        """Find the attendance page frame without assuming semester is required."""
        for attempt in range(max_attempts):
            try:
                for frame in page.frames:
                    try:
                        html = frame.content()
                        text = self._visible_text(html)
                        if "Total Classes" in text:
                            return frame

                        has_year = frame.locator("select[name='year']").count() > 0
                        has_semester = frame.locator("select[name='semester']").count() > 0
                        has_submit = frame.locator(
                            "input[type='submit'][value='Submit'], input[type='submit'], button[type='submit']"
                        ).count() > 0
                        is_activity_tree = frame.locator("#tree").count() > 0

                        if has_submit and (has_year or has_semester) and not is_activity_tree:
                            return frame
                    except:
                        pass
            except:
                pass
            time.sleep(1)
        return None

    def _select_attendance_year(self, frame):
        """Prefer the portal's selected year; otherwise choose an available year."""
        year_state = frame.evaluate("""
            () => {
                const select = document.querySelector('select[name="year"]');
                if (!select) return null;
                return {
                    value: select.value || '',
                    options: Array.from(select.options).map((option) => option.value).filter(Boolean)
                };
            }
        """)
        if not year_state:
            return None

        selected = year_state.get("value")
        if selected:
            return selected

        options = year_state.get("options") or []
        preferred = os.getenv("ATTENDANCE_YEAR", "").strip()
        for candidate in [preferred, "2025-26", "2026-27"]:
            if candidate and candidate in options:
                frame.locator("select[name='year']").select_option(candidate)
                return candidate

        if options:
            frame.locator("select[name='year']").select_option(options[0])
            return options[0]

        return None

    def _invalid_operation_detail(self, page):
        """Return portal invalid-operation details when a frame contains them."""
        try:
            for frame in page.frames:
                try:
                    text = self._visible_text(frame.content())
                    if "invalid operation" in text.lower():
                        return {
                            "frame_name": frame.name or "",
                            "url": frame.url,
                            "text": text[:500],
                        }
                except:
                    pass
        except:
            pass
        return None

    def _select_state(self, frame, selector):
        try:
            return frame.evaluate("""
                (selector) => {
                    const select = document.querySelector(selector);
                    if (!select) return { found: false, value: '', options: [] };
                    return {
                        found: true,
                        value: select.value || '',
                        options: Array.from(select.options)
                            .map((option) => option.value)
                            .filter(Boolean)
                    };
                }
            """, selector)
        except:
            return {"found": False, "value": "", "options": []}

    def _ordered_unique(self, values):
        ordered = []
        seen = set()
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            ordered.append(text)
        return ordered

    def _guess_current_semester(self, rollno):
        try:
            admission_year = int(str(rollno)[:4])
            now = datetime.now()
            academic_year_start = now.year if now.month >= 8 else now.year - 1
            academic_offset = max(0, academic_year_start - admission_year)
            semester = academic_offset * 2 + (1 if now.month >= 8 else 2)
            return str(min(max(semester, 1), 10))
        except:
            return None

    def _attendance_filter_candidates(self, frame, rollno):
        year_state = self._select_state(frame, "select[name='year']")
        semester_state = self._select_state(frame, "select[name='sem'], select[name='semester']")

        year_options = year_state.get("options") or []
        semester_options = semester_state.get("options") or []

        years = self._ordered_unique([
            os.getenv("ATTENDANCE_YEAR", "").strip(),
            year_state.get("value"),
            "2025-26",
            "2026-27",
            *year_options,
        ])
        guessed_semester = self._guess_current_semester(rollno)
        descending_semesters = []
        try:
            guessed_int = int(guessed_semester)
            descending_semesters = [str(semester) for semester in range(guessed_int, 0, -1)]
        except:
            pass
        previous_semester = None
        try:
            guessed_int = int(guessed_semester)
            if guessed_int > 1:
                previous_semester = str(guessed_int - 1)
        except:
            pass

        semesters = self._ordered_unique([
            os.getenv("ATTENDANCE_SEMESTER", "").strip(),
            os.getenv("SEMESTER", "").strip(),
            guessed_semester,
            previous_semester,
            *descending_semesters,
            semester_state.get("value"),
            *semester_options,
        ])

        return {
            "years": years or [None],
            "semesters": semesters or [None],
            "year_state": year_state,
            "semester_state": semester_state,
        }

    def _select_option_if_present(self, frame, selector, value):
        if value is None:
            return False
        try:
            locator = frame.locator(selector)
            if locator.count() == 0:
                return False
            locator.first.select_option(str(value), timeout=5000)
            return True
        except:
            return False

    def _click_attendance_submit(self, frame):
        submit = frame.locator(
            "form#frm input[type='submit'][name='submit'], "
            "form#frm input[type='submit'][value='Submit'], "
            "form#frm button[type='submit']"
        )
        if submit.count() == 0:
            submit = frame.locator("input[type='submit'][value='Submit'], button[type='submit']")
        if submit.count() == 0:
            raise Exception("Could not find attendance form Submit button")

        submit.first.click(timeout=5000)
        try:
            frame.wait_for_load_state("networkidle", timeout=15000)
        except:
            time.sleep(1)

    def _load_attendance_records(self, page, content_frame, debug_dir, attempt_no, rollno):
        candidates = self._attendance_filter_candidates(content_frame, rollno)
        self._write_debug_json(
            debug_dir,
            f"09_attendance_filter_candidates_attempt_{attempt_no}.json",
            candidates,
        )

        last_frame = content_frame
        last_html = ""
        filter_attempt = 0
        all_attendance_data = []
        success_filters = []
        processed_combinations = set()
        merged_payload = {
            "student": {},
            "subjects": [],
            "status_legend": {},
            "calendar": [],
            "available_years": candidates.get("years", []),
            "available_semesters": candidates.get("semesters", []),
            "synced_filters": [],
        }
        sync_all_semesters = os.getenv("ATTENDANCE_SYNC_ALL_SEMESTERS", "1").strip().lower() not in {"0", "false", "no", "off"}

        for year in candidates["years"]:
            for semester in candidates["semesters"]:
                filter_attempt += 1
                frame = self._find_attendance_form_frame(page, max_attempts=5) or last_frame
                last_frame = frame

                selected_year = self._select_option_if_present(frame, "select[name='year']", year)
                selected_semester = self._select_option_if_present(
                    frame,
                    "select[name='sem'], select[name='semester']",
                    semester,
                )
                self._write_debug_json(
                    debug_dir,
                    f"09_attendance_filter_attempt_{attempt_no}_{filter_attempt}.json",
                    {
                        "year": year,
                        "semester": semester,
                        "selected_year": selected_year,
                        "selected_semester": selected_semester,
                    },
                )

                try:
                    self._click_attendance_submit(frame)
                except Exception as e:
                    self._write_debug_text(
                        debug_dir,
                        f"09_attendance_submit_error_attempt_{attempt_no}_{filter_attempt}.txt",
                        str(e),
                    )
                    continue

                frame = self._find_attendance_form_frame(page, max_attempts=10) or frame
                last_frame = frame
                try:
                    last_html = frame.locator("body").inner_html()
                except:
                    try:
                        last_html = frame.content()
                    except:
                        last_html = ""

                safe_year = str(year or "none").replace("/", "-")
                safe_semester = str(semester or "none").replace("/", "-")
                self._write_debug_text(
                    debug_dir,
                    f"09_attendance_result_attempt_{attempt_no}_{filter_attempt}_{safe_year}_sem_{safe_semester}.html",
                    last_html,
                )

                attendance_data = self._parse_attendance_html(last_html)
                if attendance_data:
                    attendance_payload = getattr(self, "_last_attendance_payload", {}) or {}
                    selected_year_value = year or attendance_payload.get("student", {}).get("academic_year", "")
                    selected_semester_value = semester or attendance_payload.get("student", {}).get("semester", "")

                    actual_student = attendance_payload.get("student") or {}
                    actual_sem = actual_student.get("semester") or selected_semester_value
                    actual_year = actual_student.get("academic_year") or selected_year_value

                    comb_key = (actual_year, actual_sem)
                    if comb_key not in processed_combinations:
                        processed_combinations.add(comb_key)

                        for subject in attendance_data:
                            subject["academic_year"] = actual_year
                            subject["semester"] = actual_sem

                        merged_payload["student"].update({
                            key: value
                            for key, value in (attendance_payload.get("student") or {}).items()
                            if value
                        })
                        merged_payload["status_legend"].update(attendance_payload.get("status_legend") or {})
                        merged_payload["calendar"].extend(attendance_payload.get("calendar") or [])
                        merged_payload["subjects"].extend(attendance_data)
                        all_attendance_data.extend(attendance_data)

                    success_filter = {
                        "year": selected_year_value,
                        "semester": selected_semester_value,
                        "filter_attempt": filter_attempt,
                    }
                    success_filters.append(success_filter)
                    merged_payload["synced_filters"] = success_filters
                    self._write_debug_text(debug_dir, f"09_attendance_form_html_attempt_{attempt_no}.html", last_html)
                    self._write_debug_json(
                        debug_dir,
                        f"09_attendance_filter_success_attempt_{attempt_no}.json",
                        success_filter,
                    )

                    if not sync_all_semesters:
                        attendance_payload["selected_year"] = selected_year_value
                        attendance_payload["selected_semester"] = selected_semester_value
                        attendance_payload["available_years"] = candidates.get("years", [])
                        attendance_payload["available_semesters"] = candidates.get("semesters", [])
                        attendance_payload["synced_filters"] = success_filters
                        self._last_attendance_payload = attendance_payload
                        return frame, last_html, attendance_data

        self._write_debug_text(debug_dir, f"09_attendance_form_html_attempt_{attempt_no}.html", last_html)
        if all_attendance_data:
            synced_years = self._ordered_unique([item.get("year") for item in success_filters])
            synced_semesters = self._ordered_unique([item.get("semester") for item in success_filters])
            merged_payload["selected_year"] = synced_years[0] if len(synced_years) == 1 else "Multiple"
            merged_payload["selected_semester"] = synced_semesters[0] if len(synced_semesters) == 1 else "All synced"
            self._last_attendance_payload = merged_payload
            self._write_debug_json(
                debug_dir,
                f"09_attendance_filter_successes_attempt_{attempt_no}.json",
                success_filters,
            )
            return last_frame, last_html, all_attendance_data
        return last_frame, last_html, []

    def _has_authenticated_signal(self, page):
        """Detect logged-in portal content without relying on URL fragments."""
        try:
            for frame in page.frames:
                try:
                    text = self._visible_text(frame.content()).lower()
                    if "my attendance" in text:
                        return True
                    if "logout" in text and "welcome" in text:
                        return True
                    if "personal info" in text and "attendance" in text and "plum erp" in text:
                        return True
                except:
                    pass
        except:
            pass
        return False

    def _visible_login_error(self, page):
        """Return a visible login error message, ignoring validation strings inside scripts."""
        markers = [
            "invalid security",
            "invalid captcha",
            "captcha invalid",
            "incorrect",
            "wrong password",
            "wrong credentials",
            "login failed",
            "not valid",
        ]
        try:
            for frame in page.frames:
                try:
                    text = self._visible_text(frame.content())
                    lowered = text.lower()
                    if any(marker in lowered for marker in markers):
                        return text[:500]
                except:
                    pass
        except:
            pass
        return None

    def _detect_login_outcome(self, page):
        if self._has_authenticated_signal(page):
            return "authenticated", None

        error_text = self._visible_login_error(page)
        if error_text:
            return "invalid", error_text

        if self._find_login_frame(page):
            return "login", None

        return "pending", None

    def _wait_for_login_outcome(self, page, timeout=30):
        deadline = time.time() + timeout
        last_state = ("pending", None)

        while time.time() < deadline:
            state, detail = self._detect_login_outcome(page)
            last_state = (state, detail)
            if state in ("authenticated", "invalid"):
                return state, detail
            time.sleep(0.5)

        return last_state

    def _is_login_screen_still_visible(self, page):
        """Detect if the portal is still on login screen (captcha submission not accepted)."""
        return self._find_login_frame(page) is not None
    
    def _find_attendance_link(self, page, max_attempts=20):
        return self._find_portal_link_by_text(page, "My Attendance", max_attempts=max_attempts)

    def _find_portal_link_by_text(self, page, link_text, max_attempts=20):
        """Find an authenticated portal link by exact visible text across all frames."""
        expected = "".join(link_text.lower().split())

        for attempt in range(max_attempts):
            try:
                for frame in page.frames:
                    try:
                        html = frame.content()
                        visible_text = self._visible_text(html).lower()
                        if link_text.lower() not in visible_text and expected not in "".join(visible_text.split()):
                            continue

                        soup = BeautifulSoup(html, 'html.parser')
                        for a in soup.find_all('a', href=True):
                            text = " ".join(a.get_text(" ", strip=True).split())
                            normalized_text = text.lower().replace(" ", "")
                            if normalized_text != expected:
                                continue

                            href = self._normalize_portal_url(a.get('href'), frame.url)
                            if href:
                                return {
                                    "href": href,
                                    "target": a.get("target") or "data",
                                    "text": text,
                                    "frame_name": frame.name or "",
                                }
                    except:
                        pass
            except:
                pass
            
            time.sleep(1)
        
        return None

    def _ensure_activity_menu_loaded(self, page, debug_dir, attempt_no, force=False):
        """Open the My Activities tree when the portal lands on notices/feedback."""
        if not force and self._find_attendance_link(page, max_attempts=1):
            return True

        activity_link = self._find_portal_link_by_text(page, "My Activities", max_attempts=1)
        if not activity_link:
            return False

        self._write_debug_json(debug_dir, f"06_my_activities_link_attempt_{attempt_no}.json", activity_link)
        try:
            self._open_portal_link(page, activity_link)
            self._snapshot_page(page, debug_dir, f"06_after_my_activities_nav_attempt_{attempt_no}")
            self._snapshot_frames(page, debug_dir, f"06_after_my_activities_nav_attempt_{attempt_no}")
            return True
        except Exception as e:
            self._write_debug_text(debug_dir, f"06_my_activities_nav_error_attempt_{attempt_no}.txt", str(e))
            return False

    def _capture_student_photo_base64(self, page):
        """Capture the visible authenticated student photo when the portal exposes it."""
        blocked_markers = ("captcha", "logo", "banner", "icon")
        preferred_markers = ("round", "photo", "student", "profile", "user")

        for frame in page.frames:
            try:
                images = frame.locator("img")
                count = min(images.count(), 20)
            except:
                continue

            for index in range(count):
                try:
                    image = images.nth(index)
                    meta = image.evaluate("""
                        (img) => ({
                            src: img.getAttribute('src') || '',
                            alt: img.getAttribute('alt') || '',
                            title: img.getAttribute('title') || '',
                            className: String(img.className || ''),
                            width: Number(img.getAttribute('width') || img.naturalWidth || img.clientWidth || 0),
                            height: Number(img.getAttribute('height') || img.naturalHeight || img.clientHeight || 0)
                        })
                    """)
                    marker_text = " ".join(
                        str(meta.get(key) or "").lower()
                        for key in ("src", "alt", "title", "className")
                    )
                    if any(marker in marker_text for marker in blocked_markers):
                        continue

                    width = int(meta.get("width") or 0)
                    height = int(meta.get("height") or 0)
                    aspect = (width / height) if height else 0
                    looks_named = any(marker in marker_text for marker in preferred_markers)
                    looks_photo_sized = width >= 45 and height >= 45 and 0.65 <= aspect <= 1.55

                    if not looks_named and not looks_photo_sized:
                        continue

                    shot = image.screenshot(timeout=1500)
                    if shot:
                        return "data:image/png;base64," + base64.b64encode(shot).decode("utf-8")
                except:
                    continue

        return None

    def _extract_profile_pairs(self, soup):
        """Extract common profile table fields from authenticated portal HTML."""
        label_map = {
            "studentid": "student_id",
            "studentno": "student_id",
            "studentnumber": "student_id",
            "enrollmentno": "enrollment_no",
            "enrollmentnumber": "enrollment_no",
            "rollno": "rollno",
            "rollnumber": "rollno",
            "name": "name",
            "studentname": "name",
            "fathername": "father_name",
            "mothername": "mother_name",
            "dateofbirth": "date_of_birth",
            "dob": "date_of_birth",
            "gender": "gender",
            "category": "category",
            "email": "email",
            "mobileno": "mobile",
            "mobile": "mobile",
            "branch": "department",
            "department": "department",
            "programme": "degree",
            "program": "degree",
            "degree": "degree",
            "semester": "semester",
            "section": "section",
            "batch": "batch",
        }

        def clean(text):
            return " ".join(str(text or "").split()).strip(" :-")

        def key_for(label):
            return re.sub(r"[^a-z0-9]+", "", clean(label).lower())

        pairs = {}
        for row in soup.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            label = key_for(cells[0].get_text(" ", strip=True))
            field = label_map.get(label)
            value = clean(cells[1].get_text(" ", strip=True))
            if field and value and len(value) <= 120:
                pairs.setdefault(field, value)

        text = soup.get_text("\n", strip=True)
        for line in text.splitlines():
            if ":" not in line:
                continue
            label, value = line.split(":", 1)
            field = label_map.get(key_for(label))
            value = clean(value)
            if field and value and len(value) <= 120:
                pairs.setdefault(field, value)

        return pairs

    def _extract_portal_catalog(self, page):
        """Extract a safe inventory of authenticated portal sections and links."""
        catalog = {
            "sections": [],
            "links": [],
            "data_surfaces": [],
            "student_profile": {},
        }
        seen_sections = set()
        seen_links = set()

        try:
            for frame in page.frames:
                try:
                    soup = BeautifulSoup(frame.content(), "html.parser")
                except:
                    continue

                frame_text = self._visible_text(str(soup)).lower()
                if "my attendance" not in frame_text and "my timetable" not in frame_text and "my profile" not in frame_text:
                    continue

                text_blob = self._visible_text(str(soup))
                welcome_match = re.search(r"Welcome\s*:\s*([A-Za-z][A-Za-z .'-]+)", text_blob, re.I)
                if welcome_match and not catalog["student_profile"].get("name"):
                    catalog["student_profile"]["name"] = " ".join(welcome_match.group(1).split())

                for key, value in self._extract_profile_pairs(soup).items():
                    catalog["student_profile"].setdefault(key, value)

                if not catalog["student_profile"].get("photo_available"):
                    for image in soup.find_all("img"):
                        width = image.get("width") or ""
                        height = image.get("height") or ""
                        classes = " ".join(image.get("class") or []).lower()
                        if classes == "round" or (str(width).isdigit() and str(height).isdigit() and int(width) >= 40 and int(height) >= 40):
                            catalog["student_profile"]["photo_available"] = True
                            break

                active_section = None
                for node in soup.find_all(["b", "a"]):
                    if node.name == "b":
                        section = " ".join(node.get_text(" ", strip=True).split()).strip(" :")
                        if section and len(section) <= 80:
                            active_section = section
                            key = section.lower()
                            if key not in seen_sections:
                                seen_sections.add(key)
                                catalog["sections"].append(section)
                        continue

                    text = " ".join(node.get_text(" ", strip=True).split()).strip()
                    if not text:
                        image = node.find("img")
                        text = (image.get("title") or image.get("alt") or "").strip() if image else ""
                    if not text:
                        continue

                    key = (active_section or "", text.lower())
                    if key in seen_links:
                        continue
                    seen_links.add(key)
                    catalog["links"].append({
                        "section": active_section or "Portal",
                        "text": text,
                        "target": node.get("target") or "",
                    })
        except:
            pass

        important = {
            "profile": ["my profile", "personal", "id card"],
            "attendance": ["my attendance", "current sem courses"],
            "timetable": ["my timetable", "class timetable", "faculty timetable", "roomtimetable", "labtimetable"],
            "exams": ["admit card", "marks", "results", "grade card", "transcript"],
            "fees": ["fee"],
            "library": ["received books"],
            "requests": ["request", "certificate"],
        }
        for surface, markers in important.items():
            if any(any(marker in link["text"].lower() for marker in markers) for link in catalog["links"]):
                catalog["data_surfaces"].append(surface)

        photo_base64 = self._capture_student_photo_base64(page)
        if photo_base64:
            catalog["student_profile"]["photo_available"] = True
            catalog["student_profile"]["photo_base64"] = photo_base64

        return catalog

    def _click_portal_anchor(self, frame, link_info):
        """Click a portal anchor from inside its own frame so target/referrer are preserved."""
        return frame.evaluate(r"""
            ({ expectedText, expectedHref }) => {
                const normalize = (value) => (value || '')
                    .replace(/\s+/g, ' ')
                    .trim()
                    .toLowerCase()
                    .replace(/\s/g, '');

                const expected = normalize(expectedText);
                const links = Array.from(document.querySelectorAll('a[href]'));
                const byText = expected
                    ? links.find((anchor) => normalize(anchor.textContent) === expected)
                    : null;
                const byHref = expectedHref
                    ? links.find((anchor) => anchor.href === expectedHref || anchor.getAttribute('href') === expectedHref)
                    : null;
                const anchor = byText || byHref;

                if (!anchor) {
                    return { clicked: false, reason: 'anchor not found', link_count: links.length };
                }

                let node = anchor;
                while (node && node.nodeType === Node.ELEMENT_NODE) {
                    const style = window.getComputedStyle(node);
                    if (style.display === 'none') {
                        node.style.display = node.tagName === 'UL' ? 'block' : '';
                    }
                    if (style.visibility === 'hidden') {
                        node.style.visibility = 'visible';
                    }
                    if (node.classList) {
                        node.classList.remove('expandable', 'lastExpandable');
                        if (node.tagName === 'LI') node.classList.add('collapsable');
                    }
                    node = node.parentElement;
                }

                anchor.scrollIntoView({ block: 'center', inline: 'nearest' });
                anchor.focus({ preventScroll: true });
                anchor.click();

                return {
                    clicked: true,
                    href: anchor.href,
                    target: anchor.getAttribute('target') || '',
                    text: anchor.textContent || ''
                };
            }
        """, {
            "expectedText": link_info.get("text") or "",
            "expectedHref": link_info.get("href") or "",
        })

    def _open_portal_link(self, page, link_info):
        href = link_info.get("href")
        target = (link_info.get("target") or "data").strip()

        if not href:
            raise Exception("Portal link did not include a URL")

        source_frame = self._find_frame_by_name(page, link_info.get("frame_name"))
        candidate_frames = [source_frame] if source_frame else list(page.frames)
        last_click_result = None

        for frame in candidate_frames:
            if not frame:
                continue
            try:
                last_click_result = self._click_portal_anchor(frame, link_info)
                if last_click_result and last_click_result.get("clicked"):
                    target_frame = self._find_frame_by_name(page, target)
                    if target_frame:
                        try:
                            target_frame.wait_for_load_state("domcontentloaded", timeout=10000)
                        except:
                            pass
                    time.sleep(1)
                    return
            except Exception as e:
                last_click_result = {"clicked": False, "error": str(e)}

        if "plum_url.php" in href:
            reason = (last_click_result or {}).get("reason") or (last_click_result or {}).get("error") or "anchor click failed"
            raise Exception(f"Could not click encrypted portal link in-frame: {reason}")

        if target and target.lower() not in ("_blank", "new"):
            target_frame = self._find_frame_by_name(page, target)
            if target_frame:
                target_frame.goto(href, timeout=30000)
                target_frame.wait_for_load_state("domcontentloaded", timeout=30000)
                time.sleep(1)
                return

        page.goto(href, timeout=30000)
        page.wait_for_load_state("domcontentloaded", timeout=30000)
        time.sleep(1)

    def _open_attendance_link(self, page, link_info):
        self._open_portal_link(page, link_info)
    
    def _ocr_captcha_from_page(self, page, frame):
        """Attempt to read CAPTCHA via OCR (Tesseract)"""
        try:
            # pyrefly: ignore [missing-import]
            import pytesseract
            # pyrefly: ignore [missing-import]
            from PIL import Image
            import io
            
            # Configure tesseract executable path on Windows if not already on PATH
            if os.name == 'nt':
                import shutil
                if not shutil.which("tesseract"):
                    for path in [
                        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                        os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe")
                    ]:
                        if os.path.exists(path):
                            pytesseract.pytesseract.tesseract_cmd = path
                            break
            
            # Find and screenshot the CAPTCHA image
            try:
                captcha_img_element = frame.locator("img[id*='captcha'], img[src*='captcha']")
                if captcha_img_element.count() == 0:
                    return None
                
                # Get screenshot of just the image
                screenshot_bytes = captcha_img_element.screenshot()
            except:
                return None

            # Optional: use Runanywhere-compatible endpoint first when configured.
            solver_mode = os.getenv("CAPTCHA_SOLVER", "tesseract").strip().lower()
            if solver_mode == "runanywhere":
                solved = self._runanywhere_solve_captcha(screenshot_bytes)
                if solved:
                    return solved
            
            # Use OCR
            image = Image.open(io.BytesIO(screenshot_bytes))
            ocr_text = pytesseract.image_to_string(
                image,
                config='--oem 3 --psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
            )
            cleaned_text = ''.join(c for c in ocr_text if c.isalnum()).strip()
            
            return cleaned_text if len(cleaned_text) > 0 else None
            
        except ImportError:
            print("[DEBUG] pytesseract not installed. Install: pip install pytesseract Pillow")
            return None
        except Exception as e:
            print(f"[DEBUG] OCR error: {e}")
            return None

    def _runanywhere_solve_captcha(self, screenshot_bytes):
        """Solve captcha using external Runanywhere-compatible HTTP endpoint.

        Configure via env:
        - CAPTCHA_SOLVER=runanywhere
        - RUNANYWHERE_CAPTCHA_URL=https://.../solve
        - RUNANYWHERE_API_KEY=...
        """
        endpoint = os.getenv("RUNANYWHERE_CAPTCHA_URL", "").strip()
        if not endpoint:
            print("[DEBUG] RUNANYWHERE_CAPTCHA_URL not set; falling back to tesseract")
            return None

        try:
            payload = json.dumps({
                "task": "captcha",
                "image_base64": base64.b64encode(screenshot_bytes).decode("utf-8")
            }).encode("utf-8")

            req = urllib.request.Request(endpoint, data=payload, method="POST")
            req.add_header("Content-Type", "application/json")

            api_key = os.getenv("RUNANYWHERE_API_KEY", "").strip()
            if api_key:
                req.add_header("Authorization", f"Bearer {api_key}")

            with urllib.request.urlopen(req, timeout=20) as resp:
                body = resp.read().decode("utf-8", errors="ignore")

            data = json.loads(body)
            # Accept common field names.
            candidate = (
                data.get("text")
                or data.get("captcha")
                or data.get("solution")
                or data.get("result")
            )

            if isinstance(candidate, dict):
                candidate = candidate.get("text") or candidate.get("solution")

            if not candidate:
                return None

            cleaned = ''.join(c for c in str(candidate) if c.isalnum()).strip()
            return cleaned if cleaned else None
        except urllib.error.HTTPError as e:
            print(f"[DEBUG] Runanywhere HTTP error: {e.code}")
            return None
        except Exception as e:
            print(f"[DEBUG] Runanywhere solver error: {e}")
            return None


    def _attendance_year_for_month(self, month_abbr, academic_year):
        month = (month_abbr or "")[:3].title()
        if not academic_year or "-" not in academic_year:
            return None

        try:
            start_text, end_text = academic_year.split("-", 1)
            start_year = int(start_text)
            end_year = int(str(start_year)[:2] + end_text) if len(end_text) == 2 else int(end_text)
            return start_year if month in {"Jul", "Aug", "Sep", "Oct", "Nov", "Dec"} else end_year
        except:
            return None

    def _normalize_attendance_date(self, day_text, academic_year):
        match = re.match(r"^([A-Za-z]{3})-(\d{1,2})$", str(day_text or "").strip())
        if not match:
            return None

        month_abbr, day = match.groups()
        year = self._attendance_year_for_month(month_abbr, academic_year)
        if not year:
            return None

        try:
            parsed = datetime.strptime(f"{year}-{month_abbr.title()}-{int(day):02d}", "%Y-%b-%d")
            return parsed.strftime("%Y-%m-%d")
        except:
            return None

    def _attendance_cell_counts(self, raw_value):
        raw = " ".join(str(raw_value or "").replace("\xa0", " ").split())
        tokens = [token.strip().upper() for token in raw.split("+") if token.strip()]
        present = sum(1 for token in tokens if token == "1")
        absent = sum(1 for token in tokens if token == "0")
        special = [token for token in tokens if token not in {"0", "1"}]

        if absent and present:
            status = "mixed"
        elif absent:
            status = "absent"
        elif present:
            status = "present"
        elif special:
            status = "special"
        else:
            status = "empty"

        return {
            "raw": raw,
            "tokens": tokens,
            "present_count": present,
            "absent_count": absent,
            "special_count": len(special),
            "special_codes": special,
            "class_count": present + absent,
            "status": status,
        }

    def _parse_special_notes(self, soup):
        notes = {}
        note_pattern = re.compile(
            r"([A-Z][A-Z0-9]+)\s*-+>\s*(\d{2}-\d{2}-\d{4})\s*-+>\s*([A-Z]+)\s*-\s*([^\n\r]+)"
        )
        for match in note_pattern.finditer(soup.get_text("\n", strip=True)):
            code, date_text, mark, description = match.groups()
            try:
                parsed_date = datetime.strptime(date_text, "%d-%m-%Y").strftime("%Y-%m-%d")
            except:
                parsed_date = date_text
            notes.setdefault(code, []).append({
                "date": parsed_date,
                "mark": mark,
                "description": " ".join(description.split()),
            })
        return notes

    def _parse_attendance_payload(self, html_content):
        soup = BeautifulSoup(html_content or "", "html.parser")

        def clean(text):
            return " ".join(str(text or "").split())

        def label_key(text):
            return re.sub(r"[^a-z0-9%]+", "", clean(text).lower())

        def to_int(value):
            match = re.search(r"\d+", clean(value))
            return int(match.group(0)) if match else 0

        def to_float(value):
            match = re.search(r"\d+(?:\.\d+)?", clean(value))
            return float(match.group(0)) if match else 0.0

        def selected_value(selector):
            tag = soup.select_one(selector)
            if not tag:
                return None
            selected = tag.find("option", selected=True)
            return (selected.get("value") or selected.get_text(" ", strip=True)).strip() if selected else None

        payload = {
            "student": {},
            "subjects": [],
            "status_legend": {},
            "calendar": [],
        }

        academic_year = selected_value("select[name='year']")
        semester = selected_value("select[name='sem']") or selected_value("select[name='semester']")
        rollno_input = soup.find("input", {"name": "recentitycode"})
        dept_input = soup.find("input", {"name": "dept"})
        degree_input = soup.find("input", {"name": "degree"})

        payload["student"] = {
            "rollno": rollno_input.get("value", "").strip() if rollno_input else "",
            "department": dept_input.get("value", "").strip() if dept_input else "",
            "degree": degree_input.get("value", "").strip() if degree_input else "",
            "semester": semester or "",
            "academic_year": academic_year or "",
        }

        tables = soup.find_all("table")
        if not any("Total Classes" in table.get_text(" ", strip=True) for table in tables):
            self._last_attendance_payload = payload
            return payload

        header_pattern = re.compile(r"Name:\s*(.*?)(?:\s*\(([^)]+)\))?\s*,\s*Semester\s*:\s*(\d+)", re.I)
        header_match = header_pattern.search(soup.get_text(" ", strip=True))
        if header_match:
            name, roll_from_header, sem_from_header = header_match.groups()
            payload["student"]["name"] = clean(name)
            if roll_from_header:
                payload["student"]["rollno"] = roll_from_header.strip()
            payload["student"]["semester"] = sem_from_header

        subject_codes = []
        for row in soup.find_all("tr"):
            cells = row.find_all(["th", "td"])
            texts = [clean(cell.get_text(" ", strip=True)) for cell in cells]
            if texts and label_key(texts[0]) == "days":
                codes = [text for text in texts[1:] if text]
                if len(codes) > len(subject_codes):
                    subject_codes = codes

        if not subject_codes:
            self._last_attendance_payload = payload
            return payload

        subject_names = {}
        last_subject_code = None
        code_pattern = re.compile(r"^([A-Z]{2,}[A-Z0-9]*\d[A-Z0-9]*)\s*-\s*(.+)$")
        legend_pattern = re.compile(r"^([A-Z]{2})\s*-\s*(.+)$")
        for line in soup.get_text("\n", strip=True).splitlines():
            normalized_line = clean(line)
            if "-->" in normalized_line or "---" in normalized_line:
                last_subject_code = None
                continue
            match = code_pattern.match(normalized_line)
            if match and match.group(1) in subject_codes:
                code, name = match.groups()
                subject_names[code] = name.strip()
                last_subject_code = code
                continue
            legend_match = legend_pattern.match(normalized_line)
            if legend_match and legend_match.group(1) not in subject_codes:
                payload["status_legend"][legend_match.group(1)] = legend_match.group(2).strip()
                last_subject_code = None
                continue
            if last_subject_code and len(subject_names) < len(subject_codes):
                subject_names[last_subject_code] = clean(
                    f"{subject_names[last_subject_code]} {normalized_line}"
                )

        rows_by_label = {}
        events_by_code = {code: [] for code in subject_codes}
        for table in tables:
            header_codes = []
            for row in table.find_all("tr"):
                cells = row.find_all(["th", "td"])
                if len(cells) < 2:
                    continue
                texts = [clean(cell.get_text(" ", strip=True)) for cell in cells]
                key = label_key(texts[0])
                if key:
                    rows_by_label.setdefault(key, []).append(texts[1:])

                if key == "days":
                    header_codes = [text for text in texts[1:] if text]
                    continue

                if not header_codes or not re.match(r"^[A-Za-z]{3}-\d{1,2}$", texts[0]):
                    continue

                date_label = texts[0]
                date_iso = self._normalize_attendance_date(date_label, academic_year)
                for index, code in enumerate(header_codes):
                    if index + 1 >= len(texts):
                        continue
                    counts = self._attendance_cell_counts(texts[index + 1])
                    if counts["status"] == "empty":
                        continue
                    event = {
                        "date": date_iso or date_label,
                        "label": date_label,
                        **counts,
                    }
                    events_by_code.setdefault(code, []).append(event)
                    payload["calendar"].append({"code": code, **event})

        special_notes = self._parse_special_notes(soup)

        total_values = rows_by_label.get("overallclass", [None])[-1]
        present_values = rows_by_label.get("overallpresent", [None])[-1]
        absent_values = rows_by_label.get("overallabsent", [None])[-1]
        percentage_values = rows_by_label.get("overall%", [None])[-1]

        if not total_values or not present_values:
            monthly_totals = rows_by_label.get("totalclasses", [])
            monthly_present = rows_by_label.get("totalpresent", [])
            monthly_absent = rows_by_label.get("totalabsent", [])
            subject_count = len(subject_codes)
            total_sums = [0] * subject_count
            present_sums = [0] * subject_count
            absent_sums = [0] * subject_count

            for values in monthly_totals:
                for index, value in enumerate(values[:subject_count]):
                    total_sums[index] += to_int(value)
            for values in monthly_present:
                for index, value in enumerate(values[:subject_count]):
                    present_sums[index] += to_int(value)
            for values in monthly_absent:
                for index, value in enumerate(values[:subject_count]):
                    absent_sums[index] += to_int(value)

            total_values = total_sums
            present_values = present_sums
            absent_values = absent_sums
            percentage_values = []

        subject_count = min(len(subject_codes), len(total_values or []), len(present_values or []))
        for index in range(subject_count):
            total_classes = to_int(total_values[index])
            total_present = to_int(present_values[index])
            if total_classes <= 0:
                continue

            total_absent = to_int(absent_values[index]) if absent_values and index < len(absent_values) else max(total_classes - total_present, 0)
            if percentage_values and index < len(percentage_values):
                percentage = to_float(percentage_values[index])
            else:
                percentage = round((total_present / total_classes * 100), 2)

            code = subject_codes[index]
            day_wise = events_by_code.get(code, [])
            absent_dates = [
                event["date"] for event in day_wise
                if event.get("absent_count", 0) > 0
            ]
            special_events = special_notes.get(code, [])
            for event in day_wise:
                for special_code in event.get("special_codes", []):
                    if any(note["date"] == event["date"] and note["mark"] == special_code for note in special_events):
                        continue
                    special_events.append({
                        "date": event["date"],
                        "mark": special_code,
                        "description": payload["status_legend"].get(special_code, special_code),
                    })

            payload["subjects"].append({
                "subject": subject_names.get(code, code),
                "code": code,
                "academic_year": academic_year or "",
                "semester": semester or "",
                "attended": total_present,
                "total": total_classes,
                "absent": total_absent,
                "percentage": percentage,
                "details_link": None,
                "day_wise": day_wise,
                "absent_dates": absent_dates,
                "special_events": sorted(special_events, key=lambda item: item.get("date", "")),
            })

        self._last_attendance_payload = payload
        return payload

    def _parse_attendance_html(self, html_content):
        payload = self._parse_attendance_payload(html_content)
        return payload.get("subjects", [])

    def _parse_day_wise_html(self, html_content):
        """Parse the popup window HTML to extract day-wise attendance."""
        soup = BeautifulSoup(html_content, 'html.parser')
        day_wise_data = []
        
        # Typically the table has headers like Date, Period, Status, etc.
        tables = soup.find_all('table')
        if not tables:
            return day_wise_data
            
        # We assume the largest table or the one with "Date" header
        target_table = None
        for table in tables:
            if "Date" in table.text or "Status" in table.text or "Absent" in table.text or "Present" in table.text:
                target_table = table
                break
                
        if not target_table:
            return day_wise_data
            
        rows = target_table.find_all('tr')
        for row in rows:
            tds = row.find_all('td')
            if len(tds) >= 2:
                date_str = tds[0].get_text(strip=True)
                # Ensure it looks like a date (very basic check)
                if '-' in date_str and len(date_str) > 5:
                    status_text = ""
                    for td in tds[1:]:
                        text = td.get_text(strip=True).lower()
                        if "present" in text or "absent" in text:
                            status_text = td.get_text(strip=True)
                            break
                    if status_text:
                        day_wise_data.append({"date": date_str, "status": status_text})
                        
        return day_wise_data

    def _compute_full_analysis(self, attendance_data, attendance_payload=None, portal_catalog=None):
        attendance_payload = attendance_payload or {}
        portal_catalog = portal_catalog or {}
        subjects = []
        for subject in attendance_data:
            prediction_75 = self.get_leave_prediction(subject, threshold=75.0)
            prediction_65 = self.get_leave_prediction(subject, threshold=65.0)
            absent_classes = subject.get("absent", max(subject.get("total", 0) - subject.get("attended", 0), 0))
            day_wise = subject.get("day_wise") or []
            attended_days = len({event.get("date") for event in day_wise if event.get("present_count", 0) > 0})
            absent_days = len({event.get("date") for event in day_wise if event.get("absent_count", 0) > 0})
            recent_activity = sorted(
                [event for event in day_wise if event.get("date")],
                key=lambda item: item.get("date", ""),
                reverse=True,
            )[:8]
            
            subject_analysis = {
                **subject,
                "absent": absent_classes,
                "attended_days": attended_days,
                "absent_days": absent_days,
                "recent_activity": recent_activity,
                "status_75": prediction_75["status"],
                "message_75": prediction_75["message"],
                "skippable_75": prediction_75.get("skippable_classes", 0),
                "needed_75": prediction_75.get("needed_classes", 0),
                "status_65": prediction_65["status"],
                "message_65": prediction_65["message"],
                "skippable_65": prediction_65.get("skippable_classes", 0),
                "needed_65": prediction_65.get("needed_classes", 0),
                "status": prediction_75["status"],
                "message": prediction_75["message"],
            }
            subjects.append(subject_analysis)

        total_classes = sum(subject.get("total", 0) for subject in subjects)
        total_attended = sum(subject.get("attended", 0) for subject in subjects)
        total_absent = sum(subject.get("absent", max(subject.get("total", 0) - subject.get("attended", 0), 0)) for subject in subjects)
        overall_percentage = round((total_attended / total_classes * 100), 2) if total_classes else 0.0
        risky_subjects = [subject for subject in subjects if subject.get("status_75") != "safe"]
        lowest_subject = min(subjects, key=lambda item: item.get("percentage", 1000), default=None)
        strongest_subject = max(subjects, key=lambda item: item.get("percentage", -1), default=None)
        total_skippable_75 = sum(max(subject.get("skippable_75", 0), 0) for subject in subjects)
        all_absences = []
        all_specials = []
        for subject in subjects:
            for event in subject.get("day_wise", []):
                if event.get("absent_count", 0) > 0:
                    all_absences.append({
                        "date": event.get("date"),
                        "subject": subject.get("subject"),
                        "code": subject.get("code"),
                        "count": event.get("absent_count", 0),
                        "raw": event.get("raw", ""),
                    })
            for event in subject.get("special_events", []):
                all_specials.append({
                    "date": event.get("date"),
                    "subject": subject.get("subject"),
                    "code": subject.get("code"),
                    "mark": event.get("mark"),
                    "description": event.get("description", ""),
                })

        student = {
            **((portal_catalog or {}).get("student_profile") or {}),
            **(attendance_payload.get("student") or {}),
        }
        student = {key: value for key, value in student.items() if value}

        return {
            "schema_version": 2,
            "synced_at": datetime.utcnow().isoformat() + "Z",
            "student": student,
            "attendance": subjects,
            "insights": {
                "subject_count": len(subjects),
                "total_classes": total_classes,
                "total_attended": total_attended,
                "total_absent": total_absent,
                "overall_percentage": overall_percentage,
                "total_skippable_75": total_skippable_75,
                "risky_subject_count": len(risky_subjects),
                "risky_subjects": [
                    {
                        "subject": subject.get("subject"),
                        "code": subject.get("code"),
                        "percentage": subject.get("percentage"),
                        "needed_75": subject.get("needed_75", 0),
                    }
                    for subject in risky_subjects
                ],
                "lowest_subject": {
                    "subject": lowest_subject.get("subject"),
                    "code": lowest_subject.get("code"),
                    "percentage": lowest_subject.get("percentage"),
                } if lowest_subject else None,
                "strongest_subject": {
                    "subject": strongest_subject.get("subject"),
                    "code": strongest_subject.get("code"),
                    "percentage": strongest_subject.get("percentage"),
                } if strongest_subject else None,
                "recent_absences": sorted(all_absences, key=lambda item: item.get("date") or "", reverse=True)[:12],
                "special_events": sorted(all_specials, key=lambda item: item.get("date") or "", reverse=True)[:20],
            },
            "portal": portal_catalog,
            "source": {
                "academic_year": attendance_payload.get("selected_year") or attendance_payload.get("student", {}).get("academic_year", ""),
                "semester": attendance_payload.get("selected_semester") or attendance_payload.get("student", {}).get("semester", ""),
                "available_years": attendance_payload.get("available_years", []),
                "available_semesters": attendance_payload.get("available_semesters", []),
                "synced_filters": attendance_payload.get("synced_filters", []),
                "status_legend": attendance_payload.get("status_legend", {}),
                "data_surfaces": portal_catalog.get("data_surfaces", []),
            },
        }

    def get_leave_prediction(self, subject_data, threshold=75.0):
        attended = subject_data["attended"]
        total = subject_data["total"]
        percentage = subject_data["percentage"]
        threshold_decimal = threshold / 100.0
        
        if total == 0:
            return {"status": "safe", "message": f"No classes have been held yet.", "skippable_classes": 0}
            
        if percentage >= threshold:
            skippable = math.floor((attended / threshold_decimal) - total)
            if skippable <= 0:
                return {
                    "status": "borderline", 
                    "skippable_classes": 0,
                    "message": f"Exactly at {threshold}%! You can skip 0 classes."
                }
            return {
                "status": "safe", 
                "skippable_classes": skippable,
                "message": f"You can skip {skippable} more classses."
            }
        else:
            needed = math.ceil((threshold_decimal * total - attended) / (1 - threshold_decimal))
            return {
                "status": "danger",
                "needed_classes": needed,
                "message": f"Below {threshold}%! attend {needed} more classes to reach {threshold}%."
            }

    def deduplicate_and_recompute(self, analysis):
        if not analysis or not isinstance(analysis, dict) or "attendance" not in analysis:
            return analysis
        
        subjects = analysis.get("attendance") or []
        seen = set()
        deduped = []
        for s in subjects:
            key = (s.get("code"), s.get("academic_year"), s.get("semester"))
            if key not in seen:
                seen.add(key)
                deduped.append(s)
        
        if len(deduped) == len(subjects):
            return analysis
            
        new_analysis = self._compute_full_analysis(
            deduped,
            attendance_payload=analysis.get("source"),
            portal_catalog=analysis.get("portal")
        )
        if "student" in analysis:
            new_analysis["student"] = analysis["student"]
        return new_analysis

    def get_full_analysis(self):
        if self.cached_analysis:
            self.cached_analysis = self.deduplicate_and_recompute(self.cached_analysis)
            return self.cached_analysis
        return {
            "schema_version": 2,
            "student": {},
            "attendance": [],
            "insights": {},
            "portal": {},
            "source": {},
        }

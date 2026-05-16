from playwright.sync_api import sync_playwright
import base64
import math
import uuid
import time
import threading
from bs4 import BeautifulSoup

playwright_instance = None
browser = None
lock = threading.Lock()

def get_browser():
    global playwright_instance, browser
    with lock:
        if playwright_instance is None:
            playwright_instance = sync_playwright().start()
            browser = playwright_instance.chromium.launch(headless=True)
    return browser

# Global dictionary to store active sessions waiting for captcha
active_sessions = {}

class AttendanceScraper:
    def __init__(self, use_mock=False):
        self.use_mock = use_mock
        self.cached_analysis = None

    def _cleanup_old_sessions(self):
        current_time = time.time()
        to_delete = []
        for sid, data in active_sessions.items():
            if current_time - data["timestamp"] > 300:  # 5 minutes
                to_delete.append(sid)
                
        for sid in to_delete:
            try:
                active_sessions[sid]["context"].close()
            except:
                pass
            del active_sessions[sid]

    def start_login(self, rollno, password, semester):
        """Starts browser, fills credentials, returns captcha base64."""
        if self.use_mock:
            return {"success": True, "session_id": "mock_session", "captcha_base64": "mock_base64"}

        try:
            b = get_browser()
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
                for frame in page.frames:
                    try:
                        if frame.locator("input[name='uid']").count() > 0:
                            login_frame = frame
                            break
                    except:
                        pass
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
            captcha_bytes = captcha_element.screenshot()
            captcha_base64 = base64.b64encode(captcha_bytes).decode('utf-8')
            
            session_id = str(uuid.uuid4())
            active_sessions[session_id] = {
                "context": context,
                "page": page,
                "login_frame": login_frame,
                "semester": semester,
                "timestamp": time.time()
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

    def submit_captcha_and_scrape(self, session_id, captcha_text):
        """Submits captcha, navigates to attendance, scrapes table."""
        if self.use_mock:
             return {"success": True, "message": "Logged in with mock data"}
             
        if session_id not in active_sessions:
            return {"success": False, "message": "Session expired. Please try logging in again."}
            
        session_data = active_sessions[session_id]
        page = session_data["page"]
        login_frame = session_data.get("login_frame", page)
        context = session_data["context"]
        semester = session_data["semester"]
        
        try:
            login_frame.locator("input[name='cap']").click(click_count=3)
            login_frame.locator("input[name='cap']").fill(captcha_text)
            
            # Click Login
            login_frame.locator("input[type='submit'][value='Login']").click()
            
            page.wait_for_load_state("networkidle")
            
            # Re-fetch page content and check for errors
            # Errors could be in the main page or in the banner frame
            content = page.content()
            try:
                banner_content = page.frame_locator("frame[name='banner']").locator("body").inner_html()
                content += banner_content
            except:
                pass
                
            if "Invalid" in content or "Incorrect" in content:
                raise Exception("Invalid credentials or incorrect captcha.")
                
            # If successful, we land on the logged-in dashboard
            # The left menu already contains "My Attendance" (hidden inside the ATTENDANCE folder)
            # Since it's hidden (display: none), JS DOM queries can be flaky.
            # We will use raw HTML parsing to extract the link and navigate to it directly!
            my_attendance_href = None
            for _ in range(15):
                for f in page.frames:
                    try:
                        html = f.content()
                        if "My Attendance" in html:
                            soup = BeautifulSoup(html, 'html.parser')
                            for a in soup.find_all('a'):
                                if a.text and "My Attendance" in a.text:
                                    href = a.get('href')
                                    if href:
                                        if not href.startswith('http'):
                                            href = "https://www.imsnsit.org/imsnsit/" + href
                                        my_attendance_href = href
                                        break
                    except:
                        pass
                    if my_attendance_href:
                        break
                if my_attendance_href:
                    break
                time.sleep(1)
                
            if not my_attendance_href:
                try:
                    page.screenshot(path="debug_menu_final.png", full_page=True)
                except:
                    pass
                raise Exception("Could not find the 'My Attendance' link on the dashboard.")
                
            # Navigate the data frame directly to the extracted URL
            data_frame = None
            for f in page.frames:
                if f.name == "data":
                    data_frame = f
                    break
                    
            if data_frame:
                data_frame.goto(my_attendance_href)
            else:
                page.goto(my_attendance_href)
            
            # The form loads in the content frame (data frame)
            # Search across all frames for the attendance form
            content_frame = None
            for _ in range(30):
                for frame in page.frames:
                    try:
                        if frame.locator("select[name='year']").count() > 0:
                            content_frame = frame
                            break
                    except:
                        pass
                if content_frame:
                    break
                time.sleep(1)
                
            if not content_frame:
                raise Exception("Could not find the attendance form dropdowns.")
                
            content_frame.locator("select[name='year']").select_option("2025-26")
            
            # Assuming 'semester' is just the number like '4'
            content_frame.locator("select[name='semester']").select_option(str(semester))
            content_frame.locator("input[type='submit'][value='Submit']").click()
            
            # Wait for table to render
            try:
                content_frame.locator("table").locator("text=/Total Classes/i").wait_for(timeout=15000)
            except:
                pass
            
            html_content = content_frame.locator("body").inner_html()
            
            # Parse table
            attendance_data = self._parse_attendance_html(html_content)
            
            if not attendance_data:
                raise Exception("Could not find any attendance records.")
                
            # DEEP SCRAPE FOR DAY-WISE DATA
            for subject in attendance_data:
                href = subject.get("details_link")
                if href and "newPopup" in href:
                    try:
                        # Extract the javascript function call
                        js_code = href.replace('JavaScript:', '').replace('javascript:', '')
                        with page.expect_popup() as popup_info:
                            # Run the script in the context of the content_frame
                            content_frame.locator("body").evaluate(f"() => {{ {js_code} }}")
                        
                        popup = popup_info.value
                        popup.wait_for_load_state()
                        
                        # Wait for the table to render in the popup
                        try:
                            popup.locator("table").wait_for(timeout=5000)
                        except:
                            pass
                            
                        popup_html = popup.content()
                        subject["day_wise"] = self._parse_day_wise_html(popup_html)
                        popup.close()
                    except Exception as e:
                        print(f"Failed to scrape day-wise for {subject['subject']}: {e}")
                        subject["day_wise"] = []
                else:
                    subject["day_wise"] = []
                
            self.cached_analysis = self._compute_full_analysis(attendance_data)
            return {"success": True, "message": "Attendance data synced!"}
            
        except Exception as e:
             return {"success": False, "message": str(e)}
        finally:
             context.close()
             if session_id in active_sessions:
                 del active_sessions[session_id]

    def _parse_attendance_html(self, html_content):
        soup = BeautifulSoup(html_content, 'html.parser')
        target_table = None
        for table in soup.find_all('table'):
            if "Total Classes" in table.text:
                target_table = table
                break
                
        if not target_table:
            return []
            
        headers = []
        rows = target_table.find_all('tr')
        header_row = None
        for row in rows:
            if 'Days' in row.text:
                header_row = row
                break
                
        if not header_row:
             return []
             
        cols = header_row.find_all(['th', 'td'])
        for col in cols:
             text = col.get_text(strip=True)
             if text and text != 'Days':
                  headers.append(text)
                  
        totals = {}
        for row in reversed(rows): # Read from bottom up
            tds = row.find_all('td')
            if not tds:
                continue
            
            label = tds[0].get_text(strip=True)
            if 'Total Classes' in label:
                totals['Total'] = [td.get_text(strip=True) for td in tds[1:]]
            elif 'Total Absent' in label:
                totals['Absent'] = [td.get_text(strip=True) for td in tds[1:]]
            elif 'Total Present' in label:
                totals['Present'] = [td.get_text(strip=True) for td in tds[1:]]
                
                # Extract popup links for day-wise details
                totals['PresentLinks'] = []
                for td in tds[1:]:
                    a_tag = td.find('a')
                    if a_tag and a_tag.has_attr('href'):
                        totals['PresentLinks'].append(a_tag['href'])
                    else:
                        totals['PresentLinks'].append(None)
                
            if 'Total Classes' in totals and 'Total Absent' in totals and 'Total Present' in totals:
                break
                
        analysis = []
        for i, subject in enumerate(headers):
            try:
                if i >= len(totals.get('Total', [])) or i >= len(totals.get('Present', [])):
                    continue
                total_classes = int(totals['Total'][i])
                total_present = int(totals['Present'][i])
                percentage = round((total_present / total_classes * 100), 2) if total_classes > 0 else 0
                
                link = None
                if 'PresentLinks' in totals and i < len(totals['PresentLinks']):
                    link = totals['PresentLinks'][i]
                
                analysis.append({
                    "subject": subject,
                    "attended": total_present,
                    "total": total_classes,
                    "percentage": percentage,
                    "details_link": link
                })
            except (ValueError, IndexError):
                pass
                
        return analysis

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

    def _compute_full_analysis(self, attendance_data):
        analysis = []
        for subject in attendance_data:
            prediction_75 = self.get_leave_prediction(subject, threshold=75.0)
            prediction_65 = self.get_leave_prediction(subject, threshold=65.0)
            
            subject_analysis = {
                **subject,
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
            analysis.append(subject_analysis)
        return analysis

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
                    "message": f"Exactly at {threshold}%! You cannot skip any class without dropping below {threshold}%."
                }
            return {
                "status": "safe", 
                "skippable_classes": skippable,
                "message": f"You can skip {skippable} more class(es) before dropping below {threshold}%."
            }
        else:
            needed = math.ceil((threshold_decimal * total - attended) / (1 - threshold_decimal))
            return {
                "status": "danger",
                "needed_classes": needed,
                "message": f"Below {threshold}%! You must attend {needed} more class(es) to reach {threshold}%."
            }

    def get_full_analysis(self):
        if self.cached_analysis:
            return self.cached_analysis
        return []

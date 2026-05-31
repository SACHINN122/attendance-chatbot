# Kairon System Design & Workflow

## 🎯 Philosophy: Why CAPTCHA Matters (& Why We Can't Avoid It)

### The Trade-off: Security vs. Seamlessness

You want **"smoothless" (seamless)** attendance access. Here's why CAPTCHA is necessary:

```
┌─────────────────────────────────────────────────────────────────┐
│ Option A: Automated Login (No CAPTCHA)                          │
├─────────────────────────────────────────────────────────────────┤
│ ✓ Super fast (1 second)                                         │
│ ✓ Completely automated                                          │
│ ✗ NSUT would BLOCK our IP after 5-10 requests                   │
│ ✗ Rate-limiting triggers → app becomes unusable for everyone    │
│ ✗ Violates NSUT's Terms of Service                              │
│ ✗ Your account could get LOCKED                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Option B: CAPTCHA Required (Our Choice)                         │
├─────────────────────────────────────────────────────────────────┤
│ ✓ Only 1 CAPTCHA per session (5-min cache = repeat logins OK)   │
│ ✓ Proves it's a real user (avoids IP bans)                      │
│ ✓ NSUT allows it (respects their security)                      │
│ ✓ Account stays safe                                            │
│ ~ 5-10 second overhead (worth the security)                     │
└─────────────────────────────────────────────────────────────────┘
```

### How We Made It "As Seamless as Possible"

1. **User solves CAPTCHA ONCE per session** → data cached for 5 minutes
2. **Future logins check cache first** → skip CAPTCHA if data still fresh
3. **Frontend displays CAPTCHA inline** (not a popup) → integrated experience
4. **Auto-load from cache** if available → often instant access

### The Goal

```
First Login:    [Roll] [Pwd] [CAPTCHA] → 10 seconds → ✓ Access for 5 min
Second Login:   [Roll] [Pwd]           → 1 second   → ✓ From cache
(within 5 min)  (no CAPTCHA needed)
```

---

## 🔄 Complete Request Lifecycle: "Connect to Portal" Click

### Step 1: User Clicks "Connect to Portal"

```
Frontend receives: {rollno, password, semester}
                    ↓
          POST /api/login
                    ↓
         Backend Flask receives request
```

### Step 2-5: Backend Initiates Scraper

```mermaid
sequenceDiagram
    actor User
    participant Frontend as 🎨 Frontend<br/>index.html
    participant API as 🔌 Flask API<br/>/api/login
    participant SessionMgr as 📦 Session<br/>Manager
    participant Scraper as 🕷️ Scraper<br/>scraper.py
    participant Browser as 🌐 Chromium<br/>Browser
    participant Portal as 🏫 NSUT Portal<br/>imsnsit.org

    User->>Frontend: Enters Roll#, Password<br/>Clicks "Connect"
    Note over Frontend: Validates input<br/>Sends POST

    Frontend->>API: POST /api/login<br/>{rollno, password, semester}
    Note over API: Checks cache first<br/>rollno in /backend/data/?

    API->>SessionMgr: Create new UUID<br/>session_id

    API->>Scraper: AttendanceScraper()<br/>.start_login(rollno, pwd, sem)
    Note over Scraper: Non-mock mode

    Scraper->>Browser: get_browser()<br/>→ launch Chromium
    Note over Browser: First time?<br/>Takes 2-3 sec

    Browser->>Portal: Navigate to<br/>https://imsnsit.org/imsnsit/
    Note over Portal: Portal loads<br/>with frames
```

### Step 3: Scraper Fills Login Form & Captures CAPTCHA

```mermaid
sequenceDiagram
    participant Browser as 🌐 Browser
    participant Portal as 🏫 Portal
    participant Scraper as 🕷️ Scraper
    participant API as 🔌 API

    Browser->>Browser: Wait 2 sec for<br/>frames to load

    Scraper->>Browser: Search all frames<br/>for "Student Login" link
    Browser->>Portal: Click "Student Login"

    Scraper->>Browser: Search frames for<br/>login form<br/>(uid, pwd inputs)
    Note over Browser: Loops 120 times<br/>(up to 2 min)

    Browser->>Browser: Find login form<br/>in banner frame

    Scraper->>Browser: Force-fill uid & pwd<br/>(ignores visibility)
    Browser->>Portal: Credentials sent to<br/>form (not submitted yet!)

    Scraper->>Browser: Screenshot CAPTCHA<br/>img#captchaimg
    Browser->>Browser: Base64 encode PNG

    Scraper->>API: Return {success, session_id,<br/>captcha_base64}

    API->>Frontend: Send CAPTCHA image
    Note over Frontend: CORS-enabled<br/>response
```

### Step 4: Frontend Displays CAPTCHA & Waits for User

```html
<!-- What user sees -->
<img src="data:image/png;base64,..." alt="CAPTCHA" style="width:200px; height:60px;">
<input type="text" id="captcha-input" placeholder="Enter CAPTCHA text">
<button onclick="submitCaptcha()">Submit</button>
```

### Step 5: User Solves & Submits CAPTCHA

```mermaid
sequenceDiagram
    actor User
    participant Frontend as 🎨 Frontend
    participant API as 🔌 API
    participant Scraper as 🕷️ Scraper
    participant Portal as 🏫 Portal

    User->>Frontend: Reads CAPTCHA<br/>Enters solution
    Frontend->>Frontend: onclick="submitCaptcha()"

    Frontend->>API: POST /api/captcha<br/>{session_id, captcha: "ABC123"}
    Note over API: Retrieve stored<br/>browser context

    API->>Scraper: submit_captcha_and_scrape()<br/>(captcha_text)

    Scraper->>Portal: Fill captcha input<br/>Click Login button
    Portal->>Portal: CAPTCHA validation<br/>in backend
    
    alt Captcha Correct
        Portal->>Scraper: Redirect to dashboard
        Note over Scraper: Login successful!
    else Captcha Wrong
        Portal->>Scraper: Return error<br/>"Incorrect CAPTCHA"
        Scraper->>API: Return {success: false}
        API->>Frontend: Display error
        Frontend->>User: ❌ "Try again"
    end
```

### Step 6: Deep Scrape - Navigate to "My Attendance"

```mermaid
sequenceDiagram
    participant Scraper as 🕷️ Scraper
    participant Browser as 🌐 Browser
    participant Portal as 🏫 Portal
    participant Parser as 📄 BeautifulSoup

    Scraper->>Browser: Page loaded on dashboard
    Note over Browser: Frame structure:<br/>- banner frame<br/>- data frame<br/>- menu (hidden CSS)

    Scraper->>Browser: Get HTML from all frames
    Browser->>Parser: Parse with BeautifulSoup

    Parser->>Parser: Search for<br/>"My Attendance" link
    Note over Parser: Link may be hidden<br/>via CSS display:none<br/>Must parse raw HTML!

    alt Link Found
        Parser->>Scraper: href = "/path/to/attendance"
        Scraper->>Browser: Navigate data frame<br/>to attendance URL
        Browser->>Portal: GET attendance form
    else Link NOT Found (ERROR)
        Scraper->>Scraper: ❌ "Could not find<br/>My Attendance link"
        Note over Scraper: Save debug screenshot<br/>Log all frames checked
    end

    Portal->>Browser: Load attendance form<br/>Year/Semester dropdowns
```

### Step 7: Select Year & Semester, Submit

```mermaid
sequenceDiagram
    participant Browser as 🌐 Browser
    participant Portal as 🏫 Portal
    participant Scraper as 🕷️ Scraper

    Scraper->>Browser: Find select[name='year']
    Note over Browser: Search all frames
    
    Scraper->>Browser: .select_option("2025-26")
    Browser->>Portal: Send year selection

    Scraper->>Browser: .select_option("4")<br/>(semester)
    Browser->>Portal: Send semester selection

    Scraper->>Browser: Click Submit button
    Browser->>Portal: Form submits

    Portal->>Browser: Process request
    Note over Portal: Database query<br/>for semester 4<br/>year 2025-26
```

### Step 8: Parse Attendance Table

```mermaid
sequenceDiagram
    participant Portal as 🏫 Portal
    participant Browser as 🌐 Browser
    participant Scraper as 🕷️ Scraper
    participant Parser as 📄 BeautifulSoup
    participant Cache as 💾 Cache

    Portal->>Browser: Return attendance table<br/>HTML with all subjects

    Scraper->>Browser: .inner_html() of table
    Note over Browser: Wait for table<br/>(up to 15 seconds)

    Browser->>Parser: HTML content

    Parser->>Parser: Extract table rows:<br/>- Headers (subject names)<br/>- Total Classes<br/>- Total Present<br/>- Total Absent

    Parser->>Parser: Calculate %<br/>= Present / Total * 100

    Parser->>Scraper: {<br/>  subject: "Mathematics",<br/>  attended: 24,<br/>  total: 29,<br/>  percentage: 82.76<br/>}

    Scraper->>Scraper: For EACH subject:<br/>Click "Details" popup<br/>→ Day-wise data
```

### Step 9: Deep Scrape - Day-Wise Attendance

```mermaid
sequenceDiagram
    participant Scraper as 🕷️ Scraper
    participant Browser as 🌐 Browser
    participant Portal as 🏫 Portal
    participant Parser as 📄 Parser

    loop For Each Subject
        Scraper->>Browser: Extract popup link<br/>from subject row
        Note over Browser: Links like:<br/>JavaScript:newPopup(...)

        Scraper->>Browser: Execute JS:<br/>newPopup(subj_id)

        Portal->>Browser: Popup window opens<br/>with day-wise table

        Browser->>Parser: Parse popup HTML
        Parser->>Parser: Extract rows:<br/>Date | Status<br/>2025-01-15 | Present<br/>2025-01-16 | Absent<br/>...

        Parser->>Scraper: day_wise array

        Scraper->>Browser: popup.close()
    end

    Note over Scraper: All subjects done!<br/>Ready to compute analysis
```

### Step 10: Compute Analysis & Cache

```mermaid
sequenceDiagram
    participant Scraper as 🕷️ Scraper
    participant Analyzer as 🧮 Analyzer
    participant Cache as 💾 Cache
    participant API as 🔌 API
    participant Frontend as 🎨 Frontend

    Scraper->>Analyzer: _compute_full_analysis()<br/>(attendance_data)

    Analyzer->>Analyzer: For EACH subject:<br/>- Attendance %<br/>- Leave prediction @75%<br/>- Leave prediction @65%<br/>- Day-wise breakdown

    Note over Analyzer: Threshold logic:<br/>If % >= 75%: SAFE<br/>  Can skip N classes<br/>If % < 75%: DANGER<br/>  Need to attend M more

    Analyzer->>Scraper: Full analysis JSON

    Scraper->>Cache: Save to<br/>backend/data/&lt;roll_no&gt;.json

    Scraper->>API: {success: true,<br/>message: "Data synced!"}

    API->>Frontend: ✓ Login complete!

    Frontend->>Frontend: Hide captcha<br/>Show chat interface

    Frontend->>API: POST /api/chat<br/>{session_id, message: "hi"}

    Note over Frontend: User can now ask:<br/>"hi" / "sw" / "danger" /<br/>"safe" / "subject_name"
```

---

## 💾 Data Structure: What Gets Saved

### Raw Attendance Object (Per Subject)

```json
{
  "subject": "Data Structures",
  "attended": 18,
  "total": 22,
  "percentage": 81.82,
  "day_wise": [
    {"date": "2025-01-15", "status": "Present"},
    {"date": "2025-01-16", "status": "Absent"},
    {"date": "2025-01-17", "status": "Present"}
  ],
  "status_75": "safe",
  "message_75": "You can skip 0 more class(es) before dropping below 75%.",
  "skippable_75": 0,
  "needed_75": 0,
  "status_65": "safe",
  "message_65": "You can skip 4 more class(es) before dropping below 65%.",
  "skippable_65": 4,
  "needed_65": 0,
  "status": "safe",
  "message": "You can skip 0 more class(es) before dropping below 75%."
}
```

### Cached File Location

```
backend/data/
├── <roll_no>.json
├── <another_roll_no>.json
└── <third_roll_no>.json
```

**Each file contains:** Array of subject objects with full analysis.

---

## 🤖 Chatbot Processing Pipeline

### When User Types "HI"

```mermaid
graph TD
    A["User: 'hi'"] -->|POST /api/chat| B["Flask receives"]
    B --> C["Retrieve session"]
    C --> D["Get ChatbotEngine"]
    D --> E["chatbot.process_message"]
    E --> F["Check message.lower()"]
    
    F -->|'hi'| G["Build 75% table"]
    G --> H["Iterate subjects"]
    H --> I["Format with emoji +<br/>percentage + skip/need info"]
    I --> J["Build 65% table"]
    J --> K["Combine both"]
    K --> L["Add hint:<br/>'Type SW for...'"]
    L --> M["Return markdown"]
    
    M --> N["Frontend receives"]
    N --> O["Render markdown<br/>with colors + icons"]
    O --> P["Display to user"]
```

### When User Types "DANGER"

```mermaid
graph TD
    A["User: 'danger'"] --> B["Filter subjects"]
    B --> C["Where status_75 == 'danger'"]
    C --> D["For each dangerous subject:"]
    D --> E["Show 🔴 + name + %"]
    E --> F["Show message_75"]
    F --> G["'Need to attend X more'"]
    G --> H["Return formatted list"]
    H --> I["Frontend displays"]
```

### When User Types "SW" (Subject-Wise)

```mermaid
graph TD
    A["User: 'sw'"] --> B["State = 'waiting_for_subject_number'"]
    B --> C["Build subject list with numbers"]
    C --> D["1. Mathematics<br/>2. Physics<br/>3. Chemistry"]
    D --> E["Return numbered list"]
    E --> F["User: '1'"]
    F --> G["State = 'idle'"]
    G --> H["subject_map[1] = Mathematics obj"]
    H --> I["subjects['day_wise'] available?"]
    
    I -->|Yes| J["Build table:<br/>Date | Status"]
    I -->|No| K["'No day-wise data<br/>available'"]
    
    J --> L["Show ✅ Present / 🔴 Absent"]
    L --> M["Return to user"]
```

---

## ⚠️ Error Handling & Frame Detachment

### Why Frame Detachment Happens

```mermaid
sequenceDiagram
    participant Scraper as 🕷️ Scraper
    participant Browser as 🌐 Browser
    participant Portal as 🏫 Portal

    Scraper->>Browser: frame.content() ← Reads frame HTML
    Browser->>Portal: Sends request

    Portal->>Browser: ⚠️ Page navigates<br/>Frame reference broken!

    Scraper->>Browser: frame.content() ← ERROR!<br/>"Frame was detached"

    Note over Scraper: Frame object is now<br/>dead reference
```

### Solution: Refresh Frame List

```mermaid
graph TD
    A["Loop: for attempt in range(30)"] --> B["page.frames"]
    B --> C["Fresh snapshot<br/>of live frames"]
    C --> D["Search new list<br/>for expected element"]
    D --> E["Found?"]
    
    E -->|Yes| F["Use frame"]
    E -->|No| G["time.sleep 1"]
    G --> H["Retry - get fresh<br/>frame list again"]
```

---

## 📊 Session Lifecycle & Memory

### Active Sessions Dictionary

```python
active_sessions = {
    "uuid-1": {
        "context": BrowserContext,      # Playwright context
        "page": Page,                   # Main page object
        "login_frame": Frame,           # Cached login frame
        "semester": "4",
        "timestamp": 1715000000.0       # When created
    },
    "uuid-2": { ... }
}
```

### Cleanup Logic (Every 5 Minutes)

```mermaid
graph TD
    A["Check all sessions"] --> B["current_time - timestamp<br/>> 300 seconds?"]
    B -->|Yes| C["Session expired"]
    C --> D["context.close()"]
    D --> E["del active_sessions[id]"]
    E --> F["Free memory"]
    
    B -->|No| G["Keep session alive"]
    G --> H["Can still use"]
```

---

## 🔒 Security Measures

| Layer | Protection |
|:---|:---|
| **Credentials** | Stored in `.env` (NOT in code, NOT in git) |
| **Session IDs** | UUID v4 (cryptographically random) |
| **CAPTCHA** | Proves human user (prevents automated attacks) |
| **Cache** | 5-minute TTL (stale data auto-discarded) |
| **CORS** | Flask-CORS enabled (only same-origin requests) |
| **Frame Lifecycle** | Closed on error or timeout (prevents memory leaks) |
| **Logging** | Sensitive data NOT logged (no passwords/IPs in logs) |

---

## 🚀 Performance Metrics

| Operation | Time | Notes |
|:---|:---|:---|
| Launch browser | 2-3s | First time only |
| Navigate to portal | 1-2s | Network dependent |
| Fill credentials | 0.5s | Immediate |
| Capture CAPTCHA | 0.2s | Screenshot |
| User solves CAPTCHA | 10-30s | **User action** |
| Submit & validate | 2-3s | Portal backend |
| Parse attendance table | 1-2s | BeautifulSoup |
| Deep scrape (day-wise) | 5-10s | Multiple popups |
| **Total first login** | **25-55s** | Mostly waiting on user |
| **Cache hit (2nd login)** | **1-2s** | Instant! |

---

## 🎓 Learning Path: Understanding the Flow

1. **Start here:** README.md (setup & API overview)
2. **Understand architecture:** ARCHITECTURE.md (system design)
3. **Deep dive:** This file (workflow & data structures)
4. **Debug issues:** Check logs + compare frames
5. **Extend:** Add features to ChatbotEngine or Scraper

---

## 💡 FAQ: Frame Detachment & Portal Changes

**Q: Why does frame.content() sometimes fail?**  
A: Portal navigates to new page → old frame reference invalidates → "Frame was detached". **Solution:** Refresh frame list on every loop iteration.

**Q: Could the "My Attendance" link disappear?**  
A: Yes, if NSUT changes their portal HTML structure. **Solution:** Update the search logic in `scraper.py:_parse_attendance_html()` to look for new link patterns.

**Q: Can I use this without CAPTCHA?**  
A: Not reliably. NSUT rate-limits/blocks automated logins. **Workaround:** Use mock mode for testing (`use_mock=True`).

**Q: How long does cache persist?**  
A: 5 minutes per session. After that, user must re-login. **Rationale:** Attendance updates infrequently; 5 min is safe refresh window.

---

## 📚 Related Documentation

- **README.md** → Setup & endpoints
- **ARCHITECTURE.md** → System diagrams
- **backend/app.py** → Route handlers
- **backend/scraper.py** → Scraping logic
- **backend/chatbot.py** → Q&A logic
- **backend/logging_config.py** → Request logging

---

## 🎯 Next Steps for Enhancement

**To make it MORE seamless:**

1. **Auto-retry on frame detach** ✅ (Already implemented)
2. **Improve frame detection** ✅ (Better error messages)
3. **Add SMS CAPTCHA support** ❌ (Portal doesn't offer)
4. **Cache across days** ❌ (Data stale)
5. **Browser automation bypass** ❌ (Violates NSUT ToS)

**The CAPTCHA is NOT a limitation—it's a feature.** It's what keeps the app safe, legal, and sustainable.

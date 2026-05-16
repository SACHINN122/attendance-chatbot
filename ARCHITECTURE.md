# Architecture & Data Flow Diagrams

## Complete System Architecture

```mermaid
graph TB
    User["👤 User Browser<br/>http://127.0.0.1:5000"]
    Frontend["🎨 Frontend<br/>HTML/CSS/JS"]
    FlaskAPI["🔌 Flask Backend<br/>app.py"]
    SessionMgr["📦 Session Manager<br/>user_sessions dict"]
    Cache["💾 Cache<br/>backend/data/"]
    
    Scraper["🕷️ AttendanceScraper<br/>scraper.py"]
    Chatbot["🤖 ChatbotEngine<br/>chatbot.py"]
    PlaywrightMgr["⚙️ Playwright Manager<br/>playwright_manager.py"]
    Browser["🌐 Chromium Browser"]
    Portal["🏫 NSUT Portal<br/>imsnsit.org"]
    
    User -->|Visits| Frontend
    Frontend -->|POST /api/login| FlaskAPI
    FlaskAPI -->|Create| SessionMgr
    FlaskAPI -->|Check| Cache
    FlaskAPI -->|Scraper Init| Scraper
    Scraper -->|Get Browser| PlaywrightMgr
    PlaywrightMgr -->|Launch| Browser
    Browser -->|Navigate| Portal
    Portal -->|Captcha Image| Browser
    Browser -->|Screenshot| Scraper
    Scraper -->|Return to API| FlaskAPI
    FlaskAPI -->|Send to Frontend| Frontend
    Frontend -->|User Solves| Frontend
    Frontend -->|POST /api/captcha| FlaskAPI
    FlaskAPI -->|Submit| Scraper
    Scraper -->|Query| Portal
    Scraper -->|Parse HTML| Scraper
    Scraper -->|Cache Result| Cache
    FlaskAPI -->|Create| Chatbot
    Frontend -->|POST /api/chat| FlaskAPI
    FlaskAPI -->|Process| Chatbot
    Chatbot -->|Query Analysis| Scraper
    Chatbot -->|Reply| FlaskAPI
    FlaskAPI -->|Display| Frontend
```

## Request Flow: Login with Captcha

```mermaid
sequenceDiagram
    participant User as 👤 User
    participant Frontend as 🎨 Frontend (JS)
    participant API as 🔌 Flask API
    participant Scraper as 🕷️ Scraper
    participant Browser as 🌐 Browser
    participant Portal as 🏫 NSUT Portal

    User->>Frontend: Enter Roll #, Password
    Frontend->>API: POST /api/login<br/>(rollno, password)
    API->>Scraper: AttendanceScraper.start_login()
    Scraper->>Browser: Launch Chromium
    Browser->>Portal: Navigate to imsnsit.org
    Portal->>Browser: Return page + frames
    Browser->>Browser: Find login form in frame
    Browser->>Portal: Fill credentials (uid, pwd)
    Portal->>Browser: Return with CAPTCHA image
    Browser->>Scraper: Screenshot captcha
    Scraper->>API: Return base64 image
    API->>Frontend: Display CAPTCHA to user
    
    User->>Frontend: Solve & enter CAPTCHA text
    Frontend->>API: POST /api/captcha<br/>(session_id, captcha_text)
    API->>Scraper: submit_captcha_and_scrape()
    Scraper->>Portal: Submit captcha + login
    Portal->>Browser: Redirect to dashboard
    Scraper->>Portal: Navigate to "My Attendance"
    Portal->>Browser: Load attendance form
    Browser->>Browser: Find year/semester dropdowns
    Scraper->>Portal: Select year, semester, submit
    Portal->>Browser: Return attendance table (HTML)
    Scraper->>Scraper: Parse table → Extract subjects
    Scraper->>Scraper: For each subject, click popup
    Portal->>Browser: Day-wise attendance popup
    Scraper->>Scraper: Parse day-wise data
    Scraper->>API: Analysis complete
    API->>Cache: Save to cache JSON
    API->>Frontend: Success message
    Frontend->>User: ✓ Ready for chat!
```

## Request Flow: Chat Query

```mermaid
sequenceDiagram
    participant User as 👤 User
    participant Frontend as 🎨 Frontend
    participant API as 🔌 API
    participant Chatbot as 🤖 Chatbot
    participant Scraper as 🕷️ Scraper
    participant Frontend2 as 🎨 Display

    User->>Frontend: Type "HI" or "danger"
    Frontend->>API: POST /api/chat<br/>(session_id, message)
    API->>Chatbot: process_message(user_input)
    Chatbot->>Scraper: get_full_analysis()
    Scraper->>Chatbot: Return attendance data
    Chatbot->>Chatbot: Parse query & format response
    Chatbot->>API: Return formatted reply
    API->>Frontend: JSON reply
    Frontend2->>User: Display formatted markdown
```

## Session Lifecycle

```mermaid
stateDiagram-v2
    [*] --> NoSession: User arrives
    
    NoSession --> LoginInProgress: User submits roll/password
    LoginInProgress --> CaptchaWaiting: Captcha image returned
    
    CaptchaWaiting --> ScrapingInProgress: User solves & submits
    CaptchaWaiting --> Expired: 5 min timeout
    
    ScrapingInProgress --> Active: Data fetched & cached
    ScrapingInProgress --> Failed: Scraping failed
    
    Failed --> [*]: Redirect to login
    
    Active --> Chatting: User can now chat
    Chatting --> Chatting: Exchange messages
    
    Chatting --> Expired: 5 min inactivity
    Expired --> [*]: Session cleaned up
    
    Active --> [*]: User logs out
    Chatting --> [*]: User logs out
```

## Module Dependencies

```mermaid
graph LR
    app["<b>app.py</b><br/>Flask routes"]
    logging_config["logging_config.py<br/>Request logging"]
    scraper["scraper.py<br/>Web scraping"]
    chatbot["chatbot.py<br/>Q&A engine"]
    pw_mgr["playwright_manager.py<br/>Browser control"]
    
    app -->|Setup| logging_config
    app -->|Create| scraper
    app -->|Create| chatbot
    scraper -->|Get browser| pw_mgr
    chatbot -->|Query| scraper
```

## Data Flow: Attendance Data Processing

```mermaid
graph TD
    A["HTML Page<br/>attendance table"] -->|BeautifulSoup parse| B["Extract rows:<br/>Subject, Total, Present, Absent"]
    B -->|Calculate| C["Attendance %<br/>= Present / Total"]
    C -->|Threshold logic| D["Leave prediction<br/>@75% & @65%"]
    D -->|For each subject| E["Query popup<br/>day-wise data"]
    E -->|Parse dates| F["List: Date + Status<br/>Present/Absent per day"]
    F -->|Combine| G["Full analysis JSON<br/>subject_analysis[]"]
    G -->|Cache to disk| H["backend/data/<br/>rollno.json"]
    G -->|Return to chatbot| I["ChatbotEngine<br/>processes queries"]
    I -->|Format reply| J["Markdown output<br/>to user"]
```

## Caching Strategy

```mermaid
graph LR
    CheckCache["User login"] -->|Check cache| CacheExists{"Cache file<br/>exists?"}
    CacheExists -->|Yes| LoadCache["Load from<br/>backend/data/"]
    CacheExists -->|No| FreshScrape["Full scrape<br/>+ CAPTCHA"]
    LoadCache --> CreateSession["Create new<br/>session"]
    FreshScrape --> SaveCache["Save to<br/>backend/data/"]
    SaveCache --> CreateSession
    CreateSession --> Ready["✓ Ready<br/>for chat"]
```

## Error Handling Flow

```mermaid
graph TD
    Try["Execute endpoint<br/>or scraper"] -->|Catch exception| Error["Log error<br/>with details"]
    Error -->|Type: CAPTCHA| E1["Return 401:<br/>Captcha mismatch"]
    Error -->|Type: Frame not found| E2["Return 400:<br/>Portal structure<br/>changed"]
    Error -->|Type: Session invalid| E3["Return 401:<br/>Session expired"]
    Error -->|Type: Generic| E4["Return 500:<br/>Server error"]
    E1 --> User["User sees<br/>error message"]
    E2 --> User
    E3 --> User
    E4 --> User
```

## Technology Stack

| Layer | Component | Technology |
|:---:|:---:|:---:|
| **Frontend** | UI/UX | HTML5, CSS3, Vanilla JavaScript |
| | Styling | Glassmorphism CSS |
| **Backend** | Framework | Flask 3.1.3 |
| | CORS | flask-cors 6.0.2 |
| **Scraping** | Automation | Playwright 1.59.0 (Chromium) |
| | HTML Parsing | BeautifulSoup4 4.14.3 |
| | Web Requests | requests 2.34.2 |
| **Utilities** | Logging | Python logging |
| | Configuration | Python dotenv (via .env) |
| **Deployment** | Server | Gunicorn (production) |
| | Platform | Render, Heroku, AWS, etc. |

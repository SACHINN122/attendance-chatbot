# Attendance Assistant Session Flow

This document explains what happens when a student logs in, what is cached, and when portal changes become visible in the assistant.

## Login And Sync Flow

```mermaid
sequenceDiagram
    autonumber
    participant User as "Student browser"
    participant UI as "Frontend"
    participant API as "Flask backend"
    participant Scraper as "Playwright scraper"
    participant Portal as "IMS NSUT portal"
    participant Cache as "Local cache"

    User->>UI: "Open app"
    UI->>API: "GET /api/config"
    API-->>UI: "default roll, cache status, saved-password flag"
    UI->>API: "POST /api/check_cache"
    API->>Cache: "Read backend/data/<roll>.json"
    alt "Cache exists"
        Cache-->>API: "analysis payload"
        API-->>UI: "Cached dashboard + chat session"
    else "No cache or user chooses fresh login"
        User->>UI: "Enter roll/password"
        UI->>API: "POST /api/login"
        API->>Scraper: "Start browser context"
        Scraper->>Portal: "Open student login and fill credentials"
        Portal-->>Scraper: "CAPTCHA image"
        Scraper-->>API: "session_id + CAPTCHA"
        API-->>UI: "Show CAPTCHA"
        User->>UI: "Enter CAPTCHA"
        UI->>API: "POST /api/captcha"
        API->>Scraper: "Submit CAPTCHA"
        Scraper->>Portal: "Authenticated session"
        Scraper->>Portal: "Read menu/profile/course/timetable surfaces"
        Scraper->>Portal: "Open My Attendance"
        Scraper->>Portal: "Submit available year/semester filters"
        Portal-->>Scraper: "Attendance tables"
        Scraper->>Scraper: "Parse profile, photo, subjects, day-wise marks"
        Scraper-->>API: "schema_version 2 analysis"
        API->>Cache: "Save latest analysis"
        API-->>UI: "Dashboard + chat session"
    end
```

## What Happens When Portal Data Changes

The assistant does not automatically poll the portal in the background. On app open, it loads the local cache first because that is fast and avoids asking CAPTCHA every time.

```mermaid
flowchart TD
    A["Portal attendance changes"] --> B{"Is the app already using cached data?"}
    B -->|Yes| C["Dashboard still shows old cached values"]
    C --> D["Student performs fresh login + CAPTCHA"]
    D --> E["Scraper reads portal again"]
    E --> F["Local cache is overwritten with latest analysis"]
    B -->|No, fresh sync running| G["New portal values are parsed immediately"]
    G --> F
    F --> H["Dashboard, charts, filters, and chatbot use new payload"]
```

Important behavior:

- **Logout** in the UI only leaves the current assistant session and returns to the login screen.
- **Logout does not delete the local cache.**
- If portal data changes after the cache was created, the app needs a **fresh login + CAPTCHA** to refresh the cache.
- Fresh sync tries all available semester options by default, tags each subject with its semester, and then the dashboard semester filter reads those tags.
- Set `ATTENDANCE_SYNC_ALL_SEMESTERS=0` only if you want the old first-working-semester behavior for faster testing.
- If login succeeds but the portal returns an empty attendance report, the app now keeps the user inside the assistant and loads the last valid cache with a live-sync warning.
- CAPTCHA sessions expire quickly. If CAPTCHA is old, use refresh and submit the new image.

## Cached Payload Shape

```mermaid
erDiagram
    ANALYSIS ||--|| STUDENT : contains
    ANALYSIS ||--o{ SUBJECT : tracks
    SUBJECT ||--o{ DAY_MARK : has
    SUBJECT ||--o{ SPECIAL_EVENT : has
    ANALYSIS ||--|| INSIGHTS : computes
    ANALYSIS ||--|| PORTAL : maps
    PORTAL ||--o{ PORTAL_LINK : lists
    PORTAL ||--o{ PORTAL_TABLE : captures

    STUDENT {
        string name
        string rollno
        string student_id
        string degree
        string department
        string semester
        string academic_year
        boolean photo_available
        string photo_data_url
    }

    SUBJECT {
        string code
        string subject
        number attended
        number total
        number absent
        number percentage
        string status_75
        number skippable_75
        number needed_75
        string status_65
        number skippable_65
        number needed_65
    }

    DAY_MARK {
        string date
        string label
        string raw
        number present_count
        number absent_count
        number special_count
        number class_count
        string status
    }

    SPECIAL_EVENT {
        string date
        string code
        string mark
        string description
    }

    INSIGHTS {
        number subject_count
        number total_classes
        number total_attended
        number total_absent
        number overall_percentage
        number total_skippable_75
        number risky_subject_count
    }

    PORTAL_LINK {
        string section
        string text
        string target
    }

    PORTAL_TABLE {
        string surface
        string title
        array columns
        array rows
        number row_count
    }
```

## Portal Data Currently Used

| Portal area | What the assistant reads | Where it is used |
|:---|:---|:---|
| Login banner | Welcome name and student photo signal | Header, profile panel, chat `PROFILE` |
| Attendance form | Roll number, degree, department, academic year, semester | Profile panel, source metadata |
| Attendance tables | Subject codes, subject names, semester tags, monthly/day-wise marks, totals | Charts, tables, filters, chatbot |
| Attendance legend | GH, TL, CS, MB, MS, OD, NT and similar marks | Calendar/special event analysis |
| My Activities menu | Available portal sections and links | `WEBSITE`, portal surfaces panel |
| ID Card Details | Student/profile key-value fields when page loads | Profile panel and chat `PROFILE` |
| Current Sem Courses Registered | Course table when page loads | Captured portal tables |
| My Timetable | Timetable table when page loads | Captured portal tables |

## Attendance Table Columns

```mermaid
flowchart LR
    A["Portal monthly attendance table"] --> B["Days column"]
    A --> C["Subject code columns"]
    C --> D["Raw mark: 1, 0, 1+1, 0+0, GH, TL, CS, MB, MS"]
    D --> E["present_count"]
    D --> F["absent_count"]
    D --> G["special_codes"]
    E --> H["Subject totals"]
    F --> H
    G --> I["Calendar events"]
    H --> J["Percentage, safe skips, risk status"]
```

Meaning of common marks:

| Mark | Meaning |
|:---|:---|
| `1` | Present |
| `0` | Absent |
| `1+1` | Multiple present periods on the same day |
| `0+0` | Multiple absent periods on the same day |
| `GH` | Gazetted holiday |
| `TL` | Teacher leave |
| `CS` | Class suspended officially |
| `MB` | Mass bunk |
| `MS` | Mid-sem exam |
| `OD` | Teacher on official duty |
| `NT` | Class not taken |
| `NA` | Timetable not allotted |

## UI Behavior

```mermaid
flowchart TD
    A["Analysis payload"] --> B["Profile panel"]
    A --> C["Metric cards"]
    A --> D["Subject percentage chart"]
    A --> E["Cumulative attendance line chart"]
    A --> F["Filterable semester/subject table"]
    A --> G["Portal surfaces panel"]
    A --> H["Chatbot commands"]

    H --> I["HI summary"]
    H --> J["TOTAL overall count"]
    H --> K["ABSENT date/table view"]
    H --> L["SAFE skip buffer"]
    H --> M["RISK weak subjects"]
    H --> N["PROFILE student fields"]
    H --> O["WEBSITE portal menu"]
```

The charts and filters are frontend-only views of the same analysis payload. They do not change portal data; they only help the student inspect it faster.

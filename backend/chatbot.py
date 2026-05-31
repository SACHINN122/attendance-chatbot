class ChatbotEngine:
    def __init__(self, scraper):
        self.scraper = scraper
        self.state = "idle"
        self.subject_map = {}

    def _payload(self):
        data = self.scraper.get_full_analysis()
        if isinstance(data, list):
            return {
                "schema_version": 1,
                "student": {},
                "attendance": data,
                "insights": self._legacy_insights(data),
                "portal": {},
                "source": {
                    "cache_schema_version": 1,
                    "legacy_cache": True,
                    "note": "This cache was created before v2 day-wise portal extraction.",
                },
            }
        return data or {
            "student": {},
            "attendance": [],
            "insights": {},
            "portal": {},
            "source": {},
        }

    def analysis_payload(self):
        return self._payload()

    def _subjects(self, payload=None):
        payload = payload or self._payload()
        return payload.get("attendance") or []

    def _legacy_insights(self, subjects):
        total_classes = sum(subject.get("total", 0) for subject in subjects)
        total_attended = sum(subject.get("attended", 0) for subject in subjects)
        total_absent = sum(max(subject.get("total", 0) - subject.get("attended", 0), 0) for subject in subjects)
        return {
            "subject_count": len(subjects),
            "total_classes": total_classes,
            "total_attended": total_attended,
            "total_absent": total_absent,
            "overall_percentage": round((total_attended / total_classes * 100), 2) if total_classes else 0.0,
            "risky_subjects": [subject for subject in subjects if subject.get("status_75") != "safe"],
        }

    def _subject_label(self, subject):
        code = subject.get("code")
        name = subject.get("subject") or code or "Subject"
        return f"{code} - {name}" if code and code != name else name

    def _mask_identifier(self, value):
        text = str(value or "").strip()
        if len(text) <= 4:
            return text or "Unknown"
        return f"{text[:2]}...{text[-3:]}"

    def _status_word(self, subject):
        status = subject.get("status_75") or subject.get("status") or ""
        if status == "safe":
            return "Safe"
        if status == "borderline":
            return "Borderline"
        if status == "danger":
            return "Short"
        return status.title() or "Unknown"

    def _build_subject_table(self, subjects):
        response = "| Subject | Attendance | Absent | 75% Action | 65% Action |\n"
        response += "|:---|---:|---:|:---|:---|\n"
        for subject in subjects:
            action_75 = (
                f"Attend {subject.get('needed_75', 0)}"
                if subject.get("status_75") == "danger"
                else f"Skip {subject.get('skippable_75', 0)}"
            )
            action_65 = (
                f"Attend {subject.get('needed_65', 0)}"
                if subject.get("status_65") == "danger"
                else f"Skip {subject.get('skippable_65', 0)}"
            )
            response += (
                f"| {self._subject_label(subject)} | "
                f"{subject.get('percentage', 0)}% ({subject.get('attended', 0)}/{subject.get('total', 0)}) | "
                f"{subject.get('absent', max(subject.get('total', 0) - subject.get('attended', 0), 0))} | "
                f"{action_75} | {action_65} |\n"
            )
        return response

    def _summary(self, payload):
        subjects = self._subjects(payload)
        insights = payload.get("insights") or {}
        student = payload.get("student") or {}
        source = payload.get("source") or {}
        name = student.get("name") or "student"
        semester = source.get("semester") or student.get("semester") or "current"
        year = source.get("academic_year") or student.get("academic_year") or "selected"

        response = f"**Login accepted. Attendance analysis ready for {name}.**\n\n"
        response += (
            f"Overall: **{insights.get('overall_percentage', 0)}%** "
            f"({insights.get('total_attended', 0)}/{insights.get('total_classes', 0)}) "
            f"for semester **{semester}**, academic year **{year}**.\n"
        )
        response += (
            f"Total absent classes: **{insights.get('total_absent', 0)}**. "
            f"Subjects tracked: **{insights.get('subject_count', len(subjects))}**. "
            f"Safe skips at 75%: **{insights.get('total_skippable_75', 0)}**.\n\n"
        )
        if source.get("legacy_cache"):
            response += (
                "**Cache note:** this is an older totals-only cache. "
                "The shortcut commands work, but date-wise absences, portal profile fields, "
                "calendar marks, and website-surface mapping need one fresh portal login to rebuild the v2 cache.\n\n"
            )

        lowest = insights.get("lowest_subject")
        strongest = insights.get("strongest_subject")
        if lowest:
            response += f"Weakest right now: **{lowest.get('code')}** at **{lowest.get('percentage')}%**.\n"
        if strongest:
            response += f"Strongest right now: **{strongest.get('code')}** at **{strongest.get('percentage')}%**.\n"

        risky = insights.get("risky_subjects") or []
        if risky:
            response += f"\nSubjects needing attention: **{len(risky)}**. Type **RISK** for the list.\n"
        else:
            response += "\nNo subject is below 75%, but borderline subjects still need care.\n"

        response += "\n" + self._build_subject_table(subjects)
        response += "\nTry: **SW**, **TOTAL**, **ABSENT**, **SAFE**, **RISK**, **PROFILE**, **CALENDAR**, **WEBSITE**, or a subject code like **MEMEC303**."
        return response

    def _subject_details(self, subject):
        response = f"### **{self._subject_label(subject)}**\n\n"
        
        # Overview Stats
        response += f"📊 **Overview:**\n"
        response += f"- **Total Classes Held:** {subject.get('total', 0)}\n"
        response += f"- **Total Present:** {subject.get('attended', 0)}\n"
        response += f"- **Total Absent:** {subject.get('absent', 0)}\n"
        response += f"- **Current Attendance:** **{subject.get('percentage', 0)}%**\n\n"
        
        # Leave predictions
        needed_75 = subject.get('needed_75', 0)
        skippable_75 = subject.get('skippable_75', 0)
        status_75 = subject.get('status_75', 'safe')
        
        if status_75 == 'danger' or needed_75 > 0:
            pred_75 = f"Need to attend **{needed_75}** class(es) 🚨"
        elif status_75 == 'borderline':
            pred_75 = "Exactly at 75%. Cannot skip any class! ⚠️"
        else:
            pred_75 = f"Can skip **{skippable_75}** class(es) safely ✅"

        needed_65 = subject.get('needed_65', 0)
        skippable_65 = subject.get('skippable_65', 0)
        status_65 = subject.get('status_65', 'safe')
        
        if status_65 == 'danger' or needed_65 > 0:
            pred_65 = f"Need to attend **{needed_65}** class(es) 🚨"
        elif status_65 == 'borderline':
            pred_65 = "Exactly at 65%. Cannot skip any class! ⚠️"
        else:
            pred_65 = f"Can skip **{skippable_65}** class(es) safely ✅"

        response += f"🔮 **Leave Predictions:**\n"
        response += f"- **75% Criteria:** {pred_75}\n"
        response += f"- **65% Criteria:** {pred_65}\n\n"
        
        # Day-wise attendance records list
        response += f"📅 **Daily Attendance Records:**\n"
        
        day_wise = subject.get("day_wise") or []
        if day_wise:
            sorted_days = sorted(day_wise, key=lambda d: d.get("date", ""), reverse=True)
            for day in sorted_days:
                label = day.get("label") or day.get("date") or "Unknown"
                raw = day.get("raw") or "0"
                present = day.get("present_count", 0)
                absent = day.get("absent_count", 0)
                
                # Determine circle emoji
                if present > 0:
                    circle = "🟢"
                elif absent > 0:
                    circle = "🔴"
                else:
                    circle = "🟡"
                
                response += f"{circle} {label}: {raw}\n"
        else:
            response += "*No day-wise records available in cache. Run a fresh sync.*"
            
        return response

    def _match_subject(self, message_lower, subjects):
        compact_message = message_lower.replace(" ", "")
        for subject in subjects:
            code = (subject.get("code") or "").lower()
            name = (subject.get("subject") or "").lower()
            if code and code in compact_message:
                return subject
            if name and name in message_lower:
                return subject
            words = [word for word in name.split() if len(word) >= 4]
            if words and all(word in message_lower for word in words[:2]):
                return subject
        return None

    def _risk_report(self, payload):
        subjects = self._subjects(payload)
        risky = [subject for subject in subjects if subject.get("status_75") != "safe"]
        if not risky:
            return "No subject is below 75%. Borderline subjects can still become short after one absence, so check **SAFE** before skipping."

        response = "**Subjects near or below 75%:**\n\n"
        for subject in risky:
            response += (
                f"- **{self._subject_label(subject)}**: {subject.get('percentage')}% "
                f"({subject.get('attended')}/{subject.get('total')}). "
                f"{subject.get('message_75')}\n"
            )
        return response

    def _safe_report(self, payload):
        subjects = self._subjects(payload)
        safe_subjects = [subject for subject in subjects if subject.get("skippable_75", 0) > 0]
        if not safe_subjects:
            return "No subject has a safe skip buffer at 75% right now."

        response = "**Safe skip buffer at 75%:**\n\n"
        for subject in sorted(safe_subjects, key=lambda item: item.get("skippable_75", 0), reverse=True):
            response += (
                f"- **{self._subject_label(subject)}**: skip **{subject.get('skippable_75', 0)}** "
                f"class(es), current {subject.get('percentage')}%.\n"
            )
        return response

    def _absence_report(self, payload):
        insights = payload.get("insights") or {}
        absences = insights.get("recent_absences") or []
        if not absences:
            subjects = self._subjects(payload)
            response = f"Total absent classes: **{insights.get('total_absent', 0)}**.\n\n"
            if subjects:
                response += "| Subject | Absent | Attendance |\n|:---|---:|:---|\n"
                for subject in subjects:
                    absent = subject.get("absent", max(subject.get("total", 0) - subject.get("attended", 0), 0))
                    response += (
                        f"| {self._subject_label(subject)} | {absent} | "
                        f"{subject.get('percentage', 0)}% ({subject.get('attended', 0)}/{subject.get('total', 0)}) |\n"
                    )
            if (payload.get("source") or {}).get("legacy_cache"):
                response += (
                    "\nThis local cache is legacy totals-only, so exact absent dates are not stored. "
                    "Login once with the current scraper to rebuild the v2 cache with day-wise absence dates."
                )
            else:
                response += "\nNo detailed absence dates were found in the current cached attendance grid."
            return response

        response = f"Total absent classes: **{insights.get('total_absent', 0)}**.\n\n"
        response += "| Date | Subject | Count | Raw |\n|:---|:---|---:|:---|\n"
        for item in absences[:12]:
            response += f"| {item.get('date')} | {item.get('code')} | {item.get('count')} | {item.get('raw')} |\n"
        return response

    def _profile_report(self, payload):
        student = payload.get("student") or {}
        source = payload.get("source") or {}
        if not student:
            if source.get("legacy_cache"):
                return (
                    "This cache was created by the old totals-only scraper, so it does not contain profile/photo fields. "
                    "Fresh login with the v2 scraper will keep attendance plus student/profile surfaces in the analysis payload."
                )
            return "I only have attendance data in cache right now. The portal menu shows profile and ID-card pages, so the next scrape can attach personal/photo data when those pages are fetched."

        response = "**Student profile from attendance portal data**\n\n"
        response += f"- Name: **{student.get('name', 'Unknown')}**\n"
        if student.get("rollno"):
            response += f"- Roll no: **{self._mask_identifier(student.get('rollno'))}**\n"
        response += f"- Degree: **{student.get('degree', 'Unknown')}**\n"
        response += f"- Department: **{student.get('department', 'Unknown')}**\n"
        response += f"- Semester: **{source.get('semester') or student.get('semester', 'Unknown')}**\n"
        response += f"- Academic year: **{source.get('academic_year') or student.get('academic_year', 'Unknown')}**\n"
        response += f"- Portal photo: **{'available' if student.get('photo_available') else 'not cached'}**\n"
        return response

    def _website_report(self, payload):
        portal = payload.get("portal") or {}
        links = portal.get("links") or []
        surfaces = payload.get("source", {}).get("data_surfaces") or portal.get("data_surfaces") or []
        if not links and not surfaces:
            return "I do not have the authenticated portal menu cached yet. Login once, then I can map the available sections."

        response = "**Data seen inside the authenticated website**\n\n"
        if surfaces:
            response += "Usable data surfaces: **" + ", ".join(surfaces) + "**.\n\n"

        grouped = {}
        for link in links:
            grouped.setdefault(link.get("section") or "Portal", []).append(link.get("text"))
        for section, items in list(grouped.items())[:8]:
            clean_items = [item for item in items if item][:8]
            if clean_items:
                response += f"- **{section}**: {', '.join(clean_items)}\n"
        return response

    def _calendar_report(self, payload):
        insights = payload.get("insights") or {}
        specials = insights.get("special_events") or []
        if not specials:
            return "No holiday/leave/suspended-class marks were found in the current attendance grid."

        response = "**Recent portal calendar marks**\n\n"
        response += "| Date | Code | Mark | Meaning |\n|:---|:---|:---|:---|\n"
        for item in specials[:14]:
            response += (
                f"| {item.get('date')} | {item.get('code')} | {item.get('mark')} | "
                f"{item.get('description', '')} |\n"
            )
        return response

    def _codes(self):
        return (
            "**Shortcut commands**\n\n"
            "- **HI**: full attendance dashboard\n"
            "- **SW**: subject list, then type a number for details\n"
            "- **TOTAL**: total attendance and absent count\n"
            "- **ABSENT**: recent absent dates from the real grid\n"
            "- **SAFE**: subjects where you can skip classes\n"
            "- **RISK**: short or borderline subjects\n"
            "- **PROFILE**: student info extracted from portal data\n"
            "- **CALENDAR**: GH/TL/CS/MB and other portal marks\n"
            "- **WEBSITE**: what authenticated website sections are available\n"
            "- Subject code/name: details for one subject, like **MEMEC303**"
        )

    def process_message(self, message):
        message = (message or "").strip()
        message_lower = message.lower()
        payload = self._payload()
        subjects = self._subjects(payload)

        if message_lower in {"codes", "help", "commands", "shortcuts"}:
            return self._codes()

        if "profile" in message_lower or "student" in message_lower or "photo" in message_lower:
            return self._profile_report(payload)

        if "website" in message_lower or "available" in message_lower or "portal" in message_lower or "what data" in message_lower:
            return self._website_report(payload)

        if not subjects:
            return "I could not find attendance data yet. Please complete login and CAPTCHA once so I can show attendance summary."

        if self.state == "waiting_for_subject_number":
            if message.isdigit():
                idx = int(message)
                if idx in self.subject_map:
                    self.state = "idle"
                    return self._subject_details(self.subject_map[idx])
                return "Invalid number. Type **SW** again and choose a listed subject number."
            self.state = "idle"

        if message_lower in {"hi", "hello", "summary", "dashboard", "attendance","attendance summary"}:
            return self._summary(payload)

        if message_lower == "sw" or "subject wise" in message_lower or "subject-wise" in message_lower:
            response = ""
            for index, subject in enumerate(subjects):
                response += self._subject_details(subject)
                if index < len(subjects) - 1:
                    response += "\n\n---\n\n"
            return response

        if "calendar" in message_lower or "holiday" in message_lower or "leave" in message_lower or "gh" in message_lower or "tl" in message_lower:
            return self._calendar_report(payload)

        if message_lower in {"total", "total attendance", "overall"} or "overall" in message_lower:
            insights = payload.get("insights") or {}
            return (
                f"Overall attendance is **{insights.get('overall_percentage', 0)}%** "
                f"({insights.get('total_attended', 0)}/{insights.get('total_classes', 0)}). "
                f"Total absent classes: **{insights.get('total_absent', 0)}**."
            )

        if "absent" in message_lower or "missed" in message_lower:
            return self._absence_report(payload)

        if "danger" in message_lower or "short" in message_lower or "low" in message_lower or "risk" in message_lower:
            return self._risk_report(payload)

        if "safe" in message_lower or "skip" in message_lower or "bunk" in message_lower:
            return self._safe_report(payload)

        matched_subject = self._match_subject(message_lower, subjects)
        if matched_subject:
            return self._subject_details(matched_subject)

        return self._codes()

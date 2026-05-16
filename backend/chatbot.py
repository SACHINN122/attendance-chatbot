class ChatbotEngine:
    def __init__(self, scraper):
        self.scraper = scraper
        self.state = "idle"
        self.subject_map = {}

    def _build_table_75(self, analysis):
        """Build the 75% threshold table."""
        response = "📊 **Table 1: Leave Prediction — 75% Threshold**\n\n"
        for s in analysis:
            icon = "🟢" if s["status_75"] == "safe" else ("⚠️" if s["status_75"] == "borderline" else "🔴")
            skip_info = ""
            if s["status_75"] == "danger":
                skip_info = f"Need **{s['needed_75']}** more class(es)"
            elif s["skippable_75"] == 0:
                skip_info = "Can skip **0** classes"
            else:
                skip_info = f"Can skip **{s['skippable_75']}** class(es)"
            response += f"{icon} **{s['subject']}**: {s['percentage']}% ({s['attended']}/{s['total']}) — {skip_info}\n"
        return response

    def _build_table_65(self, analysis):
        """Build the 65% threshold table."""
        response = "📊 **Table 2: Leave Prediction — 65% Threshold**\n\n"
        for s in analysis:
            icon = "🟢" if s["status_65"] == "safe" else ("⚠️" if s["status_65"] == "borderline" else "🔴")
            skip_info = ""
            if s["status_65"] == "danger":
                skip_info = f"Need **{s['needed_65']}** more class(es)"
            elif s["skippable_65"] == 0:
                skip_info = "Can skip **0** classes"
            else:
                skip_info = f"Can skip **{s['skippable_65']}** class(es)"
            response += f"{icon} **{s['subject']}**: {s['percentage']}% ({s['attended']}/{s['total']}) — {skip_info}\n"
        return response

    def process_message(self, message):
        message = message.strip()
        message_lower = message.lower()
        analysis = self.scraper.get_full_analysis()
        
        if not analysis:
            return "I couldn't fetch your attendance data. Please check your login credentials."

        # Handle numeric input when waiting for a subject selection (SW mode)
        if self.state == "waiting_for_subject_number":
            if message.isdigit():
                idx = int(message)
                if idx in self.subject_map:
                    s = self.subject_map[idx]
                    self.state = "idle"  # Reset state
                    
                    # Build day-wise details response
                    response = f"📘 **Day-wise Attendance for {s['subject']}**\n\n"
                    if not s.get("day_wise"):
                        response += "No day-wise data available for this subject."
                    else:
                        response += "| Date | Status |\n|:---|:---|\n"
                        for entry in s["day_wise"]:
                            icon = "✅" if "present" in entry["status"].lower() else "🔴"
                            response += f"| {entry['date']} | {icon} {entry['status']} |\n"
                    return response
                else:
                    return f"Invalid number. Please enter a valid serial number from the list."
            else:
                self.state = "idle"
                # If it's not a digit, reset state and process it as a normal command below

        if message_lower == "hi":
            # Command: HI -> Full Attendance Summary
            response = self._build_table_75(analysis)
            response += "\n"
            response += self._build_table_65(analysis)
            response += "\n*Type **SW** to get subject-wise detailed attendance!*"
            return response
            
        elif message_lower == "sw":
            # Command: SW -> List subjects with serial numbers
            self.state = "waiting_for_subject_number"
            self.subject_map = {i+1: s for i, s in enumerate(analysis)}
            response = "📋 **Subject-Wise Detailed Attendance**\n\n"
            response += "Please enter the **serial number** of the subject you want to check:\n\n"
            for idx, s in self.subject_map.items():
                response += f"**{idx}.** {s['subject']}\n"
            return response

        # --- Danger zone / short attendance queries ---
        if "danger" in message or "short" in message or "low" in message:
            danger_subjects = [s for s in analysis if s["status_75"] == "danger"]
            if not danger_subjects:
                return "Great news! You have no subjects in the danger zone (all are above 75%)."
            
            response = "🔴 **Subjects below 75%:**\n\n"
            for s in danger_subjects:
                response += f"- **{s['subject']}**: {s['percentage']}% ({s['attended']}/{s['total']}). {s['message_75']}\n"
            return response
            
        # --- Safe zone / skip / bunk queries ---
        elif "safe" in message or "skip" in message or "bunk" in message:
            safe_subjects = [s for s in analysis if s["status_75"] == "safe"]
            if not safe_subjects:
                return "You have no subjects in the safe zone! You need to attend your classes."
            
            response = "🟢 **Subjects where you can skip:**\n\n"
            for s in safe_subjects:
                response += f"- **{s['subject']}**: {s['percentage']}% — Skip **{s['skippable_75']}** @75% | Skip **{s['skippable_65']}** @65%\n"
            return response

        # --- Specific subject query ---
        elif any(subj["subject"].lower() in message for subj in analysis):
            matched_subject = next(subj for subj in analysis if subj["subject"].lower() in message)
            s = matched_subject
            response = f"📘 **{s['subject']}**: {s['percentage']}% ({s['attended']}/{s['total']})\n\n"
            response += f"**@75% threshold:** {s['message_75']}\n"
            response += f"**@65% threshold:** {s['message_65']}\n"
            return response

        # --- Default: Help text ---
        else:
            response = "Welcome to your NSUT Attendance Assistant! 🤖\n\n"
            response += "Here are some quick commands you can use:\n"
            response += "- Type **HI** to get your full attendance summary & leave prediction tables.\n"
            response += "- Type **SW** to see a list of subjects and fetch day-wise attendance.\n"
            response += "- Or just ask me about 'danger zone' or 'safe zone' subjects!"
            return response

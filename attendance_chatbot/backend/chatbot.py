class ChatbotEngine:
    def __init__(self, scraper):
        self.scraper = scraper

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
        message = message.lower()
        analysis = self.scraper.get_full_analysis()
        
        if not analysis:
            return "I couldn't fetch your attendance data. Please check your login credentials."

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

        # --- Default: Full summary with BOTH tables ---
        else:
            response = self._build_table_75(analysis)
            response += "\n"
            response += self._build_table_65(analysis)
            response += "\n*Ask me about 'danger zone', 'safe zone', or a specific subject!*"
            return response

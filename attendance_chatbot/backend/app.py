from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from scraper import AttendanceScraper
from chatbot import ChatbotEngine
import os

app = Flask(__name__)
CORS(app)

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'frontend')

# Map session_id -> { "scraper": AttendanceScraper(), "chatbot": ChatbotEngine() }
user_sessions = {}

@app.route('/')
def serve_index():
    return send_from_directory(FRONTEND_DIR, 'index.html')

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory(FRONTEND_DIR, filename)

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    rollno = data.get('rollno')
    password = data.get('password')
    semester = data.get('semester', '4')
    
    scraper = AttendanceScraper(use_mock=False)
    result = scraper.start_login(rollno, password, semester)
    
    if result.get("success"):
        session_id = result["session_id"]
        user_sessions[session_id] = {
            "scraper": scraper,
            "chatbot": ChatbotEngine(scraper)
        }
        return jsonify(result)
    else:
        return jsonify({"success": False, "message": result.get("message", "Failed to load login page.")}), 401

@app.route('/api/captcha', methods=['POST'])
def verify_captcha():
    data = request.json
    session_id = data.get('session_id')
    captcha_text = data.get('captcha')
    
    if session_id not in user_sessions:
        return jsonify({"success": False, "message": "Session expired or invalid."}), 401
        
    scraper = user_sessions[session_id]["scraper"]
    result = scraper.submit_captcha_and_scrape(session_id, captcha_text)
    
    if result.get("success"):
        return jsonify({"success": True, "message": "Login successful! I've fetched your attendance data. You can ask me for a summary, danger zone subjects, or leave predictions."})
    else:
        del user_sessions[session_id]
        return jsonify({"success": False, "message": result.get("message", "Captcha or login failed.")}), 401

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    session_id = data.get('session_id')
    user_message = data.get('message', '')
    
    if session_id not in user_sessions:
        return jsonify({"reply": "Please login first. Session expired."}), 401
        
    chatbot = user_sessions[session_id]["chatbot"]
    reply = chatbot.process_message(user_message)
    return jsonify({"reply": reply})

if __name__ == '__main__':
    app.run(debug=True, port=5000, threaded=True)

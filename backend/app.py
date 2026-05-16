from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from scraper import AttendanceScraper
from chatbot import ChatbotEngine
import os
import json

app = Flask(__name__)
CORS(app)

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'frontend')
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

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
            "chatbot": ChatbotEngine(scraper),
            "rollno": rollno
        }
        return jsonify(result)
    else:
        return jsonify({"success": False, "message": result.get("message", "Failed to load login page.")}), 401

@app.route('/api/check_cache', methods=['POST'])
def check_cache():
    data = request.json
    rollno = data.get('rollno')
    
    if not rollno:
        return jsonify({"success": False, "message": "Roll number required"})

    cache_file = os.path.join(DATA_DIR, f"{rollno}.json")
    if os.path.exists(cache_file):
        with open(cache_file, "r") as f:
            cached_data = json.load(f)
            
        import uuid
        session_id = str(uuid.uuid4())
        
        # Create a mock scraper just to hold the data
        scraper = AttendanceScraper(use_mock=True)
        scraper.cached_analysis = cached_data
        
        user_sessions[session_id] = {
            "scraper": scraper,
            "chatbot": ChatbotEngine(scraper),
            "rollno": rollno
        }
        return jsonify({"success": True, "session_id": session_id, "message": "Loaded from cache"})
    
    return jsonify({"success": False, "message": "No cache found"})

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
        # Save to cache
        rollno = user_sessions[session_id]["rollno"]
        with open(os.path.join(DATA_DIR, f"{rollno}.json"), "w") as f:
            json.dump(scraper.cached_analysis, f)
            
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
    app.run(debug=True, port=5000, threaded=False, use_reloader=False)

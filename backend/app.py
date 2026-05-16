from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from scraper import AttendanceScraper
from chatbot import ChatbotEngine
from logging_config import setup_logging
import os
import json
import socket

app = Flask(__name__)
CORS(app)


def _load_local_env():
    """Load simple key=value pairs from .env for local testing."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
    if not os.path.exists(env_path):
        return

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)
    except:
        pass


_load_local_env()

# Configure logging
setup_logging(app)

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
    data = request.json or {}
    rollno = data.get('rollno') or os.getenv('roll_no') or os.getenv('ROLL_NO')
    password = data.get('password') or os.getenv('password') or os.getenv('PASSWORD')
    if not rollno or not password:
        return jsonify({"success": False, "message": "rollno and password are required"}), 400
    
    scraper = AttendanceScraper(use_mock=False)
    result = scraper.start_login(rollno, password)
    
    if result.get("success"):
        session_id = result["session_id"]
        user_sessions[session_id] = {
            "scraper": scraper,
            "chatbot": ChatbotEngine(scraper),
            "rollno": rollno
        }
        result["rollno"] = rollno
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
    data = request.json or {}
    session_id = data.get('session_id')
    captcha_text = data.get('captcha', '').strip()
    auto_ocr = data.get('auto_ocr', False)
    
    if not session_id:
        return jsonify({"success": False, "message": "session_id required"}), 400
    
    if session_id not in user_sessions:
        return jsonify({"success": False, "message": "Session expired or invalid."}), 401
    
    scraper = user_sessions[session_id]["scraper"]
    if not scraper.has_session(session_id):
        # Keep app + scraper session stores in sync.
        try:
            del user_sessions[session_id]
        except:
            pass
        return jsonify({"success": False, "message": "Session expired. Please login again."}), 401
    
    # Call scraper with optional OCR
    result = scraper.submit_captcha_and_scrape(session_id, captcha_text=captcha_text, auto_ocr=auto_ocr)
    
    if result.get("success"):
        # Save to cache
        try:
            rollno = user_sessions[session_id]["rollno"]
            with open(os.path.join(DATA_DIR, f"{rollno}.json"), "w") as f:
                json.dump(scraper.cached_analysis, f)
        except:
            pass
        
        return jsonify({"success": True, "message": "✓ Login successful! Attendance data fetched.", "data": scraper.get_full_analysis()})
    else:
        debug_dir = scraper.get_session_debug_dir(session_id)
        # Retryable failures should keep session alive so user can retry without password.
        if result.get("retryable"):
            return jsonify({
                "success": False,
                "message": result.get("message", "Captcha failed."),
                "retryable": True,
                "captcha_base64": result.get("captcha_base64"),
                "debug_dir": debug_dir
            }), 401

        try:
            del user_sessions[session_id]
        except:
            pass
        return jsonify({
            "success": False,
            "message": result.get("message", "Captcha or login failed."),
            "retryable": False,
            "debug_dir": debug_dir
        }), 401


@app.route('/api/captcha/refresh', methods=['POST'])
def refresh_captcha():
    data = request.json or {}
    session_id = data.get('session_id')

    if not session_id:
        return jsonify({"success": False, "message": "session_id required"}), 400

    if session_id not in user_sessions:
        return jsonify({"success": False, "message": "Session expired or invalid."}), 401

    scraper = user_sessions[session_id]["scraper"]
    if not scraper.has_session(session_id):
        try:
            del user_sessions[session_id]
        except:
            pass
        return jsonify({"success": False, "message": "Session expired. Please login again."}), 401

    result = scraper.refresh_captcha(session_id)
    if result.get("success"):
        return jsonify({"success": True, "captcha_base64": result.get("captcha_base64")}), 200

    return jsonify({
        "success": False,
        "message": result.get("message", "Failed to refresh captcha."),
        "debug_dir": scraper.get_session_debug_dir(session_id)
    }), 500


def _find_available_port(preferred_port):
    """Return preferred_port if free; otherwise return an OS-assigned free port."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("0.0.0.0", preferred_port))
        return preferred_port
    except OSError:
        pass
    finally:
        probe.close()

    fallback = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        fallback.bind(("0.0.0.0", 0))
        return fallback.getsockname()[1]
    finally:
        fallback.close()

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


@app.route('/api/analysis', methods=['POST'])
def analysis():
    data = request.json
    session_id = data.get('session_id')
    if not session_id or session_id not in user_sessions:
        return jsonify({"success": False, "message": "Invalid or missing session_id"}), 401

    scraper = user_sessions[session_id]["scraper"]
    return jsonify({"success": True, "analysis": scraper.get_full_analysis()})

if __name__ == '__main__':
    host = os.getenv('HOST', '0.0.0.0')
    preferred_port = int(os.getenv('PORT', '5000'))
    port = _find_available_port(preferred_port)
    print(f"[STARTUP] Preferred port {preferred_port}; using port {port}")
    app.run(host=host, debug=True, port=port, threaded=False, use_reloader=False)

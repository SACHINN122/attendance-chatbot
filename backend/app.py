from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from scraper import AttendanceScraper
from chatbot import ChatbotEngine
from logging_config import setup_logging
import os
import json
import socket
import uuid

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
APP_VERSION = "data-analysis-assistant-v2"

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# Map session_id -> { "scraper": AttendanceScraper(), "chatbot": ChatbotEngine() }
user_sessions = {}

def _default_rollno():
    return os.getenv('roll_no') or os.getenv('ROLL_NO') or ""

def _default_password():
    return os.getenv('password') or os.getenv('PASSWORD') or ""

def _cache_file_for(rollno):
    return os.path.join(DATA_DIR, f"{rollno}.json") if rollno else ""

def _cache_schema_version(cached_data):
    return cached_data.get("schema_version", 1) if isinstance(cached_data, dict) else 1

def _load_cached_analysis(rollno):
    cache_file = _cache_file_for(rollno)
    if not cache_file or not os.path.exists(cache_file):
        return None
    with open(cache_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    scraper = AttendanceScraper(use_mock=True)
    cleaned_data = scraper.deduplicate_and_recompute(data)
    
    if cleaned_data != data:
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cleaned_data, f)
        except:
            pass
            
    return cleaned_data

def _merge_live_profile(analysis, scraper):
    """Attach safe profile hints from the authenticated portal to cached analysis."""
    if not isinstance(analysis, dict):
        return analysis

    portal_catalog = getattr(scraper, "_last_portal_catalog", {}) or {}
    attendance_payload = getattr(scraper, "_last_attendance_payload", {}) or {}
    live_student = {
        **(portal_catalog.get("student_profile") or {}),
        **(attendance_payload.get("student") or {}),
    }
    live_student = {key: value for key, value in live_student.items() if value}
    if live_student:
        analysis["student"] = {**live_student, **(analysis.get("student") or {})}
        analysis["portal"] = analysis.get("portal") or portal_catalog
        source = analysis.setdefault("source", {})
        source["profile_source"] = "live_portal"
    return analysis

def _create_cached_session(session_id, rollno, cached_data, source_scraper=None):
    scraper = AttendanceScraper(use_mock=True)
    scraper.cached_analysis = cached_data
    chatbot = ChatbotEngine(scraper)
    analysis = chatbot.analysis_payload()
    analysis = _merge_live_profile(analysis, source_scraper) if source_scraper else analysis
    scraper.cached_analysis = analysis
    chatbot = ChatbotEngine(scraper)
    user_sessions[session_id] = {
        "scraper": scraper,
        "chatbot": chatbot,
        "rollno": rollno
    }
    return analysis, _cache_schema_version(cached_data)

@app.route('/')
def serve_index():
    return send_from_directory(FRONTEND_DIR, 'index.html')

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory(FRONTEND_DIR, filename)

@app.route('/api/config', methods=['GET'])
def config():
    rollno = _default_rollno()
    cache_file = _cache_file_for(rollno)
    cache_schema_version = None
    if cache_file and os.path.exists(cache_file):
        try:
            cache_schema_version = _cache_schema_version(_load_cached_analysis(rollno))
        except:
            cache_schema_version = None
    return jsonify({
        "assistant_version": APP_VERSION,
        "default_rollno": rollno,
        "has_saved_password": bool(_default_password()),
        "has_cached_data": bool(cache_file and os.path.exists(cache_file)),
        "cache_schema_version": cache_schema_version,
        "cache_needs_refresh": bool(cache_schema_version and cache_schema_version < 2),
    })

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json or {}
    rollno = data.get('rollno') or _default_rollno()
    password = data.get('password') or _default_password()
    if not rollno or not password:
        missing = "roll number" if not rollno else "password"
        return jsonify({
            "success": False,
            "message": f"{missing} required. Enter it once or set it in .env.",
            "needs_password": not bool(password),
        }), 400
    
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
    data = request.json or {}
    rollno = data.get('rollno') or _default_rollno()
    
    if not rollno:
        return jsonify({"success": False, "message": "Roll number required"})

    cache_file = _cache_file_for(rollno)
    if os.path.exists(cache_file):
        cached_data = _load_cached_analysis(rollno)
        session_id = str(uuid.uuid4())
        analysis, cache_schema_version = _create_cached_session(session_id, rollno, cached_data)
        return jsonify({
            "success": True,
            "session_id": session_id,
            "message": "Loaded from cache",
            "assistant_version": APP_VERSION,
            "cache_schema_version": cache_schema_version,
            "cache_needs_refresh": cache_schema_version < 2,
            "analysis": analysis
        })
    
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
        rollno = user_sessions[session_id]["rollno"]
        if "No attendance records found" in (result.get("message") or ""):
            try:
                cached_data = _load_cached_analysis(rollno)
                if cached_data:
                    analysis, cache_schema_version = _create_cached_session(
                        session_id,
                        rollno,
                        cached_data,
                        source_scraper=scraper,
                    )
                    try:
                        scraper.close_session(session_id)
                    except:
                        pass
                    return jsonify({
                        "success": True,
                        "message": "✓ Login accepted, but the live portal returned an empty attendance report. I loaded the last valid local cache instead.",
                        "live_sync_warning": "Portal returned no non-zero attendance records for the tested year/semester filters.",
                        "debug_dir": debug_dir,
                        "cache_schema_version": cache_schema_version,
                        "cache_needs_refresh": cache_schema_version < 2,
                        "data": analysis,
                    })
            except:
                pass

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
    data = request.json or {}
    session_id = data.get('session_id')
    user_message = data.get('message', '')
    
    if session_id not in user_sessions:
        return jsonify({"reply": "Please login first. Session expired."}), 401
        
    chatbot = user_sessions[session_id]["chatbot"]
    reply = chatbot.process_message(user_message)
    return jsonify({"reply": reply, "assistant_version": APP_VERSION})


@app.route('/api/analysis', methods=['POST'])
def analysis():
    data = request.json or {}
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

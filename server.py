from flask import Flask, request, jsonify
from flask_cors import CORS
from flask import Response
import requests
import datetime
import logging
import time
import sqlite3

app = Flask(__name__)

# The Titanium Shield (Localhost Only)
ALLOWED_ORIGINS = [
    "http://127.0.0.1:5000",      # Standard local Flask port
    "http://localhost:5000",
    "http://127.0.0.1:5500",      # VS Code Live Server default port
    "http://localhost:5500",
    "null"                        # For double-clicking the HTML file directly
]

CORS(app, resources={r"/*": {"origins": ALLOWED_ORIGINS}})

# --- THE SQLITE VAULT SETUP ---
total_logs_processed = 0  # Keep our SSE counter!

current_level = "1" # Global variable to store the slider state

def get_db_connection():
    """Opens the vault door."""
    conn = sqlite3.connect('butterclaw.db')
    conn.row_factory = sqlite3.Row # This makes it act like a dictionary
    return conn

def init_db():
    """Builds the vault if it doesn't exist yet."""
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            desc TEXT,
            action TEXT,
            time TEXT,
            icon TEXT,
            color TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Run the builder immediately!
init_db()

# ADD THESE TWO LINES TO MUTE THE SPAM
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# --- CONFIGURATION ---
OLLAMA_API = "http://localhost:11434/api/chat"
MODEL_NAME = "phi3:latest"

# Our temporary "Database"
live_oopsie_logs = []
total_logs_processed = 0  # <--- NEW: Tracks total logs over time

def ask_guardian_agent(threat_type, raw_data):
    """Passes the log through the Logic Gates using local Ollama Chat API."""
    
    global current_level  # <-- CRITICAL: Grab the slider value
    
    # Map the number to a Security Personality
    mode_instructions = "Mode: RELAXED. Be lenient unless it's a clear RCE."
    if current_level == "2": mode_instructions = "Mode: CAUTIOUS. Flag anomalies and token leaks."
    if current_level == "3": mode_instructions = "Mode: PARANOID. Zero Trust. Flag ANY external origin breathing on local ports."

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "system",
                "content": f"You are ButterClaw, an expert Blue Team cybersecurity Guardian Agent. {mode_instructions} Your ONLY job is to analyze logs. Keep your verdict to exactly two sentences. You MUST start your response with either 'VERDICT: CRITICAL', 'VERDICT: WARNING', or 'VERDICT: SAFE'. Do not repeat instructions. Do not generate fake logs or IP addresses."
            },
            {
                "role": "user",
                "content": f"Analyze this local AI agent event:\nThreat Type: {threat_type}\nRaw Data/Log: {raw_data}\n\nDetermine if this is a Cross-Site WebSocket Hijacking (CSWH) attempt, an Indirect Prompt Injection, or benign noise."
            }
        ],
        "stream": False,

        # --- THE FREEZE PATCH ---
        "options": {
            "temperature": 0.0
        }

    }
    
    try:
        response = requests.post(OLLAMA_API, json=payload, timeout=120)
        # The JSON response shape is slightly different for the chat endpoint
        return response.json().get("message", {}).get("content", "VERDICT: UNKNOWN - The brain stalled.")
    except Exception as e:
        return f"VERDICT: ERROR - Could not connect to local Ollama. Details: {e}"

@app.route('/api/analyze', methods=['POST'])
def analyze_threat():
    data = request.json
    threat_type = data.get("threat_type", "Unknown Anomaly")
    raw_data = data.get("raw_data", "")

    # --- THE TERMINAL X-RAY (FRONTEND -> BACKEND) ---
    print("\n" + "="*60)
    print(f"📥 [HTTP POST RECEIVED] From Browser Dashboard")
    print(f"   Payload: {threat_type}")
    
    # --- THE TERMINAL X-RAY (BACKEND -> OLLAMA) ---
    print(f"📡 [HTTP POST DISPATCHED] Routing to Ollama (Port 11434)...")
    start_time = time.time() # Start the stopwatch!
    
    # Let Phi-3 stew on it
    verdict_text = ask_guardian_agent(threat_type, raw_data)
    
    end_time = time.time() # Stop the stopwatch!
    stew_time = round(end_time - start_time, 2)

    # We force it to uppercase so 'Critical' and 'CRITICAL' both work
    verdict_upper = verdict_text.upper()
    
    print(f"🧠 [HTTP 200 OK] Ollama returned verdict in {stew_time} seconds.")
    print("="*60)

    # (The rest of your logic stays exactly the same)
    trigger_kill_switch = False

    if "CRITICAL" in verdict_upper:
        color = "red"      # <-- Paranoid Mode = RED
        icon = "🚨"
        action = "SIGKILL | Keys Buttered"
    elif "WARNING" in verdict_upper:
        color = "amber"    # <-- Cautious Mode = YELLOW/AMBER
        icon = "⚠️"
        action = "Monitored"
    elif "ERROR" in verdict_upper:
        color = "red"      # <-- System errors stay RED
        icon = "❌"
        action = "System Offline"
    else:
        color = "emerald"  # <-- Chill Mode = GREEN
        icon = "✅"
        action = "Monitored"

    # 3. NOW save it to the SQLITE VAULT!
    global total_logs_processed 
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO logs (title, desc, action, time, icon, color)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (threat_type, verdict_text, action, datetime.datetime.now().strftime("%H:%M:%S"), icon, color))
    conn.commit()
    conn.close()
    
    total_logs_processed += 1

    return jsonify({"status": "success", "verdict": verdict_text}), 200


@app.route('/api/logs', methods=['GET'])
def get_logs():
    """The Browser asks for history, we fetch from the Vault."""
    conn = get_db_connection()
    # Grab the 10 most recent logs, sorted newest first!
    rows = conn.execute('SELECT * FROM logs ORDER BY id DESC LIMIT 10').fetchall()
    conn.close()
    
    # Convert the SQLite rows into standard Python dictionaries for the UI
    return jsonify([dict(row) for row in rows])

@app.route('/api/rotate-keys', methods=['POST'])
def manual_key_rotation():
    """Simulates a manual key rotation event."""
    global total_logs_processed
    
    conn = get_db_connection()
    # We pass the exact strings directly into the vault!
    conn.execute('''
        INSERT INTO logs (title, desc, action, time, icon, color)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        "Manual Key Rotation", 
        "Administrator manually triggered API key rotation via ButterVault.", 
        "Keys Buttered", 
        datetime.datetime.now().strftime("%H:%M:%S"), 
        "🔑", 
        "blue"
    ))
    conn.commit()
    conn.close()
    
    total_logs_processed += 1
    
    return jsonify({"status": "success"}), 200

# --- THE CONTROL PANEL (The Missing Piece!) ---
@app.route('/api/settings', methods=['POST'])
def settings():
    global current_level
    current_level = request.json.get('level', "1")
    print(f"📡 [SENTINEL UPDATE] Paranoia Level shifted to: {current_level}")
    return {"status": "ok"}

@app.route('/api/stream')
def stream():
    def event_stream():
        # 1. Explicitly grab the global counter
        global total_logs_processed 
        last_processed = total_logs_processed
        
        while True:
            # Did the global counter go up?
            if total_logs_processed > last_processed:
                yield f"data: update_ready\n\n"
                last_processed = total_logs_processed
            
            # Take a micro-nap
            time.sleep(0.5)
            
    # 2. The Bulletproof Enterprise Wrapper
    response = Response(event_stream(), mimetype="text/event-stream")
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Cache-Control', 'no-cache')
    response.headers.add('Connection', 'keep-alive')
    
    return response

if __name__ == '__main__':
    print("🦞 ButterClaw Reasoning Engine is ONLINE.")
    app.run(host='127.0.0.1', port=5000)
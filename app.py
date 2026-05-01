import os
import json
import sqlite3
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory

from generator import generate_short

app = Flask(__name__)

# ── Database ──────────────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect('logs.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                  raw_thought TEXT,
                  llm_output TEXT,
                  video_url TEXT)''')
    conn.commit()
    conn.close()

init_db()


def log_generation(raw_thought: str, llm_output: dict, video_url: str):
    conn = sqlite3.connect('logs.db')
    c = conn.cursor()
    c.execute(
        "INSERT INTO logs (timestamp, raw_thought, llm_output, video_url) VALUES (?, ?, ?, ?)",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), raw_thought, json.dumps(llm_output), video_url)
    )
    conn.commit()
    conn.close()


# ── Job state ─────────────────────────────────────────────────────────────────
# Simple in-process state — fine for local single-user use.
# A threading.Lock guards writes so the status endpoint never reads a torn state.

_lock = threading.Lock()

job_status = {
    "status":   "Ready",
    "progress": 0,
    "error":    None,
    "result":   None,
    "running":  False,
}


def update_status(status: str, progress: int = None):
    with _lock:
        job_status["status"] = status
        if progress is not None:
            job_status["progress"] = progress


def run_job(raw_thought: str):
    with _lock:
        job_status.update(running=True, error=None, result=None)
    update_status("Starting...", 5)

    try:
        result = generate_short(raw_thought, update_status)

        folder_name = os.path.basename(result["folder"])
        video_url = f"/video/{folder_name}/final.mp4"
        log_generation(raw_thought, result.get("llm_output", {}), video_url)

        with _lock:
            job_status["result"] = result

    except Exception as e:
        with _lock:
            job_status["error"] = str(e)
        update_status("Something went wrong.", 0)

    finally:
        with _lock:
            job_status["running"] = False


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/generate', methods=['POST'])
def generate():
    with _lock:
        if job_status["running"]:
            return jsonify({"success": False, "error": "Already running — hang on a sec."}), 400

    data = request.json or {}
    raw_thought = (data.get('raw_thought') or '').strip()
    if not raw_thought:
        return jsonify({"success": False, "error": "Need a raw thought to work with."}), 400

    # Run in background thread; client polls /status and then hits /result when done.
    thread = threading.Thread(target=run_job, args=(raw_thought,), daemon=True)
    thread.start()

    return jsonify({"success": True, "message": "Generation started."})


@app.route('/result', methods=['GET'])
def get_result():
    """
    Poll this after /status shows progress=100.
    Returns the final video URL and caption, or an error if something went wrong.
    """
    with _lock:
        running = job_status["running"]
        error   = job_status["error"]
        result  = job_status["result"]

    if running:
        return jsonify({"ready": False, "message": "Still running."}), 202

    if error:
        return jsonify({"ready": False, "error": error}), 500

    if result is None:
        return jsonify({"ready": False, "message": "No job has been run yet."}), 404

    folder_name = os.path.basename(result["folder"])
    video_url = f"/video/{folder_name}/final.mp4"

    return jsonify({
        "ready":     True,
        "video_url": video_url,
        "caption":   result["caption"],
    })


@app.route('/status', methods=['GET'])
def get_status():
    with _lock:
        status   = job_status["status"]
        progress = job_status["progress"]
        error    = job_status["error"]

    return jsonify({
        "status":   status,
        "progress": progress,
        "error":    error,
    })


@app.route('/video/<folder>/<filename>')
def serve_video(folder, filename):
    # Basic path safety: reject traversal attempts
    if '..' in folder or '..' in filename:
        return "Forbidden", 403
    directory = os.path.join(os.getcwd(), folder)
    return send_from_directory(directory, filename)


@app.route('/logs')
def view_logs():
    conn = sqlite3.connect('logs.db')
    c = conn.cursor()
    c.execute("SELECT timestamp, raw_thought, llm_output, video_url FROM logs ORDER BY timestamp DESC")
    rows = c.fetchall()
    conn.close()

    logs_data = []
    for ts, raw, llm_raw, video_url in rows:
        try:
            llm_data = json.loads(llm_raw) if llm_raw else {}
        except json.JSONDecodeError:
            llm_data = {}
        logs_data.append({
            "timestamp":  ts,
            "raw_thought": raw,
            "llm_output": llm_data,
            "video_url":  video_url,
        })

    return render_template('logs.html', logs=logs_data)


if __name__ == '__main__':
    app.run(debug=True, port=5000)
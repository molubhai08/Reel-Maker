import os
from flask import Flask, render_template, request, jsonify, send_from_directory
import threading
from generator import generate_short

app = Flask(__name__)

# Very simple global state for status polling (not suitable for real production/multi-user)
# but perfect for a local script UI.
job_status = {
    "status": "Ready",
    "progress": 0,
    "error": None,
    "result": None,
    "running": False
}

def update_status(status, progress=None):
    job_status["status"] = status
    if progress is not None:
        job_status["progress"] = progress

def run_job(raw_thought):
    job_status["running"] = True
    job_status["error"] = None
    job_status["result"] = None
    update_status("Starting...", 5)
    
    try:
        result = generate_short(raw_thought, update_status)
        job_status["result"] = result
    except Exception as e:
        job_status["error"] = str(e)
        update_status("Error occurred.", 0)
    finally:
        job_status["running"] = False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    if job_status["running"]:
        return jsonify({"success": False, "error": "A job is already running."}), 400
        
    data = request.json
    raw_thought = data.get('raw_thought')
    if not raw_thought:
        return jsonify({"success": False, "error": "Raw thought is required."}), 400
        
    # Run Generation in a thread to release the HTTP request
    thread = threading.Thread(target=run_job, args=(raw_thought,))
    thread.start()
    
    # Wait for completion (simple blocking loop for the demo)
    thread.join()
    
    if job_status["error"]:
        return jsonify({"success": False, "error": job_status["error"]})
        
    res = job_status["result"]
    # The video_path might be absolute or relative, serving it via a custom route
    folder_name = os.path.basename(res["folder"])
    video_url = f"/video/{folder_name}/final.mp4"
    
    return jsonify({
        "success": True, 
        "video_url": video_url,
        "caption": res["caption"]
    })

@app.route('/status', methods=['GET'])
def get_status():
    return jsonify({
        "status": job_status["status"],
        "progress": job_status["progress"]
    })

@app.route('/video/<folder>/<filename>')
def serve_video(folder, filename):
    # folder is like 'short1'
    # Base directory is current directory
    directory = os.path.join(os.getcwd(), folder)
    return send_from_directory(directory, filename)

if __name__ == '__main__':
    app.run(debug=True, port=5000)

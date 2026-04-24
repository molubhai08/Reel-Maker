# 🎬 Reel-Maker

Reel-Maker is a powerful local toolset for automating short-form video creation for Instagram Reels, TikTok, and YouTube Shorts. It contains two main components:
1. **Video Splitter**: Quickly splits long gameplay or aesthetic footage into 1-minute 9:16 vertical clips.
2. **AI Inner Thoughts Generator**: A fully automated Flask web app that takes a "raw thought", generates an introspective script using an LLM, narrates it with offline TTS, and burns word-level animated subtitles onto background footage.

---

## 🛠️ Requirements & Setup

You will need the following installed on your machine:
- **Python 3.8+**
- **FFmpeg**: Must be installed and accessible in your system PATH.
- **Piper**: An offline Text-to-Speech system.

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/molubhai08/Reel-Maker.git
   cd Reel-Maker
   ```

2. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   *Note: `faster-whisper` will automatically download its model on the first run.*

3. **Configure the Environment:**
   Open the `.env` file and add your Groq API Key (used for fast script generation):
   ```
   GROQ_API_KEY=your_actual_key_here
   ```

4. **Prepare Background Videos:**
   Place some long gameplay or background clips (e.g., Minecraft Parkour, GTA V) into the `raw footages/` directory.

---

## 🚀 Features & Usage

###  1. AI Thoughts Short Generator
This tool turns a simple "raw thought" into a fully edited, ready-to-post short video with professional AI voiceovers and thick yellow "Karaoke-style" subtitles.

**How to run:**
1. Start the Flask application:
   ```bash
   python app.py
   ```
2. Open your web browser and navigate to `http://localhost:5000`.
3. Type in an interesting, relatable thought and click generate.
4. The output will be automatically saved in a new folder (e.g. `short1/`) along with the script JSON, the raw voiceover `.wav`, and the final `.mp4`.

### 2. Video Splitter & Cropper
A lightning-fast script to process bulk background videos. It splits them into 60-second chunks and optionally center-crops/scales them to the 9:16 vertical format (1080x1920) for Instagram Reels.

**How to run:**
```bash
python split_video.py "path_to_your_video.mp4"
```
*The script will ask if you want to format it for Reels (9:16 crop) — selecting 'y' will ensure it fits perfectly on a phone screen.*

---

## 🔧 Technologies Used
- **Flask**: Web interface for the AI Generator.
- **Groq API (`llama-3`)**: Writes introspective, relatable human-like scripts.
- **Piper TTS**: Synthesizes a calm, high-quality voiceover entirely offline.
- **Faster-Whisper**: Local, lightning-fast audio transcription for precise word-level subtitle timing.
- **FFmpeg**: Cuts, loops, crops, assembles audio/video perfectly, and natively renders Advanced SubStation Alpha (`.ass`) stylized captions.

## 📝 License
MIT License

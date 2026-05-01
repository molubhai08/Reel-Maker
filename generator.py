import os
import re
import glob
import json
import random
import subprocess
import wave
from groq import Groq

# ── Config ────────────────────────────────────────────────────────────────────

PIPER_MODEL = os.path.join("voice", "en_GB-northern_english_male-medium.onnx")
RAW_FOOTAGES_DIR = "raw footages"
WHISPER_MODELS_DIR = os.path.join(os.getcwd(), "whisper_models")

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_next_folder():
    base_dir = os.getcwd()
    i = 1
    while True:
        folder_path = os.path.join(base_dir, f"short{i}")
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
            return folder_path
        i += 1


def get_random_video():
    videos = glob.glob(os.path.join(RAW_FOOTAGES_DIR, "*.mp4"))
    return random.choice(videos) if videos else None


def naturalize_text(text: str) -> str:
    """
    Enforce contractions and fix common Piper mispronunciations.
    Critically: preserves ALL CAPS stress markers the LLM wrote.
    Those capitals are intentional voice direction — Piper reads them louder.
    """
    # Stash CAPS words so they survive lowercasing
    caps_pattern = re.compile(r'\b([A-Z]{2,})\b')
    caps_tokens = {}

    def stash_caps(m):
        token = f"__CAPS{len(caps_tokens)}__"
        caps_tokens[token] = m.group(1)
        return token

    text = caps_pattern.sub(stash_caps, text)

    # IMPORTANT: compound forms (e.g. "we have not") MUST come before their
    # sub-patterns ("we have", "have not") or the first pass partially contracts
    # them into nonsense like "we've not" or "we'ven't".
    replacements = [
        # ── Compound negations (must precede their parts) ──────────────────────
        ("i have not",      "i haven't"),
        ("i had not",       "i hadn't"),
        ("i would not",     "i wouldn't"),
        ("i will not",      "i won't"),
        ("i could not",     "i couldn't"),
        ("i should not",    "i shouldn't"),
        ("i did not",       "i didn't"),
        ("i do not",        "i don't"),
        ("we have not",     "we haven't"),
        ("we had not",      "we hadn't"),
        ("we would not",    "we wouldn't"),
        ("we will not",     "we won't"),
        ("we are not",      "we aren't"),
        ("we did not",      "we didn't"),
        ("we do not",       "we don't"),
        ("you have not",    "you haven't"),
        ("you had not",     "you hadn't"),
        ("you would not",   "you wouldn't"),
        ("you will not",    "you won't"),
        ("you are not",     "you aren't"),
        ("you did not",     "you didn't"),
        ("you do not",      "you don't"),
        ("they have not",   "they haven't"),
        ("they had not",    "they hadn't"),
        ("they would not",  "they wouldn't"),
        ("they will not",   "they won't"),
        ("they are not",    "they aren't"),
        ("they did not",    "they didn't"),
        ("they do not",     "they don't"),
        ("it is not",       "it isn't"),
        ("it has not",      "it hasn't"),
        ("that is not",     "that isn't"),
        ("there is not",    "there isn't"),
        # ── Simple negations ───────────────────────────────────────────────────
        ("do not",          "don't"),
        ("does not",        "doesn't"),
        ("did not",         "didn't"),
        ("will not",        "won't"),
        ("would not",       "wouldn't"),
        ("could not",       "couldn't"),
        ("should not",      "shouldn't"),
        ("cannot",          "can't"),
        ("can not",         "can't"),
        ("is not",          "isn't"),
        ("are not",         "aren't"),
        ("was not",         "wasn't"),
        ("were not",        "weren't"),
        ("have not",        "haven't"),
        ("has not",         "hasn't"),
        ("had not",         "hadn't"),
        # ── Positive contractions ──────────────────────────────────────────────
        ("you are",         "you're"),
        ("you have",        "you've"),
        ("you will",        "you'll"),
        ("you had",         "you'd"),
        ("they are",        "they're"),
        ("they have",       "they've"),
        ("it is",           "it's"),
        ("it has",          "it's"),
        ("that is",         "that's"),
        ("that has",        "that's"),
        ("there is",        "there's"),
        ("there are",       "there're"),
        ("i am",            "i'm"),
        ("i have",          "i've"),
        ("i will",          "i'll"),
        ("i would",         "i'd"),
        ("we are",          "we're"),
        ("we have",         "we've"),
        ("we will",         "we'll"),
        ("we would",        "we'd"),
    ]
    lower = text.lower()
    for formal, casual in replacements:
        lower = lower.replace(formal, casual)

    # Fix common Piper mispronunciations
    lower = re.sub(r'\b1\s*am\b',       'one in the morning',    lower)
    lower = re.sub(r'\b2\s*am\b',       'two in the morning',    lower)
    lower = re.sub(r'\b3\s*am\b',       'three in the morning',  lower)
    lower = re.sub(r'\b(\d+)\s*am\b',   r'\1 in the morning',    lower)
    lower = re.sub(r'\b(\d+)\s*pm\b',   r'\1 in the afternoon',  lower)

    # Restore CAPS stress words
    for token, original in caps_tokens.items():
        lower = lower.replace(token.lower(), original)

    return lower[0].upper() + lower[1:] if lower else lower


def validate_and_fix_script(data: dict) -> dict:
    """
    Validate the structured LLM output and repair common mistakes:
    - LLM returned a plain string instead of a clause array
    - Missing pause_after fields
    - Clauses too long for Piper (>12 words get split at the midpoint)
    """
    def fix_clauses(raw, section_name: str) -> list:
        if not isinstance(raw, list):
            # LLM returned a plain string — split into sentences and wrap
            text = str(raw)
            return [
                {"text": s.strip(), "pause_after": 0.4}
                for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()
            ]

        fixed = []
        for item in raw:
            if isinstance(item, str):
                item = {"text": item, "pause_after": 0.4}

            text  = item.get("text", "").strip()
            pause = min(float(item.get("pause_after", 0.3)), 0.5)  # hard cap at 0.5s

            if not text:
                continue

            words = text.split()
            if len(words) > 12:
                # Split long clauses at the midpoint; preserve the intended pause on the tail
                mid = len(words) // 2
                fixed.append({"text": " ".join(words[:mid]), "pause_after": 0.3})
                fixed.append({"text": " ".join(words[mid:]), "pause_after": pause})
            else:
                fixed.append({"text": text, "pause_after": pause})

        return fixed

    data["hook"]     = fix_clauses(data.get("hook",     []), "hook")
    data["script"]   = fix_clauses(data.get("script",   []), "script")
    data["question"] = fix_clauses(data.get("question", []), "question")

    return data


# ── Script generation ─────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a scriptwriter AND voice director for a short-form video page that narrates human inner thoughts.
Transform the RAW_THOUGHT into a 45–55 second script for Instagram Reels / TikTok.

TONE
- Quiet, late-night voice-note energy. Like texting a close friend at 1am.
- Introspective, calm, a little tired — never dramatic or preachy.
- Simple words. Short sentences. Real contractions (don't, you're, it's, can't, haven't, i've, we've).
- Occasionally second person ("you") but don't overdo it.
- NO metaphors that sound like a motivational poster.
- Be SPECIFIC and PERSONAL — avoid generic filler phrases like "that's the thing" or "i don't know".

SCRIPT STRUCTURE & CLAUSE COUNTS
You MUST hit these exact counts — count them before outputting:
1. hook:     exactly 2 clauses. A specific observation. Not a question.
2. script:   exactly 18–20 clauses. Think out loud — not an essay. This is the bulk of the video.
3. question: exactly 1 clause. A simple open question to spark comments.

TARGET LENGTH MATH (read this carefully):
- Average clause = 7 words, spoken at ~2.5 words/second = ~2.8s per clause
- Average pause_after = 0.3s per clause
- 20 script clauses × (2.8s speech + 0.3s pause) = ~62s → aim for 18 clauses = ~56s
- Hook (2 clauses) ≈ 7s, Question (1 clause) ≈ 4s
- Total target: 18 script clauses → ~45–50 seconds. DO NOT write fewer than 18 script clauses.

QUALITY RULES FOR THE SCRIPT:
- Each clause must carry a DISTINCT thought — no filler, no repetition.
- Build: start uncertain → explore the feeling → land somewhere honest.
- Use contractions naturally: haven't, i've, we've, didn't, wouldn't, it's.
- Avoid ending on vague statements. Make the listener feel understood.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TTS VOICE DIRECTION (this directly controls how the voice sounds)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Each clause is an object: {"text": "...", "pause_after": 0.0}

SENTENCE RULES:
- Each clause: 6–10 words. Never fewer than 4, never more than 12.
- Never stack more than 2 adjectives before a noun.
- No parenthetical asides mid-sentence. Break them into a new clause instead.
- Every 3–4 medium clauses, drop one short beat (4–6 words, pause_after 0.3–0.4).
  This rhythm is what makes it sound human. Don't skip it.

STRESS MARKING — capitalize the single most emotionally important word per clause:
- Write it in ALL CAPS. Only ONE word per clause.
- Good: "you kept showing up even when it was HARD."
- Good: "that's the part nobody TALKS about."
- Bad: "THAT'S the PART nobody talks about." (too many = Piper shouts everything)
- If no word deserves emphasis, don't force it — leave it lowercase.

PAUSE VALUES — keep them SHORT. This is a fast-paced short video, not a meditation:
- 0.1 = barely a breath, thought continues immediately
- 0.2 = quick natural beat between sentences
- 0.3 = standard sentence end (use this most often)
- 0.4 = slight emphasis, something worth sitting with for a moment
- 0.5 = heavier pause, emotional peak — use max 2–3 times in the whole script
- DO NOT use values above 0.5. No 0.8, no 1.0. They make the video feel broken.

RHYTHM PATTERN (vary it, don't repeat mechanically):
  medium clause (0.3) → medium clause (0.2) → medium clause (0.3) → short beat (0.4)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CAPTION (separate from script)
- 1–2 lines max, all lowercase, no hashtags, no emojis.
- Reflective and specific — not generic.

OUTPUT — strict JSON, nothing else:
{
  "hook": [
    {"text": "clause one.", "pause_after": 0.3},
    {"text": "clause two.", "pause_after": 0.4}
  ],
  "script": [
    {"text": "clause one.", "pause_after": 0.3},
    {"text": "clause two.", "pause_after": 0.2},
    {"text": "short beat.", "pause_after": 0.4},
    {"text": "clause four.", "pause_after": 0.3}
  ],
  "question": [
    {"text": "one question here?", "pause_after": 0.0}
  ],
  "caption": "plain text caption here"
}"""


def generate_script(raw_thought: str, api_key: str) -> dict:
    client = Groq(api_key=api_key)

    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": f"RAW_THOUGHT: {raw_thought}"},
        ],
        temperature=0.75,
        response_format={"type": "json_object"},
    )

    data = json.loads(completion.choices[0].message.content)

    # Validate structure, fix malformed output
    data = validate_and_fix_script(data)

    # Apply contraction enforcement to each clause.
    # naturalize_text() preserves ALL CAPS stress markers.
    for section in ("hook", "script", "question"):
        for clause in data.get(section, []):
            clause["text"] = naturalize_text(clause["text"])

    return data


# ── Audio generation ──────────────────────────────────────────────────────────

def generate_audio(text: str, output_path: str):
    """
    Run Piper TTS on a single clause.

    Parameter notes:
    - length-scale 1.30  : slightly slower = thoughtful, late-night feel
    - noise-scale  0.667 : moderate pitch variation per run (prevents robotic monotone)
    - noise-w      0.80  : moderate phoneme duration variation (natural rhythm)
    - sentence-silence 0 : we own all silence via concat_audio_parts
    """
    command = [
        "piper",
        "--model",            PIPER_MODEL,
        "--output_file",      output_path,
        "--length-scale",     "1.10",   # was 1.30 — that was adding ~15% extra duration per clause
        "--noise-scale",      "0.667",
        "--noise-w",          "0.80",
        "--sentence-silence", "0",
    ]
    subprocess.run(
        command,
        input=text.encode("utf-8"),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def get_wav_duration(wav_path: str) -> float:
    """Read WAV duration via Python's built-in wave module (no ffprobe needed)."""
    with wave.open(wav_path, "r") as wf:
        return wf.getnframes() / wf.getframerate()


def render_clauses(clauses: list[dict], output_dir: str, prefix: str, section_pad: float) -> list[tuple[str, float, str]]:
    """
    Render each structured clause as its own Piper call.

    Returns a list of (wav_path, pad_seconds, clause_text) triples.
    The text is carried through so the subtitle generator can use the
    original script wording instead of re-transcribing with Whisper.

    section_pad overrides the final clause's pause_after so the macro gap
    between hook → script → question stays consistent regardless of what
    the LLM chose for the last clause of each section.
    """
    parts = []

    for i, clause in enumerate(clauses):
        text = clause.get("text", "").strip()
        pad  = float(clause.get("pause_after", 0.4))

        if not text:
            continue

        wav_path = os.path.join(output_dir, f"{prefix}_clause{i}.wav")
        generate_audio(text, wav_path)
        parts.append((wav_path, pad, text))

    if parts:
        parts[-1] = (parts[-1][0], section_pad, parts[-1][2])

    return parts


def concat_audio_parts(parts: list[tuple], output_path: str):
    """
    Concatenate audio files with configurable silence padding after each part.
    parts: list of (wav_path, pad_seconds[, text])  — text field is optional/ignored.
    """
    filter_parts = []
    inputs = []
    for i, (path, pad, *_) in enumerate(parts):
        inputs += ["-i", path]
        filter_parts.append(f"[{i}:a]apad=pad_dur={pad}[a{i}]")

    labels = "".join(f"[a{i}]" for i in range(len(parts)))
    filter_complex = ";".join(filter_parts) + f";{labels}concat=n={len(parts)}:v=0:a=1[outa]"

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[outa]",
        output_path,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ── Subtitle generation ───────────────────────────────────────────────────────

ASS_HEADER = [
    "[Script Info]",
    "ScriptType: v4.00+",
    "PlayResX: 1080",
    "PlayResY: 1920",
    "WrapStyle: 1",
    "",
    "[V4+ Styles]",
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
    "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
    "Alignment, MarginL, MarginR, MarginV, Encoding",
    "Style: Default,Impact,120,&H0000E6FF,&H000000FF,&H00000000,&H99000000,"
    "-1,0,0,0,100,100,0,0,1,10,4,5,30,30,800,1",
    "",
    "[Events]",
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
]


def format_ass_time(seconds: float) -> str:
    hours     = int(seconds // 3600)
    minutes   = int((seconds % 3600) // 60)
    secs      = int(seconds % 60)
    centisecs = int(round((seconds - int(seconds)) * 100))
    if centisecs >= 100:
        secs += 1
        centisecs = 0
    return f"{hours}:{minutes:02d}:{secs:02d}.{centisecs:02d}"


def generate_subtitles_from_script(parts: list[tuple], output_ass_path: str):
    """
    Build an .ass subtitle file directly from the rendered clause WAVs and
    their original script text — NO Whisper transcription needed.

    Why this is better than Whisper:
    - We already know the exact words being spoken (from the LLM script).
    - Whisper re-transcription introduced errors: "real her" → "realer",
      split contractions "haven" + "'t" displayed as "HAVEN 'T", etc.
    - Timing is derived from the actual WAV durations, so there is zero drift.

    Word timing within each clause uses character-count-proportional
    distribution: longer words get a slightly larger slice of the clause
    duration, which looks more natural on screen.

    parts: list of (wav_path, pad_seconds, clause_text)
    """
    # Flatten all clauses into a sequence of word events with absolute timestamps.
    all_words: list[dict] = []
    clock = 0.0

    for wav_path, pad, text in parts:
        duration = get_wav_duration(wav_path)

        # Strip LLM stress-caps; everything is uppercased for display anyway.
        words = text.strip().split()
        if not words:
            clock += duration + pad
            continue

        # Character-count-proportional timing within the clause.
        char_counts = [max(len(w), 1) for w in words]
        total_chars = sum(char_counts)
        cumulative  = 0
        for w, chars in zip(words, char_counts):
            w_start  = clock + (cumulative / total_chars) * duration
            cumulative += chars
            w_end    = clock + (cumulative / total_chars) * duration
            all_words.append({"word": w, "start": w_start, "end": w_end})

        clock += duration + pad

    # Group into 3-word chunks for display.
    chunk_size = 3
    dialogue_lines = []
    for i in range(0, len(all_words), chunk_size):
        chunk = all_words[i : i + chunk_size]
        if not chunk:
            continue
        start = format_ass_time(chunk[0]["start"])
        end   = format_ass_time(chunk[-1]["end"])
        text  = " ".join(w["word"] for w in chunk).upper()
        dialogue_lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

    with open(output_ass_path, "w", encoding="utf-8") as f:
        f.write("\n".join(ASS_HEADER + dialogue_lines))


# ── Video assembly ────────────────────────────────────────────────────────────

def build_final_video(bg_video: str, audio_path: str, ass_path: str, output_video: str):
    ass_escaped = ass_path.replace("\\", "/").replace(":", "\\:")

    # Audio chain:
    #   acompressor  — gentle dynamic range so quiet clauses aren't lost
    #   equalizer    — cut muddiness at 200 Hz, add presence/clarity at 3 kHz
    #   asetrate     — pitch-down ~1 semitone for tired, late-night texture
    #   aresample    — restore sample rate after pitch shift
    #   atempo       — CRITICAL: asetrate=0.96 stretches audio to 1/0.96=1.0417x
    #                  duration. Without atempo compensation the subtitles (which
    #                  were stamped on the original audio) drift by ~1.7 s over
    #                  a 40 s video. atempo=1.0417 restores the original duration
    #                  while keeping the lower pitch.
    #   loudnorm     — consistent perceived loudness on mobile speakers
    PITCH_FACTOR = 0.96          # must match asetrate multiplier
    atempo_comp  = 1 / PITCH_FACTOR   # = 1.0417
    audio_filter = (
        "acompressor=threshold=-18dB:ratio=3:attack=5:release=50,"
        "equalizer=f=200:t=q:w=1:g=-3,"
        "equalizer=f=3000:t=q:w=1:g=2,"
        f"asetrate=22050*{PITCH_FACTOR},aresample=22050,"
        f"atempo={atempo_comp:.6f},"
        "loudnorm"
    )

    command = [
        "ffmpeg", "-y",
        "-stream_loop", "-1",
        "-i", bg_video,
        "-i", audio_path,
        "-filter_complex",
        f"[0:v]crop=ih*9/16:ih,scale=1080:1920,subtitles='{ass_escaped}'[v];"
        f"[1:a]{audio_filter}[a]",
        "-map", "[v]",
        "-map", "[a]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-shortest",
        output_video,
    ]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_short(raw_thought: str, update_status) -> dict:
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key or api_key == "your_groq_api_key_here":
        raise ValueError("GROQ_API_KEY not set in .env")

    bg_video = get_random_video()
    if not bg_video:
        raise FileNotFoundError(f"No .mp4 files found in '{RAW_FOOTAGES_DIR}'.")

    output_dir = get_next_folder()

    # 1 ── Script
    # LLM now returns structured clause arrays with explicit pause values + stress caps.
    # No regex guessing — the model is the voice director.
    update_status("Writing the script...", 20)
    data = generate_script(raw_thought, api_key)

    with open(os.path.join(output_dir, "script_output.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(data, indent=2))

    # 2 ── Voiceover
    # Each clause → its own Piper call → its own WAV.
    # Silence gaps come from clause["pause_after"], not from Piper's internal logic.
    # section_pad overrides the last clause of each section for macro-level breathing.
    update_status("Recording voiceover...", 40)
    audio_path = os.path.join(output_dir, "voiceover.wav")

    all_parts = []
    all_parts += render_clauses(data["hook"],     output_dir, "hook",     section_pad=0.5)
    all_parts += render_clauses(data["script"],   output_dir, "script",   section_pad=0.4)
    all_parts += render_clauses(data["question"], output_dir, "question", section_pad=0.0)

    concat_audio_parts(all_parts, audio_path)

    # 3 ── Subtitles
    # Build subtitles directly from the original script text + WAV durations.
    # No Whisper: we already know the exact words, so there are no transcription
    # errors and no sync drift.
    update_status("Generating subtitles...", 60)
    ass_path = os.path.join(output_dir, "subtitles.ass")
    generate_subtitles_from_script(all_parts, ass_path)

    # 4 ── Final render
    update_status("Putting it all together...", 80)
    final_video = os.path.join(output_dir, "final.mp4")
    build_final_video(bg_video, audio_path, ass_path, final_video)

    update_status("Done!", 100)

    return {
        "folder":     output_dir,
        "video_path": final_video,
        "caption":    data["caption"],
        "llm_output": data,
    }
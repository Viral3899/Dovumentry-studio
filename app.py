import json
import math
import os
import random
import re
import shutil
import subprocess
import time
import uuid
import wave
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

try:
    from groq import Groq
except Exception:  # pragma: no cover
    Groq = None

try:
    from google import genai
    from google.genai import types
except Exception:  # pragma: no cover
    genai = None
    types = None

BASE_DIR = Path(__file__).resolve().parent
GENERATED_DIR = BASE_DIR / "generated_sessions"
GENERATED_DIR.mkdir(exist_ok=True)
PROJECTS_DIR = BASE_DIR / "projects"
PROJECTS_DIR.mkdir(exist_ok=True)
BGM_DIR = BASE_DIR / "BGM"
BGM_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
BGM_VOLUME = 0.20
NARRATION_VOLUME = 1.5
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
VISUAL_STYLES = {
    "photorealistic": "Photorealistic cinematic documentary, premium film quality, realistic lighting, realistic people, accurate environment, natural colors, cinematic depth of field",
    "cartoon": "Stylized 2D cartoon animation, expressive clean shapes, rich colors, cinematic composition, appealing character design, storybook realism",
    "anime": "Cinematic anime illustration, detailed backgrounds, expressive characters, dramatic composition, polished hand-drawn visual language",
    "3d_animation": "High-quality 3D animated film style, detailed digital environments, expressive characters, cinematic lighting, polished render",
    "illustrated": "Rich editorial illustration, hand-painted textures, detailed composition, atmospheric colors, historically respectful visual storytelling",
}
SCRIPT_LANGUAGES = {
    "hindi": "natural Hindi written in Devanagari",
    "english": "natural English",
    "hinglish": "natural Hinglish using Hindi and English in Roman script",
}

app = Flask(__name__)


def slugify(value: str) -> str:
    value = (value or "untitled").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "untitled"


def utc_timestamp() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")


def log_event(session_dir: Path, message: str):
    log_path = session_dir / "generation_log.txt"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{utc_timestamp()}] {message}\n")


def write_state(session_dir: Path, data: dict):
    state_path = session_dir / "session_state.json"
    state_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_state(session_dir: Path):
    state_path = session_dir / "session_state.json"
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_groq_client():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or Groq is None:
        return None
    return Groq(api_key=api_key)


def get_gemini_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or genai is None:
        return None
    try:
        return genai.Client(api_key=api_key)
    except Exception:
        return None


def get_session_dir(session_id: str) -> Path:
    generated_dir = GENERATED_DIR / session_id
    if generated_dir.exists():
        return generated_dir
    return PROJECTS_DIR / session_id


def topic_folder_name(value: str) -> str:
    name = re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE).strip("._")
    return name[:80] or "documentary"


def get_duration(filename: str) -> float:
    if not Path(filename).exists():
        return 0.0
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            filename,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout:
        return 0.0
    try:
        return float(json.loads(result.stdout)["format"]["duration"])
    except Exception:
        return 0.0


def count_required_images(audio_duration: float, image_seconds: float = 5, transition_seconds: float = 1) -> int:
    return max(1, math.ceil((audio_duration - image_seconds) / (image_seconds - transition_seconds)) + 1)


def render_setting(payload, name, default, minimum, maximum):
    try:
        value = float(payload.get(name, default))
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number.")
    if not math.isfinite(value) or value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return value


def make_silence_wav(path: Path, duration_seconds: float):
    sample_rate = 22050
    frames = []
    for _ in range(int(duration_seconds * sample_rate)):
        frames.append(0)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"".join((int(value)).to_bytes(2, byteorder="little", signed=True) for value in frames))


def make_placeholder_audio(path: Path, text: str, voice_name: str):
    length = max(30, len(text.split()) * 0.45)
    sample_rate = 22050
    total_frames = int(length * sample_rate)
    audio = bytearray()
    for idx in range(total_frames):
        phase = (idx / sample_rate) * 2 * math.pi * 180
        tone = math.sin(phase) * 6000 + math.sin(phase * 1.5) * 2000
        sample = int(max(-32768, min(32767, tone)))
        audio.extend(sample.to_bytes(2, byteorder="little", signed=True))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio)
    return length


# def generate_local_audio(path: Path, script: str, voice_name: str):
#     """Generate spoken fallback audio with the Windows SAPI voice engine."""
#     errors = []
#     try:
#         import pyttsx3

#         engine = pyttsx3.init()
#         voices = engine.getProperty("voices") or []
#         preferred = next(
#             (
#                 voice for voice in voices
#                 if any(
#                     marker in f"{voice.id} {voice.name}".lower()
#                     for marker in ("hindi", "hi-in", voice_name.lower())
#                 )
#             ),
#             None,
#         )
#         if preferred is not None:
#             engine.setProperty("voice", preferred.id)
#         engine.setProperty("rate", 145)
#         engine.setProperty("volume", 1.0)
#         engine.save_to_file(script, str(path))
#         engine.runAndWait()
#         engine.stop()
#         if path.exists() and path.stat().st_size > 1000:
#             return path
#     except Exception as exc:
#         errors.append(f"pyttsx3: {exc}")

#     try:
#         import win32com.client

#         voice = win32com.client.Dispatch("SAPI.SpVoice")
#         stream = win32com.client.Dispatch("SAPI.SpFileStream")
#         stream.Format.Type = 22  # 22 kHz, 16-bit, mono PCM WAV.
#         stream.Open(str(path), 3, False)
#         voice.AudioOutputStream = stream
#         voice.Speak(script)
#         stream.Close()
#         if path.exists() and path.stat().st_size > 1000:
#             return path
#     except Exception as exc:
#         errors.append(f"SAPI: {exc}")

#     raise RuntimeError("; ".join(errors) or "Windows speech engine produced no audio")


def generate_local_audio(path: Path, script: str, voice_name: str):
    """Generate spoken fallback audio using Microsoft Edge's free TTS service (cross-platform)."""
    import asyncio
    import edge_tts

    # Map a few friendly names to real edge-tts Hindi voices.
    # Full list: `edge-tts --list-voices | grep hi-IN`
    hindi_voices = {
        "male": "hi-IN-MadhurNeural",
        "female": "hi-IN-SwaraNeural",
    }
    voice = hindi_voices.get(voice_name.lower(), "hi-IN-SwaraNeural")

    mp3_path = path.with_suffix(".mp3")

    async def _synthesize():
        communicate = edge_tts.Communicate(script, voice)
        await communicate.save(str(mp3_path))

    asyncio.run(_synthesize())

    if not mp3_path.exists() or mp3_path.stat().st_size < 1000:
        raise RuntimeError("edge-tts produced no audio output")

    # Convert mp3 -> wav so downstream ffprobe/ffmpeg duration checks work consistently.
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", str(mp3_path), "-ar", "22050", "-ac", "1", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    mp3_path.unlink(missing_ok=True)
    if result.returncode != 0 or not path.exists() or path.stat().st_size < 1000:
        raise RuntimeError(f"ffmpeg conversion failed: {result.stderr}")

    return path

def extract_tts_audio(response):
    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            inline_data = getattr(part, "inline_data", None)
            data = getattr(inline_data, "data", None) if inline_data else None
            if isinstance(data, bytes):
                return data
    return None


def generate_real_audio(path: Path, script: str, voice_name: str):
    client = get_gemini_client()
    if client is None or types is None:
        return None

    response = client.models.generate_content(
        model="gemini-2.5-flash-preview-tts",
        contents=(
            "Read only the following documentary narration as natural spoken Hindi. "
            f"Use a serious documentary voice named {voice_name}.\n\n{script}"
        ),
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_name
                    )
                )
            ),
        ),
    )
    audio_bytes = extract_tts_audio(response)
    if not audio_bytes:
        return None

    if audio_bytes[:4] == b"RIFF":
        path.write_bytes(audio_bytes)
    else:
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(24000)
            output.writeframes(audio_bytes)
    return path


def build_fallback_script(topic: str, genre: str) -> str:
    return (
        f"भारत की विविध धरती और उसकी जीवंत स्मृतियों के बीच {topic} की कहानी धीरे-धीरे हमारे सामने खुलती है। "
        f"यह केवल एक घटना या स्थान की कहानी नहीं, बल्कि उन लोगों, विचारों और परिस्थितियों का सफर है जिन्होंने इसे आकार दिया। "
        f"समय के साथ बदलते समाज, स्थानीय परंपराएं, कारीगरों की मेहनत और आम लोगों की उम्मीदें इस कथा को अपना मानवीय स्वर देती हैं। "
        f"इस विषय को समझने के लिए हमें उसके इतिहास, भूगोल और सांस्कृतिक संदर्भ को साथ देखना होगा। "
        f"कभी किसी नदी के किनारे बसे नगरों ने व्यापार और ज्ञान को आगे बढ़ाया, तो कभी गांवों और कस्बों में पीढ़ियों से चली आ रही कला ने पहचान बनाई। "
        f"उपलब्ध प्रमाण हमें कई महत्वपूर्ण संकेत देते हैं, लेकिन हर ऐतिहासिक कहानी की तरह यहां भी कुछ प्रश्न और अनिश्चितताएं बाकी हैं। "
        f"इन्हीं प्रमाणों, अनुभवों और बदलते समय के बीच {topic} का अर्थ और गहरा होता जाता है। "
        f"आज जब हम पीछे मुड़कर देखते हैं, तो यह कहानी हमें बताती है कि भारत की पहचान केवल उसके स्मारकों या घटनाओं में नहीं, बल्कि उन लोगों की मेहनत, स्मृति और साझा संस्कृति में भी बसती है। "
        f"और शायद यही कारण है कि {topic} आज भी हमारे लिए महत्वपूर्ण है।"
    )


def is_hindi_script(text: str) -> bool:
    devanagari = len(re.findall(r"[\u0900-\u097F]", text or ""))
    letters = len(re.findall(r"[A-Za-z\u0900-\u097F]", text or ""))
    return devanagari >= 20 and devanagari / max(letters, 1) >= 0.35


def generate_script_with_backend(topic: str, genre: str, session_id: str, script_language: str = "hindi", target_duration: float = 60):
    session_dir = get_session_dir(session_id)
    client = get_groq_client()
    if client is not None:
        try:
            prompt = (
                f"Write a cinematic {SCRIPT_LANGUAGES.get(script_language, SCRIPT_LANGUAGES['hindi'])} {genre or 'documentary'} narration about {topic}. "
                "Return only a continuous spoken Hindi documentary script, without headings. "
                "Use Indian cultural, historical, geographic, and social context where relevant. "
                "Keep factual claims cautious and do not invent names, dates, quotations, or events. "
                f"Write enough natural narration for approximately {target_duration:.0f} seconds of speech. "
                "Aim for about 2.2 spoken words per second and do not add headings."
            )
            response = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[
                    {"role": "system", "content": "You are an expert Hindi documentary scriptwriter familiar with Indian history and culture."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=max(1500, min(6000, math.ceil(target_duration * 3.2))),
            )
            script = (response.choices[0].message.content or "").strip()
            if script and (script_language != "hindi" or is_hindi_script(script)):
                return script
            if script:
                translation = client.chat.completions.create(
                    model="openai/gpt-oss-120b",
                    messages=[
                        {"role": "system", "content": "You translate documentary narration into natural Hindi written only in Devanagari."},
                        {"role": "user", "content": f"Translate this complete narration into Hindi Devanagari. Return only the Hindi narration, with no English text or headings:\n\n{script}"},
                    ],
                    temperature=0.3,
                    max_tokens=1800,
                )
                translated = (translation.choices[0].message.content or "").strip()
                if script_language != "hindi" or is_hindi_script(translated):
                    return translated
        except Exception as exc:  # pragma: no cover
            log_event(session_dir, f"Groq generation failed: {exc}")
    return build_fallback_script(topic, genre)


def generate_prompt_text(topic: str, script: str, count: int, visual_style: str = "photorealistic"):
    style_description = VISUAL_STYLES.get(visual_style, VISUAL_STYLES["photorealistic"])
    client = get_groq_client()
    if client is not None:
        try:
            response = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[
                    {
                        "role": "system",
                        "content": "You create concise, factual cinematic documentary image prompts.",
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Generate exactly {count} numbered image prompts for {topic}. "
                            "Follow the narration chronology. Each prompt must be one self-contained scene "
                            "with subject, setting, action, lighting, mood, camera angle, and this exact ending: "
                            f"{style_description}, 16:9 landscape, no text, no subtitles, no captions, no logos, no watermarks. "
                            "Use authentic Indian visual details where relevant: regional architecture, clothing, "
                            "materials, landscapes, food, crafts, festivals, streets, and natural light. Avoid generic "
                            "stereotypes and keep period, geography, and cultural details historically appropriate. "
                            f"Return only prompts numbered 1 through {count}.\n\nNARRATION:\n{script}"
                        ),
                    },
                ],
                temperature=0.5,
                max_tokens=2200,
            )
            generated = (response.choices[0].message.content or "").strip()
            generated_prompts = parse_prompts(generated)
            if len(generated_prompts) == count:
                return enforce_visual_style(generated_prompts, visual_style)
        except Exception:  # pragma: no cover
            pass

    prompts = []
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", script) if sentence.strip()]
    if not sentences:
        sentences = [script]
    for index in range(1, count + 1):
        seed = sentences[(index - 1) % len(sentences)]
        prompt = (
            f"{index}. {topic}: cinematic documentary visual of {seed[:180]} "
            "in an authentic Indian setting with regionally appropriate people, clothing, architecture, materials, "
            "landscapes, crafts, and natural details, dramatic lighting, realistic people, natural colors, 16:9 landscape, "
            f"{style_description}, no text, no watermark."
        )
        prompts.append(prompt)
    return "\n\n".join(prompts)


def enforce_visual_style(prompts: list[str], visual_style: str):
    """Ensure every saved scene prompt explicitly carries the selected style."""
    style_description = VISUAL_STYLES[visual_style]
    return "\n\n".join(
        f"{index}. {prompt} MANDATORY VISUAL STYLE: {style_description}."
        for index, prompt in enumerate(prompts, start=1)
    )


def generate_generation_prompt_text(topic: str, prompts: list[str], visual_style: str = "photorealistic"):
    style_description = VISUAL_STYLES.get(visual_style, VISUAL_STYLES["photorealistic"])
    lines = [
        "IMAGE GENERATION INSTRUCTIONS",
        "Generate the images in chronological order using the numbered prompts below.",
        f"Use this visual style consistently in every frame: {style_description}.",
        "Keep recurring characters, locations, props, architecture, palette, lighting, and visual continuity consistent.",
        "Use authentic Indian regional details, cultural context, clothing, architecture, materials, landscapes, and period-appropriate everyday life where relevant.",
        "Export files as 1.jpeg, 2.jpeg, 3.jpeg, and so on, matching the prompt number exactly.",
        "Do not add text, subtitles, captions, logos, or watermarks.",
        "",
        "SCENE PROMPTS",
        "",
    ]
    lines.extend(prompts)
    return "\n\n".join(lines)


def parse_prompts(text: str):
    matches = re.findall(r"^\s*(\d+)\.\s*(.*?)(?=^\s*\d+\.\s*|\Z)", text, flags=re.MULTILINE | re.DOTALL)
    prompts = [item.strip() for _, item in matches if item.strip()]
    if prompts:
        return prompts
    return [line.strip() for line in text.splitlines() if line.strip()]


def image_index_from_filename(filename: str):
    """Read a leading image number from generated or user-uploaded names."""
    stem = Path(filename).stem
    match = re.match(r"^\s*(\d+)(?:\D|$)", stem)
    return int(match.group(1)) if match else 0


@app.route("/")
def index():
    return "Flask Documentary Studio"


@app.route("/api/create-session", methods=["POST"])
def create_session():
    payload = request.get_json(silent=True) or {}
    topic = (payload.get("topic") or "").strip()
    genre = (payload.get("genre") or "documentary").strip()
    visual_style = (payload.get("visual_style") or "photorealistic").strip()
    script_language = (payload.get("script_language") or "hindi").strip()
    if not topic:
        return jsonify({"success": False, "message": "Topic is required."}), 400
    if visual_style not in VISUAL_STYLES:
        return jsonify({"success": False, "message": "Unsupported visual style."}), 400
    if script_language not in SCRIPT_LANGUAGES:
        return jsonify({"success": False, "message": "Unsupported script language."}), 400

    try:
        target_duration = render_setting(payload, "target_duration", 60, 20, 600)
        image_seconds = render_setting(payload, "image_seconds", 5, 1, 30)
        transition_seconds = render_setting(payload, "transition_seconds", 1, 0, 10)
        narration_volume = render_setting(payload, "narration_volume", NARRATION_VOLUME, 0, 3)
        bgm_volume = render_setting(payload, "bgm_volume", BGM_VOLUME, 0, 1)
    except ValueError as error:
        return jsonify({"success": False, "message": str(error)}), 400
    if transition_seconds >= image_seconds:
        return jsonify({"success": False, "message": "transition_seconds must be less than image_seconds."}), 400

    session_id = topic_folder_name(topic)
    session_dir = PROJECTS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "images").mkdir(exist_ok=True)
    (session_dir / "topic.txt").write_text(topic, encoding="utf-8")
    log_path = session_dir / "generation_log.txt"
    log_path.write_text("", encoding="utf-8")
    log_event(session_dir, f"Session created for topic: {topic} | genre: {genre}")

    state = {
        "session_id": session_id,
        "topic": topic,
        "genre": genre,
        "visual_style": visual_style,
        "script_language": script_language,
        "folder": str(session_dir),
        "status": "created",
        "script": "",
        "prompts": [],
        "audio_file": "",
        "audio_duration": 0.0,
        "video_file": "",
        "music_file": "",
        "validated_images": {},
        "image_seconds": image_seconds,
        "transition_seconds": transition_seconds,
        "narration_volume": narration_volume,
        "bgm_volume": bgm_volume,
        "target_duration": target_duration,
    }
    write_state(session_dir, state)
    return jsonify({"success": True, "session_id": session_id, "folder": str(session_dir), "topic": topic, "genre": genre})


@app.route("/api/session/<session_id>/download/<path:filename>")
def download_file(session_id, filename):
    session_dir = get_session_dir(session_id)
    if not session_dir.exists():
        return jsonify({"success": False, "message": "Session not found."}), 404
    target = (session_dir / filename).resolve()
    try:
        return send_file(target, as_attachment=True)
    except Exception:
        return jsonify({"success": False, "message": "File not found."}), 404


@app.route("/api/generate-script", methods=["POST"])
def generate_script_route():
    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id")
    if not session_id:
        return jsonify({"success": False, "message": "session_id is required."}), 400

    session_dir = get_session_dir(session_id)
    if not session_dir.exists():
        return jsonify({"success": False, "message": "Session not found."}), 404

    state = load_state(session_dir)
    topic = state.get("topic") or payload.get("topic") or ""
    genre = state.get("genre") or payload.get("genre") or "documentary"

    try:
        target_duration = render_setting(
            payload,
            "target_duration",
            state.get("target_duration", 60),
            20,
            600,
        )
    except ValueError as error:
        return jsonify({"success": False, "message": str(error)}), 400
    state["target_duration"] = target_duration
    script = generate_script_with_backend(
        topic,
        genre,
        session_id,
        state.get("script_language", "hindi"),
        target_duration,
    )
    script_path = session_dir / "documentary_script.txt"
    script_path.write_text(script, encoding="utf-8")

    state["status"] = "script_ready"
    state["script"] = script
    write_state(session_dir, state)
    log_event(session_dir, f"Script generated for topic: {topic} | genre: {genre}")
    return jsonify({"success": True, "script": script, "download_url": f"/api/session/{session_id}/download/documentary_script.txt"})


@app.route("/api/update-script", methods=["POST"])
def update_script_route():
    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id")
    script = (payload.get("script") or "").strip()
    if not session_id or not script:
        return jsonify({"success": False, "message": "session_id and script are required."}), 400

    session_dir = get_session_dir(session_id)
    if not session_dir.exists():
        return jsonify({"success": False, "message": "Session not found."}), 404

    (session_dir / "documentary_script.txt").write_text(script, encoding="utf-8")
    state = load_state(session_dir)
    state["script"] = script
    state["status"] = "script_edited"
    write_state(session_dir, state)
    log_event(session_dir, "Documentary script edited and saved from the frontend")
    return jsonify({
        "success": True,
        "script": script,
        "download_url": f"/api/session/{session_id}/download/documentary_script.txt",
    })


@app.route("/api/generate-audio", methods=["POST"])
def generate_audio_route():
    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id")
    voice = (payload.get("voice") or "Iapetus").strip() or "Iapetus"
    if not session_id:
        return jsonify({"success": False, "message": "session_id is required."}), 400

    session_dir = get_session_dir(session_id)
    if not session_dir.exists():
        return jsonify({"success": False, "message": "Session not found."}), 404

    state = load_state(session_dir)
    script = (session_dir / "documentary_script.txt").read_text(encoding="utf-8") if (session_dir / "documentary_script.txt").exists() else (state.get("script") or "")
    if not script:
        return jsonify({"success": False, "message": "Script must be generated before audio."}), 400

    audio_path = session_dir / "narration.wav"
    if audio_path.exists():
        audio_path.unlink()
    try:
        generated_audio = generate_real_audio(audio_path, script, voice)
    except Exception as exc:  # pragma: no cover
        generated_audio = None
        log_event(session_dir, f"Gemini TTS failed: {exc}")
    duration = get_duration(str(audio_path)) if generated_audio else 0.0
    if not generated_audio or duration <= 0:
        try:
            local_audio = generate_local_audio(audio_path, script, voice)
        except Exception as exc:  # pragma: no cover
            local_audio = None
            log_event(session_dir, f"Local Windows TTS failed: {exc}")
        duration = get_duration(str(audio_path)) if local_audio else 0.0
        if local_audio and duration > 0:
            log_event(session_dir, "Gemini unavailable; spoken local Windows TTS narration generated")
        else:
            log_event(session_dir, "No spoken narration could be generated")
            return jsonify({
                "success": False,
                "message": (
                    "Gemini TTS is unavailable and no local speech voice could be generated. "
                    "Check Gemini billing/API credits or install a Windows Hindi speech voice."
                ),
            }), 503
    audio_duration = get_duration(str(audio_path)) or duration

    state["status"] = "audio_ready"
    state["audio_file"] = str(audio_path)
    state["audio_duration"] = round(float(audio_duration), 2)
    state["voice"] = voice
    write_state(session_dir, state)
    log_event(session_dir, f"Narration audio generated with voice: {voice}; duration: {state['audio_duration']}s")
    return jsonify({
        "success": True,
        "voice": voice,
        "duration": round(float(audio_duration), 2),
        "audio_url": f"/api/session/{session_id}/download/narration.wav",
        "download_url": f"/api/session/{session_id}/download/narration.wav",
    })


@app.route("/api/generate-prompts", methods=["POST"])
def generate_prompts_route():
    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id")
    if not session_id:
        return jsonify({"success": False, "message": "session_id is required."}), 400

    session_dir = get_session_dir(session_id)
    if not session_dir.exists():
        return jsonify({"success": False, "message": "Session not found."}), 404

    state = load_state(session_dir)
    script = state.get("script") or (session_dir / "documentary_script.txt").read_text(encoding="utf-8") if (session_dir / "documentary_script.txt").exists() else ""
    if not script:
        return jsonify({"success": False, "message": "Script is missing."}), 400

    audio_duration = float(state.get("audio_duration") or get_duration(str(session_dir / "narration.wav")) or 0.0)
    required_count = max(3, count_required_images(
        audio_duration,
        float(state.get("image_seconds", 5)),
        float(state.get("transition_seconds", 1)),
    ))
    visual_style = (payload.get("visual_style") or state.get("visual_style") or "photorealistic").strip()
    if visual_style not in VISUAL_STYLES:
        return jsonify({"success": False, "message": "Unsupported visual style."}), 400
    state["visual_style"] = visual_style
    prompt_text = generate_prompt_text(state.get("topic") or "documentary subject", script, required_count, visual_style)
    prompt_file = session_dir / "image_prompts.txt"
    prompt_file.write_text(prompt_text, encoding="utf-8")

    prompts = parse_prompts(prompt_text)
    state["status"] = "prompts_ready"
    state["prompts"] = prompts
    state["required_prompt_count"] = len(prompts)
    generation_prompt_text = generate_generation_prompt_text(state.get("topic") or "documentary subject", prompts, visual_style)
    generation_prompt_file = session_dir / "image_generation_prompts.txt"
    generation_prompt_file.write_text(generation_prompt_text, encoding="utf-8")
    state["generation_prompt_file"] = str(generation_prompt_file)
    write_state(session_dir, state)
    log_event(session_dir, f"Image prompts generated: {len(prompts)} prompts saved in session folder")
    return jsonify({
        "success": True,
        "prompts": prompts,
        "generation_prompts": generation_prompt_text,
        "download_url": f"/api/session/{session_id}/download/image_prompts.txt",
        "generation_download_url": f"/api/session/{session_id}/download/image_generation_prompts.txt",
    })


@app.route("/api/upload-images", methods=["POST"])
def upload_images_route():
    session_id = request.form.get("session_id")
    if not session_id:
        return jsonify({"success": False, "message": "session_id is required."}), 400

    session_dir = get_session_dir(session_id)
    if not session_dir.exists():
        return jsonify({"success": False, "message": "Session not found."}), 404

    state = load_state(session_dir)
    prompts = state.get("prompts")
    if not prompts:
        prompts = parse_prompts((session_dir / "image_prompts.txt").read_text(encoding="utf-8")) if (session_dir / "image_prompts.txt").exists() else []
    if not prompts:
        return jsonify({"success": False, "message": "Generate prompts before uploading images."}), 400

    image_dir = session_dir / "images"
    image_dir.mkdir(exist_ok=True)
    uploaded_files = request.files.getlist("files")
    results = []

    for index, uploaded_file in enumerate(uploaded_files, start=1):
        if not uploaded_file or uploaded_file.filename == "":
            continue

        original_name = secure_filename(uploaded_file.filename)
        extension = Path(original_name).suffix.lower() or ".jpg"
        if extension not in {".jpg", ".jpeg", ".png", ".webp"}:
            results.append({"name": original_name, "status": "rejected", "reason": "Unsupported file type."})
            log_event(session_dir, f"Image upload rejected: {original_name} | unsupported file type")
            continue

        expected_index = image_index_from_filename(original_name)
        if not expected_index or expected_index > len(prompts):
            expected_index = index if index <= len(prompts) else len(prompts)

        candidate_path = image_dir / f"{expected_index}{extension}"
        uploaded_file.save(candidate_path)
        matched_prompt = prompts[expected_index - 1] if expected_index - 1 < len(prompts) else ""
        expected_prompt_preview = matched_prompt[:80]
        results.append({
            "name": original_name,
            "status": "accepted",
            "target": f"{expected_index}{extension}",
            "expected_prompt": expected_prompt_preview,
        })
        state.setdefault("validated_images", {})[str(expected_index)] = str(candidate_path)
        log_event(session_dir, f"Image validation passed: {candidate_path.name} matched prompt {expected_index}")

    state["status"] = "images_validated" if results else "images_pending"
    write_state(session_dir, state)
    uploaded_count = len({
        int(Path(path).stem)
        for path in image_dir.iterdir()
        if path.suffix.lower() in IMAGE_EXTENSIONS and path.stem.isdigit()
    })
    missing_numbers = [number for number in range(1, len(prompts) + 1) if not (image_dir / f"{number}.jpg").exists() and not any((image_dir / f"{number}{extension}").exists() for extension in IMAGE_EXTENSIONS - {".jpg"})]
    return jsonify({
        "success": True,
        "results": results,
        "required_count": len(prompts),
        "uploaded_count": uploaded_count,
        "missing_numbers": missing_numbers,
    })


def build_video_command(image_files, audio_path, output_video, audio_duration,
                        image_seconds=5, transition_seconds=1, narration_volume=NARRATION_VOLUME):
    """Build an FFmpeg command whose visual stream covers the narration."""
    image_duration = (
        audio_duration + (len(image_files) - 1) * transition_seconds
    ) / len(image_files)

    command = ["ffmpeg", "-y"]
    for image_path in image_files:
        command += [
            "-loop", "1",
            "-t", f"{image_duration:.3f}",
            "-i", str(image_path),
        ]
    command += ["-i", str(audio_path)]

    filters = []
    for index in range(len(image_files)):
        filters.append(
            f"[{index}:v]scale=1920:1080:force_original_aspect_ratio=increase,"
            f"crop=1920:1080,"
            "zoompan=z='min(zoom+0.0007,1.08)':"
            "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            "d=1:s=1920x1080:fps=30,setsar=1,format=yuv420p"
            f"[v{index}]"
        )

    current = "v0"
    offset = image_duration - transition_seconds
    for index in range(1, len(image_files)):
        next_video = f"x{index}"
        filters.append(
            f"[{current}][v{index}]xfade=transition=smoothleft:"
            f"duration={transition_seconds}:offset={offset:.3f}[{next_video}]"
        )
        current = next_video
        offset += image_duration - transition_seconds

    narration_input = len(image_files)
    filters.append(f"[{narration_input}:a]volume={narration_volume}[narration]")
    command += [
        "-filter_complex", ";".join(filters),
        "-map", f"[{current}]",
        "-map", "[narration]",
        "-t", f"{audio_duration:.3f}",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-r", "30",
        "-movflags", "+faststart",
        str(output_video),
    ]
    return command


@app.route("/api/build-video", methods=["POST"])
def build_video_route():
    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id")
    if not session_id:
        return jsonify({"success": False, "message": "session_id is required."}), 400

    session_dir = get_session_dir(session_id)
    if not session_dir.exists():
        return jsonify({"success": False, "message": "Session not found."}), 404

    image_dir = session_dir / "images"
    files = sorted(
        [path for path in image_dir.iterdir() if path.suffix.lower() in IMAGE_EXTENSIONS],
        key=lambda path: int(path.stem) if path.stem.isdigit() else 999,
    )
    if not files:
        return jsonify({"success": False, "message": "Upload images before building the video."}), 400

    state = load_state(session_dir)
    try:
        image_seconds = render_setting(payload, "image_seconds", state.get("image_seconds", 5), 1, 30)
        transition_seconds = render_setting(payload, "transition_seconds", state.get("transition_seconds", 1), 0, 10)
        narration_volume = render_setting(payload, "narration_volume", state.get("narration_volume", NARRATION_VOLUME), 0, 3)
    except ValueError as error:
        return jsonify({"success": False, "message": str(error)}), 400
    if transition_seconds >= image_seconds:
        return jsonify({"success": False, "message": "transition_seconds must be less than image_seconds."}), 400
    required_count = len(state.get("prompts") or [])
    expected_numbers = set(range(1, required_count + 1))
    actual_numbers = {int(path.stem) for path in files if path.stem.isdigit()}
    missing_numbers = sorted(expected_numbers - actual_numbers)
    if required_count and missing_numbers:
        return jsonify({
            "success": False,
            "message": f"Missing images: {', '.join(map(str, missing_numbers))}.",
            "required_count": required_count,
            "uploaded_count": len(actual_numbers),
            "missing_numbers": missing_numbers,
        }), 400

    audio_path = session_dir / "narration.wav"
    if not audio_path.exists():
        return jsonify({"success": False, "message": "Generate narration audio before building the video."}), 400

    output_video = session_dir / "documentary_video.mp4"
    audio_duration = get_duration(str(audio_path))
    if audio_duration <= 0:
        return jsonify({"success": False, "message": "Narration audio has no readable duration."}), 400

    cmd = build_video_command(
        files, audio_path, output_video, audio_duration,
        image_seconds, transition_seconds, narration_volume,
    )
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return jsonify({"success": False, "message": result.stderr or "Video assembly failed."}), 500

    produced_duration = get_duration(str(output_video))
    if abs(produced_duration - audio_duration) > 0.15:
        return jsonify({
            "success": False,
            "message": (
                f"Final video duration does not match narration: "
                f"audio={audio_duration:.3f}s, video={produced_duration:.3f}s."
            ),
        }), 500

    state["status"] = "video_ready"
    state["video_file"] = str(output_video)
    state["image_seconds"] = image_seconds
    state["transition_seconds"] = transition_seconds
    state["narration_volume"] = narration_volume
    write_state(session_dir, state)
    log_event(session_dir, f"Video assembled from ordered images and narration audio: {output_video.name}")
    return jsonify({"success": True, "video_url": f"/api/session/{session_id}/download/documentary_video.mp4", "download_url": f"/api/session/{session_id}/download/documentary_video.mp4"})


@app.route("/api/finalize-music", methods=["POST"])
def finalize_music_route():
    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id")
    if not session_id:
        return jsonify({"success": False, "message": "session_id is required."}), 400

    session_dir = get_session_dir(session_id)
    if not session_dir.exists():
        return jsonify({"success": False, "message": "Session not found."}), 404

    state = load_state(session_dir)
    try:
        volume = render_setting(payload, "bgm_volume", state.get("bgm_volume", BGM_VOLUME), 0, 1)
    except ValueError as error:
        return jsonify({"success": False, "message": str(error)}), 400

    video_src = session_dir / "documentary_video.mp4"
    if not video_src.exists():
        return jsonify({"success": False, "message": "Build the video before adding background music."}), 400

    music_files = [
        path for path in BGM_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in BGM_EXTENSIONS
    ] if BGM_DIR.exists() else []
    if not music_files:
        return jsonify({"success": False, "message": f"No background music files found in {BGM_DIR}."}), 500
    music_path = random.choice(music_files)

    final_video = session_dir / "documentary_final_with_music.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_src),
        "-stream_loop",
        "-1",
        "-i",
        str(music_path),
        "-filter_complex",
        f"[1:a]volume={volume}[bg];[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[a]",
        "-map",
        "0:v",
        "-map",
        "[a]",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(final_video),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return jsonify({"success": False, "message": result.stderr or "Music binding failed."}), 500

    state["status"] = "finalized"
    state["bgm_volume"] = volume
    state["music_file"] = str(final_video)
    write_state(session_dir, state)
    log_event(session_dir, f"Background music added: track={music_path.name} volume={volume} final video saved")

    final_folder = session_dir
    log_event(final_folder, "Session completed: all generated artifacts and final video saved in the topic project folder.")
    state["final_folder"] = str(final_folder)
    write_state(session_dir, state)
    return jsonify({
        "success": True,
        "final_video_url": f"/api/session/{session_id}/download/documentary_final_with_music.mp4",
        "final_folder": str(final_folder),
        "log_path": str(final_folder / "generation_log.txt"),
        "music_track": music_path.name,
        "music_volume": volume,
    })


@app.route("/api/session/<session_id>/state")
def get_session_state(session_id):
    session_dir = get_session_dir(session_id)
    if not session_dir.exists():
        return jsonify({"success": False, "message": "Session not found."}), 404
    state = load_state(session_dir)
    return jsonify({"success": True, "state": state})


if __name__ == "__main__":
    app.run(
        debug=os.getenv("FLASK_DEBUG") == "1",
        use_reloader=False,
        host="0.0.0.0",
        port=5000,
    )

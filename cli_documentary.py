#!/usr/bin/env python3
"""
Modular CLI Documentary Generator

Each step can run independently. Workflow:
1. Script generation (optional - can skip)
2. Audio generation (REQUIRED first) -> calculates duration
3. Image calculation (5 sec per image) -> asks for image count
4. Image upload (folder path or individual) -> upload images
5. Video creation with clip options

Usage:
  python cli_documentary.py --step script
  python cli_documentary.py --step audio
  python cli_documentary.py --step images
  python cli_documentary.py --step video
  python cli_documentary.py --step all
"""

import os
import re
import json
import math
import wave
import shutil
import subprocess
import argparse
import sys
from pathlib import Path
from typing import Optional, List, Tuple

try:
    from groq import Groq
except ImportError:
    Groq = None

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

try:
    import edge_tts
except ImportError:
    edge_tts = None


# ============================================================
# CONFIG
# ============================================================

GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview")
VOICE_NAME = os.getenv("TTS_VOICE", "Iapetus")

IMAGE_SECONDS = 5
TRANSITION_SECONDS = 1

FPS = 30
WIDTH = 1920
HEIGHT = 1080

PROJECTS_DIR = Path("projects")
BGM_DIR = Path("BGM")
NARRATION_VOLUME = 1.5
BGM_VOLUME = 0.20

TTS_CHUNK_CHARS = 5000
TTS_MAX_RETRIES = 5
TTS_SAMPLE_RATE = 24000
TTS_CHANNELS = 1
TTS_SAMPLE_WIDTH = 2


# ============================================================
# UTILITIES
# ============================================================

def check_command(command: str) -> None:
    if shutil.which(command) is None:
        raise RuntimeError(
            f"{command} not found in PATH. Install FFmpeg and ensure it's available."
        )


def slugify(value: str) -> str:
    value = re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE).strip("._")
    return value[:80] or "documentary"


def get_duration(filename: str) -> float:
    if not Path(filename).exists():
        return 0.0
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
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


def count_required_images(audio_duration: float, image_seconds: float = IMAGE_SECONDS) -> int:
    if audio_duration <= 0:
        return 1
    return max(1, math.ceil(float(audio_duration) / float(image_seconds)))


def write_wave(filename: str, pcm_bytes: bytes, channels: int = TTS_CHANNELS, 
               rate: int = TTS_SAMPLE_RATE, sample_width: int = TTS_SAMPLE_WIDTH) -> None:
    if not pcm_bytes:
        raise RuntimeError("Cannot write WAV: audio data is empty.")
    with wave.open(str(filename), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm_bytes)


def parse_prompts(text: str) -> List[str]:
    pattern = r"^\s*(\d+)\.\s*(.*?)(?=^\s*\d+\.\s*|\Z)"
    matches = re.findall(pattern, text, flags=re.MULTILINE | re.DOTALL)
    return [prompt.strip() for _, prompt in matches if prompt.strip()]


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
    while True:
        response = input(prompt + suffix).strip().lower()
        if not response:
            return default
        if response in ("y", "yes"):
            return True
        if response in ("n", "no"):
            return False
        print("Please enter 'y' or 'n'.")


def ask_number(prompt: str, default: float, minimum: float, maximum: float) -> float:
    while True:
        response = input(f"{prompt} ({minimum}-{maximum}, default {default}):\n> ").strip()
        if not response:
            return default
        try:
            value = float(response)
        except ValueError:
            print("Please enter a valid number.")
            continue
        if not math.isfinite(value) or value < minimum or value > maximum:
            print(f"Value must be between {minimum} and {maximum}.")
            continue
        return value


def ask_path(prompt: str, must_exist: bool = True) -> Path:
    while True:
        response = input(f"{prompt}:\n> ").strip().strip('"')
        if not response:
            print("Path cannot be empty.")
            continue
        path = Path(response).expanduser().resolve()
        if must_exist and not path.exists():
            print(f"Path does not exist: {path}")
            continue
        return path


def get_groq_client() -> Optional[Groq]:
    key = os.getenv("GROQ_API_KEY")
    if not key or Groq is None:
        return None
    return Groq(api_key=key)


def get_gemini_client():
    key = os.getenv("GEMINI_API_KEY")
    if not key or genai is None:
        return None
    try:
        return genai.Client(api_key=key)
    except Exception:
        return None


# ============================================================
# STEP 1: SCRIPT GENERATION
# ============================================================

def generate_script(topic: str, target_duration: float) -> str:
    prompt = f"""
You are an expert Hindi documentary narrator and scriptwriter.

DOCUMENTARY TOPIC:
{topic}

TARGET LENGTH:
{target_duration:.1f} seconds

Write ONE continuous Hindi narration for an AI voice-over.

CRITICAL OUTPUT RULES:
- Output ONLY the narration.
- Do NOT write a title, headings, labels, scene headings, image prompts, camera directions.
- Do NOT write bullet points, production notes, or address the editor/viewer.
- Keep it natural when read aloud by TTS.
- Use smooth transitions between paragraphs.
- Do not begin with a heading; begin directly with a strong documentary hook.
- Preserve chronology and logical flow.
- Use punctuation suitable for natural speech.

NO REPETITION — STRICT:
- Do NOT repeat the same word, phrase, idea, or fact anywhere.
- Do NOT use the same noun, verb, or adjective in consecutive/nearby sentences.
- Do NOT restate the topic name more than twice.
- Vary sentence structure — short, medium, and long sentences mixed.

NO GENERIC CONTENT — STRICT:
- Every sentence must be specific to "{topic}".
- Do NOT write filler like "यह कहानी हमें बताती है...", "भारत की धरती पर...", "समय के साथ...".
- Use concrete details: specific places, people, events, time periods.
- If you don't know a specific fact, describe a vivid concrete scene.

FACTUAL SAFETY:
- Do not invent names, dates, numbers, locations, quotations, evidence, arrests, operations, events.
- Distinguish confirmed facts from claims, reports, allegations, disputed info, unverified claims.

STYLE:
- Hindi
- Serious cinematic documentary
- Investigative but factual
- Suspenseful without sensational fabrication
- Natural spoken Hindi
- Strong specific opening hook
- Clear chronological storytelling
- Context, events, claims/evidence, uncertainty, consequences, memorable ending

Return ONLY the final continuous Hindi narration.
"""

    client = get_groq_client()
    if not client:
        raise RuntimeError("GROQ_API_KEY not set or Groq not installed.")

    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            print(f"  Groq attempt {attempt}/{max_retries}...")
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": "You are a professional Hindi documentary writer."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=2000,
            )
            script = response.choices[0].message.content.strip()
            if script:
                return script
        except Exception as e:
            print(f"  Groq error: {e}")
            if attempt < max_retries:
                wait = min(2 ** attempt, 30)
                print(f"  Retrying in {wait}s...")
                import time
                time.sleep(wait)
            else:
                raise

    raise RuntimeError("Groq failed to generate script.")


def step_script(project_dir: Path, topic: str, target_duration: float, force: bool = False) -> str:
    script_file = project_dir / "documentary_script.txt"
    
    if script_file.exists() and script_file.stat().st_size > 50 and not force:
        script = script_file.read_text(encoding="utf-8").strip()
        print(f"[OK] SKIP: Existing script found: {script_file}")
        print(f"[OK] Characters: {len(script)}")
        return script
    
    print("\n[1/5] Generating documentary script...")
    script = generate_script(topic, target_duration)
    script_file.write_text(script, encoding="utf-8")
    print(f"[OK] Script saved: {script_file}")
    print(f"[OK] Characters: {len(script)}")
    return script


# ============================================================
# STEP 2: AUDIO GENERATION
# ============================================================

def split_tts_chunks(text: str, max_chars: int = TTS_CHUNK_CHARS) -> List[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        raise RuntimeError("TTS received an empty script.")
    
    chunks = []
    current = ""
    pieces = re.split(r"(?<=[।!?])\s+|\n+", text)
    
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        if len(piece) > max_chars:
            for start in range(0, len(piece), max_chars):
                sub = piece[start:start + max_chars].strip()
                if sub:
                    if current:
                        chunks.append(current)
                        current = ""
                    chunks.append(sub)
            continue
        
        candidate = f"{current} {piece}".strip()
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = piece
        else:
            current = candidate
    
    if current:
        chunks.append(current)
    
    return chunks


def decode_audio_data(data):
    if data is None:
        return None
    if isinstance(data, bytes):
        return data
    if isinstance(data, bytearray):
        return bytes(data)
    if isinstance(data, str):
        try:
            import base64
            return base64.b64decode(data)
        except Exception:
            return None
    return None


def extract_interaction_audio(interaction):
    audio = getattr(interaction, "output_audio", None) or getattr(interaction, "outputAudio", None)
    if audio is None and isinstance(interaction, dict):
        audio = interaction.get("output_audio") or interaction.get("outputAudio")
    if audio is None:
        return None
    data = getattr(audio, "data", None)
    if data is None and isinstance(audio, dict):
        data = audio.get("data")
    return decode_audio_data(data)


def extract_legacy_audio(response):
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        if not content:
            continue
        parts = getattr(content, "parts", None) or []
        for part in parts:
            inline_data = getattr(part, "inline_data", None)
            if inline_data is None:
                continue
            data = getattr(inline_data, "data", None)
            audio = decode_audio_data(data)
            if audio:
                return audio
    return None


def normalize_pcm(audio_bytes: bytes) -> Optional[bytes]:
    if not audio_bytes:
        return None
    if audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
        import io
        with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
            channels = wf.getnchannels()
            rate = wf.getframerate()
            width = wf.getsampwidth()
            if channels != TTS_CHANNELS or rate != TTS_SAMPLE_RATE or width != TTS_SAMPLE_WIDTH:
                raise RuntimeError(f"Unexpected TTS WAV format: {channels}ch, {rate}Hz, {width * 8}bit.")
            return wf.readframes(wf.getnframes())
    return audio_bytes


def generate_tts_chunk(chunk: str, chunk_number: int, total_chunks: int) -> bytes:
    prompt = (
        "Synthesize the following Hindi documentary narration as speech. "
        "Read ONLY the text after TRANSCRIPT. Do not explain, summarize, "
        "translate, rewrite, or add words. Use a deep, mature, serious, "
        "authoritative documentary voice with natural Hindi pronunciation, "
        "controlled emotion, and natural pauses.\n\n"
        "TRANSCRIPT:\n"
        f"{chunk}"
    )
    
    last_error = None
    for attempt in range(1, TTS_MAX_RETRIES + 1):
        try:
            print(f"  TTS chunk {chunk_number}/{total_chunks} attempt {attempt}/{TTS_MAX_RETRIES}...")
            
            try:
                client = get_gemini_client()
                if client:
                    interaction = client.interactions.create(
                        model=TTS_MODEL,
                        input=prompt,
                        response_format={"type": "audio"},
                        generation_config={
                            "speech_config": [{
                                "voice": VOICE_NAME,
                                "language_code": "hi-IN",
                            }]
                        },
                    )
                    audio = extract_interaction_audio(interaction)
                    if audio:
                        return normalize_pcm(audio)
            except Exception as interaction_error:
                last_error = interaction_error
                print(f"    Interactions TTS unavailable: {interaction_error}")
            
            client = get_gemini_client()
            if client and types:
                response = client.models.generate_content(
                    model=TTS_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name=VOICE_NAME
                                )
                            ),
                        ),
                    ),
                )
                audio = extract_legacy_audio(response)
                if audio:
                    return normalize_pcm(audio)
            
            raise RuntimeError("Gemini returned a response but no audio bytes were present.")
            
        except Exception as e:
            last_error = e
            print(f"    TTS error: {e}")
            if attempt < TTS_MAX_RETRIES:
                wait = min(2 ** attempt, 30)
                print(f"    Retrying in {wait}s...")
                import time
                time.sleep(wait)
    
    raise RuntimeError(f"TTS chunk {chunk_number} failed after {TTS_MAX_RETRIES} attempts: {last_error}")


def generate_voice_fallback(script: str, output_path: Path) -> None:
    if not edge_tts:
        raise RuntimeError("edge-tts not installed. Install with: pip install edge-tts")
    
    import asyncio
    
    hindi_voices = {"male": "hi-IN-MadhurNeural", "female": "hi-IN-SwaraNeural"}
    voice = hindi_voices.get("female", "hi-IN-SwaraNeural")
    
    mp3_path = output_path.with_suffix(".mp3")
    
    async def _synthesize():
        communicate = edge_tts.Communicate(script, voice)
        await communicate.save(str(mp3_path))
    
    asyncio.run(_synthesize())
    
    if not mp3_path.exists() or mp3_path.stat().st_size < 1000:
        raise RuntimeError("edge-tts produced no audio output")
    
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", str(mp3_path), "-ar", "24000", "-ac", "1", str(output_path)],
        capture_output=True, text=True, check=False,
    )
    mp3_path.unlink(missing_ok=True)
    if result.returncode != 0 or not output_path.exists() or output_path.stat().st_size < 1000:
        raise RuntimeError(f"ffmpeg conversion failed: {result.stderr}")


def find_audio_file(project_dir: Path) -> Optional[Path]:
    """Find narration audio file with flexible naming (topic_narration.wav or narration.wav)."""
    audio_files = list(project_dir.glob("*_narration.wav"))
    if not audio_files:
        audio_files = list(project_dir.glob("narration.wav"))
    if not audio_files:
        return None
    return audio_files[0]


def step_audio(project_dir: Path, script: str, force: bool = False, use_fallback: bool = False) -> str:
    audio_file = find_audio_file(project_dir)
    if audio_file is None:
        audio_file = project_dir / "narration.wav"
    
    if audio_file.exists() and audio_file.stat().st_size > 1000 and not force:
        print(f"[OK] SKIP: Existing audio found: {audio_file}")
        return str(audio_file)
    
    print("\n[2/5] Generating Hindi voice...")
    
    if use_fallback:
        print("  Using edge-tts fallback...")
        generate_voice_fallback(script, audio_file)
    else:
        chunks = split_tts_chunks(script)
        print(f"[OK] TTS chunks: {len(chunks)}")
        
        pcm_parts = []
        for index, chunk in enumerate(chunks, start=1):
            audio = generate_tts_chunk(chunk, index, len(chunks))
            if not audio:
                raise RuntimeError(f"TTS chunk {index} produced empty audio.")
            pcm_parts.append(audio)
        
        combined_pcm = b"".join(pcm_parts)
        
        if len(combined_pcm) < TTS_SAMPLE_RATE * TTS_CHANNELS * TTS_SAMPLE_WIDTH:
            raise RuntimeError("Generated narration is suspiciously short or empty.")
        
        if audio_file.exists():
            audio_file.unlink()
        
        write_wave(str(audio_file), combined_pcm)
        
        if not audio_file.exists() or audio_file.stat().st_size <= 44:
            raise RuntimeError("TTS WAV file was not created correctly.")
    
    print(f"[OK] Audio saved: {audio_file}")
    return str(audio_file)


# ============================================================
# STEP 3: IMAGE CALCULATION & UPLOAD
# ============================================================

def step_images(project_dir: Path, audio_file: str, force: bool = False) -> Tuple[int, Path]:
    print("\n[3/5] Calculating required images...")
    
    audio_duration = get_duration(audio_file)
    print(f"[OK] Audio duration: {audio_duration:.3f} seconds")
    
    image_count = count_required_images(audio_duration, IMAGE_SECONDS)
    print(f"[OK] Images required (at {IMAGE_SECONDS} sec/image): {image_count}")
    
    prompts_file = project_dir / "image_prompts.txt"
    if prompts_file.exists() and prompts_file.stat().st_size > 50 and not force:
        existing_prompts = parse_prompts(prompts_file.read_text(encoding="utf-8"))
        if len(existing_prompts) == image_count:
            print(f"[OK] SKIP: Existing prompts found ({len(existing_prompts)} prompts)")
        else:
            print(f"⚠ Prompt count mismatch: have {len(existing_prompts)}, need {image_count}")
    else:
        print("⚠ No image prompts found. Run script generation first or create prompts manually.")
    
    image_dir = project_dir / "images"
    image_dir.mkdir(exist_ok=True)
    
    existing_images = sorted(
        [f for f in image_dir.iterdir() if f.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp')]
    )
    print(f"[OK] Existing images in folder: {len(existing_images)}")
    
    if len(existing_images) >= image_count and not force:
        print(f"[OK] SKIP: Already have {len(existing_images)} images (need {image_count})")
        return image_count, image_dir
    
    print(f"\n--- IMAGE UPLOAD STEP ---")
    print(f"Required: {image_count} images")
    print(f"Current: {len(existing_images)} images")
    print(f"Missing: {max(0, image_count - len(existing_images))} images")
    
    if not ask_yes_no("Do you want to upload/add images now?", default=True):
        print("Skipping image upload. You can add images later to:", image_dir)
        return image_count, image_dir
    
    upload_method = input("Upload method: (1) Folder path  (2) Individual files  (3) Skip\n> ").strip()
    
    if upload_method == "1":
        folder = ask_path("Enter folder path containing images", must_exist=True)
        count = 0
        for img_file in sorted(folder.iterdir()):
            if img_file.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp') and count < image_count:
                dst = image_dir / f"{count + 1:03d}{img_file.suffix.lower()}"
                shutil.copy2(img_file, dst)
                count += 1
                print(f"  Copied: {img_file.name} -> {dst.name}")
        print(f"[OK] Copied {count} images")
    
    elif upload_method == "2":
        for i in range(len(existing_images) + 1, image_count + 1):
            img_path = ask_path(f"Enter path for image {i}/{image_count}", must_exist=True)
            dst = image_dir / f"{i:03d}{img_path.suffix.lower()}"
            shutil.copy2(img_path, dst)
            print(f"  Copied: {img_path.name} -> {dst.name}")
    
    else:
        print("Skipping image upload.")
    
    return image_count, image_dir


# ============================================================
# STEP 4: VIDEO CREATION
# ============================================================

def create_video(
    project_dir: Path,
    audio_file: str,
    image_dir: Path,
    image_count: int,
    output_name: str,
    image_seconds: float = IMAGE_SECONDS,
    transition_seconds: float = TRANSITION_SECONDS,
    narration_volume: float = NARRATION_VOLUME,
    bgm_volume: float = BGM_VOLUME,
    clip_mode: bool = False,
    clip_start: float = 0,
    clip_duration: Optional[float] = None,
) -> str:
    
    print("\n[4/5] Preparing video creation...")
    
    audio_duration = get_duration(audio_file)
    if clip_mode and clip_duration:
        audio_duration = min(clip_duration, audio_duration - clip_start)
    
    image_duration = audio_duration / image_count if image_count > 0 else image_seconds
    
    print(f"[OK] Audio duration: {audio_duration:.3f}s")
    print(f"[OK] Image count: {image_count}")
    print(f"[OK] Image duration: {image_duration:.3f}s")
    print(f"[OK] Transition: {transition_seconds}s")
    
    IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp')
    
    def image_number(source: Path) -> int:
        match = re.search(r"\d+", source.stem[:6])
        if not match:
            raise RuntimeError(f"Image number must appear in filename: {source.name}")
        return int(match.group())
    
    all_images = sorted(
        [f for f in image_dir.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS],
        key=image_number
    )
    
    if len(all_images) < image_count:
        raise RuntimeError(f"Need {image_count} images, found {len(all_images)}. Add images to {image_dir}")
    
    all_images = all_images[:image_count]
    print(f"[OK] Using {len(all_images)} images")
    
    BGM_EXTENSIONS = (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac")
    BGM_FILES = [
        path for path in BGM_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in BGM_EXTENSIONS
    ] if BGM_DIR.exists() else []
    
    if not BGM_FILES:
        print("⚠ No BGM files found in BGM/ directory. Video will have no background music.")
    
    output_video = project_dir / output_name
    
    if output_video.exists() and output_video.stat().st_size > 10000 and not clip_mode:
        if not ask_yes_no(f"Video exists: {output_video}. Overwrite?", default=False):
            print("Skipping video creation.")
            return str(output_video)
    
    encoder_check = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"],
        capture_output=True, text=True,
    )
    use_nvenc = "h264_nvenc" in encoder_check.stdout
    
    if use_nvenc:
        video_codec = [
            "-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr",
            "-cq", "20", "-b:v", "8M", "-maxrate", "12M", "-bufsize", "16M",
        ]
        print("[OK] Video encoder: NVIDIA NVENC")
    else:
        video_codec = ["-c:v", "libx264", "-preset", "medium", "-crf", "20"]
        print("[OK] Video encoder: CPU libx264")
    
    cmd = ["ffmpeg", "-y"]
    
    for image in all_images:
        cmd += ["-loop", "1", "-t", str(image_duration), "-i", str(image)]
    
    if clip_mode and clip_start > 0:
        cmd += ["-ss", str(clip_start), "-i", audio_file]
    else:
        cmd += ["-i", audio_file]
    
    if BGM_FILES:
        import random
        selected_bgm = random.choice(BGM_FILES)
        cmd += ["-stream_loop", "-1", "-i", str(selected_bgm)]
        print(f"[OK] Background music: {selected_bgm.name} ({bgm_volume:.0%} volume)")
    else:
        selected_bgm = None
    
    filters = []
    zoompan_frames = math.ceil(image_duration * FPS)
    
    for i in range(image_count):
        filters.append(
            f"[{i}:v]"
            f"scale={WIDTH}:{HEIGHT}:"
            f"force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT},"
            f"zoompan=z='min(zoom+0.0007,1.08)':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={zoompan_frames}:s={WIDTH}x{HEIGHT}:fps={FPS},"
            f"setsar=1,"
            f"format=yuv420p"
            f"[v{i}]"
        )
    
    current = "v0"
    offset = image_duration - transition_seconds
    
    for i in range(1, image_count):
        output = f"x{i}"
        filters.append(
            f"[{current}][v{i}]"
            f"xfade=transition=fade:duration={transition_seconds}:offset={offset}"
            f"[{output}]"
        )
        current = output
        offset += image_duration - transition_seconds
    
    narration_input = image_count
    music_input = image_count + 1 if BGM_FILES else None
    
    if BGM_FILES:
        filters.extend([
            f"[{narration_input}:a]volume={narration_volume}[narration]",
            f"[{music_input}:a]volume={bgm_volume}[music]",
            "[narration][music]amix=inputs=2:duration=first:dropout_transition=2[aout]",
        ])
        audio_map = "[aout]"
    else:
        filters.append(f"[{narration_input}:a]volume={narration_volume}[aout]")
        audio_map = "[aout]"
    
    filter_complex = ";".join(filters)
    
    cmd += [
        "-filter_complex", filter_complex,
        "-map", f"[{current}]",
        "-map", audio_map,
        "-t", f"{audio_duration:.3f}",
        *video_codec,
        "-c:a", "aac", "-b:a", "192k",
        "-r", str(FPS),
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_video),
    ]
    
    print(f"\n[5/5] Creating video...")
    print(f"  Output: {output_video}")
    print(f"  Duration: {audio_duration:.3f}s")
    
    subprocess.run(cmd, check=True)
    
    produced_duration = get_duration(str(output_video))
    tolerance = 0.15
    
    if abs(produced_duration - audio_duration) > tolerance:
        raise RuntimeError(
            f"Final A/V duration mismatch: audio={audio_duration:.3f}s, video={produced_duration:.3f}s"
        )
    
    print(f"[OK] Video created: {output_video}")
    print(f"[OK] Final duration: {produced_duration:.3f}s")
    return str(output_video)


def step_video(
    project_dir: Path,
    audio_file: str,
    image_dir: Path,
    image_count: int,
    clip_mode: bool = False,
    args: Optional[argparse.Namespace] = None,
) -> str:
    
    print("\n--- VIDEO CREATION STEP ---")
    
    # Use CLI args if provided, otherwise prompt interactively
    if args and args.output:
        output_name = args.output
    else:
        output_name = input("Output video filename (default: documentary.mp4):\n> ").strip()
    if not output_name:
        output_name = "documentary.mp4"
    if not output_name.endswith(".mp4"):
        output_name += ".mp4"
    
    if args and args.image_seconds is not None:
        image_seconds = args.image_seconds
    else:
        image_seconds = ask_number("Seconds per image", IMAGE_SECONDS, 1, 30)
    
    if args and args.transition_seconds is not None:
        transition_seconds = args.transition_seconds
    else:
        transition_seconds = ask_number("Transition seconds", TRANSITION_SECONDS, 0, image_seconds - 0.1)
    
    if args and args.narration_volume is not None:
        narration_volume = args.narration_volume
    else:
        narration_volume = ask_number("Narration volume", NARRATION_VOLUME, 0, 3)
    
    if args and args.bgm_volume is not None:
        bgm_volume = args.bgm_volume
    else:
        bgm_volume = ask_number("BGM volume (0-1)", BGM_VOLUME, 0, 1)
    
    clip_start = 0
    clip_duration = None
    
    if clip_mode:
        if args and args.clip_start is not None and args.clip_duration is not None:
            clip_start = args.clip_start
            clip_duration = args.clip_duration
        else:
            if ask_yes_no("Enable clip mode (trim video)?", default=False):
                audio_duration = get_duration(audio_file)
                clip_start = ask_number("Clip start (seconds)", 0, 0, audio_duration - 1)
                clip_duration = ask_number("Clip duration (seconds)", audio_duration - clip_start, 1, audio_duration - clip_start)
    
    return create_video(
        project_dir=project_dir,
        audio_file=audio_file,
        image_dir=image_dir,
        image_count=image_count,
        output_name=output_name,
        image_seconds=image_seconds,
        transition_seconds=transition_seconds,
        narration_volume=narration_volume,
        bgm_volume=bgm_volume,
        clip_mode=clip_mode,
        clip_start=clip_start,
        clip_duration=clip_duration,
    )


# ============================================================
# MAIN CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Modular CLI Documentary Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli_documentary.py --step all
  python cli_documentary.py --step script --topic "Indian Railways" --duration 60
  python cli_documentary.py --step audio --project projects/my_topic
  python cli_documentary.py --step images --project projects/my_topic
  python cli_documentary.py --step video --project projects/my_topic --clip
  python cli_documentary.py --step all --topic "History of India" --duration 120 --force
        """
    )
    
    parser.add_argument(
        "--step",
        choices=["script", "audio", "images", "video", "all"],
        default="all",
        help="Pipeline step to run (default: all)"
    )
    
    parser.add_argument("--topic", help="Documentary topic (required for script step)")
    parser.add_argument("--duration", type=float, help="Target audio duration in seconds (20-200)")
    parser.add_argument("--project", help="Project directory path (for non-script steps)")
    parser.add_argument("--force", action="store_true", help="Force regeneration even if files exist")
    parser.add_argument("--fallback-tts", action="store_true", help="Use edge-tts fallback instead of Gemini TTS")
    parser.add_argument("--clip", action="store_true", help="Enable clip mode for video step")
    parser.add_argument("--output", help="Output video filename")
    parser.add_argument("--image-seconds", type=float, help="Seconds per image")
    parser.add_argument("--transition-seconds", type=float, help="Transition seconds")
    parser.add_argument("--narration-volume", type=float, help="Narration volume")
    parser.add_argument("--bgm-volume", type=float, help="BGM volume (0-1)")
    parser.add_argument("--clip-start", type=float, help="Clip start time (seconds)")
    parser.add_argument("--clip-duration", type=float, help="Clip duration (seconds)")
    
    args = parser.parse_args()
    
    check_command("ffmpeg")
    check_command("ffprobe")
    
    if args.step in ("script", "all"):
        if not args.topic:
            args.topic = input("\nEnter documentary topic:\n> ").strip()
        if not args.topic:
            print("Topic is required.")
            sys.exit(1)
        
        if not args.duration:
            args.duration = ask_number("Target audio duration (seconds)", 60, 20, 200)
        
        project_name = slugify(args.topic)
        project_dir = PROJECTS_DIR / project_name
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "images").mkdir(exist_ok=True)
        (project_dir / "topic.txt").write_text(args.topic, encoding="utf-8")
        
        script = step_script(project_dir, args.topic, args.duration, args.force)
        
        if args.step == "script":
            print(f"\n[OK] Script step complete. Project: {project_dir}")
            return
    
    if args.step in ("audio", "all"):
        if args.step == "all":
            project_dir = PROJECTS_DIR / slugify(args.topic)
        else:
            project_dir = Path(args.project).resolve()
        
        script_file = project_dir / "documentary_script.txt"
        if not script_file.exists():
            print(f"Script not found: {script_file}")
            sys.exit(1)
        
        script = script_file.read_text(encoding="utf-8").strip()
        audio_file = step_audio(project_dir, script, args.force, args.fallback_tts)
        
        if args.step == "audio":
            print(f"\n[OK] Audio step complete. Audio: {audio_file}")
            return
    
    if args.step in ("images", "all"):
        if args.step == "all":
            project_dir = PROJECTS_DIR / slugify(args.topic)
        else:
            project_dir = Path(args.project).resolve()
        
        audio_file = find_audio_file(project_dir)
        if audio_file is None:
            print(f"Audio not found in: {project_dir}")
            sys.exit(1)
        
        image_count, image_dir = step_images(project_dir, str(audio_file), args.force)
        
        if args.step == "images":
            print(f"\n[OK] Images step complete. Images: {image_dir} ({image_count} required)")
            return
    
    if args.step in ("video", "all"):
        if args.step == "all":
            project_dir = PROJECTS_DIR / slugify(args.topic)
        else:
            project_dir = Path(args.project).resolve()
        
        audio_file = find_audio_file(project_dir)
        if audio_file is None:
            print(f"Audio not found in: {project_dir}")
            sys.exit(1)
        
        image_dir = project_dir / "images"
        prompts_file = project_dir / "image_prompts.txt"
        if prompts_file.exists():
            image_count = len(parse_prompts(prompts_file.read_text(encoding="utf-8")))
        else:
            image_count = count_required_images(get_duration(str(audio_file)))
        
        output_video = step_video(project_dir, str(audio_file), image_dir, image_count, args.clip, args)
        print(f"\n[OK] Video step complete. Video: {output_video}")


if __name__ == "__main__":
    main()
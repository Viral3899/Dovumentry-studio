
import os
import re
import json
import math
import base64
import wave
import time
import shutil
import subprocess
from pathlib import Path

from groq import Groq
from google import genai
from google.genai import types


# ============================================================
# CONFIG
# ============================================================

GROQ_MODEL = "openai/gpt-oss-120b"

TTS_MODEL = "gemini-2.5-flash-preview-tts"

# Nano Banana 2IMAGE_MODEL = ""
# Nano Banana Pro

VOICE_NAME = "Iapetus"

IMAGE_SECONDS = 7
TRANSITION_SECONDS = 1

FPS = 30
WIDTH = 1920
HEIGHT = 1080

PROJECTS_DIR = Path("projects")


# ============================================================
# API KEYS
# ============================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GROQ_API_KEY:
    raise RuntimeError(
        "GROQ_API_KEY is missing.\n"
        "Run:\n"
        'export GROQ_API_KEY="YOUR_KEY"'
    )


if not GEMINI_API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is missing.\n"
        "Run:\n"
        'export GEMINI_API_KEY="YOUR_KEY"'
    )


# ============================================================
# CLIENTS
# ============================================================

groq_client = Groq(
    api_key=GROQ_API_KEY
)

gemini_client = genai.Client(
    api_key=GEMINI_API_KEY
)


# ============================================================
# CHECK COMMANDS
# ============================================================

def check_command(command):

    if shutil.which(command) is None:

        raise RuntimeError(
            f"{command} was not found in PATH.\n"
            f"Install FFmpeg and make sure {command} "
            f"is available from Git Bash."
        )


check_command("ffmpeg")
check_command("ffprobe")


# ============================================================
# TOPIC
# ============================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


if not topic:

    raise RuntimeError(
        "Topic cannot be empty."
    )


def topic_folder_name(value):
    name = re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE).strip("._")
    return name[:80] or "documentary"


PROJECT_DIR = PROJECTS_DIR / topic_folder_name(topic)
PROJECT_DIR.mkdir(parents=True, exist_ok=True)
IMAGE_DIR = PROJECT_DIR / "images"
IMAGE_DIR.mkdir(exist_ok=True)

SCRIPT_FILE = str(PROJECT_DIR / "documentary_script.txt")
PROMPTS_FILE = str(PROJECT_DIR / "image_prompts.txt")
GENERATION_PROMPTS_FILE = str(PROJECT_DIR / "image_generation_prompts.txt")
AUDIO_FILE = str(PROJECT_DIR / "narration.wav")
OUTPUT_VIDEO = str(PROJECT_DIR / "documentary.mp4")
Path(PROJECT_DIR / "topic.txt").write_text(topic, encoding="utf-8")


duration_input = input(
    "\nEnter target audio duration in seconds (20-200):\n> "
).strip()

try:
    target_duration = float(duration_input)
except ValueError as error:
    raise RuntimeError("Audio duration must be a number of seconds.") from error

if not math.isfinite(target_duration) or target_duration < 20 or target_duration > 200:
    raise RuntimeError("Audio duration must be between 20 and 200 seconds.")


print()
print("=" * 50)
print("DOCUMENTARY PIPELINE")
print("=" * 50)

print(
    f"Topic: {topic}"
)

print(
    f"Target audio duration: {target_duration:.1f} seconds"
)


# ============================================================
# 1. GROQ SCRIPT
# ============================================================

def generate_script(topic, target="80 seconds"):

    prompt = f"""
You are an expert Hindi documentary narrator and scriptwriter.

DOCUMENTARY TOPIC:
{topic}

TARGET LENGTH:
{target}

Write ONE continuous Hindi narration for an AI voice-over.

CRITICAL OUTPUT RULES:
- Output ONLY the narration.
- Do NOT write a title.
- Do NOT write headings.
- Do NOT use labels such as "पृष्ठभूमि", "मुख्य घटनाएँ", "निष्कर्ष", "भाग 1", etc.
- Do NOT write scene headings.
- Do NOT write image prompts.
- Do NOT write camera directions.
- Do NOT write bullet points.
- Do NOT write production notes.
- Do NOT address the editor or viewer with instructions.
- Keep it natural when read aloud by TTS.
- Use smooth transitions between paragraphs so the narration feels like one continuous story.
- Do not begin with a heading; begin directly with a strong documentary hook.
- Preserve chronology and logical flow.
- Avoid repetitive phrases.
- Use punctuation suitable for natural speech.

FACTUAL SAFETY:
- Do not invent names, dates, numbers, locations, quotations, evidence, arrests, operations, or events.
- Distinguish confirmed facts from government/police claims, media reports, allegations, disputed information, and unverified claims.
- If the topic contains uncertain claims, clearly attribute them rather than presenting them as proven facts.

STYLE:
- Hindi
- Serious cinematic documentary
- Investigative but factual
- Suspenseful without sensational fabrication
- Natural spoken Hindi
- Strong opening hook
- Clear chronological storytelling
- Context, events, claims/evidence, uncertainty, consequences, and a memorable ending

Return ONLY the final continuous Hindi narration.
"""

    max_retries = 5

    for attempt in range(
        1,
        max_retries + 1
    ):

        try:

            print(
                f"Groq attempt "
                f"{attempt}/{max_retries}..."
            )

            response = (
                groq_client
                .chat
                .completions
                .create(

                    model=GROQ_MODEL,

                    messages=[

                        {
                            "role": "system",
                            "content": (
                                "You are a professional "
                                "Hindi documentary writer."
                            )
                        },

                        {
                            "role": "user",
                            "content": prompt
                        }

                    ],

                    temperature=0.7,

                    max_tokens=2000
                )
            )

            script = (
                response
                .choices[0]
                .message
                .content
                .strip()
            )

            if script:

                return script


        except Exception as e:

            print(
                f"Groq error: {e}"
            )

            if attempt < max_retries:

                wait = min(
                    2 ** attempt,
                    30
                )

                print(
                    f"Retrying in {wait}s..."
                )

                time.sleep(wait)

            else:

                raise


    raise RuntimeError(
        "Groq failed to generate script."
    )


print("\n[1/7] Documentary script")
if Path(SCRIPT_FILE).exists() and Path(SCRIPT_FILE).stat().st_size > 50:
    script = Path(SCRIPT_FILE).read_text(encoding="utf-8").strip()
    print(f"✓ SKIP: Existing script found: {SCRIPT_FILE}")
    print(f"✓ Characters: {len(script)}")
else:
    print("Generating documentary script...")
    script = generate_script(topic, target=f"{target_duration:.1f} seconds")
    Path(SCRIPT_FILE).write_text(script, encoding="utf-8")
    print(f"✓ Script saved: {SCRIPT_FILE}")
    print(f"✓ Characters: {len(script)}")


# ============================================================
# 2. GEMINI TTS
# ============================================================

TTS_CHUNK_CHARS = 5000
TTS_MAX_RETRIES = 5
TTS_SAMPLE_RATE = 24000
TTS_CHANNELS = 1
TTS_SAMPLE_WIDTH = 2


def write_wave(filename, pcm_bytes, channels=TTS_CHANNELS, rate=TTS_SAMPLE_RATE, sample_width=TTS_SAMPLE_WIDTH):
    """Write raw PCM audio bytes to a valid WAV container."""
    if not pcm_bytes:
        raise RuntimeError("Cannot write WAV: audio data is empty.")

    with wave.open(str(filename), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm_bytes)


def split_tts_chunks(text, max_chars=TTS_CHUNK_CHARS):
    """Split narration at paragraph/sentence boundaries so TTS never gets one huge request."""
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        raise RuntimeError("TTS received an empty script.")

    chunks = []
    current = ""

    # Prefer paragraph/sentence boundaries.
    pieces = re.split(r"(?<=[।!?])\s+|\n+", text)

    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue

        if len(piece) > max_chars:
            # Hard-split an unusually long sentence.
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
    """Accept bytes or base64 audio returned by the Gemini SDK."""
    if data is None:
        return None

    if isinstance(data, bytes):
        return data

    if isinstance(data, bytearray):
        return bytes(data)

    if isinstance(data, str):
        try:
            return base64.b64decode(data)
        except Exception:
            return None

    return None


def extract_interaction_audio(interaction):
    """Extract raw PCM from current Interactions API response shapes."""
    audio = getattr(interaction, "output_audio", None)

    if audio is None:
        # Some SDK versions expose camelCase.
        audio = getattr(interaction, "outputAudio", None)

    if audio is None and isinstance(interaction, dict):
        audio = interaction.get("output_audio") or interaction.get("outputAudio")

    if audio is None:
        return None

    data = getattr(audio, "data", None)

    if data is None and isinstance(audio, dict):
        data = audio.get("data")

    return decode_audio_data(data)


def extract_legacy_audio(response):
    """Fallback for older google-genai SDK responses."""
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


def normalize_pcm(audio_bytes):
    """Gemini TTS normally returns raw 24 kHz PCM. Also tolerate a WAV response."""
    if not audio_bytes:
        return None

    # If the provider returned a WAV container, extract its PCM frames.
    if audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
        import io
        with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
            channels = wf.getnchannels()
            rate = wf.getframerate()
            width = wf.getsampwidth()

            if channels != TTS_CHANNELS or rate != TTS_SAMPLE_RATE or width != TTS_SAMPLE_WIDTH:
                raise RuntimeError(
                    f"Unexpected TTS WAV format: "
                    f"{channels}ch, {rate}Hz, {width * 8}bit."
                )

            return wf.readframes(wf.getnframes())

    return audio_bytes


def generate_tts_chunk(chunk, chunk_number, total_chunks):
    """Generate one reliable TTS chunk with retries and API fallback."""
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
            print(
                f"  TTS chunk {chunk_number}/{total_chunks} "
                f"attempt {attempt}/{TTS_MAX_RETRIES}..."
            )

            # Current Interactions API. This avoids the AFC warning produced
            # by the old direct generate_content TTS path.
            try:
                interaction = gemini_client.interactions.create(
                    model=TTS_MODEL,
                    input=prompt,
                    response_format={"type": "audio"},
                    generation_config={
                        "speech_config": [
                            {
                                "voice": VOICE_NAME,
                                "language_code": "hi-IN",
                            }
                        ]
                    },
                )

                audio = extract_interaction_audio(interaction)

                if audio:
                    return normalize_pcm(audio)

            except Exception as interaction_error:
                last_error = interaction_error
                print(f"    Interactions TTS unavailable: {interaction_error}")

            # Compatibility fallback for google-genai versions where the
            # Interactions audio response is not exposed correctly.
            response = gemini_client.models.generate_content(
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

            raise RuntimeError(
                "Gemini returned a response but no audio bytes were present."
            )

        except Exception as e:
            last_error = e
            print(f"    TTS error: {e}")

            if attempt < TTS_MAX_RETRIES:
                wait = min(2 ** attempt, 30)
                print(f"    Retrying in {wait}s...")
                time.sleep(wait)

    raise RuntimeError(
        f"TTS chunk {chunk_number} failed after {TTS_MAX_RETRIES} attempts: "
        f"{last_error}"
    )


def generate_voice(script):
    """Generate the complete narration safely in multiple TTS chunks."""
    chunks = split_tts_chunks(script)

    print(f"✓ TTS chunks: {len(chunks)}")
    print(f"✓ Max chunk size: {TTS_CHUNK_CHARS} characters")

    pcm_parts = []

    for index, chunk in enumerate(chunks, start=1):
        audio = generate_tts_chunk(
            chunk,
            index,
            len(chunks),
        )

        if not audio:
            raise RuntimeError(
                f"TTS chunk {index} produced empty audio."
            )

        pcm_parts.append(audio)

    combined_pcm = b"".join(pcm_parts)

    if len(combined_pcm) < TTS_SAMPLE_RATE * TTS_CHANNELS * TTS_SAMPLE_WIDTH:
        raise RuntimeError(
            "Generated narration is suspiciously short or empty."
        )

    # Never leave a stale/partial narration file behind.
    output_path = Path(AUDIO_FILE)
    if output_path.exists():
        output_path.unlink()

    write_wave(
        AUDIO_FILE,
        combined_pcm,
        channels=TTS_CHANNELS,
        rate=TTS_SAMPLE_RATE,
        sample_width=TTS_SAMPLE_WIDTH,
    )

    if not output_path.exists() or output_path.stat().st_size <= 44:
        raise RuntimeError(
            "TTS WAV file was not created correctly."
        )


print("\n[2/7] Hindi voice")
if Path(AUDIO_FILE).exists() and Path(AUDIO_FILE).stat().st_size > 1000:
    print(f"✓ SKIP: Existing audio found: {AUDIO_FILE}")
else:
    print("Generating Hindi voice...")
    generate_voice(script)
    print(f"✓ Audio saved: {AUDIO_FILE}")


# ============================================================
# 3. AUDIO DURATION
# ============================================================

def get_duration(
    filename
):

    result = subprocess.run(

        [

            "ffprobe",

            "-v",
            "error",

            "-show_entries",
            "format=duration",

            "-of",
            "json",

            filename

        ],

        capture_output=True,

        text=True,

        check=True
    )


    data = json.loads(
        result.stdout
    )


    return float(
        data["format"]["duration"]
    )


print(
    "\n[3/7] Measuring audio..."
)


audio_duration = get_duration(
    AUDIO_FILE
)


print(
    f"✓ Audio duration: "
    f"{audio_duration:.3f} seconds"
)


# ============================================================
# IMAGE COUNT
#
# 5 SECONDS = 1 IMAGE
# ============================================================

# Account for crossfade overlap. With 5s images and a 1s transition,
# N images produce 5 + (N-1)*4 seconds of visual duration.
image_count = max(
    1,
    math.ceil(
        (audio_duration - IMAGE_SECONDS) /
        (IMAGE_SECONDS - TRANSITION_SECONDS)
    ) + 1
)


print(
    f"✓ 5 seconds/image"
)

print(
    f"✓ Images required: "
    f"{image_count}"
)


def parse_prompts(text):
    pattern = r"^\s*(\d+)\.\s*(.*?)(?=^\s*\d+\.\s*|\Z)"
    matches = re.findall(pattern, text, flags=re.MULTILINE | re.DOTALL)
    return [prompt.strip() for _, prompt in matches if prompt.strip()]


# ============================================================
# 4. GROQ IMAGE PROMPTS
# ============================================================

def _call_groq_image_batch(topic, script_chunk, batch_start, batch_count, total_count):
    """Generate a small batch so Groq stays below the TPM/request limit."""
    prompt = f"""
You are an expert cinematic documentary visual director.
Generate EXACTLY {batch_count} numbered image prompts for images {batch_start} through {batch_start + batch_count - 1} of {total_count}.

TOPIC: {topic}

SCRIPT SEGMENT (chronological; use only this segment):
{script_chunk}

Each prompt represents about 5 seconds and must follow the script chronology.
Each prompt must be one self-contained scene and must include the subject, setting, period/context, lighting, mood, camera angle, action, and this exact style ending: "Photorealistic cinematic documentary, premium film quality, 16:9 landscape, realistic lighting, realistic people, accurate environment, natural colors, cinematic depth of field, no text, no subtitles, no captions, no logos, no watermarks."
INDIAN VISUAL DIRECTION (REQUIRED IN EVERY PROMPT):
- Give every scene an authentic Indian visual identity, including Indian people, regional clothing, architecture, materials, craft methods, landscapes, social details, and natural light whenever the scene permits.
- Choose details appropriate to the specific Indian region, language community, religion, dynasty, historical period, and social context in the script; do not mix unrelated regional traditions.
- Show believable Indian skin tones, facial features, hairstyles, garments, jewelry, tools, food, vehicles, streets, interiors, and sacred or everyday practices when relevant.
- Prefer lived-in documentary realism and culturally respectful details over exoticized, stereotyped, generic, or Westernized styling. Do not add unsupported cultural details.
Maintain character appearance consistently within this batch when the same person appears.
Do not invent specific facts, names, dates, locations, or events not supported by the script segment.
Return ONLY numbered prompts, one per line/paragraph, using numbers {batch_start} through {batch_start + batch_count - 1}.
"""

    max_retries = 5
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            print(f"Groq image batch {batch_start}-{batch_start + batch_count - 1} attempt {attempt}/{max_retries}...")
            response = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You create concise, factual cinematic documentary image prompts."
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.5,
                max_tokens=2200,
            )
            text = (response.choices[0].message.content or "").strip()
            if text:
                return text
            raise RuntimeError("Groq returned an empty image-prompt batch.")
        except Exception as e:
            last_error = e
            print(f"Groq image batch error: {e}")
            if attempt < max_retries:
                wait = min(2 ** attempt, 30)
                print(f"Retrying in {wait}s...")
                time.sleep(wait)

    raise RuntimeError(f"Groq image batch {batch_start}-{batch_start + batch_count - 1} failed: {last_error}")


def _split_script_for_image_batches(script, total_count, batch_size=8):
    """Split narration proportionally so every batch gets its chronological context."""
    words = script.split()
    if not words:
        raise RuntimeError("Script is empty; cannot generate image prompts.")

    batches = []
    num_batches = math.ceil(total_count / batch_size)
    total_words = len(words)

    for batch_index in range(num_batches):
        first_image = batch_index * batch_size + 1
        count = min(batch_size, total_count - first_image + 1)
        start_word = round(batch_index * total_words / num_batches)
        end_word = round((batch_index + 1) * total_words / num_batches)
        chunk = " ".join(words[start_word:end_word]).strip()
        batches.append((first_image, count, chunk))

    return batches


def generate_image_prompts(topic, script, count):
    """Generate image prompts in small independent Groq requests."""
    batch_size = 8
    batches = _split_script_for_image_batches(script, count, batch_size)
    all_prompts = []

    print(f"✓ Groq image-prompt batches: {len(batches)}")

    for first_image, batch_count, script_chunk in batches:
        text = _call_groq_image_batch(
            topic,
            script_chunk,
            first_image,
            batch_count,
            count,
        )

        batch_prompts = parse_prompts(text) if 'parse_prompts' in globals() else []

        # Local parser because parse_prompts is defined later in this file.
        if len(batch_prompts) != batch_count:
            matches = re.findall(
                r"^\s*\d+\.\s*(.*?)(?=^\s*\d+\.\s|\Z)",
                text,
                flags=re.MULTILINE | re.DOTALL,
            )
            batch_prompts = [m.strip() for m in matches if m.strip()]

        if len(batch_prompts) != batch_count:
            raise RuntimeError(
                f"Groq returned {len(batch_prompts)} prompts for batch "
                f"{first_image}-{first_image + batch_count - 1}; expected {batch_count}."
            )

        all_prompts.extend(batch_prompts)

    if len(all_prompts) != count:
        raise RuntimeError(
            f"Image prompt generation failed: expected {count}, got {len(all_prompts)}."
        )

    # Normalize numbering for the saved combined file.
    return "\n\n".join(
        f"{i}. {prompt}" for i, prompt in enumerate(all_prompts, start=1)
    )


def build_generation_prompt(prompt_text):
    """Create one reusable instruction that keeps visual identity stable."""
    return f"""IMAGE GENERATION INSTRUCTIONS

Generate the images in chronological order using the numbered prompts below.
Keep every recurring character identical across all images: same face, age,
skin tone, hairstyle, hair color, body type, clothing, accessories, and period.
Keep recurring locations, props, architecture, color palette, lighting style,
camera language, and documentary realism consistent. Change only the action,
framing, and setting details explicitly requested by each numbered prompt.
Give every image an authentic Indian visual identity. Use the specific Indian
region, community, historical period, architecture, clothing, materials, craft
traditions, landscapes, and everyday details supported by the topic or scene.
Keep Indian people, facial features, skin tones, hairstyles, garments, jewelry,
tools, interiors, and social practices believable and period-appropriate.
Avoid generic Westernized styling, anachronisms, cultural mixing, exoticization,
and stereotypes; do not invent cultural details that the prompt does not support.
Use the same visual identity and character design for every image. Do not add
text, subtitles, captions, logos, or watermarks. Export files as 1.jpeg,
2.jpeg, 3.jpeg, and so on, matching the prompt number exactly.

SCENE PROMPTS

{prompt_text}
"""


print("\n[4/7] Image prompts")
existing_prompt_text = ""
existing_prompts = []
if Path(PROMPTS_FILE).exists() and Path(PROMPTS_FILE).stat().st_size > 50:
    existing_prompt_text = Path(PROMPTS_FILE).read_text(encoding="utf-8").strip()
    existing_prompts = parse_prompts(existing_prompt_text)

if len(existing_prompts) == image_count:
    prompt_text = existing_prompt_text
    print(f"✓ SKIP: Existing prompts found: {PROMPTS_FILE} ({len(existing_prompts)} prompts)")
else:
    print("Generating image prompts...")
    prompt_text = generate_image_prompts(topic, script, image_count)
    Path(PROMPTS_FILE).write_text(prompt_text, encoding="utf-8")
    print(f"✓ Prompts saved: {PROMPTS_FILE}")

generation_prompt_text = build_generation_prompt(prompt_text)
Path(GENERATION_PROMPTS_FILE).write_text(generation_prompt_text, encoding="utf-8")
print(f"✓ Generation instructions saved: {GENERATION_PROMPTS_FILE}")

# IMPORTANT: whether prompts were loaded from disk or newly generated,
# convert the saved text into the actual prompt list used by Step 5.
prompts = parse_prompts(prompt_text)

if len(prompts) != image_count:
    raise RuntimeError(
        f"Prompt count mismatch before image generation: "
        f"expected {image_count}, got {len(prompts)}."
    )

print(f"✓ Ready for image generation: {len(prompts)} prompts")



# ============================================================
# PIPELINE 1 COMPLETE
# ============================================================
# This script stops AFTER generating:
#   1. documentary_script.txt
#   2. narration.wav
#   3. image_prompts.txt
#   4. image_generation_prompts.txt
#
# It DOES NOT generate images.
#
# Next step:
#   Run pipeline_2_after_images.py after placing the required
#   numbered images inside the "images" folder:
#       images/1.jpeg
#       images/2.jpeg
#       ...
#
print()
print("=" * 50)
print("PIPELINE 1 COMPLETE")
print("=" * 50)
print(f"Script  : {SCRIPT_FILE}")
print(f"Audio   : {AUDIO_FILE}")
print(f"Prompts : {PROMPTS_FILE}")
print(f"Generation prompts: {GENERATION_PROMPTS_FILE}")
print(f"Images required: {image_count}")
print()
print("Now generate/upload 1.jpeg, 2.jpeg, ... using image_generation_prompts.txt.")
print("Then run pipeline_2_after_images.py")
print("=" * 50)

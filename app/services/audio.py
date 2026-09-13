import asyncio
import math
import os
import re
import subprocess
import wave
from pathlib import Path
import sqlite3

from .api_keys import get_gemini_client
from .providers import ProviderRequiredError, is_auth_error, is_resource_exhausted
from . import session
from ..utils.constants import NARRATION_VOLUME, BGM_VOLUME


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
    if client is None:
        raise ProviderRequiredError("gemini", "Gemini narration requires a Gemini API key.", "gemini")

    from google.genai import types
    response = client.models.generate_content(
        model=os.getenv("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview"),
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


def generate_local_audio(path: Path, script: str, voice_name: str):
    import edge_tts

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


def generate_audio_segments(session_dir, script, voice, use_default_voice, session_id):
    """Generate audio segments from script and return concatenated audio path."""
    tts_chunks = []
    normalized = re.sub(r"\s+", " ", script).strip()
    sentences = [x.strip() for x in re.split(r"(?<=[.!?।॥])\s+", normalized) if x.strip()]
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) + 1 > 3500:
            tts_chunks.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        tts_chunks.append(current.strip())
    if not tts_chunks:
        tts_chunks = [normalized]

    segment_dir = session_dir / "audio_segments"
    segment_dir.mkdir(exist_ok=True)
    for old in segment_dir.glob("*.wav"):
        old.unlink(missing_ok=True)

    segment_paths = []
    for index, segment in enumerate(tts_chunks, start=1):
        segment_path = segment_dir / f"{index}.wav"
        generated_audio = None
        try:
            if use_default_voice:
                generated_audio = generate_local_audio(segment_path, segment, "female")
            else:
                generated_audio = generate_real_audio(segment_path, segment, voice)
        except ProviderRequiredError as exc:
            exc.detail = str(exc.detail or exc.reason)
            raise
        except Exception as exc:
            if is_resource_exhausted(exc) or is_auth_error(exc):
                raise ProviderRequiredError(
                    "gemini",
                    "Gemini narration is unavailable. Enter/save a Gemini API key, or choose Use Default Voice to continue without Gemini.",
                    "default_voice",
                    str(exc)
                ) from exc
            raise
        duration = session.get_duration(str(segment_path)) if generated_audio else 0.0
        if not segment_path.exists() or duration <= 0:
            raise RuntimeError(f"Could not generate narration audio chunk {index}.")
        segment_paths.append(segment_path)

    audio_filename = f"{session_id}_narration.wav"
    audio_path = session_dir / audio_filename
    audio_path.unlink(missing_ok=True)
    session.concatenate_audio_files(segment_paths, audio_path)
    return audio_path, audio_filename
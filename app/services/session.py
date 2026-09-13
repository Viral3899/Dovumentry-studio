import json
import math
import re
import subprocess
from datetime import datetime
from pathlib import Path

from ..utils.paths import GENERATED_DIR, PROJECTS_DIR
from ..utils.constants import VISUAL_STYLES


def slugify(value: str) -> str:
    value = (value or "untitled").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "untitled"


def utc_timestamp() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")


def log_event(session_dir: Path, message: str) -> None:
    log_path = session_dir / "generation_log.txt"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{utc_timestamp()}] {message}\n")


def write_state(session_dir: Path, data: dict) -> None:
    state_path = session_dir / "session_state.json"
    state_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_state(session_dir: Path) -> dict:
    state_path = session_dir / "session_state.json"
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_session_dir(session_id: str) -> Path:
    generated_dir = GENERATED_DIR / session_id
    if generated_dir.exists():
        return generated_dir
    return PROJECTS_DIR / session_id


def topic_folder_name(value: str) -> str:
    name = re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE).strip("._")
    return name[:80] or "documentary"


def topic_filename(session_id: str, suffix: str) -> str:
    return f"{session_id}{suffix}"


def read_session_script(session_dir: Path, state: dict, session_id: str = "") -> str:
    names = []
    if state.get("script_filename"):
        names.append(state["script_filename"])
    if session_id:
        names.append(topic_filename(session_id, "_script.txt"))
    names.append("documentary_script.txt")
    seen = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        path = session_dir / name
        if path.exists():
            return path.read_text(encoding="utf-8")
    return (state.get("script") or "").strip()


def count_required_images(audio_duration: float, image_seconds: float = 5, transition_seconds: float = 0) -> int:
    if audio_duration <= 0:
        return 1
    return max(1, math.ceil(float(audio_duration) / float(image_seconds)))


def render_count(payload, name, default=12, minimum=1, maximum=120) -> int:
    try:
        value = int(payload.get(name, default))
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a whole number.")
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return value


def split_script_for_segments(script: str, count: int) -> list:
    text = re.sub(r"\s+", " ", (script or "").strip())
    if count <= 1:
        return [text]
    sentences = [x.strip() for x in re.split(r"(?<=[.!?।॥])\s+", text) if x.strip()]
    if len(sentences) < count:
        words = text.split()
        size = max(1, math.ceil(len(words) / count))
        segments = [" ".join(words[i:i + size]).strip() for i in range(0, len(words), size)]
    else:
        segments = []
        total = len(sentences)
        start = 0
        for i in range(count):
            remaining_groups = count - i
            remaining_sentences = total - start
            take = max(1, math.ceil(remaining_sentences / remaining_groups))
            segments.append(" ".join(sentences[start:start + take]).strip())
            start += take
    while len(segments) > count:
        segments[-2] = (segments[-2] + " " + segments[-1]).strip()
        segments.pop()
    while len(segments) < count:
        segments.append(segments[-1] if segments else text)
    return segments[:count]


def image_index_from_filename(filename: str) -> int:
    stem = Path(filename).stem
    match = re.match(r"^\s*(\d+)(?:\D|$)", stem)
    return int(match.group(1)) if match else 0


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


def concatenate_audio_files(audio_paths, output_path: Path):
    """Concatenate generated narration clips into one WAV without re-encoding when possible."""
    concat_file = output_path.with_suffix(".concat.txt")
    concat_file.write_text("\n".join(f"file '{str(path).replace(chr(39), chr(39)+chr(39))}'" for path in audio_paths), encoding="utf-8")
    result = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c:a", "pcm_s16le", "-ar", "24000", "-ac", "1", str(output_path)],
        capture_output=True, text=True, check=False
    )
    concat_file.unlink(missing_ok=True)
    if result.returncode != 0 or not output_path.exists():
        raise RuntimeError(f"Audio concatenation failed: {result.stderr}")
    return output_path


def render_setting(payload, name, default, minimum, maximum):
    try:
        value = float(payload.get(name, default))
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number.")
    if not math.isfinite(value) or value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return value


def parse_prompts(text):
    matches = re.findall(r"^\s*(\d+)\.\s*(.*?)(?=^\s*\d+\.\s*|\Z)", text or "", flags=re.MULTILINE | re.DOTALL)
    return [x.strip() for _, x in matches if x.strip()] or [x.strip() for x in (text or "").splitlines() if x.strip()]
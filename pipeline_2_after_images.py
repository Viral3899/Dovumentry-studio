import os
import re
import json
import math
import random
import wave
import shutil
import subprocess
from pathlib import Path

# ============================================================
# CONFIG
# ============================================================

IMAGE_SECONDS = 5
TRANSITION_SECONDS = 1

FPS = 30
WIDTH = 1920
HEIGHT = 1080

PROJECTS_DIR = Path("projects")
BGM_DIR = Path("BGM")
NARRATION_VOLUME = 1.5
BGM_VOLUME = 0.20

# ============================================================
# CHECK COMMANDS
# ============================================================

def check_command(command):
    if shutil.which(command) is None:
        raise RuntimeError(
            f"{command} was not found in PATH.\n"
            f"Install FFmpeg and make sure {command} is available from Git Bash."
        )

check_command("ffmpeg")
check_command("ffprobe")


# ============================================================
# VERIFY REQUIRED INPUT FILES
# ============================================================

print()
print("=" * 50)
print("DOCUMENTARY PIPELINE 2 - AFTER IMAGES")
print("=" * 50)

topic_folder = input(
    "\nEnter the topic folder name from projects/:\n> "
).strip()

if not topic_folder:
    raise RuntimeError("Topic folder name cannot be empty.")

topic_folder = re.sub(r"[^\w.-]+", "_", topic_folder, flags=re.UNICODE).strip("._")[:80]


def ask_number(label, default, minimum, maximum):
    value = input(f"\n{label} ({minimum}-{maximum}, default {default}):\n> ").strip()
    try:
        value = float(value or default)
    except ValueError as error:
        raise RuntimeError(f"{label} must be a number.") from error
    if not math.isfinite(value) or value < minimum or value > maximum:
        raise RuntimeError(f"{label} must be between {minimum} and {maximum}.")
    return value


IMAGE_SECONDS = ask_number("Seconds per image", IMAGE_SECONDS, 1, 30)
TRANSITION_SECONDS = ask_number("Transition seconds", TRANSITION_SECONDS, 0, 10)
NARRATION_VOLUME = ask_number("Narration volume", NARRATION_VOLUME, 0, 3)
BGM_VOLUME = ask_number("BGM volume (0 to 1)", BGM_VOLUME, 0, 1)
if TRANSITION_SECONDS >= IMAGE_SECONDS:
    raise RuntimeError("Transition seconds must be less than seconds per image.")

PROJECT_DIR = PROJECTS_DIR / (topic_folder or "documentary")
IMAGE_DIR = PROJECT_DIR / "images"
SCRIPT_FILE = str(PROJECT_DIR / "documentary_script.txt")
PROMPTS_FILE = str(PROJECT_DIR / "image_prompts.txt")
AUDIO_FILE = str(PROJECT_DIR / "narration.wav")
OUTPUT_VIDEO = str(PROJECT_DIR / "documentary.mp4")


def get_prompt_count(filename):
    text = Path(filename).read_text(encoding="utf-8")
    numbers = [int(number) for number in re.findall(r"^\s*(\d+)\.\s+", text, re.MULTILINE)]
    expected_numbers = list(range(1, len(numbers) + 1))
    if not numbers or numbers != expected_numbers:
        raise RuntimeError(
            f"Image prompts must contain consecutive numbers starting at 1: {filename}"
        )
    return len(numbers)

if not Path(SCRIPT_FILE).exists():
    raise RuntimeError(f"Missing script file: {SCRIPT_FILE}")

if not Path(PROMPTS_FILE).exists():
    raise RuntimeError(f"Missing image prompts file: {PROMPTS_FILE}")

if not Path(AUDIO_FILE).exists() or Path(AUDIO_FILE).stat().st_size <= 1000:
    raise RuntimeError(f"Missing or invalid narration audio: {AUDIO_FILE}")

BGM_EXTENSIONS = (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac")
BGM_FILES = [
    path for path in BGM_DIR.iterdir()
    if path.is_file() and path.suffix.lower() in BGM_EXTENSIONS
] if BGM_DIR.exists() else []

if not BGM_FILES:
    raise RuntimeError(f"No background music files found in {BGM_DIR}/")

IMAGE_DIR.mkdir(exist_ok=True)

IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp')


def numbered_image_name(index, source):
    base = re.sub(r"^\d+(?:_before_)?_?", "", source.stem, flags=re.IGNORECASE) or "image"
    return f"{index:02d}_before_{base}{source.suffix.lower()}"


def image_number(source):
    match = re.search(r"\d+", source.name[:3])
    if not match:
        raise RuntimeError(
            f"Image number must appear within the first 3 filename characters: {source.name}"
        )
    return int(match.group())

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



# ============================================================
# CALCULATE REQUIRED IMAGE COUNT
# ============================================================

print("\n[1/3] Measuring audio...")
audio_duration = get_duration(AUDIO_FILE)
print(f"✓ Audio duration: {audio_duration:.3f} seconds")

image_count = get_prompt_count(PROMPTS_FILE)
image_duration = (
    audio_duration + (image_count - 1) * TRANSITION_SECONDS
) / image_count

print(f"✓ Image prompts found: {image_count}")
print(f"✓ Image duration: {image_duration:.3f} seconds (audio fitted)")

# ============================================================
# VERIFY UPLOADED/GENERATED IMAGES
# ============================================================

print("\n[2/3] Checking images...")

all_images = sorted(
    [f for f in IMAGE_DIR.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS],
    key=image_number
)

if len(all_images) > image_count:
    print(f"\n❌ IMAGE CHECK FAILED")
    print(f"Expected: {image_count} images")
    print(f"Found: {len(all_images)} images")
    print("\nNo video will be created until all required images exist.")
    raise RuntimeError(f"Found {len(all_images)} images, maximum allowed is {image_count}.")

images_by_number = {}
for image in all_images:
    number = image_number(image)
    if number in images_by_number:
        raise RuntimeError(f"Duplicate image number {number}: {image.name}")
    if number > image_count:
        raise RuntimeError(f"Image number {number} exceeds prompt count {image_count}: {image.name}")
    images_by_number[number] = image

if 1 not in images_by_number:
    raise RuntimeError(
        "Image 1 is missing; it cannot be filled because there is no previous image."
    )

ordered_images = []
for number in range(1, image_count + 1):
    source = images_by_number.get(number)
    if source is None:
        previous = ordered_images[-1]
        source = IMAGE_DIR / f".__filled_{number}{previous.suffix.lower()}"
        shutil.copy2(previous, source)
        print(f"  Filled missing image {number} using image {number - 1}")
    ordered_images.append(source)

all_images = ordered_images
print(f"✓ Images prepared in numeric filename order: {len(all_images)}")

renames = []
for i, src in enumerate(all_images, 1):
    dst = IMAGE_DIR / numbered_image_name(i, src)
    if src != dst:
        temporary = IMAGE_DIR / f".__renaming_{i}{src.suffix.lower()}"
        shutil.move(str(src), str(temporary))
        renames.append((temporary, dst))

for temporary, dst in renames:
    if dst.exists():
        dst.unlink()
    shutil.move(str(temporary), str(dst))
    print(f"  Renamed: {temporary.name} → {dst.name}")

print(f"✓ All {image_count} images renamed to {numbered_image_name(1, all_images[0])} through {numbered_image_name(image_count, all_images[-1])}")

def create_video():
    image_files = [
        next(IMAGE_DIR.glob(f"{i:02d}_before_*.jpg"), None)
        or next(IMAGE_DIR.glob(f"{i:02d}_before_*.jpeg"), None)
        or next(IMAGE_DIR.glob(f"{i:02d}_before_*.png"), None)
        or next(IMAGE_DIR.glob(f"{i:02d}_before_*.webp"), None)
        for i in range(1, image_count + 1)
    ]

    for image in image_files:
        if not image.exists():
            raise RuntimeError(f"Missing image: {image}")

    # Check for NVIDIA NVENC. Fall back automatically to CPU encoding.
    encoder_check = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
    )

    use_nvenc = "h264_nvenc" in encoder_check.stdout

    if use_nvenc:
        video_codec = [
            "-c:v", "h264_nvenc",
            "-preset", "p4",
            "-rc", "vbr",
            "-cq", "20",
            "-b:v", "8M",
            "-maxrate", "12M",
            "-bufsize", "16M",
        ]
        print("✓ Video encoder: NVIDIA NVENC")
    else:
        video_codec = [
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "20",
        ]
        print("✓ Video encoder: CPU libx264")

    cmd = ["ffmpeg", "-y"]

    # IMAGE INPUTS
    for image in image_files:
        cmd += [
            "-loop", "1",
            "-t", str(image_duration),
            "-i", str(image),
        ]

    # AUDIO
    cmd += ["-i", AUDIO_FILE]
    selected_bgm = random.choice(BGM_FILES)
    cmd += ["-stream_loop", "-1", "-i", str(selected_bgm)]
    print(f"✓ Background music: {selected_bgm.name} ({BGM_VOLUME:.0%} volume)")

    filters = []

    for i in range(image_count):
        filters.append(
            f"[{i}:v]"
            f"scale={WIDTH}:{HEIGHT}:"
            f"force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT},"
            "zoompan=z='min(zoom+0.0007,1.08)':"
            "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d=1:s={WIDTH}x{HEIGHT}:fps={FPS},"
            f"setsar=1,"
            f"format=yuv420p"
            f"[v{i}]"
        )

    current = "v0"
    offset = image_duration - TRANSITION_SECONDS

    for i in range(1, image_count):
        output = f"x{i}"

        filters.append(
            f"[{current}][v{i}]"
            f"xfade="
            f"transition=smoothleft:"
            f"duration={TRANSITION_SECONDS}:"
            f"offset={offset}"
            f"[{output}]"
        )

        current = output
        offset += image_duration - TRANSITION_SECONDS

    narration_input = image_count
    music_input = image_count + 1
    filters.extend([
        f"[{narration_input}:a]volume={NARRATION_VOLUME}[narration]",
        f"[{music_input}:a]volume={BGM_VOLUME}[music]",
        "[narration][music]amix=inputs=2:duration=first:dropout_transition=2[aout]",
    ])

    filter_complex = ";".join(filters)

    cmd += [
        "-filter_complex", filter_complex,
        "-map", f"[{current}]",
        "-map", "[aout]",
        "-t", f"{audio_duration:.3f}",
        *video_codec,
        "-c:a", "aac",
        "-b:a", "192k",
        "-r", str(FPS),
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        OUTPUT_VIDEO,
    ]

    print(f"✓ Target duration: {audio_duration:.3f}s")
    print(f"✓ Visual duration available: "
            f"{image_duration + (image_count - 1) * (image_duration - TRANSITION_SECONDS):.3f}s")

    subprocess.run(cmd, check=True)

    # Final sync verification.
    produced_duration = get_duration(OUTPUT_VIDEO)

    tolerance = 0.15

    if abs(produced_duration - audio_duration) > tolerance:
        raise RuntimeError(
            f"Final A/V duration mismatch: "
            f"audio={audio_duration:.3f}s, "
            f"video={produced_duration:.3f}s"
        )



# ============================================================
# CREATE FINAL VIDEO
# ============================================================

print("\n[3/3] Creating synchronized video...")

if Path(OUTPUT_VIDEO).exists() and Path(OUTPUT_VIDEO).stat().st_size > 10000:
    print(f"✓ SKIP: Existing video found: {OUTPUT_VIDEO}")
else:
    create_video()

final_duration = get_duration(OUTPUT_VIDEO)

print()
print("=" * 50)
print("PIPELINE 2 COMPLETE")
print("=" * 50)
print(f"Audio duration : {audio_duration:.3f}s")
print(f"Images         : {image_count}")
print(f"Image duration : {image_duration:.3f}s")
print(f"Transition     : {TRANSITION_SECONDS}s")
print(f"Resolution     : {WIDTH}x{HEIGHT}")
print(f"FPS            : {FPS}")
print(f"Final duration : {final_duration:.3f}s")
print(f"Script         : {SCRIPT_FILE}")
print(f"Prompts        : {PROMPTS_FILE}")
print(f"Audio          : {AUDIO_FILE}")
print(f"Video          : {OUTPUT_VIDEO}")
print("=" * 50)

import random
import subprocess
import tempfile
import os
import shutil
from pathlib import Path
import sqlite3

from .session import get_duration
from ..utils.paths import BGM_DIR
from ..utils.constants import BGM_EXTENSIONS, NARRATION_VOLUME, BGM_VOLUME


def build_video_pipeline(image_files, audio_path, output_video,
                          image_seconds=5, transition_seconds=1,
                          narration_volume=NARRATION_VOLUME, bgm_volume=BGM_VOLUME):
    """
    Single-pass pipeline: images + narration + background music -> final video.
    Mirrors documentary_pipeline_2.py's create_video(), but parameterized for
    per-session settings instead of global constants.
    Uses two-pass approach on Windows to avoid command line length limits.
    """
    audio_duration = get_duration(str(audio_path))
    if audio_duration <= 0:
        raise RuntimeError("Narration audio has no readable duration.")

    image_count = len(image_files)
    image_duration = (
        audio_duration + (image_count - 1) * transition_seconds
    ) / image_count

    music_files = [
        path for path in BGM_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in BGM_EXTENSIONS
    ] if BGM_DIR.exists() else []
    if not music_files:
        raise RuntimeError(f"No background music files found in {BGM_DIR}.")
    selected_bgm = random.choice(music_files)

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
    else:
        video_codec = [
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "20",
        ]

    # On Windows, use two-pass approach to avoid command line length limit
    is_windows = os.name == "nt"
    
    if is_windows and image_count > 30:
        # Two-pass approach: create individual zoomed clips, then concat with transitions
        return _build_video_two_pass(
            image_files, audio_path, output_video, selected_bgm,
            image_duration, transition_seconds, audio_duration,
            narration_volume, bgm_volume, video_codec
        )

    # Original single-pass approach for non-Windows or small image counts
    cmd = ["ffmpeg", "-y"]

    for image_path in image_files:
        cmd += [
            "-loop", "1",
            "-t", f"{image_duration:.3f}",
            "-i", str(image_path),
        ]

    cmd += ["-i", str(audio_path)]
    cmd += ["-stream_loop", "-1", "-i", str(selected_bgm)]

    filters = []
    for index in range(image_count):
        filters.append(
            f"[{index}:v]setpts=PTS-STARTPTS,"
            f"scale=1920:1080:force_original_aspect_ratio=increase,"
            f"crop=1920:1080,"
            "zoompan=z='min(zoom+0.0007,1.08)':"
            "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={round(image_duration * 30)}:s=1920x1080:fps=30,"
            "trim=duration=" + f"{image_duration:.3f}" + ","
            "setpts=PTS-STARTPTS,setsar=1,format=yuv420p"
            f"[v{index}]"
        )

    current = "v0"
    offset = image_duration - transition_seconds
    for index in range(1, image_count):
        next_video = f"x{index}"
        filters.append(
            f"[{current}][v{index}]xfade=transition=fade:"
            f"duration={transition_seconds}:offset={offset:.3f},"
            "format=yuv420p"
            f"[{next_video}]"
        )
        current = next_video
        offset += image_duration - transition_seconds

    narration_input = image_count
    music_input = image_count + 1
    filters.extend([
        f"[{narration_input}:a]volume={narration_volume}[narration]",
        f"[{music_input}:a]volume={bgm_volume}[music]",
        "[narration][music]amix=inputs=2:duration=first:dropout_transition=2[aout]",
    ])

    cmd += [
        "-filter_complex", ";".join(filters),
        "-map", f"[{current}]",
        "-map", "[aout]",
        "-t", f"{audio_duration:.3f}",
        *video_codec,
        "-c:a", "aac",
        "-b:a", "192k",
        "-r", "30",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_video),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or "Video assembly failed.")

    produced_duration = get_duration(str(output_video))
    if abs(produced_duration - audio_duration) > 0.15:
        raise RuntimeError(
            f"Final A/V duration mismatch: audio={audio_duration:.3f}s, "
            f"video={produced_duration:.3f}s"
        )

    return output_video, audio_duration, produced_duration, selected_bgm.name


def _build_video_two_pass(image_files, audio_path, output_video, selected_bgm,
                           image_duration, transition_seconds, audio_duration,
                           narration_volume, bgm_volume, video_codec):
    """Two-pass video building for Windows to avoid command line length limits."""
    zoompan_frames = round(image_duration * 30)
    temp_dir = Path(tempfile.mkdtemp(prefix="docuvideo_"))
    clip_files = []
    
    try:
        # Pass 1: Create individual zoomed clips for each image
        for i, image_path in enumerate(image_files):
            clip_file = temp_dir / f"clip_{i:04d}.mp4"
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-t", f"{image_duration:.3f}",
                "-i", str(image_path),
                "-vf",
                f"scale=1920:1080:force_original_aspect_ratio=increase,"
                f"crop=1920:1080,"
                f"zoompan=z='min(zoom+0.0007,1.08)':"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d={zoompan_frames}:s=1920x1080:fps=30,"
                f"setsar=1,format=yuv420p",
                "-r", "30",
                "-pix_fmt", "yuv420p",
                *video_codec,
                "-c:a", "aac",
                "-b:a", "192k",
                "-t", f"{image_duration:.3f}",
                str(clip_file),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"Failed to create clip {i}: {result.stderr}")
            clip_files.append(clip_file)

        # Pass 2: Concat clips with xfade transitions
        # Create concat file for the clips
        concat_file = temp_dir / "concat.txt"
        with concat_file.open("w", encoding="utf-8") as f:
            for clip_file in clip_files:
                escaped = str(clip_file).replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")

        # Build filter complex for xfade transitions
        filters = []
        current = "0:v"
        offset = image_duration - transition_seconds
        
        for i in range(1, len(clip_files)):
            next_label = f"x{i}"
            filters.append(
                f"[{current}][{i}:v]xfade=transition=fade:"
                f"duration={transition_seconds}:offset={offset:.3f}"
                f"[{next_label}]"
            )
            current = next_label
            offset += image_duration - transition_seconds

        # Audio mixing
        narration_input = len(clip_files)
        music_input = len(clip_files) + 1
        filters.extend([
            f"[{narration_input}:a]volume={narration_volume}[narration]",
            f"[{music_input}:a]volume={bgm_volume}[music]",
            "[narration][music]amix=inputs=2:duration=first:dropout_transition=2[aout]",
        ])

        # Build final command
        cmd = ["ffmpeg", "-y"]
        for clip_file in clip_files:
            cmd += ["-i", str(clip_file)]
        cmd += ["-i", str(audio_path)]
        cmd += ["-stream_loop", "-1", "-i", str(selected_bgm)]
        
        cmd += [
            "-filter_complex", ";".join(filters),
            "-map", f"[{current}]",
            "-map", "[aout]",
            "-t", f"{audio_duration:.3f}",
            *video_codec,
            "-c:a", "aac",
            "-b:a", "192k",
            "-r", "30",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output_video),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Video concat failed: {result.stderr}")

        produced_duration = get_duration(str(output_video))
        if abs(produced_duration - audio_duration) > 0.15:
            raise RuntimeError(
                f"Final A/V duration mismatch: audio={audio_duration:.3f}s, "
                f"video={produced_duration:.3f}s"
            )

        return output_video, audio_duration, produced_duration, selected_bgm.name
    finally:
        # Cleanup temp directory
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass
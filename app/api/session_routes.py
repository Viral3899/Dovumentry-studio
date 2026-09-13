import math
from pathlib import Path
from flask import jsonify, request, send_file, send_from_directory
import sqlite3

from ..services.session import (
    get_session_dir, topic_folder_name, topic_filename, load_state,
    write_state, log_event, count_required_images, render_setting, get_duration
)
from ..services.script import generate_script_with_backend
from ..services.audio import generate_audio_segments
from ..services.prompts import generate_prompt_text, generate_generation_prompt_text, parse_prompts
from ..services.video import build_video_pipeline
from ..services.social import generate_social_copy
from ..services.providers import ProviderRequiredError, provider_required_response
from ..utils.constants import VISUAL_STYLES, SCRIPT_LANGUAGES, IMAGE_EXTENSIONS, NARRATION_VOLUME, BGM_VOLUME
from ..utils.paths import FRONTEND_DIST, GENERATED_DIR, PROJECTS_DIR, BGM_DIR


def register_session_routes(app):
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
            image_seconds = 5.0
            transition_seconds = render_setting(payload, "transition_seconds", 1, 0, 4.9)
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

        required_image_count = max(1, math.ceil(target_duration / 5.0))
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
            "media_count": required_image_count,
            "audio_segment_count": 1,
            "image_prompt_count": required_image_count,
            "required_image_count": required_image_count,
        }
        write_state(session_dir, state)
        return jsonify({"success": True, "session_id": session_id, "folder": str(session_dir), "topic": topic, "genre": genre,
                        "target_duration": target_duration, "required_image_count": required_image_count, "audio_clip_count": 1})

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
        try:
            script = generate_script_with_backend(topic, genre, session_id, state.get("script_language", "hindi"), target_duration)
        except ProviderRequiredError as exc:
            return provider_required_response(exc)
        script_filename = topic_filename(session_id, "_script.txt")
        script_path = session_dir / script_filename
        script_path.write_text(script, encoding="utf-8")
        legacy_script_path = session_dir / "documentary_script.txt"
        if legacy_script_path.exists() and legacy_script_path != script_path:
            legacy_script_path.unlink()

        state["status"] = "script_ready"
        state["script"] = script
        state["script_filename"] = script_filename
        write_state(session_dir, state)
        log_event(session_dir, f"Script generated for topic: {topic} | genre: {genre}")
        return jsonify({"success": True, "script": script, "download_url": f"/api/session/{session_id}/download/{script_filename}"})

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

        state = load_state(session_dir)
        script_filename = state.get("script_filename") or topic_filename(session_id, "_script.txt")
        (session_dir / script_filename).write_text(script, encoding="utf-8")
        state["script"] = script
        state["script_filename"] = script_filename
        state["status"] = "script_edited"
        write_state(session_dir, state)
        log_event(session_dir, "Documentary script edited and saved from the frontend")
        return jsonify({
            "success": True,
            "script": script,
            "download_url": f"/api/session/{session_id}/download/{script_filename}",
        })

    @app.route("/api/generate-audio", methods=["POST"])
    def generate_audio_route():
        payload = request.get_json(silent=True) or {}
        session_id = payload.get("session_id")
        voice = (payload.get("voice") or "Iapetus").strip() or "Iapetus"
        use_default_voice = bool(payload.get("use_default_voice"))
        if not session_id:
            return jsonify({"success": False, "message": "session_id is required."}), 400

        session_dir = get_session_dir(session_id)
        if not session_dir.exists():
            return jsonify({"success": False, "message": "Session not found."}), 404

        state = load_state(session_dir)
        from ..services.session import read_session_script
        script = read_session_script(session_dir, state, session_id)
        if not script:
            return jsonify({"success": False, "message": "Script must be generated before audio."}), 400

        try:
            audio_path, audio_filename = generate_audio_segments(session_dir, script, voice, use_default_voice, session_id)
        except ProviderRequiredError as exc:
            return jsonify({
                "success": False,
                "provider_required": True,
                "provider": "gemini",
                "alternate_provider": "default_voice",
                "allow_default_voice": True,
                "purpose": "audio",
                "message": "Gemini narration is unavailable. Enter/save a Gemini API key, or choose Use Default Voice to continue without Gemini.\n\nProvider error: " + (exc.detail or ""),
            }), 409
        except Exception as exc:
            log_event(session_dir, f"Narration generation failed: {exc}")
            return jsonify({"success": False, "message": str(exc)}), 503

        audio_duration = get_duration(str(audio_path))
        image_seconds = 5.0
        required_image_count = max(1, math.ceil(float(state.get("target_duration") or audio_duration) / image_seconds))
        state["status"] = "audio_ready"
        state["audio_file"] = str(audio_path)
        state["audio_filename"] = audio_filename
        state["audio_duration"] = round(float(audio_duration), 2)
        state["voice"] = "Default Voice" if use_default_voice else voice
        state["audio_provider"] = "default_voice" if use_default_voice else "gemini"
        state["audio_segment_count"] = 1
        state["audio_segments"] = [str(audio_path)]
        state["media_count"] = required_image_count
        state["required_image_count"] = required_image_count
        state["image_prompt_count"] = required_image_count
        write_state(session_dir, state)
        log_event(session_dir, f"Narration generated from full script; duration={state['audio_duration']}s; required images={required_image_count} at 5s/image")
        return jsonify({
            "success": True,
            "voice": voice,
            "segment_count": 1,
            "duration": round(float(audio_duration), 2),
            "image_count": required_image_count,
            "audio_clip_count": 1,
            "audio_url": f"/api/session/{session_id}/download/{audio_filename}",
            "download_url": f"/api/session/{session_id}/download/{audio_filename}",
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
        from ..services.session import read_session_script
        script = read_session_script(session_dir, state, session_id)
        if not script:
            return jsonify({"success": False, "message": "Script is missing."}), 400

        audio_filename = state.get("audio_filename") or topic_filename(session_id, "_narration.wav")
        audio_duration = float(state.get("audio_duration") or get_duration(str(session_dir / audio_filename)) or 0.0)
        image_seconds = 5.0
        required_count = int(state.get("required_image_count") or max(1, math.ceil(float(state.get("target_duration") or audio_duration) / image_seconds)))
        if required_count < 1 or required_count > 240:
            return jsonify({"success": False, "message": "The calculated image count is outside the supported range (1-240)."}), 400
        visual_style = (payload.get("visual_style") or state.get("visual_style") or "photorealistic").strip()
        if visual_style not in VISUAL_STYLES:
            return jsonify({"success": False, "message": "Unsupported visual style."}), 400
        state["visual_style"] = visual_style
        try:
            prompt_text = generate_prompt_text(state.get("topic") or "documentary subject", script, required_count, visual_style)
        except ProviderRequiredError as exc:
            return provider_required_response(exc)
        prompts_filename = topic_filename(session_id, "_image_prompts.txt")
        prompt_file = session_dir / prompts_filename
        prompt_file.write_text(prompt_text, encoding="utf-8")

        prompts = parse_prompts(prompt_text)
        state["status"] = "prompts_ready"
        state["prompts"] = prompts
        state["prompts_filename"] = prompts_filename
        state["required_prompt_count"] = len(prompts)
        state["required_image_count"] = len(prompts)
        state["media_count"] = len(prompts)
        generation_prompt_text = generate_generation_prompt_text(state.get("topic") or "documentary subject", prompts, visual_style)
        generation_prompts_filename = topic_filename(session_id, "_image_generation_prompts.txt")
        generation_prompt_file = session_dir / generation_prompts_filename
        generation_prompt_file.write_text(generation_prompt_text, encoding="utf-8")
        state["generation_prompt_file"] = str(generation_prompt_file)
        state["generation_prompts_filename"] = generation_prompts_filename
        write_state(session_dir, state)
        log_event(session_dir, f"Image prompts generated: {len(prompts)} prompts saved in session folder")
        return jsonify({
            "success": True,
            "prompts": prompts,
            "generation_prompts": generation_prompt_text,
            "download_url": f"/api/session/{session_id}/download/{prompts_filename}",
            "generation_download_url": f"/api/session/{session_id}/download/{generation_prompts_filename}",
        })

    @app.route("/api/session/<session_id>/download-images")
    def download_images_zip(session_id):
        import shutil
        session_dir = get_session_dir(session_id)
        image_dir = session_dir / "images"
        if not image_dir.exists():
            return jsonify({"success": False, "message": "No image folder found for this project."}), 404

        image_files = [
            path for path in image_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS and path.stem.isdigit()
        ]
        image_files.sort(key=lambda path: int(path.stem))
        if not image_files:
            return jsonify({"success": False, "message": "No numbered images are available yet."}), 404

        archive_base = session_dir / f"{session_id}_numbered_images"
        archive_path = shutil.make_archive(str(archive_base), "zip", root_dir=image_dir)
        return send_file(archive_path, as_attachment=True, download_name=f"{session_id}_numbered_images.zip")

    @app.route("/api/upload-images", methods=["POST"])
    def upload_images_route():
        from werkzeug.utils import secure_filename
        session_id = request.form.get("session_id")
        if not session_id:
            return jsonify({"success": False, "message": "session_id is required."}), 400

        session_dir = get_session_dir(session_id)
        if not session_dir.exists():
            return jsonify({"success": False, "message": "Session not found."}), 404

        state = load_state(session_dir)
        prompts = state.get("prompts")
        if not prompts:
            prompts_filename = state.get("prompts_filename") or topic_filename(session_id, "_image_prompts.txt")
            prompts_path = session_dir / prompts_filename
            prompts = parse_prompts(prompts_path.read_text(encoding="utf-8")) if prompts_path.exists() else []
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

            from ..services.session import image_index_from_filename
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
            image_seconds = 5.0
            transition_seconds = render_setting(payload, "transition_seconds", state.get("transition_seconds", 1), 0, 4.9)
            narration_volume = render_setting(payload, "narration_volume", state.get("narration_volume", NARRATION_VOLUME), 0, 3)
            bgm_volume = render_setting(payload, "bgm_volume", state.get("bgm_volume", BGM_VOLUME), 0, 1)
        except ValueError as error:
            return jsonify({"success": False, "message": str(error)}), 400
        if transition_seconds >= image_seconds:
            return jsonify({"success": False, "message": "transition_seconds must be less than image_seconds."}), 400

        audio_filename = state.get("audio_filename") or topic_filename(session_id, "_narration.wav")
        audio_path = session_dir / audio_filename
        if not audio_path.exists():
            return jsonify({"success": False, "message": "Generate narration audio before building the video."}), 400
        audio_duration = get_duration(str(audio_path))
        required_count = len(state.get("prompts") or []) or count_required_images(audio_duration, 5, 0)
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

        video_filename = topic_filename(session_id, ".mp4")
        output_video = session_dir / video_filename

        try:
            _, audio_duration, produced_duration, music_track = build_video_pipeline(
                files, audio_path, output_video,
                image_seconds, transition_seconds, narration_volume, bgm_volume,
            )
        except RuntimeError as error:
            return jsonify({"success": False, "message": str(error)}), 500

        state["status"] = "finalized"
        state["video_file"] = str(output_video)
        state["video_filename"] = video_filename
        state["music_file"] = str(output_video)
        state["image_seconds"] = image_seconds
        state["transition_seconds"] = transition_seconds
        state["narration_volume"] = narration_volume
        state["bgm_volume"] = bgm_volume
        write_state(session_dir, state)
        log_event(
            session_dir,
            f"Video pipeline complete: images+narration+music merged in one pass, saved as {video_filename} "
            f"(track={music_track}, audio={audio_duration:.3f}s, video={produced_duration:.3f}s)",
        )

        return jsonify({
            "success": True,
            "video_url": f"/api/session/{session_id}/download/{video_filename}",
            "download_url": f"/api/session/{session_id}/download/{video_filename}",
            "music_track": music_track,
            "filename": video_filename,
        })

    @app.route("/api/generate-social", methods=["POST"])
    def generate_social_route():
        payload = request.get_json(silent=True) or {}
        session_id = payload.get("session_id")
        if not session_id:
            return jsonify({"success": False, "message": "session_id is required."}), 400

        session_dir = get_session_dir(session_id)
        if not session_dir.exists():
            return jsonify({"success": False, "message": "Session not found."}), 404

        state = load_state(session_dir)
        topic = state.get("topic") or ""
        genre = state.get("genre") or "documentary"
        language = str(payload.get("language") or "en").lower()

        from ..services.session import read_session_script
        full_script = read_session_script(session_dir, state, session_id).strip()
        script_snippet = full_script[:800]
        context_line = f"Script context (first 800 chars):\n{script_snippet}\n\n" if script_snippet else ""

        try:
            result = generate_social_copy(session_id, topic, genre, language, context_line)
        except Exception as exc:
            log_event(session_dir, f"Social copy generation failed: {exc}")
            return jsonify({"success": False, "message": str(exc)}), 500

        return jsonify({"success": True, **result})

    @app.route("/api/session/<session_id>/state")
    def get_session_state(session_id):
        session_dir = get_session_dir(session_id)
        if not session_dir.exists():
            return jsonify({"success": False, "message": "Session not found."}), 404
        state = load_state(session_dir)
        return jsonify({"success": True, "state": state})
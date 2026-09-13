import json
import re
import os
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:
    Image = ImageDraw = ImageFont = None

from .providers import call_text_provider
from .session import log_event, get_session_dir
from ..utils.paths import RUNTIME_DIR
from ..utils.constants import IMAGE_EXTENSIONS


def _strip_json_fences(text: str) -> str:
    text = (text or "").strip()
    if "```" not in text:
        return text
    for part in text.split("```"):
        part = part.strip()
        if part[:4].lower() == "json":
            part = part[4:].strip()
        if part.startswith(("[", "{")):
            return part
    return text


def _first_json_start(text: str):
    positions = [index for index in (text.find("["), text.find("{")) if index != -1]
    return min(positions) if positions else None


def _close_and_load(fragment: str):
    if not fragment:
        return None
    in_string = False
    escape_next = False
    stack = []
    repaired = []
    for ch in fragment:
        if escape_next:
            escape_next = False
            repaired.append(ch)
            continue
        if ch == "\\" and in_string:
            escape_next = True
            repaired.append(ch)
            continue
        if ch == '"':
            in_string = not in_string
        elif not in_string:
            if ch in ("{", "["):
                stack.append("}" if ch == "{" else "]")
            elif ch in ("}", "]") and stack and stack[-1] == ch:
                stack.pop()
        repaired.append(ch)
    if in_string:
        repaired.append('"')
    joined = "".join(repaired).rstrip()
    while joined.endswith(","):
        joined = joined[:-1].rstrip()
        if joined.endswith(":"):
            last_quote = joined.rfind('"')
            prev_comma = joined.rfind(",")
            cut = prev_comma if prev_comma > last_quote else joined.rfind("{")
            if cut != -1:
                joined = joined[:cut].rstrip()
    joined += "".join(reversed(stack))
    try:
        return json.loads(joined)
    except json.JSONDecodeError:
        return None


def _extract_json(text):
    if not text:
        return None
    text = _strip_json_fences(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = _first_json_start(text)
    if start is None:
        return None
    fragment = text[start:]
    parsed = _close_and_load(fragment)
    if parsed is not None:
        return parsed
    trim_from = max(0, len(fragment) - 800)
    for end in range(len(fragment) - 1, trim_from, -1):
        parsed = _close_and_load(fragment[:end])
        if parsed is not None:
            return parsed
    return None


def _repair_truncated_array(text):
    if not text:
        return []
    text = _strip_json_fences(text)
    items = []
    in_string = False
    escape_next = False
    depth = 0
    start = None
    for index, ch in enumerate(text):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            if depth == 0:
                start = index
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    obj = json.loads(text[start:index + 1])
                    if isinstance(obj, dict):
                        items.append(obj)
                except json.JSONDecodeError:
                    pass
                start = None
    if start is not None:
        repaired = _close_and_load(text[start:])
        if isinstance(repaired, dict) and repaired.get("topic"):
            items.append(repaired)
    return items


def _coerce_topic_list(parsed) -> list:
    if isinstance(parsed, dict):
        if isinstance(parsed.get("topics"), list):
            parsed = parsed["topics"]
        elif parsed.get("topic"):
            parsed = [parsed]
        else:
            parsed = []
    if not isinstance(parsed, list):
        return []
    topics = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        title = str(item.get("topic") or "").strip()
        if not title:
            continue
        keywords = item.get("keywords") or []
        if isinstance(keywords, str):
            keywords = [part.strip() for part in re.split(r"[,;]", keywords) if part.strip()]
        elif not isinstance(keywords, list):
            keywords = []
        topics.append({
            "topic": title,
            "hook": str(item.get("hook") or "").strip(),
            "angle": str(item.get("angle") or "").strip(),
            "why": str(item.get("why") or "").strip(),
            "keywords": [str(keyword).strip() for keyword in keywords if str(keyword).strip()][:8],
        })
    return topics


def _topics_from_quoted_fields(text: str) -> list:
    titles = re.findall(r'"topic"\s*:\s*"((?:\\.|[^"\\])*)"', text or "")
    hooks = re.findall(r'"hook"\s*:\s*"((?:\\.|[^"\\])*)"', text or "")
    angles = re.findall(r'"angle"\s*:\s*"((?:\\.|[^"\\])*)"', text or "")
    whys = re.findall(r'"why"\s*:\s*"((?:\\.|[^"\\])*)"', text or "")
    topics = []
    for index, title in enumerate(titles):
        decoded = json.loads(f'"{title}"')
        if not decoded.strip():
            continue
        topics.append({
            "topic": decoded.strip(),
            "hook": json.loads(f'"{hooks[index]}"') if index < len(hooks) else "",
            "angle": json.loads(f'"{angles[index]}"') if index < len(angles) else "",
            "why": json.loads(f'"{whys[index]}"') if index < len(whys) else "",
            "keywords": [],
        })
    return topics


def _find_font(language="en", bold=False):
    candidates = []
    if str(language).lower().startswith("hi"):
        candidates += [
            "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSerifDevanagari-CondensedBold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSerifDevanagari-Regular.ttf",
            r"C:\Windows\Fonts\Nirmala.ttf" if not bold else r"C:\Windows\Fonts\NirmalaB.ttf",
            r"C:\Windows\Fonts\NirmalaUI.ttf" if not bold else r"C:\Windows\Fonts\NirmalaUI-Bold.ttf",
        ]
    candidates += [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _fit_font(draw, text, max_width, start_size, language="en", bold=True):
    font_path = _find_font(language, bold=bold)
    size = start_size
    while size >= 22:
        font = ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= max_width:
            return font
        size -= 2
    return ImageFont.truetype(font_path, 22) if font_path else ImageFont.load_default()


def _wrap_text(draw, text, font, max_width):
    words = str(text or "").split()
    if not words:
        return ""
    lines, current = [], ""
    for word in words:
        trial = word if not current else current + " " + word
        if draw.textbbox((0, 0), trial, font=font)[2] <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return "\n".join(lines[:3])


def _make_thumbnail_image(session_dir, thumbnail_text, language="en"):
    if Image is None:
        raise RuntimeError("Pillow is not installed; cannot render thumbnail text overlay.")

    width, height = 1280, 720
    images_dir = session_dir / "images"
    source = None
    for path in sorted(images_dir.glob("*")) if images_dir.exists() else []:
        if path.suffix.lower() in IMAGE_EXTENSIONS:
            source = path
            break

    if source:
        try:
            base = Image.open(source).convert("RGB")
            base.thumbnail((width, height), Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (width, height), (12, 16, 20))
            canvas.paste(base, ((width - base.width) // 2, (height - base.height) // 2))
        except Exception:
            canvas = Image.new("RGB", (width, height), (12, 16, 20))
    else:
        canvas = Image.new("RGB", (width, height), (12, 16, 20))
        draw_bg = ImageDraw.Draw(canvas)
        for y in range(height):
            t = y / height
            draw_bg.line((0, y, width, y), fill=(int(12 + 18 * t), int(18 + 22 * t), int(28 + 45 * t)))

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle((0, 0, width, height), fill=(0, 0, 0, 55))
    od.rectangle((0, height * 0.48, width, height), fill=(0, 0, 0, 125))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay)

    draw = ImageDraw.Draw(canvas)
    main = str(thumbnail_text.get("main_title", "")).strip()
    subtitle = str(thumbnail_text.get("subtitle", "")).strip()
    label = str(thumbnail_text.get("label", "")).strip()
    margin = 62
    max_width = width - margin * 2

    y = height - 250
    if label:
        label_font = _fit_font(draw, label, 380, 26, language, True)
        lb = draw.textbbox((0, 0), label, font=label_font)
        lw, lh = lb[2] - lb[0], lb[3] - lb[1]
        draw.rounded_rectangle((margin, y, margin + lw + 34, y + lh + 22), radius=8, fill=(233, 69, 96, 235))
        draw.text((margin + 17, y + 11), label, font=label_font, fill=(255, 255, 255, 255))
        y += lh + 42

    main_font = _fit_font(draw, main, max_width, 76, language, True)
    main_wrapped = _wrap_text(draw, main, main_font, max_width)
    draw.multiline_text((margin + 3, y + 5), main_wrapped, font=main_font, fill=(0, 0, 0, 180), spacing=4)
    draw.multiline_text((margin, y), main_wrapped, font=main_font, fill=(255, 244, 238, 255), spacing=4)
    main_h = draw.multiline_textbbox((margin, y), main_wrapped, font=main_font, spacing=4)[3] - y
    y += main_h + 18

    if subtitle:
        sub_font = _fit_font(draw, subtitle, max_width, 34, language, True)
        sub_wrapped = _wrap_text(draw, subtitle, sub_font, max_width)
        draw.multiline_text((margin + 2, y + 3), sub_wrapped, font=sub_font, fill=(0, 0, 0, 170), spacing=3)
        draw.multiline_text((margin, y), sub_wrapped, font=sub_font, fill=(246, 192, 64, 255), spacing=3)

    draw.line((margin, height - 42, width - margin, height - 42), fill=(255, 255, 255, 80), width=2)

    out = session_dir / "thumbnail_with_text.png"
    canvas.convert("RGB").save(out, "PNG", optimize=True)
    return out


def generate_social_copy(session_id, topic, genre, language="en", script_context=""):
    session_dir = get_session_dir(session_id)
    language_name = "Hindi (Devanagari)" if language.startswith("hi") else "English"

    prompt_yt = (
        f"Documentary topic: {topic}\nGenre: {genre}\nOutput language: {language_name}\n\n"
        f"{script_context}"
        'Return a JSON object with exactly these two keys:\n'
        '"youtube_title": video title under 70 chars, factual and compelling\n'
        '"youtube_description": 80 words max. Hook first sentence. 2 context sentences. End with 4 hashtags.\n\n'
        "Start with { and end with }. No markdown."
    )
    prompt_thumb = (
        f"Documentary topic: {topic}\nGenre: {genre}\nOutput language: {language_name}\n\n"
        'Return a JSON object with exactly two keys:\n'
        '"thumbnail_prompt": one vivid sentence describing a cinematic 16:9 YouTube thumbnail image for this documentary. Bold dramatic lighting, high contrast, cinematic color grading, rule of thirds composition, no text in the image itself. Make it visually striking with strong visual hierarchy.\n'
        '"thumbnail_text": a JSON object with these sub-keys:\n'
        '  "main_title": 2-4 bold impactful words for the large headline text on the thumbnail (all caps, high contrast, readable at small sizes)\n'
        '  "subtitle": one short punchy line under the title, max 6 words, creates curiosity or urgency\n'
        '  "label": optional short badge text like "FULL DOCUMENTARY" or "UNTOLD HISTORY" or "SHOCKING TRUTH" (or empty string)\n\n'
        "Start with { and end with }. No markdown."
    )
    prompt_ig = (
        f"Documentary topic: {topic}\nGenre: {genre}\nOutput language: {language_name}\n\n"
        f"{script_context}"
        'Return JSON with exactly these keys: "instagram_caption" and "tags".\n'
        'instagram_caption: a strong hook, 2 short context sentences, and a CTA. Keep the caption under 500 characters and finish with 10 relevant hashtags.\n'
        'tags: JSON array of exactly 8 short YouTube SEO tags, without #.\n'
    )

    def call_model(prompt_text):
        return call_text_provider(prompt_text, "Return only valid JSON. Do not use markdown. Do not explain your answer.", session_dir=session_dir, purpose="social copy", groq_kwargs={"temperature": 0.4, "max_tokens": 1200})

    last_error = None
    social = {}

    for attempt in range(3):
        try:
            raw_yt, provider = call_model(prompt_yt)
            raw_thumb, _ = call_model(prompt_thumb)
            raw_ig, _ = call_model(prompt_ig)

            log_event(session_dir, f"social yt    (attempt {attempt+1}): {raw_yt[:120]}")
            log_event(session_dir, f"social thumb (attempt {attempt+1}): {raw_thumb[:120]}")
            log_event(session_dir, f"social ig    (attempt {attempt+1}): {raw_ig[:120]}")

            parsed_yt = _extract_json(raw_yt) or {}
            parsed_thumb = _extract_json(raw_thumb) or {}
            parsed_ig = _extract_json(raw_ig) or {}

            merged = {**parsed_yt, **parsed_thumb, **parsed_ig}

            if merged.get("youtube_title"):
                social = merged
                break

            last_error = f"attempt {attempt+1}: yt={raw_yt[:60]} | ig={raw_ig[:60]}"
            log_event(session_dir, f"social unparseable: {last_error}")
        except Exception as exc:
            last_error = str(exc)
            log_event(session_dir, f"generate-social attempt {attempt+1} failed: {exc}")

    if not social:
        raise RuntimeError(f"Social copy generation failed after 3 attempts. Last error: {last_error}")

    thumbnail_text = social.get("thumbnail_text") if isinstance(social.get("thumbnail_text"), dict) else {}
    tags = social.get("tags", []) if isinstance(social.get("tags"), list) else []
    tags = [str(tag).strip() for tag in tags if str(tag).strip()]

    result = {
        "youtube_title": str(social.get("youtube_title", "")).strip(),
        "youtube_description": str(social.get("youtube_description", "")).strip(),
        "instagram_caption": str(social.get("instagram_caption", "")).strip(),
        "tags": tags[:20],
        "thumbnail_prompt": str(social.get("thumbnail_prompt", "")).strip(),
        "thumbnail_text": {
            "main_title": str(thumbnail_text.get("main_title", "")).strip(),
            "subtitle": str(thumbnail_text.get("subtitle", "")).strip(),
            "label": str(thumbnail_text.get("label", "")).strip(),
        },
    }

    try:
        thumb_path = _make_thumbnail_image(session_dir, result["thumbnail_text"], language)
        result["thumbnail_image_url"] = f"/api/session/{session_id}/download/{thumb_path.name}"
    except Exception as exc:
        log_event(session_dir, f"thumbnail render failed: {exc}")
        result["thumbnail_image_url"] = ""
        result["thumbnail_image_error"] = str(exc)

    log_event(session_dir, f"Social media copy generated for: {topic} | language={language_name}")
    return result
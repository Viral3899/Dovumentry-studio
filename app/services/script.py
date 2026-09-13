import math
import re
import sqlite3

from .providers import call_text_provider
from .session import log_event
from ..utils.constants import SCRIPT_LANGUAGES


def is_hindi_script(text: str) -> bool:
    devanagari = len(re.findall(r"[\u0900-\u097F]", text or ""))
    letters = len(re.findall(r"[A-Za-z\u0900-\u097F]", text or ""))
    return devanagari >= 20 and devanagari / max(letters, 1) >= 0.35


def has_excessive_word_repetition(text: str, max_repeats: int = 3) -> bool:
    words = re.findall(r"[\w\u0900-\u097F]{4,}", (text or "").lower())
    if len(words) < 20:
        return False
    counts = {}
    for word in words:
        counts[word] = counts.get(word, 0) + 1
    most_common = max(counts.values()) if counts else 0
    return most_common > max_repeats


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


def generate_script_with_backend(topic, genre, session_id, script_language="hindi", target_duration=60):
    from .session import get_session_dir
    sd = get_session_dir(session_id)
    lang = SCRIPT_LANGUAGES.get(script_language, SCRIPT_LANGUAGES["hindi"])
    minimum = max(40, math.ceil(target_duration * 2.0))
    target = max(minimum, math.ceil(target_duration * 2.2))
    maximum = max(target + 20, math.ceil(target_duration * 2.6))
    prompt = (
        f"Write a complete cinematic {lang} {genre or 'documentary'} narration about {topic}. "
        f"Requested length {target_duration:.0f} seconds. Write {target} words, never fewer than {minimum} or more than {maximum}. "
        f"Start with a topic-specific viral hook and curiosity gap; give context; tell the story chronologically; "
        f"build to the key revelation; explain consequences; end smoothly with a memorable thought. "
        f"No headings, bullets, scene labels, production notes or generic filler. Never invent facts. Return only narration.\n\nTOPIC: {topic}"
    )
    for attempt in range(3):
        text, provider = call_text_provider(
            prompt + (f"\nRetry {attempt+1}: ensure at least {minimum} words." if attempt else ""),
            f"You are a professional {lang} documentary writer.",
            sd, "script",
            {"temperature": 0.8, "max_tokens": max(1800, min(6000, math.ceil(target_duration * 5)))}
        )
        if len(re.findall(r"\S+", text)) >= minimum and (script_language != "hindi" or is_hindi_script(text)):
            log_event(sd, f"Script generated with {provider}")
            return text
    raise RuntimeError("AI returned a script shorter than the requested duration.")
import re

from .providers import call_text_provider
from .session import log_event, parse_prompts
from ..utils.constants import VISUAL_STYLES

import sqlite3

def enforce_visual_style(prompts, visual_style):
    return "\n\n".join(
        f"{i}. {p} MANDATORY VISUAL STYLE: {VISUAL_STYLES.get(visual_style, VISUAL_STYLES['photorealistic'])}."
        for i, p in enumerate(prompts, 1)
    )


def generate_prompt_text(topic, script, count, visual_style="photorealistic"):
    """Generate exactly `count` prompts without relying on one huge LLM response.

    Groq sometimes stops early when a large prompt batch approaches the model's
    output-token limit. Generate small internal batches, then renumber them into
    one continuous list. There is intentionally no user-facing 24-image limit.
    """
    style = VISUAL_STYLES.get(visual_style, VISUAL_STYLES["photorealistic"])
    batch_size = 6
    all_prompts = []

    for batch_start in range(1, count + 1, batch_size):
        batch_end = min(count, batch_start + batch_size - 1)
        batch_count = batch_end - batch_start + 1

        words = script.split()
        total_words = len(words)
        start_word = round((batch_start - 1) * total_words / count)
        end_word = round(batch_end * total_words / count)
        script_chunk = " ".join(words[start_word:end_word]).strip() or script

        prompt = f"""Generate EXACTLY {batch_count} numbered cinematic documentary image prompts.

IMAGE NUMBERS MUST BE {batch_start} THROUGH {batch_end}.
Do not stop early. Do not omit any number. Do not add extra numbers.

TOPIC:
{topic}

NARRATION SEGMENT:
{script_chunk}

Each prompt is one self-contained scene in chronological order. Include:
- subject
- setting and historical/time context
- action
- lighting
- mood/atmosphere
- camera angle/composition

VISUAL STYLE:
{style}

16:9 landscape. Photorealistic cinematic documentary. Realistic people and environments.
No text, subtitles, captions, logos, watermarks or UI. Maintain recurring-character consistency.
Do not invent facts, names, dates, places or events not supported by the narration.

OUTPUT FORMAT — RETURN ONLY THESE NUMBERED PROMPTS:
{batch_start}. prompt
{batch_start + 1}. prompt
...
{batch_end}. prompt
"""

        last_error = None
        parsed = []
        for attempt in range(1, 4):
            raw, _ = call_text_provider(
                prompt,
                "You create concise, factual cinematic documentary image prompts. Always complete every requested numbered item.",
                purpose=f"image prompts {batch_start}-{batch_end}",
                groq_kwargs={"temperature": 0.4, "max_tokens": 3200},
            )
            parsed = parse_prompts(raw)
            if len(parsed) == batch_count:
                break
            last_error = f"Expected {batch_count} prompts for batch {batch_start}-{batch_end}, got {len(parsed)}."

            prompt += f"\n\nIMPORTANT RETRY: Your previous response contained {len(parsed)} prompts. Return ALL {batch_count} prompts, numbered {batch_start} through {batch_end}."

        if len(parsed) != batch_count:
            raise RuntimeError(last_error or f"Expected {batch_count} prompts for batch {batch_start}-{batch_end}.")

        all_prompts.extend(parsed)

    if len(all_prompts) != count:
        raise RuntimeError(f"Expected {count} image prompts, got {len(all_prompts)}.")

    return enforce_visual_style(all_prompts, visual_style)


def generate_generation_prompt_text(topic, prompts, visual_style="photorealistic"):
    return "IMAGE GENERATION INSTRUCTIONS\nGenerate images in chronological order. Keep recurring characters and visual continuity consistent. Export as 1.jpeg, 2.jpeg, 3.jpeg...\n\n" + "\n\n".join(prompts)
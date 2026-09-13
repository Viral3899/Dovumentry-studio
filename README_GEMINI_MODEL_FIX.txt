Gemini model compatibility fix

Updated Gemini text fallback from gemini-2.5-flash to gemini-3.6-flash.
Updated Gemini TTS from gemini-2.5-flash-preview-tts to gemini-3.1-flash-tts-preview.

These are current Gemini 3 model IDs. The app still allows GEMINI_TEXT_MODEL and
GEMINI_TTS_MODEL environment variables to override them.

The existing Groq -> Gemini fallback and saved API-key flow are preserved.

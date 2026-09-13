Provider + narration reliability fixes

1. Groq is primary for text generation.
2. Saved Groq keys are reused; empty/model responses are retried and do NOT trigger a fake API-key request.
3. Groq quota/rate/capacity failures fall back to a saved Gemini key.
4. If Gemini is needed and no key is saved, the UI asks for Gemini.
5. Gemini narration failures show two choices: Save Gemini API Key or Use Default Voice.
6. Use Default Voice uses the local Edge TTS fallback and produces the same single final narration WAV.
7. Saving a Gemini key from the narration dialog automatically retries narration.
8. Suggest Topics now uses the same provider fallback and more robust JSON parsing.
9. No 24-image limit; Outputs=1 remains the Flow requirement.
10. Keys are stored locally in the runtime API key file and reused.

# Documentary Studio

Documentary Studio is a Flask and React application for creating narrated documentary videos from a topic, script, image prompts, uploaded images, and background music.

## Current Workflow

The web app uses six steps:

1. **Topic**: enter the subject, script language, target duration, genre, and visual style.
2. **Script**: generate and edit narration in Hindi, English, or Hinglish.
3. **Narration**: generate and preview the voice-over.
4. **Prompts**: generate numbered image prompts with the selected visual style.
5. **Images**: upload numbered JPG, JPEG, PNG, or WEBP images.
6. **Final Cut**: choose pacing and audio levels, then render the documentary.

The renderer adds Ken Burns-style motion, smooth crossfades, narration audio, and optional background music. The final MP4 is synchronized to the narration duration.

## User Settings

Project setup supports:

- Script language: Hindi, English, or Hinglish
- Visual style: photorealistic, cartoon, anime, 3D animation, or painted illustration
- Target narration/video duration: 20 to 600 seconds
- Seconds per image: 1 to 30
- Transition duration: 0 to 10 seconds, less than the image duration
- Narration volume: 0 to 3
- BGM volume: 0 to 1

The selected visual style is written into every image prompt so cartoon projects receive cartoon prompts instead of photorealistic prompts.

## Requirements

- Python 3.11+
- Node.js 18+
- FFmpeg and FFprobe available in `PATH`
- Groq API key for script and prompt generation
- Gemini API key for Gemini TTS, unless using the Windows speech fallback

## Setup

Install frontend dependencies and Python packages:

```bash
npm run install:all
pip install flask werkzeug groq google-genai pyttsx3 pywin32
```

Set API keys as environment variables. Do not place keys in source files:

```bash
export GROQ_API_KEY="your-groq-key"
export GEMINI_API_KEY="your-gemini-key"
```

On Windows PowerShell:

```powershell
$env:GROQ_API_KEY = "your-groq-key"
$env:GEMINI_API_KEY = "your-gemini-key"
```

## Run

Start both servers from the repository root:

```bash
npm run dev
```

Open `http://localhost:5173`. The backend API runs at `http://127.0.0.1:5000`.

Backend only:

```bash
python main.py
```

Both processes with the Python launcher:

```bash
python run_app.py
```

## API Routes

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/api/create-session` | Create a project and save user settings |
| `POST` | `/api/generate-script` | Generate narration for the selected language and duration |
| `POST` | `/api/update-script` | Save edited narration |
| `POST` | `/api/generate-audio` | Generate narration WAV |
| `POST` | `/api/generate-prompts` | Generate style-enforced image prompts |
| `POST` | `/api/upload-images` | Validate and organize numbered images |
| `POST` | `/api/build-video` | Render animated visuals with narration |
| `POST` | `/api/finalize-music` | Mix selected BGM under the narration |
| `GET` | `/api/session/<id>/state` | Read project state |
| `GET` | `/api/session/<id>/download/<file>` | Download a project artifact |

## Project Artifacts

Each project is stored locally under `projects/<topic>/` and may contain:

```text
documentary_script.txt
image_prompts.txt
image_generation_prompts.txt
narration.wav
documentary_video.mp4
documentary_final_with_music.mp4
images/
session_state.json
generation_log.txt
```

Generated projects and media are ignored by Git, so large videos, images, and audio are not pushed to GitHub.

## Standalone Pipelines

The command-line stages remain available:

```bash
python pipeline_1_until_image_prompts.py
python pipeline_2_after_images.py
```

Pipeline 1 creates the script, narration, and image prompts. Pipeline 2 asks for pacing and volume settings, checks numbered images, and creates the final video.

## Tests and Build

```bash
python -m pytest -q
npm run build
```

## Security

- Keep API keys in environment variables.
- Never commit `.env` files or generated project media.
- Rotate any key that has ever appeared in source code, logs, screenshots, or terminal output.

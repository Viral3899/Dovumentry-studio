# AI Documentary Generator

A full-stack application for creating AI-generated documentaries with a step-by-step workflow.

## Features

- **8-Step Workflow**: Setup → Script → Prompts → Upload → Verify → Audio → Video → Output
- **AI Script Generation**: Uses Groq (GPT-OSS) for documentary scripts
- **Image Prompt Generation**: Detailed prompts for AI image generation
- **Image Upload & Validation**: Drag-and-drop with count verification
- **Audio Generation**: Gemini TTS for narration + background music selection
- **Video Rendering**: FFmpeg with Ken Burns effects, transitions, audio mixing
- **Download All Assets**: Video, script, prompts, audio, images, metadata

## Architecture

```
documentary-generator/
├── backend/                 # Node.js/Express API
│   ├── src/
│   │   ├── config/         # Configuration
│   │   ├── routes/         # API routes
│   │   ├── services/       # Business logic
│   │   ├── utils/          # Helpers
│   │   └── index.js        # Entry point
│   └── package.json
├── frontend/               # React + Vite + Tailwind
│   ├── src/
│   │   ├── components/     # Reusable components
│   │   ├── pages/          # Step pages
│   │   ├── context/        # React context
│   │   ├── utils/          # API client
│   │   └── styles/         # Global styles
│   └── package.json
└── projects/               # Generated projects (auto-created)
```

## Prerequisites

- Node.js 18+
- FFmpeg installed and in PATH
- Groq API key
- Gemini API key

## Setup

1. **Clone and install dependencies:**
   ```bash
   cd documentary-generator
   npm run install:all
   ```

2. **Configure environment:**
   ```bash
   cd backend
   cp .env.example .env
   # Edit .env with your API keys
   ```

3. **Start development servers:**
   ```bash
   # From root directory
   npm run dev
   ```
   
   Or run separately:
   ```bash
   # Terminal 1 - Backend
   cd backend && npm run dev
   
   # Terminal 2 - Frontend
   cd frontend && npm run dev
   ```

4. **Open frontend:** http://localhost:5173

## Workflow

### Step 1: Documentary Setup
- Enter topic, duration, genre, language, voice
- System calculates required images: `ceil(duration / 5)`

### Step 2: Generated Script
- Review AI-generated script with scenes
- Each scene has narration, visual description, duration
- Copy/download script

### Step 3: Image Prompts
- View all AI image generation prompts
- Copy individual or all prompts
- Download prompts as text/JSON

### Step 4: Upload Images
- Upload exactly the required number of images
- Drag-and-drop or click to browse
- Real-time count validation

### Step 5: Verify Images
- Rename images with scene numbers (1_, 2_, etc.)
- Validate sequence, readability, dimensions
- Check for missing/duplicate numbers

### Step 6: Generate Audio
- Generate narration via Gemini TTS
- Automatic background music selection by genre
- Audio mixing with ducking (BGM at 15%)

### Step 7: Generate Video
- FFmpeg rendering with progress tracking
- Ken Burns effects (zoom/pan)
- Crossfade transitions
- Audio synchronization

### Step 8: Final Output
- Download video (MP4, 1920×1080, H.264)
- Download all intermediate assets
- Complete project metadata

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/documentary/generate` | Generate script & prompts |
| POST | `/api/images/upload` | Upload images |
| GET | `/api/images/status` | Check upload status |
| POST | `/api/images/rename` | Rename with scene numbers |
| POST | `/api/images/verify` | Validate images |
| POST | `/api/audio/generate` | Generate narration + BGM |
| POST | `/api/video/generate` | Render final video |
| GET | `/api/job/:id/status` | Get project status |
| GET | `/api/download/:projectId/:fileType` | Download files |
| GET | `/api/projects` | List all projects |

## Project Structure

Each project creates:
```
projects/{projectId}/
├── script/
│   ├── documentary_script.txt
│   └── script.json
├── image_prompts/
│   ├── image_prompts.txt
│   └── prompts.json
├── images/
│   ├── 1_original-name.jpg
│   ├── 2_original-name.jpg
│   └── ...
├── audio/
│   ├── narration.wav
│   ├── bgm.mp3
│   └── final_audio.mp3
├── video/
│   └── documentary_final.mp4
└── metadata/
    ├── documentary_metadata.json
    └── state.json
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| PORT | Backend port | 3001 |
| GROQ_API_KEY | Groq API key | Required |
| GEMINI_API_KEY | Gemini API key | Required |
| UPLOAD_DIR | Upload directory | ./uploads |
| PROJECTS_DIR | Projects directory | ./projects |
| MAX_FILE_SIZE | Max upload size (bytes) | 50MB |

## Resume Support

Projects maintain state:
- `INIT` → `SCRIPT_COMPLETE` → `PROMPTS_COMPLETE` → `IMAGES_UPLOADED` → `IMAGES_VERIFIED` → `AUDIO_COMPLETE` → `VIDEO_RENDERING` → `COMPLETE`

If generation fails, resume from last successful step.

## Security

- API keys stored in environment variables only
- Server-side file validation
- No secrets exposed to frontend
- File type and size validation

## Tech Stack

**Backend:**
- Node.js + Express
- Groq SDK (script generation)
- Google Generative AI (TTS)
- Fluent-FFmpeg (video rendering)
- Sharp (image validation)
- Multer (file uploads)

**Frontend:**
- React 18 + Vite
- Tailwind CSS
- React Router
- Axios
- Lucide React (icons)

## License

MIT
# 🎬 VideoPeen

AI-powered video editing web app for cooking content creators. Upload raw cooking footage, and VideoPeen uses local AI models (Qwen 2.5 VL for vision, Qwen 2.5 for text) running on Apple Silicon via MLX to automatically analyze, select, and stitch the best clips into a polished cooking video.

## Architecture

- **Backend:** Python / FastAPI with WebSocket progress updates
- **Frontend:** React + TypeScript + Vite + Tailwind CSS
- **Database:** MongoDB (via motor async driver)
- **AI Models:** Qwen 2.5 VL 3B (vision) + Qwen 2.5 3B (text) via MLX
- **Video Processing:** FFmpeg for splitting, trimming, and stitching

## How It Works

1. **Upload** raw cooking videos (multiple files supported)
2. **Configure** recipe details, dish name, target output duration
3. **Process** — the AI pipeline:
   - Splits videos into 2-minute segments, then into analysis chunks
   - Extracts keyframes and analyzes each chunk with the vision model
   - Uses the text LLM to select and order the best clips
   - Stitches selected clips into the final video
4. **Preview & Download** the result

## Prerequisites

- **macOS** with Apple Silicon (M1/M2/M3/M4) — required for MLX
- **Python 3.11+**
- **Node.js 18+**
- **FFmpeg** (`brew install ffmpeg`)
- **MongoDB** (via Docker or local install)

## Quick Start

### 1. Start MongoDB

```bash
docker compose up -d
```

### 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env if needed

uvicorn app.main:app --reload --port 8000
```

The first run will download the MLX models (~2-4 GB each). This only happens once.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** in your browser.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/projects` | Create a new project |
| GET | `/api/projects` | List all projects |
| GET | `/api/projects/:id` | Get project details |
| PATCH | `/api/projects/:id` | Update project |
| DELETE | `/api/projects/:id` | Delete project |
| POST | `/api/projects/:id/upload` | Upload a video file |
| GET | `/api/projects/:id/upload` | List uploaded clips |
| POST | `/api/projects/:id/process` | Start AI processing |
| GET | `/api/projects/:id/output` | Download final video |
| WS | `/ws/:id` | Real-time progress updates |

## Project Structure

```
videopeen/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── config.py            # Settings
│   │   ├── models/project.py    # Pydantic models
│   │   ├── services/
│   │   │   ├── video_processor.py  # FFmpeg splitting
│   │   │   ├── video_analyzer.py   # MLX vision analysis
│   │   │   ├── clip_selector.py    # MLX text clip selection
│   │   │   ├── video_stitcher.py   # FFmpeg stitching
│   │   │   └── pipeline.py         # Orchestrator
│   │   ├── routers/             # API routes
│   │   └── websocket/manager.py # WS connection manager
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/          # React components
│   │   ├── hooks/               # useWebSocket, useUpload
│   │   ├── services/api.ts      # API client
│   │   └── types/index.ts       # TypeScript types
│   └── package.json
├── docker-compose.yml           # MongoDB
└── README.md
```

## Environment Variables

See `backend/.env.example` for all configurable options:

- `MONGODB_URI` — MongoDB connection string
- `VISION_MODEL` — MLX vision model ID (default: Qwen 2.5 VL 3B 4-bit)
- `TEXT_MODEL` — MLX text model ID (default: Qwen 2.5 3B 4-bit)
- `UPLOAD_DIR` / `OUTPUT_DIR` — File storage paths

## License

MIT

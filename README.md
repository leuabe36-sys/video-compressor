# 🎬 High-Quality Video Compressor

A production-ready video compression system with CLI tool and deployable REST API. Built on FFmpeg with optimized encoding profiles for maximum quality preservation.

## Features

- **6 Quality Profiles** from ultra-high-quality to web-optimized
- **H.264 & H.265 (HEVC)** codec support
- **Two-pass encoding** for maximum quality
- **Hardware acceleration** (NVIDIA NVENC, VAAPI, VideoToolbox)
- **Batch processing** for directories
- **REST API** with async job processing
- **Docker deployment** ready
- **Smart resolution/FPS limiting** per profile

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Upload Video  │────▶│  Async Compress  │────▶│  Download MP4   │
│   (API/CLI)     │     │  (FFmpeg Engine) │     │   (H.264/265)   │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

## Quick Start

### 1. CLI Usage

```bash
# Install dependencies
pip install -r requirements.txt

# Requires FFmpeg installed
# Ubuntu/Debian: sudo apt-get install ffmpeg
# macOS: brew install ffmpeg
# Windows: choco install ffmpeg

# Single file - high quality (recommended)
python video_compressor.py -i input.mov -o output.mp4 --profile high

# Ultra quality with two-pass encoding
python video_compressor.py -i input.mov -o output.mp4 --profile ultra --two-pass

# Web-optimized (720p, 30fps, smaller file)
python video_compressor.py -i input.mov -o output.mp4 --profile web

# HEVC/H.265 for maximum compression
python video_compressor.py -i input.mov -o output.mp4 --profile h265_balanced

# Batch process entire directory
python video_compressor.py -i ./videos/ -o ./compressed/ --profile balanced --batch

# NVIDIA GPU acceleration
python video_compressor.py -i input.mov -o output.mp4 --profile high --hwaccel nvenc
```

### 2. API Deployment

```bash
# Local development
python app.py

# Or with uvicorn directly
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

**API Endpoints:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Service info |
| `/profiles` | GET | List compression profiles |
| `/compress` | POST | Upload & compress video |
| `/jobs/{id}` | GET | Check job status |
| `/download/{id}` | GET | Download compressed file |
| `/jobs/{id}` | DELETE | Remove job & files |

**Example API Usage:**

```bash
# Upload and compress
curl -X POST http://localhost:8000/compress \
  -F "file=@video.mov" \
  -F "profile=high" \
  -F "two_pass=true"

# Response: {"job_id": "abc-123", "status": "pending", ...}

# Check status
curl http://localhost:8000/jobs/abc-123

# Download when complete
curl -O -J http://localhost:8000/download/abc-123
```

### 3. Docker Deployment

```bash
# Build and run
docker-compose up --build -d

# Or manually
docker build -t video-compressor .
docker run -p 8000:8000 -v $(pwd)/outputs:/app/outputs video-compressor

# With NVIDIA GPU
docker run --gpus all -p 8000:8000 video-compressor
```

## Compression Profiles

| Profile | CRF | Preset | Codec | Max Res | Use Case |
|---------|-----|--------|-------|---------|----------|
| `ultra` | 16 | veryslow | H.264 | Original | Archival, mastering |
| `high` | 18 | slow | H.264 | Original | **Recommended** general use |
| `balanced` | 23 | medium | H.264 | 1080p | Quality/size balance |
| `web` | 28 | fast | H.264 | 720p@30fps | Streaming, web |
| `h265_ultra` | 20 | slow | H.265 | Original | Maximum compression |
| `h265_balanced` | 26 | medium | H.265 | 1080p | Efficient storage |

**CRF Guide:** Lower = better quality, larger file. 18 is visually lossless. 23 is default.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | 8000 | API server port |
| `HOST` | 0.0.0.0 | Bind address |
| `WORKERS` | 1 | Uvicorn workers |
| `MAX_FILE_SIZE` | 2147483648 | Max upload (bytes) |
| `CLEANUP_HOURS` | 24 | Auto-delete old files |
| `UPLOAD_DIR` | ./uploads | Upload storage |
| `OUTPUT_DIR` | ./outputs | Output storage |

## Production Deployment

### Systemd Service (Linux)

Create `/etc/systemd/system/video-compressor.service`:

```ini
[Unit]
Description=Video Compression API
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/video-compressor
Environment=PORT=8000
Environment=WORKERS=4
Environment=MAX_FILE_SIZE=4294967296
ExecStart=/opt/video-compressor/venv/bin/python app.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable video-compressor
sudo systemctl start video-compressor
```

### Reverse Proxy (Nginx)

```nginx
server {
    listen 80;
    server_name compressor.yourdomain.com;
    client_max_body_size 4G;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 300s;
    }
}
```

### Cloud Deployment

**Render.com:**
```yaml
# render.yaml
services:
  - type: web
    name: video-compressor
    runtime: docker
    plan: standard
    envVars:
      - key: PORT
        value: 8000
      - key: MAX_FILE_SIZE
        value: 1073741824
```

**Railway:**
```bash
railway login
railway init
railway up
```

**AWS ECS/Fargate:**
Use the provided Dockerfile with Fargate. Mount EFS for persistent storage.

## Hardware Acceleration

### NVIDIA NVENC (requires NVIDIA Docker runtime)

```bash
# Check GPU support
ffmpeg -encoders | grep nvenc

# Enable in API
curl -X POST http://localhost:8000/compress \
  -F "file=@video.mov" \
  -F "hardware_accel=nvenc"
```

### Intel Quick Sync (VAAPI)

```bash
# Requires Intel GPU in container
docker run --device /dev/dri:/dev/dri video-compressor
```

## File Structure

```
video-compressor/
├── video_compressor.py    # Core compression engine
├── app.py                 # FastAPI web service
├── requirements.txt       # Python dependencies
├── Dockerfile             # Container image
├── docker-compose.yml     # Orchestration
├── .dockerignore          # Build exclusions
└── README.md             # This file
```

## License

MIT License - Free for commercial and personal use.

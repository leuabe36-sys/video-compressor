#!/usr/bin/env python3
"""
Video Compression API - Deployable Web Service
FastAPI + Uvicorn with async job processing
"""

import os
import uuid
import shutil
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional, Literal
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import uvicorn

from video_compressor import VideoCompressor, PROFILES, CompressionProfile

# Configuration
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./outputs"))
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", "2147483648"))  # 2GB default
CLEANUP_HOURS = int(os.getenv("CLEANUP_HOURS", "24"))

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# Job tracking
jobs = {}


class JobStatus(BaseModel):
    job_id: str
    status: str  # pending, processing, completed, failed
    progress: int
    message: str
    input_file: Optional[str] = None
    output_file: Optional[str] = None
    stats: Optional[dict] = None
    created_at: str
    completed_at: Optional[str] = None


class CompressRequest(BaseModel):
    profile: str = "high"
    two_pass: bool = False
    keep_audio: bool = True
    hardware_accel: Optional[Literal["nvenc", "vaapi", "videotoolbox"]] = None


def cleanup_old_files():
    """Remove files older than CLEANUP_HOURS"""
    cutoff = datetime.now().timestamp() - (CLEANUP_HOURS * 3600)
    for directory in [UPLOAD_DIR, OUTPUT_DIR]:
        for file_path in directory.iterdir():
            if file_path.is_file() and file_path.stat().st_mtime < cutoff:
                try:
                    file_path.unlink()
                except OSError:
                    pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown events"""
    # Startup
    cleanup_old_files()
    yield
    # Shutdown
    pass


app = FastAPI(
    title="Video Compression API",
    description="High-quality video compression service with multiple quality profiles",
    version="1.0.0",
    lifespan=lifespan
)

compressor = VideoCompressor()


@app.get("/")
async def root():
    return {
        "service": "Video Compression API",
        "version": "1.0.0",
        "profiles": list(PROFILES.keys()),
        "endpoints": {
            "upload_compress": "POST /compress",
            "job_status": "GET /jobs/{job_id}",
            "download": "GET /download/{job_id}",
            "profiles": "GET /profiles"
        }
    }


@app.get("/profiles")
async def get_profiles():
    """Get available compression profiles"""
    return {
        name: {
            "crf": p.crf,
            "preset": p.preset,
            "codec": p.codec,
            "audio_bitrate": p.audio_bitrate,
            "max_resolution": f"{p.max_width or 'original'}x{p.max_height or 'original'}" if p.max_width or p.max_height else "original",
            "fps": p.fps or "original"
        }
        for name, p in PROFILES.items()
    }


@app.post("/compress", response_model=JobStatus)
async def compress_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    profile: str = Form("high"),
    two_pass: bool = Form(False),
    keep_audio: bool = Form(True),
    hardware_accel: Optional[str] = Form(None)
):
    """
    Upload and compress a video file.
    Returns immediately with a job ID. Check status with /jobs/{job_id}.
    """
    if profile not in PROFILES:
        raise HTTPException(status_code=400, detail=f"Invalid profile. Choose: {list(PROFILES.keys())}")

    # Validate file extension
    allowed = (".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm", ".m4v", ".mpeg", ".mpg")
    if not file.filename.lower().endswith(allowed):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format. Allowed: {allowed}"
        )

    job_id = str(uuid.uuid4())
    input_path = UPLOAD_DIR / f"{job_id}_{file.filename}"
    output_path = OUTPUT_DIR / f"{job_id}_compressed.mp4"

    # Save uploaded file
    with open(input_path, "wb") as f:
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            input_path.unlink(missing_ok=True)
            raise HTTPException(status_code=413, detail=f"File too large. Max: {MAX_FILE_SIZE // 1024 // 1024}MB")
        f.write(content)

    # Create job
    jobs[job_id] = JobStatus(
        job_id=job_id,
        status="pending",
        progress=0,
        message="Queued for processing",
        input_file=file.filename,
        created_at=datetime.now().isoformat()
    )

    # Process in background
    background_tasks.add_task(
        process_compression,
        job_id,
        str(input_path),
        str(output_path),
        profile,
        two_pass,
        keep_audio,
        hardware_accel
    )

    return jobs[job_id]


async def process_compression(
    job_id: str,
    input_path: str,
    output_path: str,
    profile_name: str,
    two_pass: bool,
    keep_audio: bool,
    hardware_accel: Optional[str]
):
    """Background compression task"""
    job = jobs[job_id]
    job.status = "processing"
    job.progress = 10
    job.message = "Starting compression..."

    try:
        profile = PROFILES[profile_name]

        # Run compression in thread pool (FFmpeg is blocking)
        loop = asyncio.get_event_loop()
        stats = await loop.run_in_executor(
            None,
            lambda: compressor.compress(
                input_path,
                output_path,
                profile,
                two_pass=two_pass,
                keep_audio=keep_audio,
                hardware_accel=hardware_accel
            )
        )

        job.status = "completed"
        job.progress = 100
        job.message = "Compression complete"
        job.output_file = Path(output_path).name
        job.stats = stats
        job.completed_at = datetime.now().isoformat()

        # Cleanup input file
        Path(input_path).unlink(missing_ok=True)

    except Exception as e:
        job.status = "failed"
        job.progress = 0
        job.message = str(e)
        job.completed_at = datetime.now().isoformat()
        Path(input_path).unlink(missing_ok=True)
        Path(output_path).unlink(missing_ok=True)


@app.get("/jobs/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    """Check compression job status"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]


@app.get("/download/{job_id}")
async def download_file(job_id: str):
    """Download compressed video"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]
    if job.status != "completed":
        raise HTTPException(status_code=400, detail=f"Job status: {job.status}")

    file_path = OUTPUT_DIR / job.output_file
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        file_path,
        media_type="video/mp4",
        filename=f"compressed_{job.input_file or 'video'}.mp4"
    )


@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete a job and its files"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]

    # Cleanup files
    for pattern in [f"{job_id}_*"]:
        for directory in [UPLOAD_DIR, OUTPUT_DIR]:
            for file_path in directory.glob(pattern):
                file_path.unlink(missing_ok=True)

    del jobs[job_id]
    return {"message": "Job deleted"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    workers = int(os.getenv("WORKERS", "1"))

    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        workers=workers,
        reload=False
    )

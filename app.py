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
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
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


UI_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Compressor</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root{
    --bg:#0A1412;
    --panel:#101E1A;
    --panel-2:#16281F;
    --border:#24392F;
    --text:#E9F5EE;
    --text-dim:#7E9689;
    --mint:#6EE7B0;
    --mint-dim:#3E7A5C;
    --amber:#F0B429;
    --coral:#F2704B;
    --mono:'IBM Plex Mono',ui-monospace,monospace;
    --sans:'Inter',system-ui,sans-serif;
  }
  *{box-sizing:border-box;}
  html,body{margin:0;padding:0;}
  body{
    background:
      radial-gradient(ellipse 80% 50% at 50% -10%, rgba(110,231,176,0.06), transparent),
      var(--bg);
    color:var(--text);
    font-family:var(--sans);
    min-height:100vh;
    padding:24px 16px 64px;
  }
  @media (prefers-reduced-motion: no-preference){
    .rec-dot{animation:pulse 1.6s ease-in-out infinite;}
  }
  @keyframes pulse{0%,100%{opacity:1;}50%{opacity:0.25;}}

  .wrap{max-width:640px;margin:0 auto;}

  header{
    display:flex;align-items:center;gap:10px;
    padding:14px 18px;
    border:1px solid var(--border);
    border-radius:10px 10px 0 0;
    background:var(--panel);
    font-family:var(--mono);
  }
  .rec-dot{width:8px;height:8px;border-radius:50%;background:var(--coral);flex-shrink:0;}
  header .brand{font-weight:600;letter-spacing:0.08em;font-size:13px;}
  header .spacer{flex:1;}
  header .chan{font-size:12px;color:var(--text-dim);}
  header .chan b{color:var(--mint);font-weight:600;}

  main{
    border:1px solid var(--border);
    border-top:none;
    border-radius:0 0 10px 10px;
    background:var(--panel);
    padding:22px;
  }

  .drop{
    border:1.5px dashed var(--border);
    border-radius:8px;
    padding:28px 16px;
    text-align:center;
    cursor:pointer;
    transition:border-color .15s ease, background .15s ease;
    background:var(--panel-2);
  }
  .drop:hover, .drop.drag{
    border-color:var(--mint-dim);
    background:#132621;
  }
  .drop input{display:none;}
  .drop .icon{
    font-family:var(--mono);font-size:20px;color:var(--mint-dim);margin-bottom:6px;
  }
  .drop .label{font-size:14px;color:var(--text);}
  .drop .sub{font-size:12px;color:var(--text-dim);margin-top:4px;}
  .drop .file{
    font-family:var(--mono);font-size:13px;color:var(--mint);margin-top:8px;word-break:break-all;
  }

  .section-label{
    font-family:var(--mono);font-size:11px;letter-spacing:0.1em;color:var(--text-dim);
    margin:22px 0 10px;text-transform:uppercase;
  }

  .presets{display:flex;flex-wrap:wrap;gap:8px;}
  .preset{
    font-family:var(--mono);font-size:12px;
    padding:8px 12px;border-radius:6px;
    border:1px solid var(--border);background:var(--panel-2);color:var(--text-dim);
    cursor:pointer;transition:all .12s ease;
  }
  .preset:hover{border-color:var(--mint-dim);color:var(--text);}
  .preset.active{border-color:var(--mint);color:var(--mint);background:#10261D;}
  .preset:focus-visible{outline:2px solid var(--mint);outline-offset:2px;}

  .meta{
    font-family:var(--mono);font-size:11px;color:var(--text-dim);
    margin-top:10px;min-height:14px;
  }
  .meta b{color:var(--text);font-weight:500;}

  .toggles{display:flex;gap:20px;margin-top:18px;flex-wrap:wrap;}
  .toggle{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--text-dim);cursor:pointer;}
  .toggle input{accent-color:var(--mint);width:15px;height:15px;}

  .run{
    width:100%;margin-top:22px;padding:13px;
    border-radius:7px;border:1px solid var(--mint-dim);
    background:var(--mint);color:#052014;
    font-family:var(--mono);font-weight:600;font-size:13px;letter-spacing:0.04em;
    cursor:pointer;transition:filter .12s ease;
  }
  .run:hover:not(:disabled){filter:brightness(1.08);}
  .run:disabled{opacity:0.35;cursor:not-allowed;background:var(--panel-2);color:var(--text-dim);border-color:var(--border);}
  .run:focus-visible{outline:2px solid var(--mint);outline-offset:2px;}

  .status{margin-top:22px;display:none;}
  .status.show{display:block;}
  .status-row{
    display:flex;justify-content:space-between;align-items:baseline;
    font-family:var(--mono);font-size:12px;color:var(--text-dim);margin-bottom:8px;
  }
  .status-row .state{color:var(--amber);}
  .status-row .state.done{color:var(--mint);}
  .status-row .state.err{color:var(--coral);}
  .bar-track{height:6px;border-radius:3px;background:var(--panel-2);border:1px solid var(--border);overflow:hidden;}
  .bar-fill{height:100%;background:var(--amber);width:0%;transition:width .4s ease;}
  .bar-fill.done{background:var(--mint);}
  .bar-fill.err{background:var(--coral);}

  .meters{margin-top:20px;display:none;}
  .meters.show{display:block;}
  .meter-row{margin-bottom:10px;}
  .meter-label{
    display:flex;justify-content:space-between;
    font-family:var(--mono);font-size:11px;color:var(--text-dim);margin-bottom:4px;
  }
  .meter-track{height:16px;border-radius:3px;background:var(--panel-2);border:1px solid var(--border);overflow:hidden;}
  .meter-fill{height:100%;}
  .meter-fill.orig{background:var(--text-dim);}
  .meter-fill.comp{background:var(--mint);}
  .reduction{
    font-family:var(--mono);font-size:13px;color:var(--mint);margin-top:12px;
    text-align:center;letter-spacing:0.03em;
  }

  .download{
    display:block;width:100%;margin-top:16px;padding:12px;text-align:center;
    border-radius:7px;border:1px solid var(--mint);
    color:var(--mint);text-decoration:none;font-family:var(--mono);font-size:13px;font-weight:600;
    transition:background .12s ease;
  }
  .download:hover{background:#10261D;}

  .error-msg{
    margin-top:14px;padding:10px 12px;border-radius:6px;
    background:#2A130D;border:1px solid var(--coral);color:var(--coral);
    font-family:var(--mono);font-size:12px;display:none;
  }
  .error-msg.show{display:block;}

  footer{
    text-align:center;margin-top:16px;font-family:var(--mono);
    font-size:11px;color:var(--text-dim);
  }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <span class="rec-dot" id="recDot"></span>
    <span class="brand">COMPRESSOR</span>
    <span class="spacer"></span>
    <span class="chan">preset: <b id="chanLabel">HIGH</b></span>
  </header>

  <main>
    <label class="drop" id="drop">
      <input type="file" id="fileInput" accept="video/*">
      <div class="icon">&#9650;</div>
      <div class="label" id="dropLabel">Drop a video file here, or click to browse</div>
      <div class="sub">MP4, MOV, AVI, MKV, WMV, FLV, WEBM, M4V, MPEG</div>
      <div class="file" id="fileName"></div>
    </label>

    <div class="section-label">Preset</div>
    <div class="presets" id="presets"></div>
    <div class="meta" id="presetMeta"></div>

    <div class="toggles">
      <label class="toggle"><input type="checkbox" id="twoPass"> two-pass encode</label>
      <label class="toggle"><input type="checkbox" id="keepAudio" checked> keep audio</label>
    </div>

    <button class="run" id="runBtn" disabled>Compress video</button>

    <div class="error-msg" id="errorMsg"></div>

    <div class="status" id="status">
      <div class="status-row">
        <span id="statusMsg">Queued</span>
        <span class="state" id="statusState">encoding</span>
      </div>
      <div class="bar-track"><div class="bar-fill" id="barFill"></div></div>
    </div>

    <div class="meters" id="meters">
      <div class="meter-row">
        <div class="meter-label"><span>original</span><span id="origSize">-</span></div>
        <div class="meter-track"><div class="meter-fill orig" id="origBar" style="width:0%"></div></div>
      </div>
      <div class="meter-row">
        <div class="meter-label"><span>compressed</span><span id="compSize">-</span></div>
        <div class="meter-track"><div class="meter-fill comp" id="compBar" style="width:0%"></div></div>
      </div>
      <div class="reduction" id="reduction"></div>
      <a class="download" id="downloadLink" href="#" download>Download compressed file</a>
    </div>
  </main>

  <footer>Files auto-delete after a set retention window. Nothing is stored permanently.</footer>
</div>

<script>
let selectedFile = null;
let selectedProfile = 'high';
let profilesData = {};
let pollTimer = null;

const drop = document.getElementById('drop');
const fileInput = document.getElementById('fileInput');
const fileName = document.getElementById('fileName');
const dropLabel = document.getElementById('dropLabel');
const runBtn = document.getElementById('runBtn');
const presetsEl = document.getElementById('presets');
const presetMeta = document.getElementById('presetMeta');
const chanLabel = document.getElementById('chanLabel');
const errorMsg = document.getElementById('errorMsg');
const statusEl = document.getElementById('status');
const statusMsg = document.getElementById('statusMsg');
const statusState = document.getElementById('statusState');
const barFill = document.getElementById('barFill');
const metersEl = document.getElementById('meters');
const origSize = document.getElementById('origSize');
const compSize = document.getElementById('compSize');
const origBar = document.getElementById('origBar');
const compBar = document.getElementById('compBar');
const reduction = document.getElementById('reduction');
const downloadLink = document.getElementById('downloadLink');

function fmtBytes(bytes){
  if(bytes < 1024) return bytes + ' B';
  const units = ['KB','MB','GB'];
  let val = bytes;
  let i = -1;
  do { val /= 1024; i++; } while (val >= 1024 && i < units.length - 1);
  return val.toFixed(1) + ' ' + units[i];
}

function showError(msg){
  errorMsg.textContent = msg;
  errorMsg.classList.add('show');
}
function clearError(){
  errorMsg.classList.remove('show');
  errorMsg.textContent = '';
}

drop.addEventListener('dragover', e => { e.preventDefault(); drop.classList.add('drag'); });
drop.addEventListener('dragleave', () => drop.classList.remove('drag'));
drop.addEventListener('drop', e => {
  e.preventDefault();
  drop.classList.remove('drag');
  if(e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', e => {
  if(e.target.files.length) handleFile(e.target.files[0]);
});

function handleFile(file){
  selectedFile = file;
  dropLabel.textContent = 'File selected';
  fileName.textContent = file.name + '  (' + fmtBytes(file.size) + ')';
  runBtn.disabled = false;
  clearError();
}

async function loadProfiles(){
  try{
    const res = await fetch('/profiles');
    profilesData = await res.json();
    presetsEl.innerHTML = '';
    Object.keys(profilesData).forEach(name => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'preset' + (name === selectedProfile ? ' active' : '');
      btn.textContent = name;
      btn.addEventListener('click', () => selectProfile(name));
      presetsEl.appendChild(btn);
    });
    updatePresetMeta();
  } catch(e){
    showError('Could not load presets - the service may be waking up. Try again in a few seconds.');
  }
}

function selectProfile(name){
  selectedProfile = name;
  chanLabel.textContent = name.toUpperCase();
  [...presetsEl.children].forEach(btn => {
    btn.classList.toggle('active', btn.textContent === name);
  });
  updatePresetMeta();
}

function updatePresetMeta(){
  const p = profilesData[selectedProfile];
  if(!p) return;
  presetMeta.innerHTML = 'crf <b>' + p.crf + '</b> &nbsp; preset <b>' + p.preset + '</b> &nbsp; codec <b>' +
    p.codec + '</b> &nbsp; max res <b>' + p.max_resolution + '</b> &nbsp; fps <b>' + p.fps + '</b>';
}

runBtn.addEventListener('click', async () => {
  if(!selectedFile) return;
  clearError();
  runBtn.disabled = true;
  metersEl.classList.remove('show');

  const form = new FormData();
  form.append('file', selectedFile);
  form.append('profile', selectedProfile);
  form.append('two_pass', document.getElementById('twoPass').checked);
  form.append('keep_audio', document.getElementById('keepAudio').checked);

  try{
    const res = await fetch('/compress', { method: 'POST', body: form });
    if(!res.ok){
      const err = await res.json().catch(() => ({detail: 'Upload failed'}));
      showError(err.detail || 'Upload failed');
      runBtn.disabled = false;
      return;
    }
    const job = await res.json();
    statusEl.classList.add('show');
    poll(job.job_id);
  } catch(e){
    showError('Could not reach the service. Try again.');
    runBtn.disabled = false;
  }
});

function poll(jobId){
  if(pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try{
      const res = await fetch('/jobs/' + jobId);
      const job = await res.json();
      renderStatus(job);
      if(job.status === 'completed' || job.status === 'failed'){
        clearInterval(pollTimer);
        runBtn.disabled = false;
        if(job.status === 'completed') renderResult(job);
        if(job.status === 'failed') showError(job.message || 'Compression failed');
      }
    } catch(e){
      clearInterval(pollTimer);
      showError('Lost connection while checking job status.');
      runBtn.disabled = false;
    }
  }, 2000);
}

function renderStatus(job){
  statusMsg.textContent = job.message || job.status;
  barFill.style.width = job.progress + '%';
  statusState.classList.remove('done','err');
  barFill.classList.remove('done','err');
  if(job.status === 'completed'){
    statusState.textContent = 'done';
    statusState.classList.add('done');
    barFill.classList.add('done');
  } else if(job.status === 'failed'){
    statusState.textContent = 'failed';
    statusState.classList.add('err');
    barFill.classList.add('err');
  } else {
    statusState.textContent = job.status;
  }
}

function renderResult(job){
  const stats = job.stats || {};
  const origMb = stats.original_size_mb || 0;
  const compMb = stats.compressed_size_mb || 0;
  const maxMb = Math.max(origMb, compMb, 0.01);
  origSize.textContent = origMb + ' MB';
  compSize.textContent = compMb + ' MB';
  origBar.style.width = (origMb / maxMb * 100) + '%';
  compBar.style.width = (compMb / maxMb * 100) + '%';
  reduction.textContent = (stats.reduction_percent != null ? stats.reduction_percent : '-') + '% smaller';
  downloadLink.href = '/download/' + job.job_id;
  metersEl.classList.add('show');
}

selectProfile('high');
loadProfiles();
</script>
</body>
</html>
"""


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
            "web_ui": "GET /ui",
            "upload_compress": "POST /compress",
            "job_status": "GET /jobs/{job_id}",
            "download": "GET /download/{job_id}",
            "profiles": "GET /profiles"
        }
    }


@app.get("/ui", response_class=HTMLResponse)
async def ui():
    """Serves the browser UI for uploading and compressing videos."""
    return UI_HTML


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

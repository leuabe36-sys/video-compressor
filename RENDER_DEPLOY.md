# 🚀 Deploy to Render.com

## Option A: Blueprint (Recommended)

The `render.yaml` file defines your entire infrastructure. One-click deploy.

### Steps

1. **Push code to GitHub**
   ```bash
   git init
   git add .
   git commit -m "Initial video compressor"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/video-compressor.git
   git push -u origin main
   ```

2. **Deploy via Blueprint**
   - Go to [dashboard.render.com/blueprints](https://dashboard.render.com/blueprints)
   - Click **New Blueprint Instance**
   - Connect your GitHub repo
   - Render auto-detects `render.yaml` and provisions the service
   - Wait for build (~3-5 minutes)

3. **Done!** Your API is live at `https://video-compressor-xxx.onrender.com`

---

## Option B: Manual Docker Service

If you prefer not to use Blueprints:

1. Go to [dashboard.render.com](https://dashboard.render.com) → **New +** → **Web Service**
2. Connect your GitHub repo
3. Select **Docker** as environment
4. Set environment variables:
   - `PORT` = `8000`
   - `MAX_FILE_SIZE` = `1073741824` (1GB)
   - `WORKERS` = `1`
5. Click **Create Web Service**

---

## Important Render Considerations

### ⚠️ Free Tier Limitations
- **Sleeps after 15 min** of inactivity (cold starts ~30s)
- **512MB RAM** — may fail on large videos
- **Ephemeral disk** — files deleted on restart
- **Build timeout** — 15 minutes max

### ✅ Production (Standard Plan)
- Always-on
- 2GB+ RAM
- Faster builds
- Custom domains

### 💾 Persistent Storage
Add a disk in `render.yaml` (uncomment the disk section):
```yaml
disk:
  name: video-storage
  mountPath: /app/outputs
  sizeGB: 10
```

Or manually: Dashboard → Service → Disks → Add Disk

---

## Testing Your Deployed API

```bash
# Replace with your actual Render URL
URL="https://video-compressor-xxx.onrender.com"

# Check health
curl $URL/

# List profiles
curl $URL/profiles

# Compress a video
curl -X POST "$URL/compress" \
  -F "file=@sample.mp4" \
  -F "profile=high"

# Check job status (replace JOB_ID)
curl "$URL/jobs/YOUR_JOB_ID"

# Download result
curl -O -J "$URL/download/YOUR_JOB_ID"
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Build fails | Check `Dockerfile` has `apt-get install ffmpeg` |
| Out of memory | Upgrade to Standard plan (2GB+) or reduce `MAX_FILE_SIZE` |
| Files disappear | Add a Render Disk or use external S3 storage |
| Slow cold start | Use Standard plan (always-on) or keep-alive ping |
| Upload timeout | Increase client timeout or use smaller files |

---

## Keep-Alive for Free Tier (Optional)

Use a cron job to ping your service every 10 minutes:

```yaml
# Add to render.yaml
  - type: cron
    name: keep-alive
    runtime: docker
    plan: free
    dockerfilePath: ./Dockerfile
    schedule: "*/10 * * * *"
    envVars:
      - key: URL
        value: https://video-compressor-xxx.onrender.com
    startCommand: curl -s $URL/ > /dev/null
```

Or use [UptimeRobot](https://uptimerobot.com) (free) to ping every 5 minutes.

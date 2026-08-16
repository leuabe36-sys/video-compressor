# Video Compression API - Production Dockerfile
FROM python:3.11-slim

# Install FFmpeg and dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    libgl1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Verify FFmpeg installation
RUN ffmpeg -version

# Set working directory
WORKDIR /app

# Copy requirements first (for layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY video_compressor.py .
COPY app.py .

# Create upload/output directories
RUN mkdir -p uploads outputs

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV UPLOAD_DIR=/app/uploads
ENV OUTPUT_DIR=/app/outputs
ENV MAX_FILE_SIZE=2147483648
ENV PORT=8000
ENV HOST=0.0.0.0
ENV WORKERS=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/ || exit 1

# Expose port
EXPOSE 8000

# Run application
CMD ["python", "app.py"]

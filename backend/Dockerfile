# Study Trail Builder - Django backend image (Req 7.1)
# Small base image; metadata-only yt-dlp search needs no ffmpeg or extra system deps.
FROM python:3.12-slim

# Keep Python output unbuffered and skip .pyc files for cleaner container logs
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install dependencies first to leverage Docker layer caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source
COPY . .

# Django app served by gunicorn listens on 8000
EXPOSE 8000

# Serve the WSGI app (config.wsgi:application) with gunicorn on port 8000.
# A single /api/trail request can legitimately be slow: the bounded yt-dlp
# search (up to ~30s) plus the Ollama calls run synchronously in the worker.
# The default 30s gunicorn timeout kills the worker mid-request, so it is raised
# to 120s to comfortably cover the app's own internal time bounds. Two workers
# keep the app responsive while one request is in flight.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120", "config.wsgi:application"]

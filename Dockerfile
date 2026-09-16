FROM python:3.11-slim

# Install ffmpeg (required by yt-dlp for merging audio/video)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY . .

# Expose port
EXPOSE 8000

# Start server
CMD /bin/sh -c "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"

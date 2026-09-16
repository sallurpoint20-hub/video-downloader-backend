FROM python:3.10-bullseye

# Install system dependencies (ffmpeg is required by yt-dlp, libnss3 for curl_cffi)
RUN apt-get update && \
    apt-get install -y ffmpeg libnss3 && \
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

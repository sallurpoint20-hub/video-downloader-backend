FROM ubuntu:22.04

# Prevent timezone prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# Install all system dependencies required for curl_cffi and yt-dlp on a pure Ubuntu image
RUN apt-get update && \
    apt-get install -y python3 python3-pip ffmpeg libnss3 libnspr4 ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy backend code
COPY . .

# Expose port
EXPOSE 8000

# Start server
CMD /bin/sh -c "python3 -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"

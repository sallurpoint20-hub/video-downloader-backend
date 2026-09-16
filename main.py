from fastapi import FastAPI, BackgroundTasks, Request, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp
import uuid
import os
import threading
import glob

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Video Downloader API is running"}

# In-memory storage for download statuses
# Format: { download_id: {"status": "downloading" | "completed" | "error", "progress": int, "error": str} }
downloads = {}

DOWNLOAD_DIR = os.path.join(os.path.expanduser('~'), 'Downloads', 'VideoDownloader')
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

class DownloadRequest(BaseModel):
    url: str
    format: str = 'video'  # 'video' or 'audio' or 'thumb'
    quality: str = 'best'

class AnalyzeRequest(BaseModel):
    url: str

def create_progress_hook(download_id: str):
    def hook(d):
        if d['status'] == 'downloading':
            percent_str = d.get('_percent_str', '0%')
            import re
            percent_str = re.sub(r'\x1b\[[0-9;]*m', '', percent_str).replace('%', '').strip()
            try:
                percent = float(percent_str)
                downloads[download_id]['progress'] = int(percent)
                downloads[download_id]['status'] = 'downloading'
            except Exception:
                pass
        elif d['status'] == 'finished':
            downloads[download_id]['progress'] = 100
            # Will be marked completed after post-processing
        elif d['status'] == 'error':
            downloads[download_id]['status'] = 'error'
            downloads[download_id]['error'] = 'Download failed'
    return hook

def download_task(url: str, format_type: str, quality: str, download_id: str):
    ydl_opts = {
        'outtmpl': os.path.join(DOWNLOAD_DIR, f"{download_id}.%(ext)s"),
        'progress_hooks': [create_progress_hook(download_id)],
        'quiet': False, 
    }
    
    if format_type == 'audio':
        ydl_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
    elif format_type == 'thumb':
        ydl_opts.update({
            'skip_download': True,
            'writethumbnail': True,
        })
    else:
        video_format = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        if quality != "best":
            height = quality.replace("p", "")
            video_format = f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={height}][ext=mp4]/best"
        ydl_opts.update({
            'format': video_format,
            'merge_output_format': 'mp4',
        })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            downloads[download_id]['status'] = 'completed'
            downloads[download_id]['progress'] = 100
            downloads[download_id]['title'] = info.get('title', 'Video')
    except Exception as e:
        print(f"Download error: {e}")
        downloads[download_id]['status'] = 'error'
        downloads[download_id]['error'] = str(e)

def remove_file(path: str):
    try:
        if os.path.exists(path):
            os.remove(path)
            print(f"Cleaned up file: {path}")
    except Exception as e:
        print(f"Error removing file {path}: {e}")

@app.get("/api/file/{download_id}")
def get_file(download_id: str, background_tasks: BackgroundTasks):
    if download_id not in downloads:
        raise HTTPException(status_code=404, detail="Download not found")
        
    pattern = os.path.join(DOWNLOAD_DIR, f"{download_id}.*")
    files = glob.glob(pattern)
    
    # Exclude intermediate files if any are left
    final_files = [f for f in files if not f.endswith('.part') and not f.endswith('.ytdl')]
    
    if not final_files:
        raise HTTPException(status_code=404, detail="File not found on disk")
        
    file_path = final_files[0]
    title = downloads[download_id].get('title', 'Video')
    ext = os.path.splitext(file_path)[1]
    
    # Replace invalid characters in title for safe filename
    safe_title = "".join([c for c in title if c.isalpha() or c.isdigit() or c==' ']).rstrip()
    
    # Schedule file for deletion after the response is sent
    background_tasks.add_task(remove_file, file_path)
    
    return FileResponse(path=file_path, filename=f"{safe_title}{ext}")

@app.post("/api/download")
async def start_download(req: DownloadRequest, background_tasks: BackgroundTasks):
    download_id = str(uuid.uuid4())
    downloads[download_id] = {
        "status": "starting",
        "progress": 0,
        "error": None
    }
    
    thread = threading.Thread(target=download_task, args=(req.url, req.format, req.quality, download_id))
    thread.start()
    
    return {"download_id": download_id}

@app.get("/api/status/{download_id}")
async def get_status(download_id: str):
    if download_id not in downloads:
        return {"status": "error", "error": "Download ID not found", "progress": 0}
    
    return downloads[download_id]

@app.post("/api/analyze")
async def analyze_video(req: AnalyzeRequest):
    try:
        ydl_opts = {
            'quiet': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=False)
            
            title = info.get('title', 'Unknown Title')
            uploader = info.get('uploader', 'Unknown Uploader')
            duration = info.get('duration', 0)
            thumbnail = info.get('thumbnail', '')
            try:
                duration = int(float(duration))
            except (ValueError, TypeError):
                duration = 0
            
            # Convert duration to mm:ss
            m, s = divmod(duration, 60)
            duration_str = f"{m:02d}:{s:02d}"

            qualities = [
                {"id": "best", "label": "Best Available"},
                {"id": "1080p", "label": "1080p"},
                {"id": "720p", "label": "720p"},
                {"id": "480p", "label": "480p"},
            ]
            
            return {
                "title": title,
                "uploader": uploader,
                "duration": duration_str,
                "thumbnail": thumbnail,
                "qualities": qualities
            }
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

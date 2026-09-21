from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import yt_dlp
import os
import uuid
import urllib.parse
import imageio_ffmpeg
import logging
import re

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="ToolFlex Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class VideoRequest(BaseModel):
    url: str

DOWNLOAD_DIR = os.path.abspath("downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Dictionary to store download progress and status
# format: {task_id: {"status": str, "progress": float, "file_path": str, "error": str}}
download_tasks = {}

# الحصول على مسار ffmpeg التلقائي المدمج
FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

def yt_dlp_progress_hook(task_id):
    def hook(d):
        if d['status'] == 'downloading':
            try:
                downloaded = d.get('downloaded_bytes', 0)
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                if total > 0:
                    download_tasks[task_id]['progress'] = round((downloaded / total) * 100, 1)
                else:
                    # Fallback to string parsing if total is not available
                    percent_str = d.get('_percent_str', '0%').replace('%', '').strip()
                    # Remove ANSI escape sequences if any
                    percent_str = re.sub(r'\x1b\[[0-9;]*m', '', percent_str)
                    download_tasks[task_id]['progress'] = float(percent_str)
            except Exception:
                pass
            download_tasks[task_id]['status'] = 'downloading'
        elif d['status'] == 'finished':
            download_tasks[task_id]['status'] = 'processing'
            download_tasks[task_id]['progress'] = 100
    return hook

def download_video_task(task_id: str, url: str, download_type: str):
    clean_url = urllib.parse.unquote(url)
    output_template = os.path.join(DOWNLOAD_DIR, f"{task_id}_%(title)s.%(ext)s")
    
    if download_type == "audio":
        format_selector = 'bestaudio/best'
    else:
        format_selector = 'bestvideo+bestaudio/best'

    ydl_opts = {
        'noplaylist': True,
    'format': 'bestvideo+bestaudio/best',
    'outtmpl': os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s'),
        'format': format_selector,
        'outtmpl': output_template,
        'ffmpeg_location': FFMPEG_PATH,
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'progress_hooks': [yt_dlp_progress_hook(task_id)],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=True)
            filename = ydl.prepare_filename(info)
            
            # Handle cases where extension changes (e.g. merge to mp4)
            if not os.path.exists(filename):
                files = [f for f in os.listdir(DOWNLOAD_DIR) if f.startswith(task_id)]
                if files:
                    filename = os.path.join(DOWNLOAD_DIR, files[0])
            
            if os.path.exists(filename):
                download_tasks[task_id]['status'] = 'completed'
                download_tasks[task_id]['file_path'] = filename
            else:
                raise Exception("File not found after download")

    except Exception as e:
        logger.error(f"Download failed for {task_id}: {str(e)}")
        download_tasks[task_id]['status'] = 'failed'
        download_tasks[task_id]['error'] = str(e)

@app.post("/api/fetch")

def fetch_video_info(req: VideoRequest):
    clean_url = urllib.parse.unquote(req.url)
    ydl_opts = {'quiet': True, 'no_warnings': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)
            return {
                "title": info.get("title", "Video"),
                "duration": info.get("duration_string", "N/A"),
                "thumbnail": info.get("thumbnail", ""),
                "url": clean_url
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/download/start")
def start_download(url: str, type: str = "video", background_tasks: BackgroundTasks = None):
    task_id = str(uuid.uuid4())[:8]
    download_tasks[task_id] = {
        "status": "starting",
        "progress": 0,
        "file_path": None,
        "error": None
    }
    background_tasks.add_task(download_video_task, task_id, url, type)
    return {"task_id": task_id}

@app.get("/api/download/status/{task_id}")
def get_download_status(task_id: str):
    if task_id not in download_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return download_tasks[task_id]

@app.get("/api/download/file/{task_id}")
def get_download_file(task_id: str):
    if task_id not in download_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = download_tasks[task_id]
    if task['status'] != 'completed':
        raise HTTPException(status_code=400, detail="File not ready or download failed")
    
    file_path = task['file_path']
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File no longer exists on server")
        
    return FileResponse(
        path=file_path,
        filename=os.path.basename(file_path),
        media_type='application/octet-stream'
    )
from fastapi.responses import FileResponse

@app.get("/")
async def read_index():
    return FileResponse("index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
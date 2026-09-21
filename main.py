import os
import glob
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import yt_dlp

app = FastAPI()

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# قاموس لتتبع نسبة التحميل لكل عملية
download_progress = {}

def progress_hook(d):
    if d['status'] == 'downloading':
        total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
        downloaded = d.get('downloaded_bytes', 0)
        if total > 0:
            percentage = int((downloaded / total) * 100)
            download_progress[d.get('filename')] = percentage

def cleanup_file(file_path: str):
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            print(f"Error cleaning up file: {e}")

@app.get("/")
def read_root():
    return FileResponse("index.html")

@app.post("/api/download")
def download_media(url: str, format_type: str = "video", background_tasks: BackgroundTasks = None):
    try:
        ydl_opts = {
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s'),
            'noplaylist': True,
            'quiet': True,
            'progress_hooks': [progress_hook],
        }

        if format_type == "audio":
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        else:
            ydl_opts.update({
                'format': 'bestvideo+bestaudio/best',
            })

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            if format_type == "audio":
                filename = os.path.splitext(filename)[0] + ".mp3"

        if not os.path.exists(filename):
            raise HTTPException(status_code=500, detail="File download failed")

        if background_tasks:
            background_tasks.add_task(cleanup_file, filename)

        return FileResponse(
            path=filename,
            filename=os.path.basename(filename),
            media_type='application/octet-stream'
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
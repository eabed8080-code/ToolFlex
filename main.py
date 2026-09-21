import os
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import yt_dlp

app = FastAPI()

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory="."), name="static")

def cleanup_file(file_path: str):
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            print(f"Cleaned up: {file_path}")
        except Exception as e:
            print(f"Error cleaning up file: {e}")

@app.get("/")
def read_root():
    return FileResponse("index.html")

@app.post("/api/download")
def download_media(url: str, format_type: str = "video", background_tasks: BackgroundTasks = None):
    try:
        # اختيار صيغ جاهزة ومدمجة مسبقاً لتجنب الحاجة لـ FFmpeg
        if format_type == "audio":
            format_str = "bestaudio/best"
        else:
            # يجلب مقطع مدمج (صوت + فيديو معاً) بصيغة mp4 مباشرة
            format_str = "best[ext=mp4]/b[ext=mp4]/best"

        ydl_opts = {
            'format': format_str,
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s'),
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            base_id = info.get('id')
            
            # تحديد اسم الملف المحمل
            filename = ydl.prepare_filename(info)

        # التحقق من وجود الملف أو البحث عنه في مجلد التنزيلات
        if not os.path.exists(filename):
            matching_files = [os.path.join(DOWNLOAD_DIR, f) for f in os.listdir(DOWNLOAD_DIR) if base_id in f]
            if matching_files:
                filename = matching_files[0]
            else:
                raise HTTPException(status_code=500, detail="File download failed")

        if background_tasks:
            background_tasks.add_task(cleanup_file, filename)

        return FileResponse(
            path=filename,
            filename=os.path.basename(filename),
            media_type='application/octet-stream'
        )

    except Exception as e:
        print("Detailed Error:", str(e))
        raise HTTPException(status_code=400, detail=str(e))
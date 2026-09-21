import os
import glob
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import yt_dlp

app = FastAPI()

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# خدمة الملفات الثابتة (لواجهة الموقع)
app.mount("/static", StaticFiles(directory="."), name="static")

@app.get("/")
def read_root():
    return FileResponse("index.html")

def cleanup_file(file_path: str):
    """حذف الملف تلقائياً من السيرفر بعد التحميل"""
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            print(f"Cleaned up: {file_path}")
        except Exception as e:
            print(f"Error cleaning up file: {e}")

@app.post("/api/download")
def download_media(url: str, format_type: str = "video", background_tasks: BackgroundTasks = None):
    try:
        # إعدادات yt-dlp الأساسية مع تفعيل noplaylist
        ydl_opts = {
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s'),
            'noplaylist': True,
            'quiet': True,
        }

        if format_type == "audio":
            # إعدادات استخراج MP3
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        else:
            # إعدادات الفيديو
            ydl_opts.update({
                'format': 'bestvideo+bestaudio/best',
            })

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            # في حال التحويل لـ MP3 يتغير الامتداد
            if format_type == "audio":
                filename = os.path.splitext(filename)[0] + ".mp3"

        if not os.path.exists(filename):
            raise HTTPException(status_code=500, detail="File download failed")

        # إضافة مهمة التنظيف التلقائي في الخلفية بعد إرسال الملف للمستخدم
        if background_tasks:
            background_tasks.add_task(cleanup_file, filename)

        return FileResponse(
            path=filename,
            filename=os.path.basename(filename),
            media_type='application/octet-stream'
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
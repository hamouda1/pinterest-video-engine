import os
import tempfile
from pathlib import Path
from typing import Dict, Any, Tuple
import yt_dlp

def extract_and_download_video(url: str, output_dir: str = None) -> Tuple[Dict[str, Any], Path]:
    """
    Downloads a TikTok / Short-form vertical video without watermark using yt-dlp.
    Returns:
      (metadata_dict, local_file_path)
    """
    if not output_dir:
        output_dir = tempfile.gettempdir()

    out_template = os.path.join(output_dir, "pin_video_%(id)s.%(ext)s")

    ydl_opts = {
        "format": "best[ext=mp4]/best",
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "overwrites": True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)

    meta = {
        "id": info.get("id"),
        "title": info.get("title") or "Aesthetic Inspiration",
        "description": info.get("description") or "",
        "uploader": info.get("uploader") or "",
        "duration": info.get("duration") or 0,
        "thumbnail": info.get("thumbnail") or "",
        "tags": info.get("tags") or []
    }

    return meta, Path(filename)

import os
import tempfile
from pathlib import Path
from typing import Dict, Any, Tuple
import yt_dlp

def extract_and_download_video(url: str, output_dir: str = None) -> Tuple[Dict[str, Any], Path]:
    """
    Downloads a TikTok / Short-form vertical video without watermark.
    Supports direct MP4 URLs (from Apify) and standard TikTok web URLs (via yt-dlp).
    Returns:
      (metadata_dict, local_file_path)
    """
    if not output_dir:
        output_dir = tempfile.gettempdir()

    # 1. Direct MP4 stream (e.g. from Apify storage)
    if ".mp4" in url.lower() or "apify.com" in url.lower():
        import requests
        out_path = Path(output_dir) / f"pin_video_{tempfile.mktemp(dir='')}.mp4"
        print(f"   📥 Downloading direct clean MP4 stream...", flush=True)
        resp = requests.get(url, stream=True, timeout=60)
        resp.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

        meta = {
            "title": "Aesthetic Viral Video",
            "duration": 15,
            "size": out_path.stat().st_size
        }
        return meta, out_path

    # 2. Standard Web URL via yt-dlp
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

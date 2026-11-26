import time
import requests
from pathlib import Path
from typing import Dict, Any, Optional

API_BASE = "https://api.pinterest.com/v5"

class PinterestVideoUploader:
    def __init__(self, access_token: str):
        self.token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

    def register_media(self) -> Dict[str, Any]:
        """Step 1: Register video upload session with Pinterest API v5."""
        url = f"{API_BASE}/media"
        payload = {"media_type": "video"}
        last_err = None
        for attempt in range(1, 4):
            try:
                resp = requests.post(url, headers=self.headers, json=payload, timeout=60)
                if resp.status_code >= 400:
                    print(f"   ❌ Pinterest Media Registration API Error ({resp.status_code}): {resp.text}", flush=True)
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.RequestException as e:
                last_err = e
                if attempt < 3:
                    print(f"   ⚠️ Media registration attempt {attempt} failed ({e}), retrying in 5s...", flush=True)
                    time.sleep(5)
                else:
                    raise last_err

    def upload_file_to_s3(self, upload_url: str, upload_params: Dict[str, Any], file_path: Path):
        """Step 2: Upload MP4 binary file directly to Pinterest AWS S3 bucket."""
        with open(file_path, "rb") as f:
            files = {"file": f}
            # Note: Do NOT include Pinterest Authorization header when uploading to S3
            resp = requests.post(upload_url, data=upload_params, files=files, timeout=120)
            resp.raise_for_status()

    def wait_for_transcoding(self, media_id: str, timeout: int = 300, poll_interval: int = 5) -> bool:
        """Step 3: Poll Pinterest media endpoint until transcoding succeeds."""
        url = f"{API_BASE}/media/{media_id}"
        start_time = time.time()

        while time.time() - start_time < timeout:
            resp = requests.get(url, headers=self.headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                status = data.get("status")
                print(f"   ⏳ Pinterest Video Processing Status: [{status}]", flush=True)
                if status == "succeeded":
                    return True
                elif status == "failed":
                    raise RuntimeError(f"Pinterest video transcoding failed for media_id: {media_id}")
            time.sleep(poll_interval)

        raise TimeoutError(f"Pinterest video transcoding timed out after {timeout} seconds.")

    def create_video_pin(
        self,
        board_id: str,
        media_id: str,
        title: str,
        description: str,
        link: Optional[str] = None,
        cover_image_key_frame_time: int = 1
    ) -> Dict[str, Any]:
        """Step 4: Create final Video Pin using verified media_id."""
        url = f"{API_BASE}/pins"
        payload = {
            "board_id": str(board_id),
            "title": title[:100].strip(),
            "description": description[:500].strip(),
            "media_source": {
                "source_type": "video_id",
                "media_id": str(media_id),
                "cover_image_key_frame_time": int(cover_image_key_frame_time)
            }
        }
        if link and link.strip():
            payload["link"] = link.strip()

        # Pin creation is non-idempotent: never replay an ambiguous POST.
        try:
            resp = requests.post(url, headers=self.headers, json=payload, timeout=60)
        except requests.exceptions.RequestException:
            raise RuntimeError("Pin request outcome unknown; reconcile before retrying") from None
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Pin creation not confirmed: HTTP {resp.status_code}")
        data = resp.json()
        if not isinstance(data, dict) or not isinstance(data.get("id"), str) or not data["id"].isdigit():
            raise RuntimeError("Pin response lacks a valid identity; reconcile before retrying")
        return data

    def upload_and_publish(
        self,
        file_path: Path,
        board_id: str,
        title: str,
        description: str,
        link: Optional[str] = None
    ) -> Dict[str, Any]:
        """Full end-to-end pipeline: Register -> S3 Upload -> Wait -> Create Pin."""
        print(f"   🚀 Step 1: Registering media with Pinterest...", flush=True)
        reg = self.register_media()
        media_id = reg["media_id"]
        upload_url = reg["upload_url"]
        upload_params = reg["upload_parameters"]

        print(f"   📤 Step 2: Uploading {file_path.name} to Pinterest S3 (media_id: {media_id})...", flush=True)
        self.upload_file_to_s3(upload_url, upload_params, file_path)

        print(f"   ⏳ Step 3: Waiting for Pinterest cloud transcoding...", flush=True)
        self.wait_for_transcoding(media_id)

        print(f"   📌 Step 4: Creating video pin on board {board_id}...", flush=True)
        pin_res = self.create_video_pin(board_id, media_id, title, description, link)
        return pin_res

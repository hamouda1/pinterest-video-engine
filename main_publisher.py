import os
import sys
import json
import tempfile
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from vault_crypto import decrypt_bytes, encrypt_bytes
from tiktok_extractor import extract_and_download_video
from pinterest_video_uploader import PinterestVideoUploader
from apify_discovery import clean_tiktok_caption

VAULT_REPO = os.environ.get("VAULT_REPO", "hamouda1/pinterest-video-vault")
VAULT_PAT = os.environ.get("VAULT_PAT")
MASTER_KEY = os.environ.get("VIDEO_VAULT_KEY")

def get_vault_dir() -> Path:
    """Clones or resolves the private vault directory."""
    local_vault = Path(__file__).resolve().parent.parent / "pinterest-video-vault"
    if local_vault.exists() and (local_vault / "accounts_vault.json.enc").exists():
        return local_vault

    # Cloud environment: clone via PAT
    if not VAULT_PAT:
        raise ValueError("Missing VAULT_PAT environment variable for vault access.")

    temp_clone = Path(tempfile.mkdtemp(prefix="video_vault_"))
    clone_url = f"https://x-access-token:{VAULT_PAT}@github.com/{VAULT_REPO}.git"
    print(f"🔒 Cloning private vault from {VAULT_REPO}...", flush=True)
    subprocess.run(["git", "clone", "--depth", "1", clone_url, str(temp_clone)], check=True, capture_output=True)
    return temp_clone

def load_encrypted_json(file_path: Path, key: str = None) -> Any:
    if not file_path.exists():
        return None
    with open(file_path, "rb") as f:
        enc_data = f.read()
    plain_data = decrypt_bytes(enc_data, key)
    return json.loads(plain_data.decode("utf-8"))

def save_encrypted_json(data: Any, file_path: Path, key: str = None):
    plain_bytes = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    enc_bytes = encrypt_bytes(plain_bytes, key)
    with open(file_path, "wb") as f:
        f.write(enc_bytes)

def commit_and_push_vault(vault_dir: Path):
    """Pushes encrypted changes back to the private vault."""
    print("🔒 Committing encrypted state back to private vault...", flush=True)
    subprocess.run(["git", "-C", str(vault_dir), "config", "user.name", "Pinterest Video Bot"], check=True)
    subprocess.run(["git", "-C", str(vault_dir), "config", "user.email", "bot@pinterest-video.internal"], check=True)
    subprocess.run(["git", "-C", str(vault_dir), "add", "."], check=True)

    # Check if there are changes
    status = subprocess.run(["git", "-C", str(vault_dir), "status", "--porcelain"], capture_output=True, text=True)
    if not status.stdout.strip():
        print("   ℹ️ No vault changes to commit.", flush=True)
        return

    msg = f"Auto-sync video vault state: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [skip ci]"
    subprocess.run(["git", "-C", str(vault_dir), "commit", "-m", msg], check=True)

    if VAULT_PAT:
        push_url = f"https://x-access-token:{VAULT_PAT}@github.com/{VAULT_REPO}.git"
        subprocess.run(["git", "-C", str(vault_dir), "push", push_url, "main"], check=True)
    else:
        subprocess.run(["git", "-C", str(vault_dir), "push", "origin", "main"], check=True)
    print("   ✅ Encrypted vault successfully synchronized!", flush=True)

def main():
    print("=" * 65)
    print("🚀 PINTEREST AUTONOMOUS VIDEO PUBLISHING CYCLE")
    print(f"⏰ Execution Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    if not MASTER_KEY:
        print("❌ Error: Missing VIDEO_VAULT_KEY.")
        sys.exit(1)

    vault_dir = get_vault_dir()
    acc_file = vault_dir / "accounts_vault.json.enc"
    queue_file = vault_dir / "video_queue.json.enc"

    # 1. Load accounts in-memory
    accs_data = load_encrypted_json(acc_file, MASTER_KEY)
    if not accs_data:
        print("❌ Failed to decrypt accounts from vault.")
        sys.exit(1)

    accounts = accs_data.get("accounts", {})

    # 2. Load or initialize video queue in-memory
    queue = load_encrypted_json(queue_file, MASTER_KEY) or []

    # If queue is empty, initialize default seed queue
    if not queue:
        print("ℹ️ Initializing queue with seed viral aesthetic topics...")
        queue = [
            {
                "id": "vid_seed_01",
                "account_id": "CozyReadHaven",
                "board_id": "239676080108617140",
                "board_name": "Cozy Reading Nook Ideas & Inspo",
                "video_source_url": "https://www.tiktok.com/@the_book_nook_official/video/7234567890123456789",
                "title": "Aesthetic Cozy Book Nook Essentials & Reading Inspo ✨",
                "description": "Transform your reading corner into the ultimate cozy haven! Tap follow for daily bookish finds. #booktok #cozyvibes #readingnook #aestheticbooks #homedecor",
                "link": "",
                "status": "pending"
            }
        ]

    # Find next pending video
    target_item = None
    for item in queue:
        if item.get("status") == "pending":
            target_item = item
            break

    if not target_item:
        print("ℹ️ All videos in queue already published. Queue complete.")
        return

    acc_id = target_item.get("account_id", "CozyReadHaven")
    acc_info = accounts.get(acc_id)
    if not acc_info:
        print(f"❌ Account credentials for @{acc_id} not found in vault.")
        return

    token = acc_info.get("access_token")
    if not token:
        print(f"❌ No access token found for @{acc_id}.")
        return

    source_url = target_item.get("video_source_url")
    board_id = target_item.get("board_id")
    title = target_item.get("title")
    desc = target_item.get("description")
    link = target_item.get("link")

    print(f"\n🎯 Target Account: @{acc_id}")
    print(f"📌 Board ID: {board_id}")
    print(f"🎬 Video Source: {source_url}")
    print(f"📝 Title: {title}")

    # 3. Extract and download MP4 without watermark
    local_mp4 = None
    try:
        print(f"\n📥 Extracting and downloading video via yt-dlp...", flush=True)
        meta, local_mp4 = extract_and_download_video(source_url)
        print(f"   ✅ Downloaded: {local_mp4.name} (Duration: {meta.get('duration')}s, Size: {os.path.getsize(local_mp4)} bytes)", flush=True)

        # Automated Fair-Use Creator Attribution and Caption Sanitization
        creator = target_item.get("creator_username") or meta.get("uploader") or "creator"
        board_name_low = str(target_item.get("board_name", "")).lower()
        acc_low = str(acc_id).lower()
        if any(w in board_name_low or w in acc_low for w in ["montessori", "nursery", "baby", "toddler"]):
            tag = "montessori"
        elif any(w in board_name_low or w in acc_low for w in ["coffee", "brew", "matcha"]):
            tag = "coffee"
        elif any(w in board_name_low or w in acc_low for w in ["book", "reading", "read"]):
            tag = "reading"
        else:
            tag = "aesthetic"

        desc = clean_tiktok_caption(desc, creator, tag)

        # 4. Upload and Publish to Pinterest API v5
        uploader = PinterestVideoUploader(access_token=token)
        pin_res = uploader.upload_and_publish(
            file_path=local_mp4,
            board_id=board_id,
            title=title,
            description=desc,
            link=link
        )

        pin_id = pin_res.get("id")
        pin_url = f"https://www.pinterest.com/pin/{pin_id}/" if pin_id else "N/A"
        print(f"\n🎉 SUCCESS! Video Pin Published Live!")
        print(f"   📌 Pin ID: {pin_id}")
        print(f"   🔗 URL: {pin_url}")

        target_item["status"] = "published"
        target_item["pin_id"] = pin_id
        target_item["pin_url"] = pin_url
        target_item["published_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    except Exception as e:
        print(f"\n❌ Error during video publishing: {e}", flush=True)
        target_item["status"] = "failed"
        target_item["error"] = str(e)
        target_item["failed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    finally:
        # Cleanup temporary downloaded MP4
        if local_mp4 and local_mp4.exists():
            try:
                os.remove(local_mp4)
                print("   🧹 Cleaned up temporary video file.")
            except Exception:
                pass

    # 5. Save encrypted queue back to vault and push
    save_encrypted_json(queue, queue_file, MASTER_KEY)
    commit_and_push_vault(vault_dir)

if __name__ == "__main__":
    main()

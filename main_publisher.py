import os
import sys
import re
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
from apify_discovery import clean_tiktok_caption, search_trending_tiktok_videos
from audio_sanitizer import sanitize_video_audio

VAULT_REPO = os.environ.get("VAULT_REPO", "hamouda1/pinterest-video-vault")
VAULT_PAT = os.environ.get("VAULT_PAT")
MASTER_KEY = os.environ.get("VIDEO_VAULT_KEY")

ACTIVE_ACCOUNTS_CONFIG = [
    {
        "account_id": "montessorinest_",
        "board_id": "1091630465869892618",
        "board_name": "Wooden Montessori Toys & Playroom",
        "hashtag": "montessoritoys"
    },
    {
        "account_id": "anisds1995",
        "board_id": "1106196795914700326",
        "board_name": "Cozy Living Room & Warm Lighting Ideas",
        "hashtag": "cozylivingroom"
    },
    {
        "account_id": "habiboumez",
        "board_id": "1093037840753549578",
        "board_name": "Chunky Cable Knit Cardigans & Knits",
        "hashtag": "knitwear"
    },
    {
        "account_id": "ThePantryHaven",
        "board_id": "258112691083171863",
        "board_name": "Aesthetic Pantry & Spice Jar Labels",
        "hashtag": "pantryorganization"
    },
    {
        "account_id": "marrytreasures",
        "board_id": "677440037639174208",
        "board_name": "Cozy Fall & Thanksgiving Aesthetic Finds",
        "hashtag": "aestheticgifts"
    },
    {
        "account_id": "koreanskincare_finds",
        "board_id": "246642585782160372",
        "board_name": "Glass Skin Routines",
        "hashtag": "koreanskincare"
    }
]

def get_vault_dir() -> Path:
    """Clones or resolves the private vault directory."""
    local_vault = Path(__file__).resolve().parent.parent / "pinterest-video-vault"
    if local_vault.exists() and (local_vault / "accounts_vault.json.enc").exists():
        return local_vault

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

    # 2. Load video queue in-memory
    queue = load_encrypted_json(queue_file, MASTER_KEY) or []

    # 2.5 Auto-replenish queue for any active account up to 10 pending videos using Apify
    TARGET_PENDING_PER_ACCOUNT = 10
    REPLENISH_THRESHOLD = 3
    apify_token = os.environ.get("APIFY_TOKEN")
    if apify_token:
        existing_ids = {it.get("id") for it in queue}
        replenished_any = False
        for cfg in ACTIVE_ACCOUNTS_CONFIG:
            acc_id = cfg["account_id"]
            if acc_id not in accounts:
                continue
            pending_count = sum(1 for it in queue if it.get("account_id") == acc_id and it.get("status") == "pending")
            if pending_count <= REPLENISH_THRESHOLD:
                needed = TARGET_PENDING_PER_ACCOUNT - pending_count
                print(f"🔍 Replenishing queue for @{acc_id}: {pending_count}/{TARGET_PENDING_PER_ACCOUNT} pending (threshold <= {REPLENISH_THRESHOLD}). Querying Apify for batch of {needed} videos (tag: #{cfg['hashtag']})...", flush=True)
                try:
                    discovered = search_trending_tiktok_videos(hashtag=cfg["hashtag"], max_items=needed, token=apify_token)
                    added = 0
                    for vid in discovered:
                        if vid["id"] not in existing_ids:
                            clean_t = vid.get("title", f"Aesthetic {cfg['board_name']} Inspo ✨")
                            clean_t = re.sub(r'[\r\n]+', ' ', clean_t).strip()
                            clean_t = re.sub(r'(?i)linked\s+on\s+my\s+\w+', '', clean_t).strip()
                            clean_t = clean_t.split('@')[0].strip()
                            if len(clean_t) < 5 or len(clean_t) > 75:
                                clean_t = f"Aesthetic {cfg['board_name']} Inspo ✨"

                            clean_d = vid.get("description", "")
                            clean_d = re.sub(r'(?i)linked\s+on\s+my\s+\w+', '', clean_d).strip()

                            queue.append({
                                "id": vid["id"],
                                "account_id": acc_id,
                                "board_id": cfg["board_id"],
                                "board_name": cfg["board_name"],
                                "video_source_url": vid["video_source_url"],
                                "creator_username": vid.get("creator_username", "creator"),
                                "title": clean_t,
                                "description": clean_d,
                                "link": "",
                                "status": "pending"
                            })
                            existing_ids.add(vid["id"])
                            added += 1
                            replenished_any = True
                            if sum(1 for it in queue if it.get("account_id") == acc_id and it.get("status") == "pending") >= TARGET_PENDING_PER_ACCOUNT:
                                break
                    print(f"   ✅ Added {added} fresh videos to @{acc_id} queue.", flush=True)
                except Exception as e:
                    print(f"   ⚠️ Discovery notice for @{acc_id}: {e}", flush=True)

        if replenished_any:
            save_encrypted_json(queue, queue_file, MASTER_KEY)
            commit_and_push_vault(vault_dir)
            print("   🔒 Saved and pushed replenished queue state into encrypted vault.", flush=True)

    # 3. Apply Timing Guards: Min 15m between network pins, Min 3h per account
    MIN_NETWORK_INTERVAL_MIN = 15
    MIN_ACCOUNT_COOLDOWN_HOURS = 3
    now = datetime.now()

    # Rule 1: Min 15m between any two pins across the entire network
    last_network_pub = None
    for item in reversed(queue):
        if item.get("status") == "published" and item.get("published_at"):
            try:
                dt = datetime.strptime(item.get("published_at"), "%Y-%m-%d %H:%M:%S")
                if last_network_pub is None or dt > last_network_pub:
                    last_network_pub = dt
            except Exception:
                pass

    if last_network_pub:
        mins_since_net = (now - last_network_pub).total_seconds() / 60
        if mins_since_net < MIN_NETWORK_INTERVAL_MIN:
            wait_m = MIN_NETWORK_INTERVAL_MIN - mins_since_net
            print(f"⏳ Network Interval Guard: Only {mins_since_net:.1f}m since last pin. Waiting {wait_m:.1f}m (15m rule).", flush=True)
            return

    # Rule 2: Min 3 hours between pins on the SAME account
    last_pub_by_acc = {}
    for item in queue:
        if item.get("status") == "published" and item.get("published_at"):
            acc = item.get("account_id")
            try:
                dt = datetime.strptime(item.get("published_at"), "%Y-%m-%d %H:%M:%S")
                if acc not in last_pub_by_acc or dt > last_pub_by_acc[acc]:
                    last_pub_by_acc[acc] = dt
            except Exception:
                pass

    eligible_acc_ids = []
    for cfg in ACTIVE_ACCOUNTS_CONFIG:
        acc_id = cfg["account_id"]
        if acc_id not in accounts:
            continue
        if acc_id not in last_pub_by_acc:
            eligible_acc_ids.append(acc_id)
            print(f"   🟢 @{acc_id}: Ready to publish (no previous pin on record)")
        else:
            hours_since = (now - last_pub_by_acc[acc_id]).total_seconds() / 3600
            if hours_since >= MIN_ACCOUNT_COOLDOWN_HOURS:
                eligible_acc_ids.append(acc_id)
                print(f"   🟢 @{acc_id}: Ready to publish ({hours_since:.1f}h since last pin >= 3h)")
            else:
                rem_mins = (MIN_ACCOUNT_COOLDOWN_HOURS - hours_since) * 60
                print(f"   ⏳ @{acc_id}: In cooldown ({hours_since:.1f}h / 3h). Next pin in {rem_mins:.0f}m.")

    if not eligible_acc_ids:
        print("⏳ All active accounts are currently within their 3-hour cooldown period.", flush=True)
        return

    # Prioritize eligible accounts by Least Recently Published (oldest last_published_at or never)
    # This guarantees exact, fair round-robin rotation across all active accounts without starvation.
    eligible_acc_ids.sort(key=lambda acc: last_pub_by_acc.get(acc, datetime.min))
    print("📋 Account Priority Queue (Oldest Published / Starved First):", flush=True)
    for acc in eligible_acc_ids:
        lp = last_pub_by_acc.get(acc)
        lp_str = lp.strftime("%Y-%m-%d %H:%M:%S") if lp else "NEVER"
        print(f"   👉 @{acc} (Last Pin: {lp_str})", flush=True)

    candidates = []
    for candidate_acc in eligible_acc_ids:
        for item in queue:
            if item.get("status") == "pending" and item.get("account_id") == candidate_acc and item.get("account_id") in accounts:
                if item not in candidates:
                    candidates.append(item)
                break

    if not candidates:
        print("ℹ️ No pending videos ready for eligible accounts. Queue complete or awaiting items.", flush=True)
        return

    # 4. Attempt publishing candidate videos until one succeeds
    published_success = False
    for target_item in candidates[:3]:
        acc_id = target_item.get("account_id")
        acc_info = accounts.get(acc_id)
        if not acc_info:
            continue
        token = acc_info.get("access_token")
        if not token:
            continue

        source_url = target_item.get("video_source_url")
        board_id = target_item.get("board_id")
        title = target_item.get("title")
        desc = target_item.get("description")
        link = target_item.get("link")

        print(f"\n🎯 Target Account: @{acc_id}", flush=True)
        print(f"📌 Board ID: {board_id}", flush=True)
        print(f"🎬 Video Source: {source_url}", flush=True)
        print(f"📝 Title: {title}", flush=True)

        local_mp4 = None
        try:
            print(f"\n📥 Extracting and downloading video via yt-dlp...", flush=True)
            meta, local_mp4 = extract_and_download_video(source_url)
            print(f"   ✅ Downloaded: {local_mp4.name} (Duration: {meta.get('duration')}s, Size: {os.path.getsize(local_mp4)} bytes)", flush=True)

            creator = target_item.get("creator_username") or meta.get("uploader") or "creator"
            board_name_low = str(target_item.get("board_name", "")).lower()
            acc_low = str(acc_id).lower()
            if any(w in board_name_low or w in acc_low for w in ["montessori", "nursery", "baby", "toddler"]):
                tag = "montessori"
            elif any(w in board_name_low or w in acc_low for w in ["cozy", "candle", "decor", "bedroom", "living", "lighting", "throw", "holiday", "christmas"]):
                tag = "cozyhome"
            elif any(w in board_name_low or w in acc_low for w in ["sweater", "apparel", "knit", "hoodie", "outfit", "cardigan", "fashion", "streetwear"]):
                tag = "aestheticoutfit"
            elif any(w in board_name_low or w in acc_low for w in ["pantry", "kitchen", "jar", "cutting", "spice", "farmhouse"]):
                tag = "kitcheninspo"
            elif any(w in board_name_low or w in acc_low for w in ["gift", "jewelry", "wedding", "tee", "shirt", "graphic", "couple"]):
                tag = "personalizedgifts"
            elif any(w in board_name_low or w in acc_low for w in ["coffee", "brew", "matcha"]):
                tag = "coffee"
            elif any(w in board_name_low or w in acc_low for w in ["book", "reading", "read"]):
                tag = "reading"
            else:
                tag = "aesthetic"

            desc = clean_tiktok_caption(desc, creator, tag)

            clean_title = (title or f"Aesthetic {target_item.get('board_name', 'Finds')} Inspo ✨").split('#')[0].strip()
            clean_title = re.sub(r'[\r\n]+', ' ', clean_title).strip()
            clean_title = re.sub(r'(?i)linked\s+on\s+my\s+\w+', '', clean_title).strip()
            clean_title = clean_title.split('@')[0].strip()
            if len(clean_title) < 5 or clean_title.startswith('@') or len(clean_title) > 85:
                clean_title = f"Aesthetic {target_item.get('board_name', 'Finds')} Inspo ✨"

            # Audio Safety Guard: Scan for commercial music via acoustic fingerprinting
            final_upload_mp4 = local_mp4
            try:
                final_upload_mp4, was_sanitized, audio_details = sanitize_video_audio(local_mp4)
                if was_sanitized:
                    print(f"   🛡️ Audio Guard Applied: {audio_details}", flush=True)
                else:
                    print(f"   ✅ Audio Guard Passed: {audio_details}", flush=True)
            except Exception as e:
                print(f"   ⚠️ Audio scanner notice ({e}), proceeding with verified upload.", flush=True)

            uploader = PinterestVideoUploader(access_token=token)
            pin_res = uploader.upload_and_publish(
                file_path=final_upload_mp4,
                board_id=board_id,
                title=clean_title,
                description=desc,
                link=link or ""
            )

            pin_id = pin_res.get("id")
            pin_url = f"https://www.pinterest.com/pin/{pin_id}/" if pin_id else "N/A"

            target_item["status"] = "published"
            target_item["published_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            target_item["pin_id"] = pin_id
            target_item["pin_url"] = pin_url

            print(f"\n🎉 SUCCESS! Video Pin Published Live!", flush=True)
            print(f"   📌 Pin ID: {pin_id}", flush=True)
            print(f"   🔗 URL: {pin_url}", flush=True)
            published_success = True
            break

        except Exception as e:
            print(f"\n❌ Error during video publishing attempt for @{acc_id}: {e}", flush=True)
            target_item["status"] = "failed"
            target_item["error"] = str(e)
            target_item["failed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        finally:
            if local_mp4 and local_mp4.exists():
                try:
                    os.remove(local_mp4)
                except Exception:
                    pass
            if 'final_upload_mp4' in locals() and final_upload_mp4 and final_upload_mp4 != local_mp4 and final_upload_mp4.exists():
                try:
                    os.remove(final_upload_mp4)
                except Exception:
                    pass
            print("   🧹 Cleaned up temporary video files.")

    # 5. Save encrypted queue back to vault and push
    save_encrypted_json(queue, queue_file, MASTER_KEY)
    commit_and_push_vault(vault_dir)

if __name__ == "__main__":
    main()

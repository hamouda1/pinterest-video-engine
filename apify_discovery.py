import os
import requests
from typing import List, Dict, Any

APIFY_BASE = "https://api.apify.com/v2"

def search_trending_tiktok_videos(
    hashtag: str,
    max_items: int = 15,
    token: str = None
) -> List[Dict[str, Any]]:
    """
    Uses Apify TikTok Scraper actor to discover viral videos matching a hashtag.
    Returns a list of structured video items.
    """
    api_token = token or os.environ.get("APIFY_TOKEN")
    if not api_token:
        print("   ⚠️ Notice: APIFY_TOKEN not configured. Skipping automated discovery.")
        return []

    # Using the industry standard clockworks/free-tiktok-scraper actor
    actor_id = "clockworks~free-tiktok-scraper"
    url = f"{APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"

    clean_tag = hashtag.replace("#", "").strip()
    payload = {
        "hashtags": [clean_tag],
        "resultsPerPage": max_items,
        "shouldDownloadVideos": True,
        "shouldDownloadCovers": False
    }

    headers = {"Authorization": f"Bearer {api_token}"}

    try:
        print(f"   🔍 Querying Apify for #{clean_tag} viral videos...", flush=True)
        resp = requests.post(url, headers=headers, json=payload, timeout=90)
        resp.raise_for_status()
        items = resp.json()

        results = []
        for it in items:
            download_url = it.get("downloadAddr") or (it.get("mediaUrls", [None])[0] if it.get("mediaUrls") else None)
            if download_url and "token=" not in download_url:
                download_url = f"{download_url}?token={api_token}"

            web_url = it.get("webVideoUrl")
            if not web_url and it.get("id"):
                author = it.get("authorMeta", {}).get("name", "tiktok")
                web_url = f"https://www.tiktok.com/@{author}/video/{it.get('id')}"

            if download_url or web_url:
                creator_username = it.get("authorMeta", {}).get("name") or "creator"
                clean_title = (it.get("text") or f"Aesthetic #{clean_tag} Inspiration").split("#")[0].strip()[:85]
                caption_text = it.get("text", "").strip()[:240]
                
                credit_block = f"✨ Video credit: @{creator_username} on TikTok\n(All rights reserved to the creator - DM for credit or removal)"
                full_desc = f"{caption_text}\n\n{credit_block}\n\nFollow for daily aesthetic #{clean_tag} inspiration! #{clean_tag} #aesthetic #viral"
                
                results.append({
                    "id": f"vid_{it.get('id')}",
                    "creator_username": creator_username,
                    "video_source_url": download_url or web_url,
                    "web_url": web_url,
                    "title": clean_title or f"Aesthetic #{clean_tag} Find",
                    "description": full_desc[:500],
                    "play_count": it.get("playCount", 0),
                    "digg_count": it.get("diggCount", 0),
                    "share_count": it.get("shareCount", 0),
                    "hashtag": clean_tag
                })

        print(f"   ✅ Discovered {len(results)} viral videos for #{clean_tag}", flush=True)
        return results
    except Exception as e:
        print(f"   ⚠️ Apify discovery notice ({clean_tag}): {e}", flush=True)
        return []

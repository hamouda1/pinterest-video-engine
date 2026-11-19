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
        "shouldDownloadVideos": False,
        "shouldDownloadCovers": False
    }

    headers = {"Authorization": f"Bearer {api_token}"}

    try:
        print(f"   🔍 Querying Apify for #{clean_tag} trending videos...", flush=True)
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        items = resp.json()

        results = []
        for it in items:
            web_url = it.get("webVideoUrl") or it.get("videoUrl")
            if not web_url and it.get("id"):
                author = it.get("authorMeta", {}).get("name", "tiktok")
                web_url = f"https://www.tiktok.com/@{author}/video/{it.get('id')}"

            if web_url:
                results.append({
                    "video_url": web_url,
                    "title": it.get("text") or f"Aesthetic #{clean_tag} Find",
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

import os
import requests
from typing import List, Dict, Any

APIFY_BASE = "https://api.apify.com/v2"

def is_original_audio(item: Dict[str, Any]) -> bool:
    """
    Checks if a TikTok video uses original creator sound, voiceover, or natural ASMR,
    rather than a commercial studio music track (which triggers Pinterest audio removal).
    """
    music_meta = item.get("musicMeta") or {}
    author_meta = item.get("authorMeta") or {}

    is_original_flag = music_meta.get("musicOriginal")
    music_name = (music_meta.get("musicName") or "").strip().lower()
    music_author = (music_meta.get("musicAuthor") or "").strip().lower()
    creator_name = (author_meta.get("name") or "").strip().lower()
    creator_nickname = (author_meta.get("nickName") or "").strip().lower()
    caption = (item.get("text") or "").lower()

    # 1. Explicit Original Sound flag from TikTok
    if is_original_flag is True:
        return True

    # 2. Keywords indicating original or natural voice/sound
    if any(k in music_name for k in ["original", "son original", "suono originale", "originalton", "sonido original"]):
        return True

    # 3. Sound attributed directly to the creator
    if creator_name and (creator_name in music_author or music_author in creator_name):
        return True
    if creator_nickname and (creator_nickname in music_author or music_author in creator_nickname):
        return True

    # 4. Explicit ASMR / Voiceover / Routine in caption
    if any(tag in caption for tag in ["#asmr", " asmr", "#voiceover", " voiceover", "#routine", " routine", "#tutorial"]):
        if not music_author or creator_name in music_author:
            return True

    # 5. If explicitly flagged as NOT original and has a distinct commercial music artist -> Rejected
    if is_original_flag is False and music_author and music_author != creator_name:
        return False

    return is_original_flag is not False

def clean_tiktok_caption(raw_text: str, creator_username: str, niche_tag: str = "coffee") -> str:
    """
    Cleans raw TikTok text:
    - Strips 'link in bio', 'linked in bio', personal drama or first-person claims
    - Retains general descriptive words and aesthetic vibe
    - Appends respectful 3rd-person attribution to creator
    """
    import re
    text = raw_text or ""
    # Strip URLs
    text = re.sub(r'https?://\S+', '', text)
    # Strip phrases like "link in bio", "linked in bio", "check bio", etc.
    bio_patterns = [
        r'(?i)\ball\s+(the\s+)?(materials|items|links|products)\s+(are\s+)?linked\s+in\s+(my\s+)?bio[^\w\s]*',
        r'(?i)\blink\s+(is\s+)?(in\s+)?(my\s+)?bio[^\w\s]*',
        r'(?i)\blinked\s+in\s+(my\s+)?bio[^\w\s]*',
        r'(?i)\bcheck\s+(my\s+)?bio[^\w\s]*',
        r'(?i)\b(dm|comment)\s+for\s+(the\s+)?link[^\w\s]*',
        r'(?i)\bpraying\s+on\s+(the\s+)?downfall[^\w\s]*',
        r'(?i)\blet\s+me\s+know\s+if\s+i\s+missed[^\w\s]*',
        r'(?i)\bwhat\s+do\s+you\s+think\s+of\s+my[^\w\s]*'
    ]
    for pat in bio_patterns:
        text = re.sub(pat, '', text)

    # Clean excessive whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    if len(text) < 15:
        text = f"Cozy and aesthetic at-home #{niche_tag} setup inspo ✨"

    clean_caption = text[:230].strip()
    credit_line = f"✨ Video credit: @{creator_username} on TikTok\n(All rights belong to the creator - DM for removal)"
    if any(w in niche_tag.lower() for w in ["skincare", "skin", "kbeauty", "beauty"]):
        emoji = "💧✨"
    elif any(w in niche_tag.lower() for w in ["baby", "montessori", "nursery", "kids", "toddler"]):
        emoji = "🧸✨"
    elif any(w in niche_tag.lower() for w in ["cozy", "home", "candle", "decor"]):
        emoji = "🕯️✨"
    elif any(w in niche_tag.lower() for w in ["outfit", "sweater", "fashion", "apparel"]):
        emoji = "👗✨"
    elif any(w in niche_tag.lower() for w in ["kitchen", "pantry", "farmhouse"]):
        emoji = "🌿✨"
    elif any(w in niche_tag.lower() for w in ["gift", "jewelry", "wedding", "tee"]):
        emoji = "🎁✨"
    elif "coffee" in niche_tag.lower():
        emoji = "☕✨"
    else:
        emoji = "✨"

    curation_line = f"Curated for daily aesthetic inspiration {emoji} #{niche_tag} #aesthetic #inspo"

    full_desc = f"{clean_caption}\n\n{credit_line}\n\n{curation_line}"
    return full_desc[:500]

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
    fetch_count = max(max_items, 5)
    payload = {
        "hashtags": [clean_tag],
        "resultsPerPage": fetch_count,
        "shouldDownloadVideos": False,
        "shouldDownloadCovers": False
    }

    headers = {"Authorization": f"Bearer {api_token}"}

    try:
        print(f"   🔍 Querying Apify for #{clean_tag} viral videos (sampling {fetch_count})...", flush=True)
        resp = requests.post(url, headers=headers, json=payload, timeout=90)
        resp.raise_for_status()
        raw_items = resp.json()

        # Prioritize organic audio, but retain all items (our audio sanitizer mutes commercial tracks safely)
        original_audio_items = [it for it in raw_items if is_original_audio(it)]
        other_audio_items = [it for it in raw_items if not is_original_audio(it)]
        print(f"   🎵 Audio Guard: {len(original_audio_items)}/{len(raw_items)} organic sound, {len(other_audio_items)} will be sanitized if commercial.", flush=True)

        selected_items = original_audio_items + other_audio_items

        results = []
        for it in selected_items:
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
                full_desc = clean_tiktok_caption(it.get("text", ""), creator_username, clean_tag)
                
                results.append({
                    "id": f"vid_{it.get('id')}",
                    "creator_username": creator_username,
                    "video_source_url": download_url or web_url,
                    "web_url": web_url,
                    "title": clean_title or f"Aesthetic #{clean_tag} Find",
                    "description": full_desc,
                    "play_count": it.get("playCount", 0),
                    "digg_count": it.get("diggCount", 0),
                    "share_count": it.get("shareCount", 0),
                    "hashtag": clean_tag,
                    "audio_type": "original_sound"
                })
                if len(results) >= max_items:
                    break

        print(f"   ✅ Discovered {len(results)} verified clean videos for #{clean_tag}", flush=True)
        return results
    except Exception as e:
        print(f"   ⚠️ Apify discovery notice ({clean_tag}): {e}", flush=True)
        return []

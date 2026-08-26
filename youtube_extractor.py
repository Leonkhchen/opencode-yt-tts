from __future__ import annotations
import re
import requests

YOUTUBE_RE = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})")

def extract_video_id(url: str) -> str | None:
    m = YOUTUBE_RE.search(url.strip())
    return m.group(1) if m else None

def fetch_title(video_id: str) -> str:
    try:
        r = requests.get("https://www.youtube.com/oembed", params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"}, timeout=8)
        if r.ok:
            return r.json().get("title", video_id)
    except Exception:
        pass
    return video_id

def fetch_transcript(video_id: str, langs: list[str] | None = None) -> tuple[str, str]:
    from youtube_transcript_api import YouTubeTranscriptApi
    langs = langs or ["zh-TW", "zh-Hant", "zh", "en"]
    try:
        fetched = YouTubeTranscriptApi.get_transcript(video_id, languages=langs)
    except Exception:
        fetched = YouTubeTranscriptApi.get_transcript(video_id)
    text = "\n".join(seg["text"] for seg in fetched)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    title = fetch_title(video_id)
    return title, text

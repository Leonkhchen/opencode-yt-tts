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

def _fetch_via_invidious(video_id: str) -> str | None:
    hosts = ["https://inv.nadeko.net", "https://invidious.io.lol", "https://invidious.snopyta.org", "https://iv.melmac.space"]
    import xml.etree.ElementTree as ET, html
    for h in hosts:
        try:
            r = requests.get(f"{h}/api/v1/captions/{video_id}", timeout=10)
            if not r.ok: continue
            caps = r.json()
            if not caps: continue
            pref = None
            for c in caps:
                code = c.get("languageCode","")
                if code.startswith("zh"): pref = c; break
            if not pref:
                for c in caps:
                    if c.get("languageCode","").startswith("en"): pref=c; break
            if not pref: pref=caps[0]
            url = pref.get("url","")
            if not url: continue
            if url.startswith("/"): url = h + url
            r2 = requests.get(url, timeout=10)
            if not r2.ok or not r2.text: continue
            root = ET.fromstring(r2.text)
            texts = []
            for elem in root.findall("text"):
                t = elem.text or ""
                t = html.unescape(t)
                if t.strip(): texts.append(t.strip())
            if texts:
                return "\n".join(texts)
        except Exception:
            continue
    return None

def fetch_transcript(video_id: str, langs: list[str] | None = None) -> tuple[str, str]:
    from youtube_transcript_api import YouTubeTranscriptApi
    langs = langs or ["zh-TW", "zh-Hant", "zh", "en"]
    last_err = None
    try:
        if hasattr(YouTubeTranscriptApi, "get_transcript"):
            try:
                fetched = YouTubeTranscriptApi.get_transcript(video_id, languages=langs)
            except Exception as e:
                last_err = e
                if "blocking" in str(e).lower() or "blocked" in str(e).lower() or "IP" in str(e):
                    raise e
                fetched = YouTubeTranscriptApi.get_transcript(video_id)
        else:
            api = YouTubeTranscriptApi()
            if hasattr(api, "fetch"):
                fetched = api.fetch(video_id, languages=langs)
            else:
                fetched = api.get_transcript(video_id, languages=langs)
            if fetched and hasattr(fetched, "snippets"):
                fetched = [{"text": s.text} for s in fetched.snippets]
            elif fetched and len(fetched)>0 and hasattr(fetched[0], "text"):
                fetched = [{"text": s.text} for s in fetched]
        text = "\n".join(seg["text"] if isinstance(seg, dict) else getattr(seg,"text","") for seg in fetched)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if text:
            title = fetch_title(video_id)
            return title, text
    except Exception as e:
        last_err = e
    inv = _fetch_via_invidious(video_id)
    if inv:
        inv = re.sub(r"[ \t]+", " ", inv)
        inv = re.sub(r"\n{3,}", "\n\n", inv).strip()
        title = fetch_title(video_id)
        return title, inv
    if last_err:
        raise RuntimeError(f"官方字幕被YouTube封鎖(雲主機IP)，Invidious備援也失敗: {last_err}. 請改用『貼上字幕文字』或換有字幕的影片。")
    raise RuntimeError("無法取得字幕")

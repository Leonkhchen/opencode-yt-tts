from __future__ import annotations
import base64, os
from pathlib import Path
import requests
from text_chunk import chunk_text
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent/".env")
except: pass
GOOGLE_TTS_API_KEY=os.environ.get("GOOGLE_TTS_API_KEY","")
_API="https://texttospeech.googleapis.com/v1/text:synthesize"
_CHUNK=1400
VOICES={"cmn-TW-Standard-A":"Standard-A（女聲）","cmn-TW-Standard-B":"Standard-B（男聲）","cmn-TW-Standard-C":"Standard-C（男聲）","cmn-TW-Wavenet-A":"Wavenet-A（女聲・高音質）","cmn-TW-Wavenet-B":"Wavenet-B（男聲）","cmn-TW-Wavenet-C":"Wavenet-C（男聲）"}
DEFAULT_VOICE="cmn-TW-Wavenet-A"
def _call(text,voice,log,retries=3):
    import time
    body={"input":{"text":text},"voice":{"languageCode":"cmn-TW","name":voice},"audioConfig":{"audioEncoding":"MP3"}}
    last=""
    for a in range(1,retries+1):
        try: r=requests.post(_API,params={"key":GOOGLE_TTS_API_KEY},json=body,timeout=60)
        except Exception as e:
            last=f"{type(e).__name__}:{e}"
            if a<retries: log(f" ⚠ {last}");time.sleep(2*a);continue
            raise RuntimeError(last)
        if r.status_code==200:
            d=r.json().get("audioContent")
            if d: return base64.b64decode(d)
            last="無audioContent"
        else:
            try: last=f"HTTP{r.status_code}:{r.json().get('error',{}).get('message',r.text[:200])}"
            except: last=f"HTTP{r.status_code}:{r.text[:200]}"
            if 400<=r.status_code<500: raise RuntimeError(last)
        if a<retries: log(f" ⚠ {last}");time.sleep(2*a)
    raise RuntimeError(last)
def synthesize_chapter(text,out_no_ext,voice,log):
    if not GOOGLE_TTS_API_KEY: raise RuntimeError("未設定 GOOGLE_TTS_API_KEY")
    chunks=chunk_text(text,_CHUNK)
    if not chunks or not chunks[0]: raise RuntimeError("空內容")
    log(f" 分{len(chunks)}段 (Cloud TTS)")
    parts=[]
    for i,ch in enumerate(chunks):
        log(f" 段{i+1}/{len(chunks)}")
        parts.append(_call(ch,voice,log))
    mp3=out_no_ext.with_suffix(".mp3");mp3.write_bytes(b"".join(parts))
    log(f" 完成{mp3.name} {mp3.stat().st_size//1024}KB");return mp3

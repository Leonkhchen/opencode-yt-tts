from __future__ import annotations
import base64, os, shutil, subprocess, wave
from pathlib import Path
from text_chunk import chunk_text
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except: pass
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY","")
_TTS_MODEL="gemini-2.5-flash-preview-tts"
_CHUNK=1800
_SR=24000;_SW=2;_CH=1
VOICES={"Kore":"Kore（女聲・沉穩）","Puck":"Puck（男聲・輕快）","Charon":"Charon（男聲・低沉）","Zephyr":"Zephyr（女聲・明亮）","Fenrir":"Fenrir（男聲・渾厚）","Leda":"Leda（女聲・年輕）","Autonoe":"Autonoe（女聲・清晰）","Enceladus":"Enceladus（男聲・柔和）"}
DEFAULT_VOICE="Kore"
def _call(client,text,voice,log,retries=3):
    from google.genai import types as T, errors as E
    import time
    last=""
    for a in range(1,retries+1):
        try:
            resp=client.models.generate_content(model=_TTS_MODEL,contents=text,config=T.GenerateContentConfig(response_modalities=["AUDIO"],speech_config=T.SpeechConfig(voice_config=T.VoiceConfig(prebuilt_voice_config=T.PrebuiltVoiceConfig(voice_name=voice))),http_options=T.HttpOptions(timeout=360000)))
        except Exception as e:
            last=f"{type(e).__name__}:{e}"
            if a<retries:
                log(f" ⚠ {last} {a}/{retries}重試")
                time.sleep(2*a);continue
            raise RuntimeError(f"Gemini失敗:{last}") from e
        cands=resp.candidates or []
        if cands and cands[0].content and cands[0].content.parts:
            d=cands[0].content.parts[0].inline_data.data
            return base64.b64decode(d) if isinstance(d,str) else d
        last=f"空回應 finish={cands[0].finish_reason if cands else 'none'}"
        if a<retries:
            log(f" ⚠ {last} {a}/{retries}重試");time.sleep(2*a)
    raise RuntimeError(last)
def _wav(chunks,path):
    with wave.open(str(path),"wb") as w:
        w.setnchannels(_CH);w.setsampwidth(_SW);w.setframerate(_SR)
        for c in chunks: w.writeframes(c)
def _mp3(wav,mp3,log):
    ff=shutil.which("ffmpeg")
    if not ff: return False
    try:
        p=subprocess.run([ff,"-y","-i",str(wav),"-codec:a","libmp3lame","-qscale:a","4",str(mp3)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding="utf-8",errors="replace")
        return p.returncode==0 and mp3.exists()
    except Exception as e: log(str(e));return False
def synthesize_chapter(text,out_no_ext,voice,log):
    if not GEMINI_API_KEY: raise RuntimeError("未設定 GEMINI_API_KEY")
    from google import genai
    client=genai.Client(api_key=GEMINI_API_KEY)
    chunks=chunk_text(text,_CHUNK)
    if not chunks or not chunks[0]: raise RuntimeError("空內容")
    log(f" 分{len(chunks)}段生成")
    parts=[]
    for i,ch in enumerate(chunks):
        log(f" 段{i+1}/{len(chunks)} {len(ch):,}字")
        parts.append(_call(client,ch,voice,log))
    wav=out_no_ext.with_suffix(".wav");_wav(parts,wav)
    mp3=out_no_ext.with_suffix(".mp3")
    if _mp3(wav,mp3,log):
        wav.unlink(missing_ok=True);log(f" 完成{mp3.name} {mp3.stat().st_size//1024}KB");return mp3
    log(f" 完成{wav.name} {wav.stat().st_size//1024}KB");return wav

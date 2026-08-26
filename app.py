from __future__ import annotations
import io, json, os, queue, sys, threading, traceback, uuid, zipfile, re
from pathlib import Path
from functools import wraps
from flask import Flask, request, jsonify, send_file, Response, render_template, session, redirect, url_for
from youtube_extractor import extract_video_id, fetch_transcript, fetch_title
import tts_gemini, tts_gcloud

PROVIDERS={
 "gemini":{"synthesize":tts_gemini.synthesize_chapter,"voices":tts_gemini.VOICES,"default_voice":tts_gemini.DEFAULT_VOICE,"label":"Gemini TTS","has_key":bool(tts_gemini.GEMINI_API_KEY)},
 "gcloud":{"synthesize":tts_gcloud.synthesize_chapter,"voices":tts_gcloud.VOICES,"default_voice":tts_gcloud.DEFAULT_VOICE,"label":"Google Cloud TTS","has_key":bool(tts_gcloud.GOOGLE_TTS_API_KEY)},
}
DEFAULT_PROVIDER="gemini"
def _dbg(m): print(f"[PID={os.getpid()}] {m}",file=sys.stderr,flush=True)
app=Flask(__name__)
app.config["MAX_CONTENT_LENGTH"]=100*1024*1024
app.secret_key=os.environ.get("SECRET_KEY",os.urandom(32))
JOBS_DIR=Path(os.environ.get("JOBS_DIR","/tmp/yt_tts_jobs"))
APP_PASSWORD=os.environ.get("APP_PASSWORD","")
JOBS_DIR.mkdir(parents=True,exist_ok=True)
_jobs:dict[str,dict]={}
_lock=threading.Lock()
def _check():
    if not APP_PASSWORD: return True
    return session.get("authed") is True
def need(f):
    @wraps(f)
    def d(*a,**k):
        if not _check():
            if request.path.startswith("/api/"): return jsonify(error="未授權"),401
            return redirect(url_for("login_page"))
        return f(*a,**k)
    return d
@app.route("/login",methods=["GET"])
def login_page():
    if _check(): return redirect(url_for("index"))
    return render_template("login.html")
@app.route("/login",methods=["POST"])
def login_post():
    if request.form.get("password","")==APP_PASSWORD:
        session["authed"]=True
        return redirect(url_for("index"))
    return render_template("login.html",error="密碼錯誤"),401
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page") if APP_PASSWORD else url_for("index"))
def _job(p): return JOBS_DIR/p
def _in(j): p=_job(j)/"input";p.mkdir(parents=True,exist_ok=True);return p
def _out(j): p=_job(j)/"output";p.mkdir(parents=True,exist_ok=True);return p
def _push(q,e,d): q.put({"event":e,"data":d})
def _safe(s): s="".join(c for c in s if c.isalnum() or c in "._- ()[]（）【】");return (s.strip() or "file")[:80]
@app.route("/")
@need
def index():
    for_js={k:{"label":v["label"],"voices":v["voices"],"default_voice":v["default_voice"]} for k,v in PROVIDERS.items()}
    return render_template("index.html",has_password=bool(APP_PASSWORD),providers=PROVIDERS,default_provider=DEFAULT_PROVIDER,providers_json=json.dumps(for_js,ensure_ascii=False))
@app.route("/api/extract",methods=["POST"])
@need
def extract():
    body=request.get_json(silent=True) or {}
    url=body.get("url","").strip()
    vid=extract_video_id(url)
    if not vid: return jsonify(error="無法解析 YouTube 連結，請貼上完整 youtube.com/watch?v= 或 youtu.be/ 連結"),400
    manual_text = body.get("manual_text","").strip()
    if manual_text and len(manual_text)>=20:
        title = fetch_title(vid) + " (手動字幕)"
        text = manual_text
    else:
        try:
            title,text=fetch_transcript(vid)
        except Exception as e:
            return jsonify(error=f"字幕抓取失敗: {e}", need_manual=True),400
    if len(text)<20: return jsonify(error="字幕內容過短"),400
    job_id=uuid.uuid4().hex
    _out(job_id)
    total=len(text)
    preview=text[:600]
    with _lock:
        _jobs[job_id]={"title":title,"video_id":vid,"url":url,"text":text,"provider":DEFAULT_PROVIDER,"voice":PROVIDERS[DEFAULT_PROVIDER]["default_voice"],"done":False,"started":False,"results":[],"queue":queue.Queue()}
    return jsonify(job_id=job_id,title=title,video_id=vid,chars=total,preview=preview,has_transcript=True)
@app.route("/api/convert/<job_id>",methods=["POST"])
@need
def convert(job_id):
    with _lock:
        job=_jobs.get(job_id)
        if job and job["started"]: return jsonify(ok=True)
    if not job: return jsonify(error="job不存在"),404
    body=request.get_json(silent=True) or {}
    prov=body.get("provider",DEFAULT_PROVIDER)
    if prov not in PROVIDERS: prov=DEFAULT_PROVIDER
    voices=PROVIDERS[prov]["voices"]
    dv=PROVIDERS[prov]["default_voice"]
    voice=body.get("voice",dv)
    if voice not in voices: voice=dv
    job["provider"]=prov;job["voice"]=voice;job["started"]=True
    threading.Thread(target=_worker,args=(job_id,),daemon=True).start()
    return jsonify(ok=True)
@app.route("/api/progress/<job_id>")
@need
def progress(job_id):
    with _lock: job=_jobs.get(job_id)
    if not job: return jsonify(error="job不存在"),404
    q=job["queue"]
    def gen():
        yield 'data: {"type":"connected"}\n\n'
        while True:
            try: msg=q.get(timeout=30)
            except queue.Empty: yield ": heartbeat\n\n";continue
            yield f"data: {json.dumps(msg,ensure_ascii=False)}\n\n"
            if msg.get("event")=="done": break
    return Response(gen(),content_type="text/event-stream",headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})
@app.route("/api/status/<job_id>")
@need
def status(job_id):
    with _lock: job=_jobs.get(job_id)
    if not job: return jsonify(error="job不存在"),404
    return jsonify(title=job["title"],done=job["done"],voice=job["voice"],provider=job.get("provider",DEFAULT_PROVIDER),results=job["results"])
@app.route("/api/download/<job_id>/<fname>")
@need
def download(job_id,fname):
    p=_out(job_id)/fname
    if not p.exists(): return jsonify(error="檔案不存在"),404
    return send_file(str(p),as_attachment=True,download_name=fname)
@app.route("/api/download_zip/<job_id>")
@need
def download_zip(job_id):
    with _lock: job=_jobs.get(job_id)
    if not job: return jsonify(error="job不存在"),404
    buf=io.BytesIO()
    out=_out(job_id)
    with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as zf:
        for r in job["results"]:
            if r["status"]=="ok":
                fp=out/r["filename"]
                if fp.exists(): zf.write(fp,arcname=r["filename"])
    buf.seek(0)
    return send_file(buf,as_attachment=True,download_name=_safe(job["title"])+"_YT有聲書.zip",mimetype="application/zip")
def _worker(job_id):
    with _lock: job=_jobs[job_id]
    text=job["text"];title=job["title"];prov=job.get("provider",DEFAULT_PROVIDER);voice=job["voice"];q=job["queue"];out=_out(job_id)
    synthesize=PROVIDERS[prov]["synthesize"]
    def log(m): _push(q,"log",{"text":m});print(m,file=sys.stderr,flush=True)
    log(f"標題: {title} | 引擎:{PROVIDERS[prov]['label']} 聲音:{voice} | 共{len(text):,}字")
    fname_stem=_safe(title) or "yt_audio"
    result={"index":1,"title":title,"filename":"","status":"converting","error":""}
    job["results"].append(result)
    _push(q,"chapter_status",{**result,"idx":0,"total":1,"pct":5})
    existing=next((p for p in (out/(fname_stem+".mp3"),out/(fname_stem+".wav")) if p.exists() and p.stat().st_size>0),None)
    if existing:
        log(f"已存在略過: {existing.name}")
        result["filename"]=existing.name;result["status"]="ok"
        _push(q,"chapter_status",{**result,"idx":0,"total":1,"pct":100})
    else:
        try:
            out_path=synthesize(text,out/fname_stem,voice,log)
            result["filename"]=out_path.name;result["status"]="ok"
            _push(q,"chapter_status",{**result,"idx":0,"total":1,"pct":100})
        except Exception as e:
            result["status"]="error";result["error"]=str(e)
            _push(q,"chapter_status",{**result,"idx":0,"total":1,"pct":100})
            log(f"FAIL:{e}");traceback.print_exc()
    job["done"]=True
    ok=sum(1 for r in job["results"] if r["status"]=="ok")
    log(f"完成 成功{ok}/1")
    _push(q,"done",{"total":1,"ok":ok,"errors":1-ok})
if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5050)),threaded=True)

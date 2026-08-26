FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
COPY . .
RUN mkdir -p /tmp/yt_tts_jobs
EXPOSE 8080
CMD ["gunicorn", "-w", "1", "--threads", "4", "--timeout", "600", "-b", "0.0.0.0:8080", "app:app"]

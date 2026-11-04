import os
import sys
import json
import subprocess
import cv2
import numpy as np
import yt_dlp
from faster_whisper import WhisperModel

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")

url = "https://www.facebook.com/reel/1794865671634029"
reel_id = "1794865671634029"
v_dir = os.path.abspath("videos_descobrindo_mundo")
f_dir = os.path.abspath("frames_descobrindo_mundo")
os.makedirs(v_dir, exist_ok=True)
os.makedirs(f_dir, exist_ok=True)

out_filepath = os.path.join(v_dir, f"single_{reel_id}.mp4")

print(f"Baixando Reel: {url}...", flush=True)
ydl_opts = {
    'outtmpl': os.path.join(v_dir, f"single_{reel_id}.%(ext)s"),
    'quiet': True,
    'no_warnings': True,
    'merge_output_format': 'mp4'
}

meta = {}
with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    meta = ydl.extract_info(url, download=True)

print("Download concluído!", flush=True)
print(f"Título: {meta.get('title')}", flush=True)
print(f"Descrição: {meta.get('description')}", flush=True)
print(f"Canal / Uploader: {meta.get('uploader')} (ID: {meta.get('uploader_id')})", flush=True)
print(f"Views: {meta.get('view_count')}", flush=True)
print(f"Data de Upload: {meta.get('upload_date')}", flush=True)

# Frames e propriedades
cap = cv2.VideoCapture(out_filepath)
fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
duration = round(total_frames / fps, 2) if fps > 0 else 0
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

sample_times = [0.5, 2.0, 4.0, 8.0, duration / 2.0, max(1.0, duration - 2.0)]
frame_paths = []
for t_sec in sample_times:
    f_idx = min(total_frames - 1, max(0, int(fps * t_sec)))
    cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
    ret, frame = cap.read()
    if ret:
        fname = f"single_{reel_id}_t{int(t_sec*10):03d}.jpg"
        fpath = os.path.join(f_dir, fname)
        cv2.imwrite(fpath, frame)
        frame_paths.append(fpath)
cap.release()

print(f"Duração: {duration}s | Resolução: {width}x{height} | FPS: {fps:.1f}", flush=True)
print(f"Frames salvos: {frame_paths}", flush=True)

# Transcrição Whisper
print("Transcrevendo áudio com Whisper...", flush=True)
cmd_audio = [
    'ffmpeg', '-v', 'error',
    '-i', out_filepath,
    '-f', 's16le', '-acodec', 'pcm_s16le',
    '-ar', '16000', '-ac', '1', '-'
]
res_audio = subprocess.run(cmd_audio, capture_output=True, check=True)
audio_data = np.frombuffer(res_audio.stdout, np.int16).flatten().astype(np.float32) / 32768.0

whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
segments, info = whisper_model.transcribe(audio_data, beam_size=5)

seg_list = []
for s in segments:
    seg_list.append({
        "start": round(s.start, 2),
        "end": round(s.end, 2),
        "text": s.text.strip()
    })
    print(f"[{s.start:5.2f}s -> {s.end:5.2f}s] {s.text.strip()}", flush=True)

full_text = " ".join(s["text"] for s in seg_list)
wpm = round((len(full_text.split()) / duration) * 60, 1) if duration > 0 else 0

print("\n--- RESUMO DAS MÉTRICAS ---", flush=True)
print(f"Idioma detectado: {info.language}", flush=True)
print(f"Total de palavras: {len(full_text.split())}", flush=True)
print(f"WPM (Palavras por minuto): {wpm}", flush=True)
print(f"Transcrição completa:\n{full_text}", flush=True)

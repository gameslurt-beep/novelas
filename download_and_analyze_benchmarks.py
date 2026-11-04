import os
import sys
import json
import time
import subprocess
import cv2
import numpy as np
import yt_dlp
from faster_whisper import WhisperModel

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")

def process_channel(targets, channel_name, out_vdir, out_fdir, whisper_model):
    os.makedirs(out_vdir, exist_ok=True)
    os.makedirs(out_fdir, exist_ok=True)
    
    results = []
    total = len(targets)
    print(f"\n=======================================================", flush=True)
    print(f"🎬 PROCESSANDO CANAL: {channel_name} ({total} Shorts)", flush=True)
    print(f"=======================================================", flush=True)

    for idx, item in enumerate(targets, 1):
        v_id = item["id"]
        v_url = item["url"]
        views = item["views"]
        title = item["title"]
        prefix = f"{channel_name.lower()}_{idx:02d}_{v_id}"
        v_filepath = os.path.join(out_vdir, f"{prefix}.mp4")

        print(f"\n[{idx}/{total}] [{channel_name}] {title[:50]} ({views:,} views)", flush=True)
        print(f"  URL: {v_url}", flush=True)

        # 1. Download with yt_dlp
        if not os.path.exists(v_filepath) or os.path.getsize(v_filepath) < 50000:
            print("  -> Baixando vídeo com yt-dlp...", flush=True)
            ydl_opts = {
                'outtmpl': os.path.join(out_vdir, f"{prefix}.%(ext)s"),
                'quiet': True,
                'no_warnings': True,
                'merge_output_format': 'mp4'
            }
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([v_url])
                print(f"  -> Sucesso: {os.path.getsize(v_filepath):,} bytes", flush=True)
            except Exception as e:
                print(f"  -> Erro no download: {e}", flush=True)
                # Check if downloaded with other extension
                found = [f for f in os.listdir(out_vdir) if f.startswith(prefix)]
                if found:
                    v_filepath = os.path.join(out_vdir, found[0])
                else:
                    continue
        else:
            print(f"  -> Vídeo já existente: {os.path.getsize(v_filepath):,} bytes", flush=True)

        # 2. Extract properties and keyframes
        duration = 0.0
        fps = 30.0
        width = 0
        height = 0
        frame_files = []
        try:
            cap = cv2.VideoCapture(v_filepath)
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = round(total_frames / fps, 2) if fps > 0 else 0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            midpoint = max(1.0, duration / 2.0)
            sample_times = [0.5, 1.5, 3.0, 5.0, midpoint]
            for t_sec in sample_times:
                f_idx = min(total_frames - 1, max(0, int(fps * t_sec)))
                cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
                ret, frame = cap.read()
                if ret:
                    fname = f"{prefix}_t{int(t_sec*10):03d}.jpg"
                    fpath = os.path.join(out_fdir, fname)
                    cv2.imwrite(fpath, frame)
                    frame_files.append(fname)
            cap.release()
            print(f"  -> Duração: {duration}s | Resolução: {width}x{height} | {len(frame_files)} frames extraídos", flush=True)
        except Exception as e:
            print(f"  -> Erro ao extrair frames: {e}", flush=True)

        # 3. Transcribe audio
        transcript = ""
        hook_text = ""
        seg_list = []
        lang = "en"
        try:
            cmd_audio = [
                'ffmpeg', '-v', 'error',
                '-i', v_filepath,
                '-f', 's16le', '-acodec', 'pcm_s16le',
                '-ar', '16000', '-ac', '1', '-'
            ]
            res_audio = subprocess.run(cmd_audio, capture_output=True, check=True)
            audio_data = np.frombuffer(res_audio.stdout, np.int16).flatten().astype(np.float32) / 32768.0

            segments, info = whisper_model.transcribe(audio_data, beam_size=1)
            lang = info.language
            for s in segments:
                seg_list.append({
                    "start": round(s.start, 2),
                    "end": round(s.end, 2),
                    "text": s.text.strip()
                })

            transcript = " ".join(s["text"] for s in seg_list)
            opening = [s["text"] for s in seg_list if s["start"] <= 4.0]
            hook_text = " ".join(opening) if opening else (transcript[:100] if transcript else "")
            print(f"  -> Idioma: {lang.upper()} | Transcrição ({len(transcript.split())} palavras): {transcript[:80]}...", flush=True)
            print(f"  -> Gancho (0-4s): \"{hook_text}\"", flush=True)
        except Exception as e:
            print(f"  -> Erro na transcrição: {e}", flush=True)

        record = {
            "channel": channel_name,
            "rank": idx,
            "id": v_id,
            "title": title,
            "views": views,
            "url": v_url,
            "duration": duration,
            "width": width,
            "height": height,
            "fps": fps,
            "filename": os.path.basename(v_filepath),
            "frames": frame_files,
            "language": lang,
            "word_count": len(transcript.split()),
            "wpm": round((len(transcript.split()) / duration) * 60, 1) if duration > 0 else 0,
            "hook_text": hook_text,
            "transcript": transcript,
            "segments": seg_list
        }
        results.append(record)
        time.sleep(1)

    return results

def main():
    with open("targets_geoff_top15.json", "r", encoding="utf-8") as f:
        geoff_targets = json.load(f)
    with open("targets_happyearth_top15.json", "r", encoding="utf-8") as f:
        happy_targets = json.load(f)

    print("Carregando Whisper base model...", flush=True)
    whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
    print("Whisper pronto.", flush=True)

    base_dir = r"c:\Projetos\teste"
    vdir_geoff = os.path.join(base_dir, "videos_geoff_shorts")
    vdir_happy = os.path.join(base_dir, "videos_happyearth_shorts")
    fdir_all = os.path.join(base_dir, "frames_benchmark_shorts")

    res_geoff = process_channel(geoff_targets, "GeographyByGeoff", vdir_geoff, fdir_all, whisper_model)
    res_happy = process_channel(happy_targets, "HappyEarth", vdir_happy, fdir_all, whisper_model)

    combined = {
        "GeographyByGeoff": res_geoff,
        "HappyEarth": res_happy
    }

    out_file = os.path.join(base_dir, "benchmark_30_shorts_analysis.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)

    print("\n===========================================================", flush=True)
    print(f"✅ CONCLUÍDO! Processados {len(res_geoff)} de Geoff e {len(res_happy)} de Happy Earth.")
    print(f"Salvo em: {out_file}", flush=True)
    print("===========================================================", flush=True)

if __name__ == "__main__":
    main()

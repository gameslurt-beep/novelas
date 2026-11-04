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

def main():
    json_path = "fb_25_reels.json"
    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found.", flush=True)
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        all_reels = json.load(f)

    target_reels = all_reels[:25]
    v_dir = os.path.abspath("videos_descobrindo_mundo")
    f_dir = os.path.abspath("frames_descobrindo_mundo")
    os.makedirs(v_dir, exist_ok=True)
    os.makedirs(f_dir, exist_ok=True)

    print("===========================================================", flush=True)
    print("🚀 INICIANDO DOWNLOAD E ANÁLISE DOS 25 VÍDEOS DO FACEBOOK", flush=True)
    print("Perfil: Descobrindo o Mundo (ID: 61580795965769)", flush=True)
    print(f"Vídeos alvo: {len(target_reels)}", flush=True)
    print(f"Diretório de vídeos: {v_dir}", flush=True)
    print(f"Diretório de frames: {f_dir}", flush=True)
    print("===========================================================\n", flush=True)

    print("Carregando Whisper base model...", flush=True)
    whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
    print("Whisper pronto.\n", flush=True)

    dataset = []

    for idx, url in enumerate(target_reels, 1):
        reel_id = url.rstrip("/").split("/")[-1]
        out_base = f"{idx:02d}_{reel_id}"
        out_filepath = os.path.join(v_dir, f"{out_base}.mp4")

        print(f"\n[{idx}/25] Processando Reel {idx}: {url} (ID: {reel_id})", flush=True)

        meta = {}
        # 1. Download via yt_dlp
        if not os.path.exists(out_filepath) or os.path.getsize(out_filepath) < 50000:
            print(f"  -> Baixando via yt-dlp Python API...", flush=True)
            ydl_opts = {
                'outtmpl': os.path.join(v_dir, f"{out_base}.%(ext)s"),
                'quiet': True,
                'no_warnings': True,
                'merge_output_format': 'mp4'
            }
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    meta = ydl.extract_info(url, download=True)
                print(f"  -> Sucesso no download: {os.path.getsize(out_filepath):,} bytes", flush=True)
            except Exception as e:
                print(f"  -> Erro no download de {url}: {e}", flush=True)
                # Tenta localizar arquivo se foi salvo com outra extensão
                found = [f for f in os.listdir(v_dir) if f.startswith(out_base)]
                if found:
                    out_filepath = os.path.join(v_dir, found[0])
                else:
                    continue
        else:
            print(f"  -> Vídeo já existente: {out_filepath} ({os.path.getsize(out_filepath):,} bytes)", flush=True)
            # Extrair apenas metadados rápidos
            try:
                with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
                    meta = ydl.extract_info(url, download=False)
            except Exception:
                meta = {}

        # 2. Obter propriedades de vídeo e extrair keyframes
        duration = 0.0
        fps = 30.0
        width = 0
        height = 0
        frame_files = []

        try:
            cap = cv2.VideoCapture(out_filepath)
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = round(total_frames / fps, 2) if fps > 0 else 0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            # Extrair frames nos tempos estratégicos: 0.5s, 1.5s, 3.0s, 6.0s e metade do vídeo
            midpoint = max(1.0, duration / 2.0)
            sample_times = [0.5, 1.5, 3.0, 6.0, midpoint]
            for t_sec in sample_times:
                f_idx = min(total_frames - 1, max(0, int(fps * t_sec)))
                cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
                ret, frame = cap.read()
                if ret:
                    fname = f"{out_base}_t{int(t_sec*10):03d}.jpg"
                    fpath = os.path.join(f_dir, fname)
                    cv2.imwrite(fpath, frame)
                    frame_files.append(fname)
            cap.release()
            print(f"  -> Duração: {duration}s | Resolução: {width}x{height} | {len(frame_files)} frames extraídos", flush=True)
        except Exception as e:
            print(f"  -> Erro ao extrair frames: {e}", flush=True)

        # 3. Transcrever áudio via Whisper + FFmpeg
        transcript = ""
        hook_text = ""
        seg_list = []
        try:
            cmd_audio = [
                'ffmpeg', '-v', 'error',
                '-i', out_filepath,
                '-f', 's16le', '-acodec', 'pcm_s16le',
                '-ar', '16000', '-ac', '1', '-'
            ]
            res_audio = subprocess.run(cmd_audio, capture_output=True, check=True)
            audio_data = np.frombuffer(res_audio.stdout, np.int16).flatten().astype(np.float32) / 32768.0

            segments, info = whisper_model.transcribe(audio_data, language="pt", beam_size=1)
            for s in segments:
                seg_list.append({
                    "start": round(s.start, 2),
                    "end": round(s.end, 2),
                    "text": s.text.strip()
                })

            transcript = " ".join(s["text"] for s in seg_list)
            opening = [s["text"] for s in seg_list if s["start"] <= 4.0]
            hook_text = " ".join(opening) if opening else (transcript[:100] if transcript else "")
            print(f"  -> Transcrição ({len(transcript.split())} palavras): {transcript[:90]}...", flush=True)
            print(f"  -> Gancho (0-4s): \"{hook_text}\"", flush=True)
        except Exception as e:
            print(f"  -> Erro na transcrição: {e}", flush=True)

        # 4. Consolidar registro
        record = {
            "index": idx,
            "reel_id": reel_id,
            "url": url,
            "title": meta.get("title", ""),
            "description": meta.get("description", ""),
            "views": meta.get("view_count", 0),
            "duration": duration,
            "width": width,
            "height": height,
            "fps": fps,
            "filename": os.path.basename(out_filepath),
            "frames": frame_files,
            "word_count": len(transcript.split()),
            "wpm": round((len(transcript.split()) / duration) * 60, 1) if duration > 0 else 0,
            "hook_text": hook_text,
            "transcript": transcript,
            "segments": seg_list
        }
        dataset.append(record)
        time.sleep(1)

    with open("fb_25_analysis.json", "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)

    print("\n===========================================================", flush=True)
    print(f"✅ CONCLUÍDO COM SUCESSO! {len(dataset)}/25 vídeos processados.", flush=True)
    print("Arquivo salvo em fb_25_analysis.json", flush=True)
    print("===========================================================", flush=True)

if __name__ == "__main__":
    main()

import os
import sys
import json
import re
import subprocess
import cv2
from faster_whisper import WhisperModel

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")

def clean_spanish(t):
    if not t:
        return ""
    subs = [
        ("Por qu", "¿Por qué"), ("por qu", "por qué"), ("qu", "qué"), ("Qu", "¿Qué"),
        ("quin", "quién"), ("Quin", "¿Quién"), ("cmo", "cómo"), ("Cmo", "¿Cómo"),
        ("dnde", "dónde"), ("Dnde", "¿Dónde"), ("cul", "cuál"), ("Cul", "¿Cuál"),
        ("cunto", "cuánto"), ("Cunto", "¿Cuánto"), ("pap", "papá"), ("Pap", "Papá"),
        ("mam", "mamá"), ("Mam", "Mamá"), ("campen", "campeón"), ("aos", "años"),
        ("ao", "año"), ("nia", "niña"), ("nio", "niño"), ("nios", "niños"),
        ("compaero", "compañero"), ("pequeo", "pequeño"), ("das", "días"), ("da", "día"),
        ("ms", "más"), ("est", "está"), ("Est", "Está"), ("ests", "estás"),
        ("estn", "están"), ("s", "sí"), ("t", "tú"), ("as", "así"),
        ("seor", "señor"), ("Seor", "Señor"), ("lrgate", "lárgate"),
        ("corazn", "corazón"), ("habitacin", "habitación"), ("milln", "millón"),
        ("haba", "había"), ("deca", "decía"), ("tena", "tenía"), ("quera", "quería"),
        ("poda", "podía"), ("saba", "sabía"), ("pas", "pasó"), ("qued", "quedó"),
        ("volvi", "volvió"), ("cay", "cayó"), ("acab", "acabó"), ("gan", "ganó"),
        ("venci", "venció"), ("sali", "salió"), ("muri", "murió"), ("dej", "dejó")
    ]
    for old, new in subs:
        t = t.replace(old, new)
    t = re.sub(r"\s+", " ", t).strip()
    return t

def main():
    targets_file = "videos_1m_targets.json"
    if not os.path.exists(targets_file):
        print(f"Error: {targets_file} not found.")
        return

    with open(targets_file, "r", encoding="utf-8") as f:
        targets = json.load(f)

    print(f"\n=======================================================")
    print(f"🚀 INICIANDO PIPELINE PARA {len(targets)} VÍDEOS (>= 1M VIEWS)")
    print(f"=======================================================")

    out_video_dir = "videos_virais_1m"
    out_frame_dir = "hook_frames_1m"
    os.makedirs(out_video_dir, exist_ok=True)
    os.makedirs(out_frame_dir, exist_ok=True)

    # Load Whisper
    print("Carregando Whisper base...")
    model = WhisperModel("base", device="cpu", compute_type="int8")
    print("Whisper pronto.")

    results = []

    for idx, item in enumerate(targets, 1):
        ch = item["channel"].lstrip("@")
        v_id = item["id"]
        v_url = item["url"]
        views = item["views"]
        v_label = item["view_label"]

        filename = f"{idx:02d}_{ch}_{v_id}.mp4"
        filepath = os.path.join(out_video_dir, filename)

        print(f"\n[{idx}/{len(targets)}] Processando @{ch} - {views:,} views ({v_label})")
        print(f"URL: {v_url}")

        # 1. Download with yt-dlp if not exists
        if not os.path.exists(filepath):
            print(f"Baixando com yt-dlp: {filepath}...")
            cmd = [
                "yt-dlp",
                "--no-playlist",
                "--quiet",
                "--no-warnings",
                "-o", filepath,
                v_url
            ]
            try:
                subprocess.run(cmd, check=True, timeout=120)
                print("Download concluído com sucesso.")
            except Exception as e:
                print(f"Erro no download: {e}")
                continue
        else:
            print(f"Arquivo já existe: {filepath}")

        # 2. Video properties and frame extraction
        cap = cv2.VideoCapture(filepath)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = round(total_frames / fps, 2) if fps > 0 else 0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Extract frames at 0.5s, 1.5s, 2.8s
        frame_files = []
        for t_sec in [0.5, 1.5, 2.8]:
            f_idx = int(fps * t_sec)
            cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
            ret, frame = cap.read()
            if ret:
                frame_name = f"v{idx:02d}_{ch}_{int(t_sec*10):02d}s.jpg"
                frame_path = os.path.join(out_frame_dir, frame_name)
                cv2.imwrite(frame_path, frame)
                frame_files.append(frame_name)
        cap.release()

        # 3. Transcribe with Whisper
        print("Transcrevendo áudio com Whisper...")
        try:
            segments, info = model.transcribe(filepath, beam_size=5)
            seg_list = list(segments)
            lang = info.language
            full_text = " ".join([s.text.strip() for s in seg_list])
            clean_text = clean_spanish(full_text)

            # Opening snippet (first 3.5s or first sentence)
            opening_segments = [s.text.strip() for s in seg_list if s.start <= 3.8]
            opening_text = " ".join(opening_segments) if opening_segments else (clean_text[:120] if clean_text else "")
            opening_text = clean_spanish(opening_text)
        except Exception as e:
            print(f"Erro na transcrição: {e}")
            lang = "unknown"
            clean_text = ""
            opening_text = ""
            seg_list = []

        print(f"Idioma detectado: {lang.upper()}")
        print(f"Fala de abertura (0-3.5s): {opening_text[:100]}...")

        results.append({
            "index": idx,
            "channel": f"@{ch}",
            "id": v_id,
            "url": v_url,
            "filename": filename,
            "views": views,
            "view_label": v_label,
            "duration": duration,
            "resolution": f"{width}x{height}",
            "fps": fps,
            "language": lang,
            "hook_frames": frame_files,
            "opening_transcript_raw": opening_text,
            "full_transcript_raw": clean_text
        })

    with open("complete_1m_dataset.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Pipeline concluído! {len(results)} vídeos processados e salvos em 'complete_1m_dataset.json'.")

if __name__ == "__main__":
    main()

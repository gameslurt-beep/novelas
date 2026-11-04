import os
import sys
import json
import subprocess
import numpy as np
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
    import re
    return re.sub(r"\s+", " ", t).strip()

def main():
    print("Loading Whisper base model on CPU...")
    model = WhisperModel("base", device="cpu", compute_type="int8")
    print("Model loaded.")

    v_dir = "videos_virais_1m"
    files = sorted([f for f in os.listdir(v_dir) if f.endswith(".mp4")])
    print(f"Found {len(files)} downloaded videos in {v_dir}:")

    with open("videos_1m_targets.json", "r", encoding="utf-8") as f:
        targets = json.load(f)

    results = []

    for idx, fn in enumerate(files, 1):
        fp = os.path.join(v_dir, fn)
        matching_target = [t for t in targets if t["id"] in fn]
        meta = matching_target[0] if matching_target else {}
        ch = meta.get("channel", "")
        views = meta.get("views", 0)
        v_url = meta.get("url", "")
        v_label = meta.get("view_label", "")

        print(f"\n[{idx}/{len(files)}] Transcrevendo: {fn} ({ch} - {views:,} views)...")

        # Decode audio using ffmpeg to raw 16kHz s16le PCM
        cmd = ['ffmpeg', '-v', 'error', '-i', fp, '-f', 's16le', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', '-']
        res = subprocess.run(cmd, capture_output=True, check=True)
        audio_data = np.frombuffer(res.stdout, np.int16).flatten().astype(np.float32) / 32768.0

        segments, info = model.transcribe(audio_data, beam_size=1)
        seg_list = []
        for s in segments:
            seg_list.append({
                "start": round(s.start, 2),
                "end": round(s.end, 2),
                "text": s.text.strip()
            })

        lang = info.language
        full_text = " ".join([s["text"] for s in seg_list])
        clean_text = clean_spanish(full_text)

        # Hook segment (0.0s to 3.8s)
        opening_segs = [s["text"] for s in seg_list if s["start"] <= 3.8]
        opening_text = " ".join(opening_segs) if opening_segs else (clean_text[:120] if clean_text else "")
        opening_text = clean_spanish(opening_text)

        print(f"  -> Idioma: {lang.upper()}")
        print(f"  -> Gancho (0-3.5s): {opening_text}")
        print(f"  -> Total de palavras: {len(clean_text.split())}")

        results.append({
            "index": idx,
            "channel": ch,
            "filename": fn,
            "views": views,
            "view_label": v_label,
            "url": v_url,
            "language": lang,
            "opening_transcript": opening_text,
            "full_transcript": clean_text,
            "segments": seg_list
        })

    with open("complete_1m_transcripts.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n🎉 Sucesso! Todas as 8 transcrições salvas em 'complete_1m_transcripts.json'.")

if __name__ == "__main__":
    main()

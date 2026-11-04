import subprocess
import os
import json

base_dir = r"c:\Projetos\teste\analise_video_youtube"
input_video = os.path.join(base_dir, "video_completo.mp4")
output_clean = os.path.join(base_dir, "video_limpo_sem_rastros.mp4")

# Script to completely strip all metadata, container tags, and reconstruct container cleanly
# -map_metadata -1: removes all global and stream metadata
# -map_chapters -1: removes all chapter markers
# -fflags +bitexact -flags:v +bitexact -flags:a +bitexact: removes encoder signatures, muxing timestamps
# -c:v copy -c:a copy: keeps exact stream quality without loss, or re-encode if needed
print("Executando limpeza profunda de metadados e assinaturas...")

cmd_clean = [
    "ffmpeg", "-y",
    "-i", input_video,
    "-map_metadata", "-1",
    "-map_chapters", "-1",
    "-fflags", "+bitexact",
    "-flags:v", "+bitexact",
    "-flags:a", "+bitexact",
    "-c:v", "copy",
    "-c:a", "copy",
    output_clean
]

res = subprocess.run(cmd_clean, capture_output=True, text=True)
print("FFmpeg return code:", res.returncode)

# Check metadata of cleaned file
cmd_probe = [
    "ffprobe", "-v", "error",
    "-show_format", "-show_streams",
    "-of", "json",
    output_clean
]
probe_res = subprocess.run(cmd_probe, capture_output=True, text=True, encoding="utf-8")
info = json.loads(probe_res.stdout)

print("\n--- METADADOS DO ARQUIVO LIMPO ---")
print("Format tags:", info.get("format", {}).get("tags", {}))
for s in info.get("streams", []):
    print(f"Stream {s.get('index')} ({s.get('codec_type')}): tags={s.get('tags', {})}")

print(f"\nArquivo limpo gerado com sucesso: {output_clean} ({os.path.getsize(output_clean):,} bytes)")

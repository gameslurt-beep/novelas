import os
import subprocess
import json

base_dir = r"c:\Projetos\teste\analise_video_youtube"
os.makedirs(base_dir, exist_ok=True)

url = "https://www.youtube.com/shorts/QUlMRny0ou0"
out_template = os.path.join(base_dir, "original_QUlMRny0ou0.%(ext)s")

print(f"Baixando {url}...")
cmd = [
    "yt-dlp",
    "--no-playlist",
    "-f", "bestvideo+bestaudio/best",
    "--merge-output-format", "mp4",
    "-o", out_template,
    url
]

res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
print("Returncode:", res.returncode)
print("Stdout:", res.stdout[-400:])
if res.stderr:
    print("Stderr:", res.stderr[-400:])

files = os.listdir(base_dir)
print("\nArquivos na pasta:", files)
for f in files:
    fp = os.path.join(base_dir, f)
    print(f"  {f}: {os.path.getsize(fp):,} bytes")

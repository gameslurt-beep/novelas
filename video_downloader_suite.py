#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
🎬 UNIVERSAL VIDEO DOWNLOADER, SCRAPER & ANALYZER (TikTok | YouTube | Facebook)
================================================================================
Ferramenta completa e unificada para:
1. Baixar vídeos individuais ou em lote do TikTok, YouTube (Shorts/Vídeos) e Facebook (Reels/Watch).
2. Raspar perfis e canais inteiros:
   - TikTok: perfis completos e vídeos populares via Playwright + yt-dlp.
   - YouTube: canais completos e aba Shorts ordenados por visualizações.
   - Facebook: páginas e aba Reels (com bypass automático de popups de login).
3. Limpar metadados e assinaturas de plataforma (FFmpeg bitexact + H.264/AAC).
4. Extrair keyframes estratégicos (OpenCV) e transcrever áudio com timestamps e WPM (Faster-Whisper via FFmpeg pipe).

Uso Rápido (CLI):
  python video_downloader_suite.py download <URL> [--clean] [--transcribe] [--frames]
  python video_downloader_suite.py profile <URL_PERFIL_OU_CANAL> [--limit 25] [--download] [--transcribe]
  python video_downloader_suite.py clean <CAMINHO_VIDEO_MP4>
  python video_downloader_suite.py menu  (Abre o menu interativo)
================================================================================
"""

import os
import sys
import re
import json
import time
import argparse
import subprocess
from pathlib import Path

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import yt_dlp

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    from faster_whisper import WhisperModel
    HAS_WHISPER = True
except ImportError:
    HAS_WHISPER = False

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


# ==============================================================================
# 1. DETECÇÃO DE PLATAFORMA E UTILITÁRIOS
# ==============================================================================

def detect_platform(url: str) -> str:
    u = url.lower()
    if "tiktok.com" in u:
        return "tiktok"
    elif "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    elif "facebook.com" in u or "fb.watch" in u or "fb.com" in u:
        return "facebook"
    return "generic"


def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", name).strip()


# ==============================================================================
# 2. LIMPEZA PROFUNDA DE METADADOS E RASTROS (SANITIZAÇÃO FFMPEG)
# ==============================================================================

def clean_video_metadata(input_path: str, output_path: str = None, reencode_h264: bool = True) -> str:
    """
    Remove todos os metadados, capítulos e assinaturas de container (ex: isomav01 do Facebook/TikTok)
    e opcionalmente recodifica para H.264 High Profile (CRF 18) + AAC 48kHz limpo.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Arquivo não encontrado: {input_path}")

    if not output_path:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_limpo.mp4"

    print(f"🧹 Limpando rastros e metadados de: {os.path.basename(input_path)}...")

    if reencode_h264:
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", input_path,
            "-map_metadata", "-1",
            "-map_chapters", "-1",
            "-fflags", "+bitexact",
            "-flags:v", "+bitexact",
            "-flags:a", "+bitexact",
            "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart",
            output_path
        ]
    else:
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", input_path,
            "-map_metadata", "-1",
            "-map_chapters", "-1",
            "-fflags", "+bitexact",
            "-flags:v", "+bitexact",
            "-flags:a", "+bitexact",
            "-c:v", "copy",
            "-c:a", "copy",
            output_path
        ]

    subprocess.run(cmd, check=True)
    print(f"✅ Vídeo limpo salvo em: {output_path} ({os.path.getsize(output_path):,} bytes)")
    return output_path


# ==============================================================================
# 3. EXTRAÇÃO DE FRAMES (OPENCV) E TRANSCRIÇÃO DE ÁUDIO (WHISPER + FFMPEG PIPE)
# ==============================================================================

def extract_keyframes(video_path: str, frames_dir: str, prefix: str = "frame") -> dict:
    """Extrai propriedades de vídeo e salva keyframes nos momentos de gancho e retenção."""
    if not HAS_CV2:
        print("⚠️ OpenCV (cv2) não instalado. Pulando extração de frames.")
        return {}

    os.makedirs(frames_dir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = round(total_frames / fps, 2) if fps > 0 else 0.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    midpoint = max(1.0, duration / 2.0)
    sample_times = sorted(list(set([0.5, 1.5, 3.0, 5.0, round(midpoint, 1)])))
    saved_frames = []

    for t_sec in sample_times:
        if t_sec >= duration and duration > 0:
            continue
        f_idx = min(total_frames - 1, max(0, int(fps * t_sec)))
        cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
        ret, frame = cap.read()
        if ret:
            fname = f"{prefix}_t{int(t_sec * 10):03d}.jpg"
            fpath = os.path.join(frames_dir, fname)
            cv2.imwrite(fpath, frame)
            saved_frames.append(fpath)

    cap.release()
    return {
        "duration": duration,
        "fps": round(fps, 2),
        "width": width,
        "height": height,
        "frames": saved_frames
    }


def transcribe_video_whisper(video_path: str, whisper_model=None, model_size: str = "base") -> dict:
    """
    Transcreve qualquer vídeo decodificando o áudio via FFmpeg direto para memória (PCM 16kHz float32),
    evitando bugs de PyAV/containers e calculando WPM + Hook (primeiros 5s).
    """
    if not HAS_WHISPER:
        print("⚠️ faster-whisper não instalado. Pulando transcrição.")
        return {}

    if whisper_model is None:
        print(f"🎙️ Carregando modelo Faster-Whisper ({model_size})...")
        whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8")

    cmd_audio = [
        "ffmpeg", "-v", "error",
        "-i", video_path,
        "-f", "s16le", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1", "-"
    ]
    res_audio = subprocess.run(cmd_audio, capture_output=True, check=True)
    audio_data = np.frombuffer(res_audio.stdout, np.int16).flatten().astype(np.float32) / 32768.0

    segments, info = whisper_model.transcribe(audio_data, beam_size=5)
    seg_list = []
    for s in segments:
        seg_list.append({
            "start": round(s.start, 2),
            "end": round(s.end, 2),
            "text": s.text.strip()
        })

    full_text = " ".join(s["text"] for s in seg_list)
    hook_5s = " ".join(s["text"] for s in seg_list if s["start"] <= 5.0)
    duration = seg_list[-1]["end"] if seg_list else 0.0
    words = len(full_text.split())
    wpm = round((words / duration) * 60, 1) if duration > 0 else 0.0

    return {
        "language": info.language,
        "word_count": words,
        "wpm": wpm,
        "hook_5s": hook_5s,
        "full_text": full_text,
        "segments": seg_list
    }


# ==============================================================================
# 4. DOWNLOADER UNIVERSAL (TIKTOK, YOUTUBE, FACEBOOK)
# ==============================================================================

def download_single_video(
    url: str,
    output_dir: str = "downloads_videos",
    custom_prefix: str = "",
    do_clean: bool = False,
    do_frames: bool = False,
    do_transcribe: bool = False,
    whisper_model=None
) -> dict:
    """Baixa um vídeo de qualquer plataforma (TikTok, YouTube, Facebook) com metadados completos."""
    os.makedirs(output_dir, exist_ok=True)
    platform = detect_platform(url)

    print(f"\n⬇️ [{platform.upper()}] Baixando vídeo: {url}")

    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": False,
        "outtmpl": os.path.join(output_dir, f"{custom_prefix}%(id)s.%(ext)s") if custom_prefix else os.path.join(output_dir, "%(id)s.%(ext)s"),
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        video_id = info.get("id", "video")
        expected_file = os.path.join(output_dir, f"{custom_prefix}{video_id}.mp4")
        if not os.path.exists(expected_file):
            # Procura arquivo recém-criado com o ID
            matches = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if video_id in f]
            expected_file = matches[0] if matches else expected_file

    result = {
        "platform": platform,
        "id": video_id,
        "url": url,
        "title": info.get("title", ""),
        "description": info.get("description", ""),
        "uploader": info.get("uploader") or info.get("channel") or "",
        "uploader_id": info.get("uploader_id") or "",
        "views": info.get("view_count") or 0,
        "likes": info.get("like_count") or 0,
        "comments": info.get("comment_count") or 0,
        "upload_date": info.get("upload_date") or "",
        "filepath": expected_file,
    }

    print(f"✅ Download concluído: {expected_file} ({os.path.getsize(expected_file):,} bytes)")
    print(f"📊 Views: {result['views']:,} | Likes: {result['likes']:,} | Uploader: {result['uploader']}")

    if do_clean:
        result["clean_filepath"] = clean_video_metadata(expected_file)

    if do_frames:
        frames_dir = os.path.join(output_dir, "frames")
        result["video_props"] = extract_keyframes(expected_file, frames_dir, prefix=f"{custom_prefix}{video_id}")
        print(f"🖼️ Keyframes extraídos: {len(result['video_props'].get('frames', []))} imagens")

    if do_transcribe:
        print("🎙️ Transcrevendo áudio...")
        result["transcription"] = transcribe_video_whisper(expected_file, whisper_model=whisper_model)
        print(f"📝 Transcrição ({result['transcription'].get('wpm', 0)} WPM): {result['transcription'].get('full_text', '')[:120]}...")

    return result


# ==============================================================================
# 5. SCRAPERS DE PERFIS E CANAIS (FACEBOOK REELS, TIKTOK, YOUTUBE SHORTS)
# ==============================================================================

def scrape_facebook_reels_profile(profile_url: str, max_videos: int = 25) -> list:
    """
    Coleta links de Reels de uma página ou perfil do Facebook via Playwright,
    fechando automaticamente o modal de login ('div[aria-label="Fechar"]') para liberar o scroll.
    """
    if not HAS_PLAYWRIGHT:
        raise RuntimeError("Playwright não está instalado. Rode: pip install playwright && python -m playwright install chromium")

    target_url = profile_url
    if "sk=reels_tab" not in target_url and "/reel/" not in target_url:
        sep = "&" if "?" in target_url else "?"
        target_url = f"{target_url.rstrip('/')}/{sep}sk=reels_tab"

    print(f"🔍 [Facebook Scraper] Coletando até {max_videos} Reels de: {target_url}")
    reels = []
    seen = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
            locale="pt-BR"
        )
        page = context.new_page()
        page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        for step in range(30):
            # Fecha popup de login do Facebook se aparecer
            try:
                fechar = page.locator('div[aria-label="Fechar"], div[aria-label="Close"]')
                if fechar.count() > 0:
                    fechar.first.click()
                    time.sleep(1)
            except Exception:
                pass

            links = page.evaluate("() => Array.from(document.querySelectorAll('a')).map(a => a.href)")
            for l in links:
                m = re.search(r'/reel/(\d+)', l)
                if m:
                    clean_link = f"https://www.facebook.com/reel/{m.group(1)}"
                    if clean_link not in seen:
                        seen.add(clean_link)
                        reels.append({"id": m.group(1), "url": clean_link, "views": 0, "title": f"FB Reel {m.group(1)}"})

            print(f"  -> Scroll {step + 1}: {len(reels)} Reels encontrados...")
            if len(reels) >= max_videos:
                break

            page.mouse.wheel(0, 3000)
            time.sleep(2)

        browser.close()

    return reels[:max_videos]


def scrape_youtube_channel_shorts(channel_url: str, max_videos: int = 25, sort_by_popular: bool = True) -> list:
    """
    Lista os vídeos/Shorts de um canal do YouTube e ordena pelos mais vistos (Top Viral).
    """
    clean_url = channel_url.strip().rstrip("/")
    if not clean_url.startswith("http"):
        clean_url = f"https://www.youtube.com/@{clean_url.lstrip('@')}"
    if not any(tab in clean_url for tab in ["/shorts", "/videos"]):
        clean_url += "/shorts"

    print(f"🔍 [YouTube Scraper] Extraindo Shorts de: {clean_url}")
    ydl_opts = {
        "extract_flat": True,
        "quiet": True,
        "no_warnings": True,
        "playlistend": max(max_videos * 4, 60),
    }

    entries = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(clean_url, download=False)
        raw_entries = info.get("entries", []) if info else []
        for e in raw_entries:
            if not e or not e.get("id"):
                continue
            v_id = e["id"]
            v_url = e.get("url") or f"https://www.youtube.com/shorts/{v_id}"
            if not v_url.startswith("http"):
                v_url = f"https://www.youtube.com/shorts/{v_id}"
            entries.append({
                "id": v_id,
                "url": v_url,
                "title": e.get("title") or f"Short {v_id}",
                "views": e.get("view_count") or 0
            })

    if sort_by_popular:
        entries.sort(key=lambda x: x["views"], reverse=True)

    print(f"✅ Total de vídeos listados no canal: {len(entries)} (Retornando Top {min(max_videos, len(entries))})")
    return entries[:max_videos]


def scrape_tiktok_profile_videos(profile_url: str, max_videos: int = 25, sort_by_popular: bool = True) -> list:
    """
    Lista vídeos de um perfil do TikTok via yt-dlp (ou Playwright fallback) e ordena pelos mais populares.
    """
    clean_url = profile_url.strip()
    if not clean_url.startswith("http"):
        clean_url = f"https://www.tiktok.com/@{clean_url.lstrip('@')}"

    print(f"🔍 [TikTok Scraper] Extraindo vídeos do perfil: {clean_url}")
    entries = []

    try:
        ydl_opts = {
            "extract_flat": True,
            "quiet": True,
            "no_warnings": True,
            "playlistend": max(max_videos * 3, 50),
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)
            raw_entries = info.get("entries", []) if info else []
            for e in raw_entries:
                if not e or not e.get("id"):
                    continue
                v_id = e["id"]
                v_url = e.get("url") or e.get("webpage_url") or f"{clean_url}/video/{v_id}"
                entries.append({
                    "id": v_id,
                    "url": v_url,
                    "title": e.get("title") or f"TikTok {v_id}",
                    "views": e.get("view_count") or 0
                })
    except Exception as e:
        print(f"⚠️ yt-dlp flat extraction falhou ({e}), tentando Playwright...")

    # Fallback Playwright se yt-dlp retornar vazio
    if not entries and HAS_PLAYWRIGHT:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            )
            page = browser.new_page()
            page.goto(clean_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3500)
            for _ in range(10):
                page.mouse.wheel(0, 2000)
                page.wait_for_timeout(1500)
            links = page.evaluate("() => Array.from(document.querySelectorAll('a')).map(a => a.href)")
            seen = set()
            for l in links:
                m = re.search(r'/video/(\d+)', l)
                if m and m.group(1) not in seen:
                    seen.add(m.group(1))
                    entries.append({
                        "id": m.group(1),
                        "url": l,
                        "title": f"TikTok {m.group(1)}",
                        "views": 0
                    })
            browser.close()

    if sort_by_popular:
        entries.sort(key=lambda x: x["views"], reverse=True)

    print(f"✅ Total de vídeos encontrados no TikTok: {len(entries)} (Retornando {min(max_videos, len(entries))})")
    return entries[:max_videos]


# ==============================================================================
# 6. PIPELINE EM LOTE PARA PERFIS / CANAIS
# ==============================================================================

def process_profile_batch(
    profile_url: str,
    max_videos: int = 15,
    output_dir: str = "downloads_lote",
    do_download: bool = True,
    do_clean: bool = False,
    do_frames: bool = True,
    do_transcribe: bool = True
) -> list:
    platform = detect_platform(profile_url)
    if platform == "facebook":
        targets = scrape_facebook_reels_profile(profile_url, max_videos=max_videos)
    elif platform == "youtube":
        targets = scrape_youtube_channel_shorts(profile_url, max_videos=max_videos, sort_by_popular=True)
    elif platform == "tiktok":
        targets = scrape_tiktok_profile_videos(profile_url, max_videos=max_videos, sort_by_popular=True)
    else:
        raise ValueError(f"Plataforma não reconhecida para perfil: {profile_url}")

    os.makedirs(output_dir, exist_ok=True)
    targets_json = os.path.join(output_dir, "targets_scraped.json")
    with open(targets_json, "w", encoding="utf-8") as f:
        json.dump(targets, f, indent=2, ensure_ascii=False)
    print(f"📄 Lista de alvos salva em: {targets_json}")

    if not do_download:
        return targets

    whisper_model = None
    if do_transcribe and HAS_WHISPER:
        print("🎙️ Inicializando modelo Whisper (base) para o lote...")
        whisper_model = WhisperModel("base", device="cpu", compute_type="int8")

    results = []
    for idx, item in enumerate(targets, 1):
        print(f"\n--- [{idx}/{len(targets)}] Processando {item['url']} ---")
        try:
            res = download_single_video(
                url=item["url"],
                output_dir=output_dir,
                custom_prefix=f"{idx:02d}_",
                do_clean=do_clean,
                do_frames=do_frames,
                do_transcribe=do_transcribe,
                whisper_model=whisper_model
            )
            results.append(res)
        except Exception as e:
            print(f"❌ Erro no item {idx} ({item['url']}): {e}")

    report_json = os.path.join(output_dir, "batch_analysis_report.json")
    with open(report_json, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n🎉 Lote finalizado! Relatório completo salvo em: {report_json}")
    return results


# ==============================================================================
# 7. MENU INTERATIVO & CLI
# ==============================================================================

def interactive_menu():
    while True:
        print("\n" + "=" * 65)
        print("🎬 SUITE DE DOWNLOAD & ENGENHARIA REVERSA (TIKTOK | YOUTUBE | FB)")
        print("=" * 65)
        print("1. Baixar 1 Vídeo (TikTok / YouTube / Facebook Reel)")
        print("2. Baixar & Limpar Rastros/Metadados de 1 Vídeo (Pronto p/ Edição)")
        print("3. Baixar + Extrair Frames + Transcrever 1 Vídeo (Raio-X Completo)")
        print("4. Baixar Lote de um Perfil/Canal (TikTok, YouTube Shorts ou FB Reels)")
        print("5. Limpar Metadados/Rastros de um arquivo MP4 local")
        print("0. Sair")
        choice = input("\nEscolha uma opção: ").strip()

        if choice == "0":
            break
        elif choice in ["1", "2", "3"]:
            url = input("Cole a URL do vídeo: ").strip()
            out_dir = input("Pasta de destino [Enter = downloads_videos]: ").strip() or "downloads_videos"
            download_single_video(
                url=url,
                output_dir=out_dir,
                do_clean=(choice == "2" or choice == "3"),
                do_frames=(choice == "3"),
                do_transcribe=(choice == "3")
            )
        elif choice == "4":
            url = input("Cole a URL do Perfil/Canal (TikTok, YouTube ou Facebook): ").strip()
            limit = int(input("Quantos vídeos baixar? [Enter = 15]: ").strip() or "15")
            out_dir = input("Pasta de destino [Enter = downloads_lote]: ").strip() or "downloads_lote"
            trans = input("Transcrever áudios com Whisper? (s/n) [Enter = s]: ").strip().lower() != "n"
            process_profile_batch(
                profile_url=url,
                max_videos=limit,
                output_dir=out_dir,
                do_download=True,
                do_clean=False,
                do_frames=True,
                do_transcribe=trans
            )
        elif choice == "5":
            fpath = input("Caminho do arquivo MP4 local: ").strip().strip('"')
            clean_video_metadata(fpath)


def main():
    parser = argparse.ArgumentParser(description="Universal Video Downloader & Reverse Engineering Suite (TikTok, YouTube, Facebook)")
    subparsers = parser.add_subparsers(dest="command")

    # Comando: download
    p_dl = subparsers.add_parser("download", help="Baixar um único vídeo")
    p_dl.add_argument("url", help="URL do vídeo (TikTok, YouTube, Facebook)")
    p_dl.add_argument("-o", "--output", default="downloads_videos", help="Pasta de saída")
    p_dl.add_argument("--clean", action="store_true", help="Gerar cópia sem metadados/rastros")
    p_dl.add_argument("--frames", action="store_true", help="Extrair keyframes com OpenCV")
    p_dl.add_argument("--transcribe", action="store_true", help="Transcrever áudio com Faster-Whisper")

    # Comando: profile
    p_prof = subparsers.add_parser("profile", help="Raspar e baixar vídeos de um perfil/canal")
    p_prof.add_argument("url", help="URL do perfil/canal (TikTok, YouTube, Facebook)")
    p_prof.add_argument("-n", "--limit", type=int, default=15, help="Quantidade máxima de vídeos")
    p_prof.add_argument("-o", "--output", default="downloads_lote", help="Pasta de saída")
    p_prof.add_argument("--no-download", action="store_true", help="Apenas listar URLs no JSON sem baixar")
    p_prof.add_argument("--clean", action="store_true", help="Limpar metadados de cada vídeo baixado")
    p_prof.add_argument("--frames", action="store_true", help="Extrair keyframes de cada vídeo")
    p_prof.add_argument("--transcribe", action="store_true", help="Transcrever todos os vídeos com Whisper")

    # Comando: clean
    p_clean = subparsers.add_parser("clean", help="Limpar metadados e assinaturas de um MP4 local")
    p_clean.add_argument("filepath", help="Caminho do arquivo MP4")
    p_clean.add_argument("-o", "--output", default=None, help="Caminho do MP4 limpo de saída")

    # Comando: menu
    subparsers.add_parser("menu", help="Abrir menu interativo")

    args = parser.parse_args()

    if args.command == "download":
        download_single_video(
            url=args.url,
            output_dir=args.output,
            do_clean=args.clean,
            do_frames=args.frames,
            do_transcribe=args.transcribe
        )
    elif args.command == "profile":
        process_profile_batch(
            profile_url=args.url,
            max_videos=args.limit,
            output_dir=args.output,
            do_download=not args.no_download,
            do_clean=args.clean,
            do_frames=args.frames,
            do_transcribe=args.transcribe
        )
    elif args.command == "clean":
        clean_video_metadata(args.filepath, args.output)
    else:
        interactive_menu()


if __name__ == "__main__":
    main()

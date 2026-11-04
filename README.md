# 🎬 Novelas & Viral Video Reverse Engineering Suite (TikTok, YouTube & Facebook)

Suite completa em Python para **download de vídeos**, **raspagem de perfis/canais**, **limpeza de metadados/rastros de plataforma**, **extração de keyframes** e **transcrição com IA (Faster-Whisper)** no **TikTok**, **YouTube (Shorts/Vídeos)** e **Facebook (Reels/Watch)**.

---

## 🚀 Principais Scripts

### 1. `video_downloader_suite.py` (Script Unificado — TikTok, YouTube & Facebook)
O script mestre que reúne todas as ferramentas de download e análise:
- **Download Universal (`yt-dlp`):** Baixa vídeos individuais ou lotes inteiros do TikTok, YouTube Shorts e Facebook Reels em MP4 de alta qualidade.
- **Scraper de Perfis/Canais:**
  - **Facebook Reels:** Coleta todos os Reels de qualquer página/perfil com bypass automático do popup de login (`div[aria-label="Fechar"]`).
  - **YouTube Shorts:** Lista todos os Shorts de um canal e ordena automaticamente pelos mais vistos (Top Virais).
  - **TikTok:** Raspa a grade de vídeos de perfis do TikTok (via `yt-dlp` + fallback Playwright).
- **Sanitização e Limpeza de Rastros (`--clean`):** Remove metadados, capítulos e assinaturas DASH/AV1 (`-map_metadata -1 -fflags +bitexact`) recodificando em H.264 + AAC 48kHz limpo.
- **Extração de Keyframes (`--frames`):** Extrai quadros estratégicos (`0.5s`, `1.5s`, `3.0s`, `5.0s`, metade do vídeo) via OpenCV.
- **Transcrição Turbo (`--transcribe`):** Decodifica áudio via pipe FFmpeg direto para memória (`PCM 16kHz float32`) e transcreve com `Faster-Whisper`, calculando **WPM (palavras por minuto)** e isolando o **Gancho (primeiros 5s)**.

#### Exemplos de Uso:
```bash
# Menu Interativo Completo
python video_downloader_suite.py

# Baixar 1 vídeo (TikTok, YouTube ou Facebook) já limpo, com frames e transcrição
python video_downloader_suite.py download "https://www.facebook.com/reel/1794865671634029" --clean --frames --transcribe

# Baixar os Top 15 vídeos de um perfil/canal (TikTok, YouTube ou Facebook)
python video_downloader_suite.py profile "https://www.youtube.com/@GeographyByGeoff" -n 15 --frames --transcribe

# Limpar rastros e metadados de um vídeo MP4 local
python video_downloader_suite.py clean "video_original.mp4" -o "video_limpo.mp4"
```

---

### 2. Outros Módulos Especializados no Repositório
- **`hub.py`**: Central interativa para pesquisa de tendências, transcrição rápida do YouTube, comentários e cruzamento com Reddit.
- **`tiktok_extractor.py` & `tiktok_profile_scraper.py`**: Extração de metadados, comentários e perfis do TikTok.
- **`scrape_fb_playwright.py` & `download_and_analyze_25_fb.py`**: Raspagem dedicada de Reels do Facebook com Playwright e análise em lote.
- **`download_and_analyze_benchmarks.py`**: Pipeline de download e comparação de Top Shorts de canais do YouTube.
- **`analyze_single_reel.py`**: Raio-X forense de um único Reel/Short (frames + transcrição timestamped + WPM).
- **`clean_video_metadata.py`**: Utilitário direto para remoção de metadados e assinaturas de vídeo com FFmpeg.
- **`trend_scanner_universal.py` & `trend_scanner_youtube.py`**: Scanners de vídeos breakout e tendências virais.

---

## 📦 Instalação

```bash
git clone https://github.com/gameslurt-beep/novelas.git
cd novelas
pip install -r requirements.txt
python -m playwright install chromium
```
*(Requer `ffmpeg` instalado no sistema / PATH para limpeza de metadados e transcrição de áudio).*

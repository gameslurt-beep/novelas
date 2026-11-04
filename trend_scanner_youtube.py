import sys
import re
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from curl_cffi import requests
from statistics import median

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")

def parse_views_to_int(text: str) -> int:
    """Converte strings de contagem de views ('62 mil visualizações', '1,2 mi', '850') em int."""
    if not text:
        return 0
    t = text.lower()
    match = re.search(r'([\d.,]+)\s*(milhões|milhão|mil|mi|k|m|b)?', t)
    if not match:
        return 0
    num_str = match.group(1).replace(".", "").replace(",", ".")
    unit = match.group(2) or ""
    try:
        val = float(num_str)
        if unit in ["milhões", "milhão", "mi", "m"]:
            return int(val * 1_000_000)
        elif unit in ["mil", "k"]:
            return int(val * 1_000)
        elif unit in ["b", "bi"]:
            return int(val * 1_000_000_000)
        else:
            return int(val)
    except:
        return 0

def parse_subs_to_int(text: str) -> int:
    """Extrai número de inscritos evitando colisão entre 'mil' e 'mi'."""
    if not text:
        return 0
    t = text.lower()
    m = re.search(r'([\d.,]+)\s*(milhões|milhão|mil|mi|k|m|b)?\s*inscrito', t)
    if not m:
        m = re.search(r'([\d.,]+)\s*(milhões|milhão|mil|mi|k|m|b)\b', t)
    if not m:
        return 0
    num_str = m.group(1).replace(".", "").replace(",", ".")
    unit = m.group(2) or ""
    try:
        val = float(num_str)
        if unit in ["milhões", "milhão", "mi", "m"]:
            return int(val * 1_000_000)
        elif unit in ["mil", "k"]:
            return int(val * 1_000)
        else:
            return int(val)
    except:
        return 0

def is_recent_published(pub_text: str) -> bool:
    """Garante que o vídeo foi postado nos últimos dias (horas, minutos ou até 7 dias)."""
    if not pub_text:
        return True
    t = pub_text.lower()
    # Se tiver ano ou mês, é antigo
    if "ano" in t or "anos" in t or "mês" in t or "mes" in t or "meses" in t:
        return False
    # Aceita horas, minutos, segundos, hoje, ontem, ou dias recentes (até 7)
    if any(k in t for k in ["minuto", "hora", "hoje", "ontem"]):
        return True
    m = re.search(r'(\d+)\s*dia', t)
    if m:
        days = int(m.group(1))
        return days <= 7
    return True

class YouTubeTrendScanner:
    def __init__(self, max_workers: int = 12):
        self.session = requests.Session(impersonate="chrome124")
        self.max_workers = max_workers
        self.headers = {
            "Content-Type": "application/json",
            "X-YouTube-Client-Name": "1",
            "X-YouTube-Client-Version": "2.20240410.01.00",
            "Origin": "https://www.youtube.com",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }

    def search_recent_shorts(self, query: str, period: str = "week") -> list[dict]:
        """
        Busca Shorts recentes.
        period: 'today' (últimas 24h) ou 'week' (últimos 7 dias).
        """
        url = "https://www.youtube.com/youtubei/v1/search"
        # CAISBAgCEAE%3D = Uploads de hoje | CAISBAgDEAE%3D = Uploads desta semana
        params_val = "CAISBAgCEAE%3D" if period == "today" else "CAISBAgDEAE%3D"

        payload = {
            "context": {
                "client": {
                    "clientName": "WEB",
                    "clientVersion": "2.20240410.01.00",
                    "hl": "pt-BR",
                    "gl": "BR"
                }
            },
            "query": query,
            "params": params_val
        }

        try:
            r = self.session.post(url, json=payload, headers=self.headers, timeout=12)
            if r.status_code != 200:
                return []
            
            data = r.json()
            sections = data.get("contents", {}).get("twoColumnSearchResultsRenderer", {}).get("primaryContents", {}).get("sectionListRenderer", {}).get("contents", [])
            
            videos = []
            for s in sections:
                contents = s.get("itemSectionRenderer", {}).get("contents", [])
                for c in contents:
                    vr = c.get("videoRenderer")
                    if vr:
                        vid = vr.get("videoId")
                        title = vr.get("title", {}).get("runs", [{}])[0].get("text", "")
                        channel_runs = vr.get("ownerText", {}).get("runs", [{}])
                        channel_name = channel_runs[0].get("text", "") if channel_runs else ""
                        channel_id = channel_runs[0].get("navigationEndpoint", {}).get("browseEndpoint", {}).get("browseId", "") if channel_runs else ""
                        
                        view_text = vr.get("viewCountText", {}).get("simpleText", "")
                        if not view_text:
                            view_text = vr.get("shortViewCountText", {}).get("simpleText", "")
                        published = vr.get("publishedTimeText", {}).get("simpleText", "")
                        
                        # Extrai duração
                        overlays = vr.get("thumbnailOverlays", [])
                        duration_str = ""
                        for o in overlays:
                            tsr = o.get("thumbnailOverlayTimeStatusRenderer", {})
                            if tsr:
                                duration_str = tsr.get("text", {}).get("simpleText") or tsr.get("style", "")
                                
                        # Filtro de Shorts (<= 60s ou presença da tag #shorts)
                        is_short = False
                        if "short" in duration_str.lower() or "shorts" in title.lower() or "shorts" in query.lower():
                            is_short = True
                        elif ":" in duration_str:
                            parts = duration_str.split(":")
                            if len(parts) == 2 and int(parts[0]) <= 1:
                                is_short = True
                                
                        # Filtro temporal estrito
                        if not is_recent_published(published):
                            continue

                        if vid and channel_id and is_short:
                            videos.append({
                                "video_id": vid,
                                "title": title,
                                "channel_name": channel_name,
                                "channel_id": channel_id,
                                "views_raw": view_text,
                                "views": parse_views_to_int(view_text),
                                "published": published,
                                "duration": duration_str,
                                "url": f"https://www.youtube.com/shorts/{vid}"
                            })
                            
                    # Prateleiras automáticas de shorts do YouTube
                    shelf = c.get("reelShelfRenderer")
                    if shelf:
                        for item in shelf.get("items", []):
                            rir = item.get("reelItemRenderer")
                            if rir:
                                vid = rir.get("videoId")
                                headline = rir.get("headline", {}).get("simpleText", "")
                                v_text = rir.get("viewCountText", {}).get("simpleText", "")
                                ch_nav = rir.get("navigationEndpoint", {}).get("browseEndpoint", {})
                                ch_id = ch_nav.get("browseId", "")
                                videos.append({
                                    "video_id": vid,
                                    "title": headline,
                                    "channel_name": "Criador de Shorts",
                                    "channel_id": ch_id,
                                    "views_raw": v_text,
                                    "views": parse_views_to_int(v_text),
                                    "published": "recente",
                                    "duration": "SHORTS",
                                    "url": f"https://www.youtube.com/shorts/{vid}"
                                })
            return videos
        except Exception as e:
            print(f"⚠️ Erro ao buscar '{query}': {e}")
            return []

    def get_channel_analysis(self, channel_id: str) -> dict:
        """Puxa dados do canal (inscritos) e calcula a média/mediana exata dos últimos Shorts postados."""
        if not channel_id:
            return None
            
        url = "https://www.youtube.com/youtubei/v1/browse"
        payload = {
            "context": {
                "client": {
                    "clientName": "WEB",
                    "clientVersion": "2.20240410.01.00",
                    "hl": "pt-BR",
                    "gl": "BR"
                }
            },
            "browseId": channel_id,
            "params": "EgZzaG9ydHPyBgUKA5oBAA%3D%3D"  # Aba Shorts
        }

        try:
            r = self.session.post(url, json=payload, headers=self.headers, timeout=10)
            if r.status_code != 200:
                return None
            
            data = r.json()
            
            # 1. Extração confiável de inscritos
            header = data.get("header", {}).get("pageHeaderRenderer") or data.get("header", {}).get("c4TabbedHeaderRenderer") or {}
            sub_text = ""
            content_rows = header.get("content", {}).get("pageHeaderViewModel", {}).get("metadata", {}).get("contentMetadataViewModel", {}).get("metadataRows", [])
            for row in content_rows:
                for part in row.get("metadataParts", []):
                    t = part.get("text", {}).get("content", "")
                    if "inscrito" in t.lower() or "sub" in t.lower():
                        sub_text = t
                        break
            if not sub_text:
                sub_text = header.get("subscriberCountText", {}).get("simpleText", "")
            
            subscribers = parse_subs_to_int(sub_text)

            # 2. Extração dos últimos Shorts usando OverlayMetadata
            tabs = data.get("contents", {}).get("twoColumnBrowseResultsRenderer", {}).get("tabs", [])
            shorts_views = []
            for t in tabs:
                tr = t.get("tabRenderer", {})
                if tr.get("selected"):
                    grid = tr.get("content", {}).get("richGridRenderer", {}).get("contents", [])
                    for item in grid:
                        content = item.get("richItemRenderer", {}).get("content", {})
                        slv = content.get("shortsLockupViewModel")
                        if slv:
                            # Campo limpo de visualizações no OverlayMetadata
                            sec_text = slv.get("overlayMetadata", {}).get("secondaryText", {}).get("content", "")
                            v_int = parse_views_to_int(sec_text)
                            if v_int > 0:
                                shorts_views.append(v_int)
                        else:
                            rir = content.get("reelItemRenderer")
                            if rir:
                                v_text = rir.get("viewCountText", {}).get("simpleText", "")
                                v_int = parse_views_to_int(v_text)
                                if v_int > 0:
                                    shorts_views.append(v_int)
                    break
            
            # Base histórica do canal (mediana dos vídeos anteriores)
            history_sample = shorts_views[1:25] if len(shorts_views) > 3 else shorts_views
            channel_median = median(history_sample) if history_sample else (shorts_views[0] if shorts_views else 0)
            
            return {
                "channel_id": channel_id,
                "subscribers": subscribers,
                "subscribers_raw": sub_text or "Oculto",
                "recent_shorts_count": len(shorts_views),
                "median_views": int(channel_median),
                "shorts_views_sample": shorts_views[:10]
            }
        except Exception:
            return None

    def scan_for_trends(
        self,
        queries: list[str],
        period: str = "week",
        min_views: int = 1_000,
        min_subscribers: int = 100,
        max_subscribers: int = 300_000,
        min_multiplier: float = 2.0
    ) -> list[dict]:
        """Varre múltiplos termos recentes, avalia canais em paralelo e calcula outliers de crescimento."""
        print(f"🚀 [Varredor YouTube Shorts] Iniciando varredura rápida (Filtro: {period})...")
        start_time = time.time()
        
        # 1. Coleta concorrente dos vídeos
        raw_videos = []
        with ThreadPoolExecutor(max_workers=min(len(queries), 8)) as executor:
            future_to_query = {executor.submit(self.search_recent_shorts, q, period): q for q in queries}
            for future in as_completed(future_to_query):
                q = future_to_query[future]
                vids = future.result()
                print(f"   ↳ Termo '{q}': {len(vids)} Shorts recentes coletados.")
                raw_videos.extend(vids)

        # Remove duplicados
        unique_videos = {}
        for v in raw_videos:
            if v["video_id"] not in unique_videos and v["channel_id"]:
                unique_videos[v["video_id"]] = v
                
        print(f"📊 Total de {len(unique_videos)} Shorts recentes únicos para análise.")
        
        # 2. Coleta de histórico dos canais em alta concorrência
        unique_channel_ids = list({v["channel_id"] for v in unique_videos.values()})
        print(f"🔍 Analisando {len(unique_channel_ids)} canais em paralelo (Inscritos & Mediana)...")
        
        channel_data_map = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_ch = {executor.submit(self.get_channel_analysis, ch_id): ch_id for ch_id in unique_channel_ids}
            for future in as_completed(future_to_ch):
                ch_id = future_to_ch[future]
                res = future.result()
                if res:
                    channel_data_map[ch_id] = res

        # 3. Detecção de Outliers e Filtragem de Canais em Explosão
        breakout_trends = []
        for v in unique_videos.values():
            ch_info = channel_data_map.get(v["channel_id"])
            if not ch_info:
                continue
                
            subs = ch_info["subscribers"]
            med_views = ch_info["median_views"]
            vid_views = v["views"]
            
            # Filtro da faixa de inscritos (focar em criadores pequenos/médios em ascensão)
            if subs > 0 and (subs < min_subscribers or subs > max_subscribers):
                continue
                
            if vid_views < min_views:
                continue

            # Cálculo de baseline e multiplicador
            # Se a mediana histórica for muito baixa (ex: 300 views), usamos no mínimo 500 para evitar falsos positivos
            baseline = max(med_views, 500)
            multiplier = round(vid_views / baseline, 2)
            
            # Se o vídeo recente bateu a taxa de multiplicador desejada
            if multiplier >= min_multiplier:
                breakout_trends.append({
                    "title": v["title"],
                    "channel_name": v["channel_name"],
                    "channel_id": v["channel_id"],
                    "url": v["url"],
                    "views": vid_views,
                    "views_raw": v["views_raw"],
                    "published": v["published"],
                    "duration": v["duration"],
                    "subscribers": subs,
                    "subscribers_raw": ch_info["subscribers_raw"],
                    "channel_median_views": med_views,
                    "multiplier": multiplier,
                    "virality_index": round((vid_views * multiplier) / (max(subs, 1000)), 2)
                })

        # Ordenar por multiplicador (maior surto de crescimento relativo)
        breakout_trends.sort(key=lambda x: (x["multiplier"], x["views"]), reverse=True)
        
        elapsed = round(time.time() - start_time, 2)
        print(f"\n⚡ Varredura concluída em {elapsed}s! Encontrados {len(breakout_trends)} criadores/Shorts em ascensão.")
        return breakout_trends

if __name__ == "__main__":
    scanner = YouTubeTrendScanner(max_workers=12)
    
    # Nichos com alto volume de novas tendências e canais dark/storytelling
    search_terms = [
        "#shorts curiosidades",
        "#shorts historias",
        "#shorts fatos",
        "#shorts quiz",
        "#shorts misterio",
        "#shortsbrasil",
        "#shorts motivacional",
        "#shorts dark"
    ]
    
    # Rastrear o que explodiu nos últimos 7 dias
    results = scanner.scan_for_trends(
        queries=search_terms,
        period="week",              # Últimos 7 dias (ou "today" para últimas 24h)
        min_views=1_500,            # Mínimo de 1.500 visualizações
        min_subscribers=200,        # Pelo menos 200 inscritos
        max_subscribers=300_000,    # Até 300 mil inscritos (elimina gigantes consolidados)
        min_multiplier=2.0          # Pelo menos 2x acima da média habitual do canal
    )
    
    print("\n" + "="*85)
    print("🔥 TOP SHORTS & CANAIS EM ASCENSÃO IDENTIFICADOS (ÚLTIMOS 7 DIAS)")
    print("="*85)
    for i, r in enumerate(results[:15], 1):
        print(f"\n#{i} | Canal: {r['channel_name']} [Inscritos: {r['subscribers_raw']}]")
        print(f"     Título: {r['title']}")
        print(f"     Visualizações: {r['views_raw']} | Publicado: {r['published']}")
        print(f"     Média do Canal: ~{r['channel_median_views']:,} views | 💥 EXPLOSÃO: {r['multiplier']}x acima da média")
        print(f"     Link: {r['url']}")
    
    # Salvar resultados em JSON
    with open("youtube_breakout_trends.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n📁 Resultados completos salvos em 'youtube_breakout_trends.json'")

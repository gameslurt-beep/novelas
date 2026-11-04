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
    """Garante que o vídeo foi postado nos últimos dias."""
    if not pub_text:
        return True
    t = pub_text.lower()
    if any(k in t for k in ["ano", "anos", "mês", "mes", "meses"]):
        return False
    if any(k in t for k in ["minuto", "hora", "hoje", "ontem"]):
        return True
    m = re.search(r'(\d+)\s*dia', t)
    if m:
        return int(m.group(1)) <= 7
    return True

def classify_niche(title: str) -> str:
    """Classifica automaticamente o nicho do vídeo para o painel geral."""
    t = title.lower()
    if any(k in t for k in ["gol", "futebol", "vasco", "flamengo", "corinthians", "palmeiras", "grêmio", "messi", "ronaldo", "neymar", "campeonato", "copa"]):
        return "⚽ Futebol & Esportes"
    elif any(k in t for k in ["ia", "ai", "inteligência artificial", "chatgpt", "tecnologia", "celular", "iphone", "pc", "software", "truque"]):
        return "🤖 Tecnologia & IA"
    elif any(k in t for k in ["meme", "humor", "engraçado", "comédia", "piada", "tente não rir", "rir", "vizinho", "pegadinha"]):
        return "😂 Humor & Memes"
    elif any(k in t for k in ["jogo", "gameplay", "roblox", "minecraft", "fortnite", "gta", "free fire", "granny"]):
        return "🎮 Games"
    elif any(k in t for k in ["música", "musica", "rap", "trap", "funk", "cantor", "show", "clipe"]):
        return "🎵 Música"
    elif any(k in t for k in ["notícia", "lula", "bolsonaro", "urgente", "polícia", "brasil", "investigado", "crime"]):
        return "📰 Notícias & Política"
    elif any(k in t for k in ["receita", "comida", "cozinha", "delícia", "prato", "doce", "almoço"]):
        return "🍳 Gastronomia"
    elif any(k in t for k in ["saúde", "médico", "treino", "academia", "dieta", "remédio", "vacina"]):
        return "💪 Saúde & Fitness"
    elif any(k in t for k in ["curiosidade", "você sabia", "fatos", "mistério", "ciência", "história"]):
        return "🧠 Conhecimento & Curiosidades"
    elif any(k in t for k in ["novela", "drama", "dorama", "episódio", "esposa", "marido", "vingança", "bilionário", "herdeira"]):
        return "🎭 Dramas & Ficção"
    else:
        return "🌐 Geral & Outros"

class UniversalTrendScanner:
    def __init__(self, max_workers: int = 15):
        self.session = requests.Session(impersonate="chrome124")
        self.max_workers = max_workers
        self.headers = {
            "Content-Type": "application/json",
            "X-YouTube-Client-Name": "1",
            "X-YouTube-Client-Version": "2.20240410.01.00",
            "Origin": "https://www.youtube.com",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }

    def fetch_neutral_search_feed(self, query: str = "#shortsbrasil", max_pages: int = 4) -> list[dict]:
        """Varre busca neutra com paginação profunda via InnerTube."""
        url = "https://www.youtube.com/youtubei/v1/search"
        payload = {
            "context": {"client": {"clientName": "WEB", "clientVersion": "2.20240410.01.00", "hl": "pt-BR", "gl": "BR"}},
            "query": query,
            "params": "CAISBAgDEAE%3D"  # Uploads desta semana
        }

        videos = []
        continuation_token = None

        for page in range(max_pages):
            if continuation_token:
                payload = {
                    "context": {"client": {"clientName": "WEB", "clientVersion": "2.20240410.01.00", "hl": "pt-BR", "gl": "BR"}},
                    "continuation": continuation_token
                }

            try:
                r = self.session.post(url, json=payload, headers=self.headers, timeout=12)
                if r.status_code != 200:
                    break
                data = r.json()
            except Exception:
                break

            sections = []
            if page == 0:
                sections = data.get("contents", {}).get("twoColumnSearchResultsRenderer", {}).get("primaryContents", {}).get("sectionListRenderer", {}).get("contents", [])
            else:
                commands = data.get("onResponseReceivedCommands", [])
                for cmd in commands:
                    append_action = cmd.get("appendContinuationItemsAction", {})
                    sections.extend(append_action.get("continuationItems", []))

            continuation_token = None
            for s in sections:
                # 1. Vídeos normais
                contents = s.get("itemSectionRenderer", {}).get("contents", [])
                for c in contents:
                    vr = c.get("videoRenderer")
                    if vr:
                        vid = vr.get("videoId")
                        title = vr.get("title", {}).get("runs", [{}])[0].get("text", "")
                        ch_runs = vr.get("ownerText", {}).get("runs", [{}])
                        ch_name = ch_runs[0].get("text", "") if ch_runs else ""
                        ch_id = ch_runs[0].get("navigationEndpoint", {}).get("browseEndpoint", {}).get("browseId", "") if ch_runs else ""
                        v_text = vr.get("viewCountText", {}).get("simpleText", "") or vr.get("shortViewCountText", {}).get("simpleText", "")
                        published = vr.get("publishedTimeText", {}).get("simpleText", "")

                        overlays = vr.get("thumbnailOverlays", [])
                        duration_str = ""
                        for o in overlays:
                            tsr = o.get("thumbnailOverlayTimeStatusRenderer", {})
                            if tsr:
                                duration_str = tsr.get("text", {}).get("simpleText") or tsr.get("style", "")

                        is_short = False
                        if "short" in duration_str.lower() or "shorts" in title.lower() or "shorts" in query.lower():
                            is_short = True
                        elif ":" in duration_str:
                            parts = duration_str.split(":")
                            if len(parts) == 2 and int(parts[0]) <= 1:
                                is_short = True

                        if vid and ch_id and is_short and is_recent_published(published):
                            videos.append({
                                "video_id": vid,
                                "title": title,
                                "channel_name": ch_name,
                                "channel_id": ch_id,
                                "views_raw": v_text,
                                "views": parse_views_to_int(v_text),
                                "published": published,
                                "duration": duration_str,
                                "niche": classify_niche(title),
                                "url": f"https://www.youtube.com/shorts/{vid}"
                            })

                # 2. Prateleiras Shorts
                shelf = s.get("reelShelfRenderer")
                if shelf:
                    for item in shelf.get("items", []):
                        rir = item.get("reelItemRenderer")
                        if rir:
                            vid = rir.get("videoId")
                            headline = rir.get("headline", {}).get("simpleText", "")
                            v_text = rir.get("viewCountText", {}).get("simpleText", "")
                            ch_id = rir.get("navigationEndpoint", {}).get("browseEndpoint", {}).get("browseId", "")
                            if vid and ch_id:
                                videos.append({
                                    "video_id": vid,
                                    "title": headline,
                                    "channel_name": "Criador de Shorts",
                                    "channel_id": ch_id,
                                    "views_raw": v_text,
                                    "views": parse_views_to_int(v_text),
                                    "published": "recente",
                                    "duration": "SHORTS",
                                    "niche": classify_niche(headline),
                                    "url": f"https://www.youtube.com/shorts/{vid}"
                                })

                cir = s.get("continuationItemRenderer")
                if cir:
                    continuation_token = cir.get("continuationEndpoint", {}).get("continuationCommand", {}).get("token")

            if not continuation_token:
                break

        return videos

    def get_channel_analysis(self, channel_id: str) -> dict:
        """Puxa dados do canal (inscritos e mediana histórica de visualizações)."""
        if not channel_id:
            return None

        url = "https://www.youtube.com/youtubei/v1/browse"
        payload = {
            "context": {"client": {"clientName": "WEB", "clientVersion": "2.20240410.01.00", "hl": "pt-BR", "gl": "BR"}},
            "browseId": channel_id,
            "params": "EgZzaG9ydHPyBgUKA5oBAA%3D%3D"
        }

        try:
            r = self.session.post(url, json=payload, headers=self.headers, timeout=10)
            if r.status_code != 200:
                return None
            data = r.json()

            # Extração de inscritos
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

            # Histórico de visualizações
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

            history_sample = shorts_views[1:25] if len(shorts_views) > 3 else shorts_views
            channel_median = median(history_sample) if history_sample else (shorts_views[0] if shorts_views else 0)

            return {
                "channel_id": channel_id,
                "subscribers": subscribers,
                "subscribers_raw": sub_text or "Oculto",
                "median_views": int(channel_median)
            }
        except Exception:
            return None

    def scan_global_landscape(
        self,
        queries: list[str] = None,
        pages_per_query: int = 3,
        min_views: int = 2_000,
        min_subscribers: int = 200,
        max_subscribers: int = 300_000,
        min_multiplier: float = 2.5
    ) -> list[dict]:
        """Varre o cenário geral de forma totalmente neutra e ampla."""
        if queries is None:
            # Consultas puramente neutras de descoberta geral
            queries = [
                "#shortsbrasil",
                "#shorts",
                "#viralbrasil",
                "#humorbr",
                "#brasil",
                "#curiosidades"
            ]

        print(f"🌐 [Varredor Panorama Geral] Buscando em {len(queries)} fluxos neutros (paginação de {pages_per_query} páginas cada)...")
        start_time = time.time()

        raw_videos = []
        with ThreadPoolExecutor(max_workers=min(len(queries), 6)) as executor:
            future_to_q = {executor.submit(self.fetch_neutral_search_feed, q, pages_per_query): q for q in queries}
            for future in as_completed(future_to_q):
                q = future_to_q[future]
                vids = future.result()
                print(f"   ↳ Fluxo '{q}': {len(vids)} Shorts coletados.")
                raw_videos.extend(vids)

        # Desduplicar
        unique_videos = {}
        for v in raw_videos:
            if v["video_id"] not in unique_videos and v["channel_id"]:
                unique_videos[v["video_id"]] = v

        print(f"📊 Amostra Global: {len(unique_videos)} Shorts recentes únicos coletados.")

        # Análise concorrente de canais
        unique_channel_ids = list({v["channel_id"] for v in unique_videos.values()})
        print(f"🔍 Analisando perfil e histórico de {len(unique_channel_ids)} canais em paralelo...")

        channel_map = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_ch = {executor.submit(self.get_channel_analysis, ch_id): ch_id for ch_id in unique_channel_ids}
            for future in as_completed(future_to_ch):
                ch_id = future_to_ch[future]
                res = future.result()
                if res:
                    channel_map[ch_id] = res

        # Detecção de anomalias estatísticas
        breakouts = []
        for v in unique_videos.values():
            ch = channel_map.get(v["channel_id"])
            if not ch:
                continue

            subs = ch["subscribers"]
            med_views = ch["median_views"]
            vid_views = v["views"]

            # Filtro da faixa de inscritos
            if subs > 0 and (subs < min_subscribers or subs > max_subscribers):
                continue

            if vid_views < min_views:
                continue

            baseline = max(med_views, 500)
            multiplier = round(vid_views / baseline, 2)

            if multiplier >= min_multiplier:
                breakouts.append({
                    "niche": v["niche"],
                    "title": v["title"],
                    "channel_name": v["channel_name"],
                    "channel_id": v["channel_id"],
                    "url": v["url"],
                    "views": vid_views,
                    "views_raw": v["views_raw"],
                    "published": v["published"],
                    "subscribers": subs,
                    "subscribers_raw": ch["subscribers_raw"],
                    "channel_median_views": med_views,
                    "multiplier": multiplier
                })

        breakouts.sort(key=lambda x: (x["multiplier"], x["views"]), reverse=True)
        elapsed = round(time.time() - start_time, 2)
        print(f"\n⚡ Varredura concluída em {elapsed}s! Encontrados {len(breakouts)} criadores em ascensão em múltiplos nichos.")
        return breakouts

if __name__ == "__main__":
    scanner = UniversalTrendScanner(max_workers=15)
    
    # Executa varredura 100% neutra em todo o cenário
    results = scanner.scan_global_landscape(
        queries=[
            "#shortsbrasil",
            "#shorts",
            "#viralbrasil",
            "#humor",
            "#futebol",
            "#tecnologia",
            "#curiosidades"
        ],
        pages_per_query=3,
        min_views=2_500,
        min_subscribers=200,
        max_subscribers=250_000,
        min_multiplier=2.5
    )

    print("\n" + "="*85)
    print("🌍 PANORAMA GERAL: TOP CRESCIMENTOS RECENTES POR NICHO (SEM CONTAMINAÇÃO)")
    print("="*85)
    
    # Agrupar por nicho
    by_niche = {}
    for r in results:
        by_niche.setdefault(r["niche"], []).append(r)
        
    for n, items in by_niche.items():
        print(f"\n📁 NICHO: {n} ({len(items)} canais em ascensão)")
        for item in items[:3]:
            print(f"   • [{item['channel_name']} | {item['subscribers_raw']}] {item['title'][:55]}")
            print(f"     Views: {item['views_raw']} ({item['published']}) | 💥 Crescimento: {item['multiplier']}x a média")
            print(f"     Link: {item['url']}")

    with open("panorama_geral_breakouts.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Base completa salva em 'panorama_geral_breakouts.json'")

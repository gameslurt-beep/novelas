import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

with open("benchmark_30_shorts_analysis.json", "r", encoding="utf-8") as f:
    data = json.load(f)

geoff = data["GeographyByGeoff"]
happy = data["HappyEarth"]

def stats(channel_data, name):
    durs = [x["duration"] for x in channel_data]
    views = [x["views"] for x in channel_data]
    wpms = [x["wpm"] for x in channel_data]
    words = [x["word_count"] for x in channel_data]
    print(f"=== {name} ({len(channel_data)} Shorts) ===")
    print(f"Views: Total = {sum(views):,} | Média = {sum(views)/len(views):,.0f} | Min = {min(views):,} | Max = {max(views):,}")
    print(f"Duração: Média = {sum(durs)/len(durs):.1f}s | Min = {min(durs):.1f}s | Max = {max(durs):.1f}s")
    print(f"WPM: Média = {sum(wpms)/len(wpms):.1f} | Min = {min(wpms):.1f} | Max = {max(wpms):.1f}")
    print(f"Palavras: Média = {sum(words)/len(words):.1f} | Min = {min(words)} | Max = {max(words)}")
    print()

stats(geoff, "Geography By Geoff")
stats(happy, "Happy Earth")

print("--- TOP 15 GEOGRAPHY BY GEOFF ---")
for x in geoff:
    print(f"[{x['rank']:02d}] {x['views']:,} views | {x['duration']}s | {x['wpm']} WPM")
    print(f"     Title: {x['title']}")
    print(f"     Hook: \"{x['hook_text'][:120]}\"")

print("\n--- TOP 15 HAPPY EARTH ---")
for x in happy:
    print(f"[{x['rank']:02d}] {x['views']:,} views | {x['duration']}s | {x['wpm']} WPM")
    print(f"     Title: {x['title']}")
    print(f"     Hook: \"{x['hook_text'][:120]}\"")

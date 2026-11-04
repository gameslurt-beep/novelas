import sys
import time
import re
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

reels = set()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://www.facebook.com/people/Descobrindo-o-Mundo/61580795965769/?sk=reels_tab')
    page.wait_for_timeout(3000)

    # Click Fechar button
    try:
        fechar = page.locator('div[aria-label="Fechar"]')
        if fechar.count() > 0:
            print("Clicking Fechar button...")
            fechar.first.click()
            time.sleep(2)
        else:
            print("No Fechar button found on initial load.")
    except Exception as e:
        print("Error clicking Fechar:", e)

    for i in range(25):
        # Dismiss any popup if it reappeared
        try:
            fechar = page.locator('div[aria-label="Fechar"]')
            if fechar.count() > 0:
                print(f"Dismissing dialog at loop {i}...")
                fechar.first.click()
                time.sleep(1)
        except Exception:
            pass

        links = page.evaluate('''() => {
            return Array.from(document.querySelectorAll('a')).map(a => a.href);
        }''')
        for l in links:
            m = re.search(r'/reel/(\d+)', l)
            if m:
                reels.add(f'https://www.facebook.com/reel/{m.group(1)}/')
        
        print(f"Scroll {i}: {len(reels)} reels collected", flush=True)
        if len(reels) >= 30:
            break

        page.mouse.wheel(0, 3000)
        time.sleep(2)

    browser.close()

print(f"Total collected: {len(reels)}")
for r in list(reels)[:35]:
    print(r)

with open("fb_25_reels.json", "w", encoding="utf-8") as f:
    import json
    json.dump(list(reels), f, indent=2)

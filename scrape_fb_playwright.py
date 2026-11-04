import time
import re
import sys
import json
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

def get_facebook_videos():
    urls = set()
    url = "https://www.facebook.com/people/Descobrindo-o-Mundo/61580795965769/"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
            locale="pt-BR"
        )
        page = context.new_page()

        # Intercept responses
        def handle_response(response):
            try:
                if "graphql" in response.url or "video" in response.url or "api" in response.url:
                    body = response.text()
                    for r_id in re.findall(r'/reel/(\d+)', body):
                        urls.add(f"https://www.facebook.com/reel/{r_id}")
                    for v_id in re.findall(r'"video_id":"(\d+)"', body):
                        urls.add(f"https://www.facebook.com/reel/{v_id}")
            except Exception:
                pass

        page.on("response", handle_response)

        print(f"Navigating to {url}...", flush=True)
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(5)
        print("Initial load completed.", flush=True)

        for step in range(1, 35):
            # Dismiss any popup/dialog or remove overlays
            try:
                page.evaluate("""() => {
                    // Remove login banner or modal
                    const dialogs = document.querySelectorAll('div[role="dialog"]');
                    dialogs.forEach(d => {
                        const closeBtn = d.querySelector('div[aria-label="Fechar"], div[aria-label="Close"], i');
                        if (closeBtn) closeBtn.click();
                    });
                    // Also enable body overflow if locked
                    document.body.style.overflow = 'auto';
                    document.documentElement.style.overflow = 'auto';
                }""")
            except Exception:
                pass

            # Extract links from DOM
            hrefs = page.evaluate("""() => {
                const links = Array.from(document.querySelectorAll('a'));
                return links.map(a => a.href);
            }""")
            for h in hrefs:
                if "/reel/" in h:
                    m = re.search(r'/reel/(\d+)', h)
                    if m:
                        urls.add(f"https://www.facebook.com/reel/{m.group(1)}")
                elif "/watch/?v=" in h:
                    m = re.search(r'v=(\d+)', h)
                    if m:
                        urls.add(f"https://www.facebook.com/watch/?v={m.group(1)}")
                elif "/videos/" in h:
                    m = re.search(r'/videos/(\d+)', h)
                    if m:
                        urls.add(f"https://www.facebook.com/watch/?v={m.group(1)}")

            print(f"Step {step}: currently found {len(urls)} video URLs...", flush=True)
            if len(urls) >= 30:
                print("Target reached!", flush=True)
                break

            # Scroll down
            page.mouse.wheel(0, 2500)
            time.sleep(2)

        page.screenshot(path="fb_step.png")
        browser.close()

    return list(urls)

if __name__ == "__main__":
    v_urls = get_facebook_videos()
    print(f"\nTotal video URLs found: {len(v_urls)}", flush=True)
    with open("fb_targets_found.json", "w", encoding="utf-8") as f:
        json.dump(v_urls, f, indent=2)

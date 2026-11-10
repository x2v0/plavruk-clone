"""Clone published site + optimize to static (no JS)."""
import asyncio
from playwright.async_api import async_playwright
import pathlib, os, re, urllib.request, io, urllib.parse, shutil, subprocess
from bs4 import BeautifulSoup
from PIL import Image

TARGET = os.environ.get("TARGET_URL", "")
MARKER_TEXT = os.environ.get("MARKER_TEXT", "")
MAX_EDGE = int(os.environ.get("MAX_EDGE", "1200"))
QUALITY = int(os.environ.get("QUALITY", "78"))
MODE = os.environ.get("MODE", "gamma").lower()

def fetch(url, base_url=None):
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("/") and base_url:
        url = urllib.parse.urljoin(base_url, url)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read(), r.geturl()

async def grab_html():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        c = await b.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
        )
        page = await c.new_page()
        print(f"Navigating to {TARGET}...")
        wait_until = "networkidle" if MODE == "js" else "domcontentloaded"
        try:
            await page.goto(TARGET, wait_until=wait_until, timeout=60000)
        except Exception as e:
            print(f"  goto warning: {e}")
        await page.mouse.move(100, 100)
        await page.mouse.move(500, 500)
        await page.wait_for_timeout(3000)
        if MARKER_TEXT:
            try:
                await page.wait_for_selector(f"text={MARKER_TEXT}", timeout=15000)
            except Exception:
                pass
        html = await page.content()
        await b.close()
        return html

def run_wget():
    print("=== Wget mode ===")
    domain = urllib.parse.urlparse(TARGET).netloc
    subprocess.run(["wget", "-p", "-k", "-E", "--no-parent", "-P", "site", TARGET], check=True)
    site_dir = pathlib.Path("site") / domain
    if site_dir.exists():
        for item in site_dir.iterdir():
            shutil.move(str(item), str(pathlib.Path(".") / item.name))
    shutil.rmtree("site", ignore_errors=True)
    pathlib.Path(".nojekyll").touch()
    print("  wget done")

def run_singlefile():
    print("=== SingleFile mode ===")
    subprocess.run(["single-file", TARGET, "index.html"], check=True)
    pathlib.Path(".nojekyll").touch()
    print("  singlefile done")

async def main():
    if MODE == "wget":
        run_wget()
        return
    if MODE == "singlefile":
        run_singlefile()
        return

    print(f"=== Clone {TARGET} (MODE={MODE}) ===")
    html = await grab_html()
    soup = BeautifulSoup(html, "html.parser")

    if MODE == "gamma":
        print("=== Gamma mode: Strip scripts & Gamma badge ===")
        for s in soup.find_all("script"): s.decompose()
        for a in soup.find_all("a", attrs={"data-id": "made-with-gamma-btn"}): a.decompose()
        for m in soup.find_all("meta", attrs={"name": "robots"}): m.decompose()

        st = soup.new_tag("style"); st["id"] = "no-js-visibility"
        st.string = ".animatable-on-load,.animatable-on-load-accent,.animatable-on-load-atom{opacity:1!important;transform:none!important;visibility:visible!important}"
        if soup.head: soup.head.append(st)
    elif MODE == "js":
        print("=== JS mode: keep scripts, wait networkidle ===")
        # Удаляем только трекеры
        trackers = ['google-analytics.com', 'googletagmanager.com', 'mc.yandex.ru', 'top-fwz1.mail.ru']
        for s in soup.find_all("script"):
            if s.get("src") and any(t in s.get("src") for t in trackers):
                s.decompose()
            elif s.string and any(t in s.string for t in ['yaCounter', 'gtag', 'ym(']):
                s.decompose()

    os.makedirs("assets/images", exist_ok=True)
    os.makedirs("assets/css", exist_ok=True)

    print("=== Download CSS ===")
    css_count = 0
    if soup.head:
        for link in soup.find_all("link", rel="stylesheet"):
            href = link.get("href", "")
            if href:
                try:
                    data, _ = fetch(href, TARGET)
                    css_count += 1
                    name = f"style_{css_count:02d}.css"
                    path = f"assets/css/{name}"
                    with open(path, "wb") as f:
                        f.write(data)
                    link["href"] = path
                    print(f"  {name} ({len(data)//1024}KB)")
                except Exception as e:
                    print(f"  fail css {href[:50]}: {e}")

    print("=== Images -> WebP ===")
    cnt = 0
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if not src or "data:" in src: continue
        try:
            data, _ = fetch(src, TARGET)
            im = Image.open(io.BytesIO(data))
            if im.mode in ("RGBA", "LA", "P"):
                bg = Image.new("RGB", im.size, (255, 255, 255))
                im2 = im.convert("RGBA"); bg.paste(im2, mask=im2.split()[-1]); im = bg
            elif im.mode != "RGB":
                im = im.convert("RGB")
            w, h = im.size
            if max(w, h) > MAX_EDGE:
                if w > h: im = im.resize((MAX_EDGE, int(h * MAX_EDGE / w)), Image.LANCZOS)
                else: im = im.resize((int(w * MAX_EDGE / h), MAX_EDGE), Image.LANCZOS)
            cnt += 1
            name = f"img_{cnt:02d}.webp"; path = f"assets/images/{name}"
            im.save(path, "WEBP", quality=QUALITY, method=6)
            img["src"] = path
            if "srcset" in img.attrs: del img["srcset"]
            print(f"  {name} ({len(data)//1024}->{os.path.getsize(path)//1024}KB)")
        except Exception as e:
            print(f"  fail img {src[:50]}: {e}")

    for l in soup.find_all("link"):
        if l.get("rel") == ["preload"] and l.get("href", "").startswith("http"):
            l.decompose()

    pathlib.Path("index.html").write_text(str(soup), encoding="utf-8")
    pathlib.Path(".nojekyll").touch()
    print(f"=== done: index.html {os.path.getsize('index.html')//1024}KB ===")

if __name__ == "__main__":
    asyncio.run(main())

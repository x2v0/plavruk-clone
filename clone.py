"""Clone published site + optimize to static (no JS)."""
import asyncio
from playwright.async_api import async_playwright
import pathlib, os, re, urllib.request, io
from bs4 import BeautifulSoup
from PIL import Image

TARGET = os.environ.get("TARGET_URL", "")
MARKER_TEXT = os.environ.get("MARKER_TEXT", "")
MAX_EDGE = int(os.environ.get("MAX_EDGE", "1200"))
QUALITY = int(os.environ.get("QUALITY", "78"))

async def grab_html():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        c = await b.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
        )
        page = await c.new_page()
        print(f"Navigating to {TARGET}...")
        await page.goto(TARGET, wait_until="domcontentloaded", timeout=60000)
        await page.mouse.move(100, 100)
        await page.mouse.move(500, 500)
        await page.wait_for_timeout(8000)
        if MARKER_TEXT:
            try:
                await page.wait_for_selector(f"text={MARKER_TEXT}", timeout=30000)
            except Exception:
                pass
        html = await page.content()
        await b.close()
        return html

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()

async def main():
    print(f"=== Clone {TARGET} ===")
    html = await grab_html()
    print(f"  {len(html)} bytes")
    soup = BeautifulSoup(html, "html.parser")

    print("=== Strip scripts ===")
    n = 0
    for s in soup.find_all("script"):
        s.decompose(); n += 1
    print(f"  removed {n} scripts")

    print("=== Emergency CSS + bootstrap ===")
    st = soup.new_tag("style"); st["id"] = "no-js-visibility"
    st.string = (
        ".animatable-on-load,.animatable-on-load-accent,"
        ".animatable-on-load-atom,.animatable-on-load-content-child,"
        ".animatable-on-load-as-block,.navbar-view-content,"
        ".navbar-view-backdrop{opacity:1!important;"
        "transform:none!important;visibility:visible!important}"
        ".is-present-mode .animatable-on-load-accent{opacity:1!important;"
        "transform:scale(1)!important}"
    )
    if soup.head: soup.head.append(st)
    body = soup.find("body")
    if body:
        cls = body.get("class", [])
        if isinstance(cls, str): cls = cls.split()
        if "site-animations-bootstrap" not in cls:
            cls.append("site-animations-bootstrap")
        body["class"] = cls

    print("=== Remove noindex ===")
    for m in soup.find_all("meta", attrs={"name": "robots"}): m.decompose()

    print("=== Remove Gamma badge ===")
    removed = 0
    for a in soup.find_all("a", attrs={"data-id": "made-with-gamma-btn"}):
        a.decompose(); removed += 1
    for b in soup.find_all(attrs={"aria-label": "Report this page"}):
        b.decompose(); removed += 1
    for d in soup.find_all(class_="css-2upw6"):
        d.decompose(); removed += 1
    for g in soup.find_all(class_="css-1ayoy1w"):
        if not g.find("a") or not g.find("button"):
            g.decompose(); removed += 1
    for tag in soup.find_all(string=lambda t: t and "Made with" in str(t)):
        parent = tag.find_parent("a") or tag.find_parent("div")
        if parent:
            parent.decompose(); removed += 1
    print(f"  removed {removed} badge elements")

    print("=== Remove external preloads ===")
    for l in soup.find_all("link"):
        h = l.get("href", "")
        if "imgproxy.gamma.app" in h or "assets.gammahosted.com" in h:
            l.decompose()

    os.makedirs("assets/images", exist_ok=True)

    print("=== Images -> WebP ===")
    cnt = 0
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if not src.startswith("http"): continue
        try:
            data = fetch(src)
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
            print(f"  {name}: {len(data)//1024}->{os.path.getsize(path)//1024}KB")
        except Exception as e:
            print(f"  fail {src[:60]}: {e}")

    print("=== Remove external stylesheet links ===")
    for l in soup.find_all("link", rel="stylesheet"):
        h = l.get("href", "")
        if h.startswith("http"):
            l.decompose()

    print("=== Google Fonts CDN ===")
    if soup.head:
        for t in [soup.new_tag("link", rel="preconnect", href="https://fonts.googleapis.com"),
                  soup.new_tag("link", rel="preconnect", href="https://fonts.gstatic.com", crossorigin="")]:
            soup.head.append(t)
        soup.head.append(soup.new_tag("link", rel="stylesheet",
            href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=Inter:wght@400;500;700&display=swap"))

    print("=== Preload hero + lazy ===")
    imgs = soup.find_all("img")
    hero = [i.get("src") for i in imgs[:3] if i.get("src")]
    if soup.head:
        for s in hero:
            soup.head.append(soup.new_tag("link", rel="preload",
                **{"as": "image", "href": s, "fetchpriority": "high"}))
    for i, img in enumerate(imgs):
        if i < 3: img["fetchpriority"] = "high"
        else: img["loading"] = "lazy"
        img["decoding"] = "async"

    pathlib.Path("index.html").write_text(str(soup), encoding="utf-8")
    pathlib.Path(".nojekyll").touch()
    print(f"=== done: index.html {os.path.getsize('index.html')//1024}KB ===")

if __name__ == "__main__":
    asyncio.run(main())

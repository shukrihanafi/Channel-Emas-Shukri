"""Berita emas: pilih berita dari sumber dipercayai, screenshot bahagian atas artikel, tulis caption BM.

Guna:  mode `berita` (hantar ke semua) atau `berita-test` (hantar ke Telegram peribadi sahaja).
Env:   NEWS_URL (pilihan: paksa satu artikel), ANTHROPIC_API_KEY (pilihan: ringkasan BM oleh AI;
       jika tiada, guna tajuk + penerangan asal artikel).
"""
import json, os, re, sys, html
import requests

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
      "Accept-Language": "en-MY,en;q=0.9"}
LISTING = "https://theedgemalaysia.com/flash-categories/Precious%20Metals"
BULAN = ["Januari", "Februari", "Mac", "April", "Mei", "Jun", "Julai", "Ogos", "September", "Oktober", "November", "Disember"]
MODEL = os.getenv("NEWS_MODEL", "claude-haiku-5-5")


RSS_SOURCES = [  # sumber tambahan (RSS); jika gagal dicapai, dilangkau tanpa menjejaskan yang lain
    "https://www.bernama.com/en/rss/news_business.xml",
    "https://www.thestar.com.my/rss/business/business-news",
]
KEYWORDS = re.compile(r"\b(gold|bullion|precious metal|emas)\b", re.I)
MAX_AGE_H = 48


def _parse_dt(s):
    from email.utils import parsedate_to_datetime
    from datetime import datetime, timezone
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        try:
            d = parsedate_to_datetime(s)
        except Exception:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def discover(posted):
    """Kumpul calon dari semua sumber, tapis yang terlalu lama / sudah dihantar, pilih yang paling baharu."""
    from datetime import datetime, timezone
    cands = []  # (tarikh, url)
    try:  # The Edge Malaysia: kategori Precious Metals
        r = requests.get(LISTING, headers=UA, timeout=30)
        r.raise_for_status()
        seen = []
        for m in re.finditer(r'(?:https://theedgemalaysia\.com)?/node/(\d+)', r.text):
            u = f"https://theedgemalaysia.com/node/{m.group(1)}"
            if u not in seen:
                seen.append(u)
        for u in seen[:8]:
            if u in posted:
                continue
            try:
                d = _parse_dt(_meta(requests.get(u, headers=UA, timeout=30).text, "article:published_time"))
            except Exception:
                d = None
            cands.append((d, u))
    except Exception as e:
        print("Sumber The Edge gagal:", str(e)[:100])
    for feed in RSS_SOURCES:  # Bernama, The Star
        try:
            r = requests.get(feed, headers=UA, timeout=30)
            r.raise_for_status()
            for it in re.findall(r"(?is)<item>(.*?)</item>", r.text):
                t = html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", " ".join(re.findall(r"(?is)<(?:title|description)>(.*?)</(?:title|description)>", it))))
                lk = re.search(r"(?is)<link>\s*(?:<!\[CDATA\[)?\s*(https?://[^<\s\]]+)", it)
                pd = re.search(r"(?is)<pubDate>(.*?)</pubDate>", it)
                if lk and KEYWORDS.search(t) and lk.group(1) not in posted:
                    cands.append((_parse_dt(pd.group(1).strip()) if pd else None, lk.group(1)))
        except Exception as e:
            print("Sumber RSS gagal:", feed, str(e)[:100])
    now = datetime.now(timezone.utc)
    fresh = [(d, u) for d, u in cands if d and (now - d).total_seconds() <= MAX_AGE_H * 3600]
    print(f"Calon berita: {len(cands)}, terkini (<{MAX_AGE_H}j): {len(fresh)}")
    if not fresh:
        return None
    return max(fresh)[1]


def _meta(page, prop):
    m = re.search(r'<meta[^>]+(?:property|name)=["\']%s["\'][^>]+content=["\']([^"\']*)["\']' % re.escape(prop), page, re.I) \
        or re.search(r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']%s["\']' % re.escape(prop), page, re.I)
    return html.unescape(m.group(1)).strip() if m else ""


def fetch_article(url):
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    page = r.text
    body = re.sub(r"(?is)<(script|style|nav|header|footer).*?</\1>", " ", page)
    paras = [html.unescape(re.sub(r"<[^>]+>", " ", p)).strip() for p in re.findall(r"(?is)<p[^>]*>(.*?)</p>", body)]
    paras = [re.sub(r"\s+", " ", p) for p in paras if len(p) > 60]
    return {"url": url, "title": _meta(page, "og:title") or "", "desc": _meta(page, "og:description"),
            "date": _meta(page, "article:published_time"), "text": "\n".join(paras)[:12000]}


def summarise(a):
    """Kembalikan (tajuk_bm, ringkasan_bm). Guna AI jika ada kunci; jika tidak, teks asal."""
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return None  # tanpa AI tiada terjemahan BM yang boleh dipercayai
    prompt = (
        "Anda menulis caption berita emas untuk saluran WhatsApp/Telegram pengguna Malaysia.\n"
        "Berdasarkan HANYA artikel di bawah, tulis dalam Bahasa Melayu mudah:\n"
        '1) "tajuk": terjemahan tajuk (ringkas)\n2) "ringkasan": tepat DUA ayat ringkas. Jangan tambah fakta, ramalan atau nasihat pelaburan.\n'
        'Balas JSON sahaja: {"tajuk": "...", "ringkasan": "..."}\n\n'
        f"TAJUK: {a['title']}\nARTIKEL:\n{a['text'] or a['desc']}"
    )
    r = requests.post("https://api.anthropic.com/v1/messages", timeout=90,
                      headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                      json={"model": MODEL, "max_tokens": 600, "messages": [{"role": "user", "content": prompt}]})
    r.raise_for_status()
    txt = r.json()["content"][0]["text"]
    j = json.loads(re.search(r"\{.*\}", txt, re.S).group(0))
    return j["tajuk"].strip(), j["ringkasan"].strip()


def screenshot(url, path):
    """Tangkap bahagian atas artikel (tajuk, penulis, gambar, perenggan pertama)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 900, "height": 1400}, device_scale_factor=1.5, user_agent=UA["User-Agent"])
        pg.goto(url, wait_until="load", timeout=60000)
        pg.wait_for_timeout(5000)
        print("Halaman:", pg.title(), "|", pg.inner_text("body")[:160].replace("\n", " "))
        pg.evaluate("""() => { document.querySelectorAll('[class*=cookie],[id*=cookie],[class*=consent],[class*=advert],[id*=google_ads],iframe')
                       .forEach(e => e.remove()); }""")
        try:
            pg.wait_for_selector("h1", timeout=15000)
            top = max(pg.locator("h1").first.bounding_box(timeout=5000)["y"] - 16, 0)
        except Exception as e:  # tajuk tidak ditemui: tangkap bahagian atas halaman dan simpan untuk semakan
            print("h1 tidak ditemui:", str(e)[:120])
            top = 0
        pg.screenshot(path=path, clip={"x": 0, "y": top, "width": 900, "height": 860})
        b.close()
    return path


def build_caption(a, tajuk, ringkas, dt):
    tarikh = f"{dt.day} {BULAN[dt.month - 1]} {dt.year}"
    return f"Berita emas @ {tarikh}\n\n{tajuk}\n\n{ringkas}\n\nBerita penuh di : {a['url']}"


def run(st, send, dt, out="out"):
    n = st.setdefault("news", {"posted": []})
    url = os.getenv("NEWS_URL", "").strip() or discover(n["posted"])
    if not url:
        print("Tiada berita baharu untuk dihantar.")
        return
    a = fetch_article(url)
    test = getattr(sys.modules.get("__main__"), "CURRENT_MODE", "").endswith("-test")
    res = summarise(a)
    if res is None:
        if not test:
            print("ANTHROPIC_API_KEY tiada: berita tidak dihantar (caption mesti BM).")
            return
        print("Mod ujian tanpa kunci AI: guna teks asal (Inggeris) sebagai contoh sahaja.")
        res = (a["title"], a["desc"])
    tajuk, ringkas = res
    os.makedirs(out, exist_ok=True)
    img = screenshot(url, f"{out}/berita.png")
    send(build_caption(a, tajuk, ringkas, dt), img, "berita", closing=False)
    if not test and url not in n["posted"]:  # mod ujian tidak menanda berita sebagai sudah dihantar
        n["posted"] = (n["posted"] + [url])[-60:]

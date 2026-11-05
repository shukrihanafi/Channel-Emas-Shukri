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


KEYWORDS = re.compile(r"\b(gold|bullion|precious metals?|emas|dinar)\b", re.I)
BERNAMA_PAGES = ["https://www.bernama.com/bm/index.php", "https://www.bernama.com/bm/ekonomi/"]  # Bernama BM
MAX_AGE_H = 48


def _parse_dt(s):
    """Terima ISO (The Edge), RFC822, atau 'dd/mm/yyyy hh:mm AM' (Bernama, waktu Malaysia)."""
    from email.utils import parsedate_to_datetime
    from datetime import datetime, timezone, timedelta
    if not s:
        return None
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})\s*([AP]M)?", s.strip(), re.I)
    if m:
        d_, mo, y, h, mi, ap = m.groups()
        h = int(h) % 12 + (12 if (ap or "").upper() == "PM" else 0) if ap else int(h)
        return datetime(int(y), int(mo), int(d_), h, int(mi), tzinfo=timezone(timedelta(hours=8)))
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        try:
            d = parsedate_to_datetime(s)
        except Exception:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _edge_candidates(posted):
    """The Edge Malaysia (kategori Precious Metals): senarai berita ada dalam JSON __NEXT_DATA__ (nid + created ms)."""
    from datetime import datetime, timezone
    r = requests.get(LISTING, headers=UA, timeout=30)
    r.raise_for_status()
    out = []
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
    if m:
        data = json.loads(m.group(1))
        for it in data.get("props", {}).get("pageProps", {}).get("corporateData", []) or []:
            if it.get("nid") and it.get("created"):
                u = f"https://theedgemalaysia.com/node/{it['nid']}"
                if u not in posted:
                    out.append((datetime.fromtimestamp(it["created"] / 1000, timezone.utc), u))
    if not out:  # sandaran: pautan /node/ biasa
        for n_ in list(dict.fromkeys(re.findall(r"/node/(\d+)", r.text)))[:8]:
            u = f"https://theedgemalaysia.com/node/{n_}"
            if u not in posted:
                try:
                    out.append((_parse_dt(_meta(requests.get(u, headers=UA, timeout=30).text, "article:published_time")), u))
                except Exception:
                    pass
    return out


def _bernama_candidates(posted):
    """Bernama BM: imbas halaman utama + Ekonomi, ambil pautan yang tajuknya berkaitan emas, baca tarikh dari artikel."""
    links = []
    for pgurl in BERNAMA_PAGES:
        try:
            t = requests.get(pgurl, headers=UA, timeout=30).text
        except Exception as e:
            print("Bernama gagal:", pgurl, str(e)[:80])
            continue
        for h, txt in re.findall(r'(?is)<a[^>]+href=["\']([^"\']*news(?:-bm)?\.php\?id=\d+[^"\']*)["\'][^>]*>(.*?)</a>', t):
            txt = html.unescape(re.sub(r"<[^>]+>", " ", txt))
            if KEYWORDS.search(txt):
                links.append(requests.compat.urljoin(pgurl, html.unescape(h)))
    out = []
    for u in list(dict.fromkeys(links))[:10]:
        if u in posted:
            continue
        try:
            out.append((_parse_dt(_meta(requests.get(u, headers=UA, timeout=30).text, "article:published_time")), u))
        except Exception:
            pass
    return out


def discover(posted):
    """Kumpul calon dari semua sumber, tapis yang terlalu lama / sudah dihantar, pilih yang paling baharu."""
    from datetime import datetime, timezone
    cands = []
    for name, fn in (("The Edge", _edge_candidates), ("Bernama BM", _bernama_candidates)):
        try:
            got = fn(posted)
            print(f"Sumber {name}: {len(got)} calon")
            cands += got
        except Exception as e:
            print(f"Sumber {name} gagal:", str(e)[:100])
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
                      json={"model": MODEL, "max_tokens": 1500, "messages": [{"role": "user", "content": prompt}]})
    r.raise_for_status()
    txt = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
    j = json.loads(re.search(r"\{.*\}", txt, re.S).group(0))
    return j["tajuk"].strip(), j["ringkasan"].strip()


def screenshot(url, path, title=""):
    """Tangkap bahagian atas artikel (tajuk, penulis, gambar, perenggan pertama)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 900, "height": 1400}, device_scale_factor=1.5, user_agent=UA["User-Agent"])
        pg.goto(url, wait_until="load", timeout=60000)
        pg.wait_for_timeout(5000)
        print("Halaman:", pg.title(), "|", pg.inner_text("body")[:160].replace("\n", " "))
        pg.evaluate("""() => { document.querySelectorAll('[class*=cookie],[id*=cookie],[class*=consent],[class*=advert],[id*=google_ads],iframe,nav,[class*=sticky],[class*=Sticky]')
                       .forEach(e => e.remove()); }""")
        top = 0
        try:  # cari tajuk artikel mengikut teksnya (h1 tidak boleh dipercayai)
            loc = pg.get_by_text(title[:60], exact=False).first if title else pg.locator("h1").first
            loc.wait_for(state="visible", timeout=15000)
            top = max(loc.bounding_box(timeout=5000)["y"] - 16, 0)
        except Exception as e:
            print("Tajuk tidak ditemui:", str(e)[:120])
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
    img = screenshot(url, f"{out}/berita.png", a["title"])
    send(build_caption(a, tajuk, ringkas, dt), img, "berita", closing=False)
    if not test and url not in n["posted"]:  # mod ujian tidak menanda berita sebagai sudah dihantar
        n["posted"] = (n["posted"] + [url])[-60:]

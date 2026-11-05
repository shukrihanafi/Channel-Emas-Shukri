"""Berita emas: pilih berita dari sumber dipercayai, screenshot bahagian atas artikel, tulis caption BM.

Guna:  mode `berita` (hantar ke semua) atau `berita-test` (hantar ke Telegram peribadi sahaja).
Sumber diputar bergilir (lihat SOURCES), emas sahaja.
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


KEYWORDS = re.compile(r"\b(gold|bullion|precious metals?|emas|dinar|xau)\b", re.I)
# Fokus emas sahaja: buang berita sukan (pingat emas, dll.) dan sebutan "emas" yang bukan berkaitan logam
NEGATIVE = re.compile(r"pingat|medal|olimpik|olympic|sukan|sea games|juara|kejohanan|gold coast|gold cup|golden globe|piala|warga emas|sindiket|scam|ditahan|penipuan|bunuh|samun|rompak", re.I)
# Sumber berita, diputar bergilir (satu sumber setiap hari); sumber tanpa berita emas terkini dilangkau
SOURCES = [
    ("The Edge Malaysia", None),
    ("Bernama", ["https://www.bernama.com/bm/carian.php?terms=harga+emas", "https://www.bernama.com/bm/ekonomi/", "https://www.bernama.com/bm/"]),
    ("Astro Awani", ["https://www.astroawani.com/search?q=harga+emas", "https://www.astroawani.com/search?q=emas", "https://www.astroawani.com/"]),
    ("Sinar Harian", ["https://www.sinarharian.com.my/carian?query=harga+emas", "https://www.sinarharian.com.my/"]),
    ("Kitco", ["https://www.kitco.com/news"]),
    ("Investing.com", ["https://www.investing.com/commodities/gold", "https://www.investing.com/commodities/gold-news"]),  # jika disekat anti-bot, dilangkau automatik
    ("GoldSeek", ["https://goldseek.com/", "https://goldseek.com/gold-headlines"]),
]
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


def _article_date(page):
    """Tarikh siaran artikel: meta, JSON-LD atau <time>."""
    for prop in ("article:published_time", "og:article:published_time", "datePublished", "date", "pubdate"):
        d = _parse_dt(_meta(page, prop))
        if d:
            return d
    m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', page) or re.search(r'<time[^>]+datetime=["\']([^"\']+)["\']', page)
    if m:
        return _parse_dt(m.group(1))
    m = re.search(r"(?is)<h1.{0,1500}?\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.? (\d{1,2}),? (\d{4})", page)  # tarikh dipaparkan selepas tajuk (GoldSeek)
    if m:
        from datetime import datetime, timezone
        mon = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"].index(m.group(1).lower()) + 1
        return datetime(int(m.group(3)), mon, int(m.group(2)), 12, tzinfo=timezone.utc)
    return None


def _generic_candidates(pages, posted):
    """Imbas halaman utama sumber: ambil pautan yang tajuk/URL-nya berkaitan emas, baca tarikh dan tajuk dari artikel."""
    from urllib.parse import urljoin, urlparse
    host = urlparse(pages[0]).netloc.replace("www.", "")
    links = {}
    for pgurl in pages:
        try:
            r = requests.get(pgurl, headers=UA, timeout=30)
            r.raise_for_status()
        except Exception as e:
            print("  halaman gagal:", pgurl, str(e)[:80])
            continue
        for h, txt in re.findall(r'(?is)<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', r.text):
            txt = html.unescape(re.sub(r"<[^>]+>", " ", txt))
            u = urljoin(pgurl, html.unescape(h)).split("#")[0]
            p = urlparse(u)
            if host not in p.netloc or len(p.path) + len(p.query) < 12:
                continue
            if (KEYWORDS.search(txt) or KEYWORDS.search(p.path)) and not NEGATIVE.search(txt + " " + p.path):
                links[u] = 1
    out = []
    # utamakan pautan berbentuk artikel (halaman harga/carta tidak membawa tarikh berita)
    ranked = sorted(links, key=lambda u: not re.search(r"/(article|news|berita|read|story)/|/\d{5,}", urlparse(u).path))
    for u in ranked[:15]:
        if u in posted:
            continue
        try:
            page = requests.get(u, headers=UA, timeout=30).text
        except Exception:
            continue
        title = _meta(page, "og:title") or _meta(page, "twitter:title")
        if not KEYWORDS.search(title) or NEGATIVE.search(title):  # mesti tajuk berkaitan emas sahaja
            continue
        out.append((_article_date(page), u))
    return out


def discover(posted, rot=0):
    """Putar sumber bergilir bermula dari `rot`; hasilkan (indeks, nama, url) bagi berita emas terkini (<48j), yang paling baharu dahulu."""
    from datetime import datetime, timezone
    for i in range(len(SOURCES)):
        idx = (rot + i) % len(SOURCES)
        name, pages = SOURCES[idx]
        try:
            got = _edge_candidates(posted) if pages is None else _generic_candidates(pages, posted)
        except Exception as e:
            print(f"Sumber {name} gagal:", str(e)[:100])
            continue
        now = datetime.now(timezone.utc)
        fresh = sorted(((d, u) for d, u in got if d and 0 <= (now - d).total_seconds() <= MAX_AGE_H * 3600), reverse=True)
        print(f"Sumber {name}: {len(got)} calon, terkini (<{MAX_AGE_H}j): {len(fresh)}")
        for d, u in fresh[:2]:
            yield idx, name, u


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
        head = pg.title() + " | " + pg.inner_text("body")[:200].replace("\n", " ")
        print("Halaman:", head[:200])
        if re.search(r"access denied|just a moment|attention required|are you a robot|captcha|forbidden|unusual activity|verify you are human|px-captcha", head, re.I):
            b.close()
            raise RuntimeError("halaman disekat (anti-bot)")
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
    forced = os.getenv("NEWS_URL", "").strip()
    cands = iter([(-1, "manual", forced)]) if forced else discover(n["posted"], n.get("rot", 0))
    test = getattr(sys.modules.get("__main__"), "CURRENT_MODE", "").endswith("-test")
    if test and not forced:  # ujian: semak semua sumber supaya log melaporkan setiap satu
        cands = iter(list(cands))
    tries = 0
    for idx, name, url in cands:
        if tries >= 5:
            break
        tries += 1
        try:
            a = fetch_article(url)
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
        except Exception as e:  # sumber ini bermasalah (disekat/ralat): cuba calon seterusnya
            print(f"Calon {name} dilangkau: {str(e)[:120]}")
            continue
        print(f"Berita dipilih dari {name}: {url}")
        send(build_caption(a, tajuk, ringkas, dt), img, "berita", closing=False)
        if not test:  # mod ujian tidak menanda berita sebagai sudah dihantar dan tidak memutar sumber
            if url not in n["posted"]:
                n["posted"] = (n["posted"] + [url])[-60:]
            if idx >= 0:
                n["rot"] = (idx + 1) % len(SOURCES)
        return
    print("Tiada berita emas baharu untuk dihantar.")

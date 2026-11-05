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
    ("Kitco", ["https://www.kitco.com/news"]),
    ("Astro Awani", ["https://www.astroawani.com/search?q=harga+emas", "https://www.astroawani.com/search?q=emas", "https://www.astroawani.com/"]),
    ("GoldSeek", ["https://goldseek.com/", "https://goldseek.com/gold-headlines"]),
    ("Sinar Harian", ["https://www.sinarharian.com.my/carian?query=harga+emas", "https://www.sinarharian.com.my/"]),
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
            "date": _meta(page, "article:published_time"), "text": "\n".join(paras)[:12000],
            "image": _meta(page, "og:image"), "site": _meta(page, "og:site_name"), "paras": paras[:4]}


class ApiKeyError(Exception):
    """Kunci API tidak sah / kredit habis / akaun disekat."""


def summarise(a):
    """Kembalikan (tajuk_bm, ringkasan_bm). Guna AI jika ada kunci; jika tidak, teks asal."""
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return None  # tanpa AI tiada terjemahan BM yang boleh dipercayai
    prompt = (
        "Anda menulis kandungan berita emas untuk pengguna Malaysia. Berdasarkan HANYA artikel di bawah, tulis dalam Bahasa Melayu mudah. "
        "Jangan reka fakta atau angka yang tiada dalam artikel. Jangan buat ramalan harga atau nasihat pelaburan.\n\n"
        'Balas JSON sahaja dengan 3 kunci:\n'
        '1) "tajuk": tajuk pendek dan jelas dalam HURUF BESAR (contoh: "HARGA EMAS TERUS MENINGKAT!"), maksimum 8 patah perkataan.\n'
        '2) "ringkasan": ringkasan SELURUH artikel (bukan sekadar perenggan pertama) kepada DUA perenggan sangat pendek dipisahkan baris kosong (guna \\n\\n), '
        'jumlah 30 hingga 60 patah perkataan. Ayat pendek, padat, bahasa harian yang layman mudah faham. '
        'Perenggan 1 = apa yang berlaku (harga naik/turun) dan sebab utama; perenggan 2 = perkara penting lain dalam berita atau apa yang pasaran sedang tunggu. '
        'Terangkan istilah teknikal dengan perkataan harian. Hanya fakta daripada artikel. Tanpa tajuk, tanpa emoji.\n'
        '3) "threads": satu posting Threads 50 hingga 100 patah perkataan. Gaya santai, natural, berkongsi pendapat, BUKAN gaya laporan berita atau artikel akhbar. '
        'Struktur: (a) hook atau persoalan menarik; (b) fakta utama daripada berita; (c) pandangan atau kesan berkaitan simpanan emas; '
        '(d) akhiri dengan satu soalan untuk menggalakkan perbincangan. Elakkan ayat terlalu formal dan terlalu menjual. '
        'Maksimum satu emoji jika benar-benar sesuai; tiada hashtag berlebihan (maksimum satu). Tiada pautan.\n\n'
        f"TAJUK ASAL: {a['title']}\nARTIKEL:\n{a['text'] or a['desc']}"
    )
    r = requests.post("https://api.anthropic.com/v1/messages", timeout=90,
                      headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                      json={"model": MODEL, "max_tokens": 8000, "messages": [{"role": "user", "content": prompt}]})
    if r.status_code in (401, 402, 403, 429) or (r.status_code == 400 and "credit" in r.text.lower()):
        raise ApiKeyError(f"HTTP {r.status_code}: {r.text[:160]}")
    r.raise_for_status()
    jr = r.json()
    txt = "".join(b.get("text", "") for b in jr.get("content", []) if b.get("type") == "text")
    m_ = re.search(r"\{.*\}", txt, re.S)
    if not m_:
        print("AI tidak balas JSON. stop_reason=%s, balasan: %r" % (jr.get("stop_reason"), txt[:300]))
        raise ValueError("balasan AI bukan JSON")
    try:
        j = json.loads(m_.group(0), strict=False)
    except ValueError:
        print("JSON AI rosak: %r" % txt[:300])
        raise
    a["threads"] = (j.get("threads") or "").strip()
    return j["tajuk"].strip().upper(), j["ringkasan"].strip()


def _dl_image(url, referer):
    """Muat turun gambar utama artikel sebagai data-URI (kembalikan "" jika gagal)."""
    import base64
    if not url:
        return ""
    try:
        r = requests.get(url, headers={**UA, "Referer": referer}, timeout=30)
        r.raise_for_status()
        ct = r.headers.get("content-type", "image/jpeg").split(";")[0]
        if not ct.startswith("image/") or len(r.content) < 5000:
            return ""
        return f"data:{ct};base64," + base64.b64encode(r.content).decode()
    except Exception as e:
        print("Gambar utama gagal dimuat turun:", str(e)[:100])
        return ""


def _first_paras(a, limit=520):
    """Perenggan pertama artikel seperti di laman web (tambah perenggan seterusnya hanya jika terlalu pendek)."""
    out = ""
    for p in a.get("paras", []):
        if len(p) < 90 and out == "":  # buang baris pendek (penulis / caption)
            continue
        out = (out + " " + p).strip()
        if len(out) >= 200:
            break
    if not out:
        out = a.get("desc", "")
    if len(out) > limit:
        cut = out[:limit]
        k = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
        out = cut[:k + 1] if k > limit * 0.5 else cut.rsplit(" ", 1)[0] + " ..."
    return out


def screenshot(url, path, title="", a=None, source=""):
    """Bina kad berita bersih (tajuk, gambar utama, perenggan pertama) TANPA iklan laman, lalu tangkap sebagai PNG."""
    from playwright.sync_api import sync_playwright
    a = a or {}
    img = _dl_image(a.get("image", ""), url)
    try:
        d = _parse_dt(a.get("date", ""))
        tarikh = f"{d.day} {BULAN[d.month - 1]} {d.year}" if d else ""
    except Exception:
        tarikh = ""
    esc = html.escape
    fonts = os.path.abspath("fonts")
    doc = f"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{{font-family:P;font-weight:700;src:url('file://{fonts}/Poppins-Bold.ttf')}}
@font-face{{font-family:P;font-weight:400;src:url('file://{fonts}/Poppins-Regular.ttf')}}
*{{box-sizing:border-box}} body{{margin:0;background:#fffdf8;font-family:P,sans-serif;color:#222}}
html,body{{height:100%}} #c{{width:1080px;height:1080px;padding:48px 54px 44px;display:flex;flex-direction:column;overflow:hidden}}
.bar{{width:90px;height:8px;background:#d4a017;border-radius:4px;margin-bottom:22px;flex:none}}
h1{{font-size:46px;line-height:1.22;margin:0 0 14px;font-weight:700;color:#1f1f1f;flex:none;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}}
.by{{font-size:25px;color:#8a8a8a;margin-bottom:20px;flex:none}} .by b{{color:#c8860d;font-weight:700}}
.im{{width:100%;flex:1 1 0;min-height:0;object-fit:cover;border-radius:18px;display:block;margin-bottom:22px}}
p{{font-size:28px;line-height:1.5;margin:0;color:#3a3a3a;flex:none;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden}}
</style></head><body><div id="c"><div class="bar"></div><h1>{esc(a.get('title') or title)}</h1>
<div class="by"><b>{esc(source)}</b>{' · ' + esc(tarikh) if tarikh else ''}</div>
{f'<img class="im" src="{img}">' if img else ''}<p>{esc(_first_paras(a))}</p></div></body></html>"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    hp = os.path.abspath(os.path.join(os.path.dirname(path) or ".", "berita.html"))
    open(hp, "w", encoding="utf-8").write(doc)
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1080, "height": 1080}, device_scale_factor=1)
        pg.goto("file://" + hp, wait_until="load")
        pg.wait_for_timeout(800)
        pg.locator("#c").screenshot(path=path)
        b.close()
    return path


def build_caption(a, tajuk, ringkas, dt, source=""):
    src = f"Sumber: {source}\n\n" if source else ""
    return f"[BERITA EMAS]\n\n{tajuk}\n\n{ringkas}\n\n{src}Berita penuh di :\n{a['url']}"


def run(st, send, dt, out="out", notify=print):
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
                    notify("⚠️ Kunci API Anthropic tiada (ANTHROPIC_API_KEY), berita BM tidak dihantar.")
                    return
                print("Mod ujian tanpa kunci AI: guna teks asal (Inggeris) sebagai contoh sahaja.")
                res = (a["title"], a["desc"])
            tajuk, ringkas = res
            os.makedirs(out, exist_ok=True)
            src_name = a.get("site") or (name if name != "manual" else re.sub(r"^www\.", "", url.split("/")[2]))
            img = screenshot(url, f"{out}/berita.png", a["title"], a, src_name)
        except ApiKeyError as e:  # bukan salah sumber: jangan cuba calon lain, beritahu pemilik
            print(f"Kunci API Anthropic bermasalah: {e}")
            notify("⚠️ Kunci API Anthropic bermasalah, berita BM hari ini tidak dihantar. "
                   "Semak baki kredit / kunci di platform.claude.com/settings/billing. "
                   "Slot lain tidak terjejas.\n" + str(e)[:200])
            return
        except Exception as e:  # sumber ini bermasalah (disekat/ralat): cuba calon seterusnya
            print(f"Calon {name} dilangkau: {str(e)[:120]}")
            continue
        print(f"Berita dipilih dari {name}: {url}")
        send(build_caption(a, tajuk, ringkas, dt, src_name), img, "berita", closing=False)
        if not test:  # mod ujian tidak menanda berita sebagai sudah dihantar dan tidak memutar sumber
            if url not in n["posted"]:
                n["posted"] = (n["posted"] + [url])[-60:]
            if idx >= 0:
                n["rot"] = (idx + 1) % len(SOURCES)
        return
    print("Tiada berita emas baharu untuk dihantar.")

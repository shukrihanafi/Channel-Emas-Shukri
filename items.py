"""Ambil item PG Jewel (API) dan PG Mall Hotday Sale (HTML) untuk post Channel."""
import html, random, re
import requests

UA = {"User-Agent": "Mozilla/5.0 (compatible; PGChannelBot/1.0)", "Accept": "application/json, text/html"}
JEWEL_API = "https://api.pgjewel.my/api"
JEWEL_SITE = "https://www.pgjewel.my/product/product"
JEWEL_RPC = "PG032390"
MALL_RPC = "m.shukri.hanafi@gmail.com"
# Kategori PG Jewel (cincin, rantai, loket, gelang, dll.) - dipusing bergilir
JEWEL_CATS = [1565, 1562, 1568, 1563, 1566, 1561, 1556, 1553, 1559, 1554, 1557, 1552, 1564, 1567]
MALL_URL = "https://pgmall.my/hotsales"
RECENT_MAX = 150


def rm(v, dec=0):
    return f"RM {float(v):,.{dec}f}"


def _pick(cands, recent, rnd):
    fresh = [c for c in cands if str(c["id"]) not in recent]
    return rnd.choice(fresh or cands)


def _remember(st, key):
    r = st.setdefault("recent_items", [])
    r.append(str(key))
    del r[:-RECENT_MAX]


# ---------------- PG Jewel ----------------
def jewel_item(st, rnd=random):
    i = st.get("jewel_cat_idx", 0)
    st["jewel_cat_idx"] = i + 1
    for k in range(len(JEWEL_CATS)):  # cuba kategori lain jika kosong
        cat = JEWEL_CATS[(i + k) % len(JEWEL_CATS)]
        r = requests.get(f"{JEWEL_API}/category/{cat}?limit=32&page=1", headers=UA, timeout=30)
        r.raise_for_status()
        prods = [{"id": p["product_id"]} for p in r.json()["data"]["products"] if int(p.get("quantity") or 0) > 0]
        if prods:
            break
    else:
        raise RuntimeError("Tiada produk PG Jewel dalam stok ditemui")
    pid = _pick(prods, st.get("recent_items", []), rnd)["id"]
    d = requests.get(f"{JEWEL_API}/products/{pid}", headers=UA, timeout=30)
    d.raise_for_status()
    d = d.json()["data"]
    _remember(st, f"J{pid}")
    return jewel_text(d), d.get("image")


def jewel_text(d):
    skus = [s for s in d.get("sku", []) if int(s.get("quantity") or 0) > 0] or d.get("sku", [])
    lo, hi = float(d["min_price"]), float(d["max_price"])
    price = rm(lo) if lo == hi else f"{rm(lo)} - {rm(hi)}"
    lines = ["💎 BARANG KEMAS PG JEWEL", "", f"Produk : {d['name']}", "", f"Harga: {price}"]
    ws = []
    for s in skus:
        m = re.match(r"\s*([\d.]+)\s*g", str(s.get("option_value_name") or ""), re.I)
        if m:
            ws.append(float(m.group(1)))
    if ws:
        fw = lambda x: f"{x:g}g"
        wt = fw(min(ws)) if min(ws) == max(ws) else f"{fw(min(ws))} - {fw(max(ws))}"
        lines = lines[:3] + ["", f"Berat: {wt}"] + lines[3:]
    lines += ["", f"Link: {JEWEL_SITE}/{d['product_id']}?rpc={JEWEL_RPC}", "", "Cantik kan? Klik link di atas atau", "", "WhatsApp saya sekarang di https://shukriee.com/pgjewel"]
    return "\n".join(lines)


# ---------------- PG Mall (Hotday Sale) ----------------
CARD = re.compile(r'<a href="(https://(?:www\.)?pgmall\.my/p/[^"]+)" class="ix-P-card">(.*?)</a>', re.S)


def parse_mall(page):
    items = []
    for link, body in CARD.findall(page):
        name = re.search(r'<p class="ix-P-name">(.*?)</p>', body, re.S)
        price = re.search(r'class="ix-P-price"[^>]*>\s*RM\s*<span[^>]*>\s*([\d,.]+)\s*</span>', body, re.S)
        if not (name and price):
            continue
        old = re.search(r"<strike>\s*RM\s*([\d,.]+)\s*</strike>", body)
        disc = re.search(r'ix-P-discounttag">\s*-\s*(\d+)%', body)
        img = re.search(r'data-src="([^"]+)"', body)
        items.append({
            "id": link.rstrip("/").split("/p/")[-1].replace("/", "-"),
            "link": link.replace("://www.", "://"),
            "name": html.unescape(re.sub(r"\s+", " ", name.group(1))).strip(),
            "price": price.group(1).replace(",", ""),
            "old": old.group(1).replace(",", "") if old else None,
            "disc": disc.group(1) if disc else None,
            "img": img.group(1) if img else None,
        })
    return items


def mall_item(st, rnd=random):
    r = requests.get(MALL_URL, headers=UA, timeout=30)
    r.raise_for_status()
    items = parse_mall(r.text)
    if not items:
        raise RuntimeError("Tiada item Hotday Sale ditemui - struktur PG Mall mungkin berubah")
    it = _pick(items, st.get("recent_items", []), rnd)
    _remember(st, f"M{it['id']}")
    return mall_text(it), it["img"]


def mall_text(it):
    lines = ["🛒 Item PG Mall (Hotday Sale)", "", f"Item: {it['name']}", "", f"Harga: {rm(it['price'], 2)}"]
    if it["old"]:
        lines.append(f"Harga asal: {rm(it['old'], 2)}" + (f" (-{it['disc']}%)" if it["disc"] else ""))
    lines += ["", f"Link: {it['link']}?rpc={MALL_RPC}", "", "Cantik kan? Klik link di atas atau", "", "WhatsApp saya sekarang di https://shukriee.com/pgjewel"]
    return "\n".join(lines)

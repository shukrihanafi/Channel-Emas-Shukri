"""Item Gold Bar / Dinar / Perak daripada publicgold.com.my (senarai produk awam)."""
import html, random, re
import requests

BASE = "https://publicgold.com.my/index.php?route=product/category&vw=list"
UA = {"User-Agent": "Mozilla/5.0 (compatible; PGChannelBot/1.0)"}
CATS = ["bar", "dinar", "silver"]            # putaran kategori
PATHS = {"gold": 1, "silver": 2}             # path=1 Gold, path=2 Silver
SKIP = re.compile(r"promotion|casing|special|pre-?order|wealth card|set\b", re.I)
MAX_PRICE = 150000                            # elak produk terlalu besar (cth 12.5kg)

BLOCK = re.compile(
    r'product_id=(\d+)"[^>]*>\s*<img src="([^"]+)"[^>]*>\s*</a>\s*'
    r'<span class="ItemDescFrameControl">(.*?)</span>\s*'
    r'<span class="itemBillboardListPrice">\s*RM\s*([\d,.]+)', re.S)


def _tidy(name):
    name = re.sub(r"\s+", " ", html.unescape(name)).strip()
    if name.isupper():
        name = name.title()
    name = re.sub(r"(\d)G\b", r"\1g", name)
    name = re.sub(r"\b(Au|Ag)\b", lambda m: m.group(1).capitalize(), name, flags=re.I)
    return name.replace("Ounce", "Ounce")


def kind_of(name):
    n = name.lower()
    if "dinar" in n:
        return "dinar"
    if "silver" in n or "dirham" in n:
        return "silver"
    if "bar" in n:
        return "bar"
    return None


def parse_list(page):
    out = []
    for pid, img, name, price in BLOCK.findall(page):
        name = _tidy(name)
        price = float(price.replace(",", ""))
        k = kind_of(name)
        if not k or SKIP.search(name) or price > MAX_PRICE:
            continue
        out.append({"id": pid, "img": img, "name": name, "price": price, "kind": k})
    return out


def fetch_catalog():
    items, seen = [], set()
    for path in PATHS.values():
        for pg in range(1, 8):
            r = requests.get(f"{BASE}&path={path}&page={pg}", headers=UA, timeout=30)
            r.raise_for_status()
            got = parse_list(r.text)
            raw = BLOCK.findall(r.text)
            if not raw:
                break
            for it in got:
                if it["id"] not in seen:
                    seen.add(it["id"])
                    items.append(it)
    if not items:
        raise ValueError("Tiada produk ditemui - struktur laman mungkin berubah")
    return items


def specs(name):
    """Berat & ketulenan daripada nama produk, cth '5g', '999.9'."""
    w = re.search(r"(\d+(?:\.\d+)?)\s*(kg|g)\b", name, re.I)
    p = re.search(r"\((?:A[ug]\s*)?(\d{3}(?:\.\d)?)\)", name, re.I)
    weight = f"{w.group(1)}{w.group(2).lower()}" if w else None
    return weight, (p.group(1) if p else None)


TITLES = {"bar": "🥇 Gold Bar Public Gold", "dinar": "🪙 Dinar Emas Public Gold", "silver": "🥈 Perak Public Gold"}


def pg_text(it, ts):
    weight, purity = specs(it["name"])
    lines = [TITLES[it["kind"]], "", f"Item: {it['name']}"]
    if weight:
        lines += ["", f"Berat: {weight}"]
    if purity:
        lines += ["", f"Ketulenan: {purity}"]
    lines += ["", f"Harga: RM {it['price']:,.0f}", "", f"Dikemaskini: {ts}"]
    return "\n".join(lines)


def pick(st, catalog):
    """Pilih item seterusnya: putar kategori bar -> dinar -> perak, elak ulang item baru-baru ini."""
    s = st.setdefault("pgitem", {"n": 0, "recent": []})
    for step in range(len(CATS)):
        kind = CATS[(s["n"] + step) % len(CATS)]
        pool = [i for i in catalog if i["kind"] == kind]
        if not pool:
            continue
        fresh = [i for i in pool if i["id"] not in s["recent"]]
        if not fresh:  # semua sudah keluar -> mula pusingan baharu untuk kategori ini
            s["recent"] = [r for r in s["recent"] if r not in {i["id"] for i in pool}]
            fresh = pool
        it = random.choice(fresh)
        s["n"] += step + 1
        s["recent"] = (s["recent"] + [it["id"]])[-40:]
        return it
    raise ValueError("Tiada item sesuai")

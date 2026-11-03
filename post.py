"""Bot Channel Emas - jana post & hantar ke Telegram (mod separa-auto).

Guna:  python post.py <mod>
Mod:   gap | jewel | alert | ilmu | item | item-jewel | item-mall
Env:   TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID   (DRY_RUN=1 -> simpan dalam out/ sahaja)
       ALERT_THRESHOLD (RM, lalai 3)
"""
import json, os, sys
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
import pgfetch, card, items

TZ = ZoneInfo("Asia/Kuala_Lumpur")
STATE = "data/state.json"
OUT = "out"
SITE = "shukriee.com"
BELI_LINK = "https://shukriee.com/beliemas"
BULAN = ["Jan", "Feb", "Mac", "Apr", "Mei", "Jun", "Jul", "Ogos", "Sep", "Okt", "Nov", "Dis"]


def now_my():
    return datetime.now(TZ)


def fmt_dt(dt):
    h = dt.hour % 12 or 12
    return f"{dt.day:02d} {BULAN[dt.month-1]} {dt.year} @ {h}:{dt.minute:02d} {'am' if dt.hour < 12 else 'pm'}"


def dpath(name):
    """data/<name> jika ada, kalau tidak <name> di akar repositori."""
    return f"data/{name}" if os.path.exists(f"data/{name}") or not os.path.exists(name) else name


def load(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except FileNotFoundError:
        return default


def save(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    json.dump(data, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)


# ---------- Telegram ----------
def send(text, image=None, label="post"):
    os.makedirs(OUT, exist_ok=True)
    stamp = now_my().strftime("%Y%m%d-%H%M%S")
    open(f"{OUT}/{stamp}-{label}.txt", "w", encoding="utf-8").write(text)
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if os.getenv("DRY_RUN") or not (token and chat):
        print(f"--- [{label}] (DRY RUN) ---\n{text}\n[imej: {image}]\n")
        return
    base = f"https://api.telegram.org/bot{token}"
    tag = f"📋 Post untuk Channel ({label})\n\n"
    if image:
        with open(image, "rb") as f:
            r = requests.post(f"{base}/sendPhoto", data={"chat_id": chat}, files={"photo": f}, timeout=60)
        r.raise_for_status()
    r = requests.post(f"{base}/sendMessage", data={"chat_id": chat, "text": tag + text}, timeout=60)
    r.raise_for_status()


# ---------- Mod ----------
def trend_text(diff):
    if diff > 0:
        return f"▲ Naik RM{diff:,.0f}"
    if diff < 0:
        return f"▼ Turun RM{abs(diff):,.0f}"
    return "Harga GAP Tidak Berubah"


def update_range(st, price, date_iso):
    g = st["gap"]
    if price < g["low"]["price"]:
        g["low"] = {"price": price, "date": date_iso}
    if price > g["high"]["price"]:
        g["high"] = {"price": price, "date": date_iso}


def d_my(iso):  # 2026-06-30 -> 30 Jun 2026
    y, m, d = iso.split("-")
    return f"{int(d)} {BULAN[int(m)-1]} {y}"


def mode_gap(p, st):
    g, dt = st["gap"], now_my()
    price = p["gap_rm_per_gram"]
    update_range(st, price, dt.strftime("%Y-%m-%d"))
    g.setdefault("history", {})[dt.strftime("%Y-%m-%d")] = price
    seed_history(st)
    prev = g.get("last_post")
    if prev is None:  # guna harga semalam daripada sejarah
        ks = sorted(k for k in g["history"] if k < dt.strftime("%Y-%m-%d"))
        prev = g["history"][ks[-1]] if ks else price
    diff = price - prev
    ts = fmt_dt(dt)
    text = (
        f"Public Gold GAP\n"
        f"RM 100 = {p['gap_gram_per_rm100']} gram\n"
        f"RM {price:,.0f} = 1.0000 gram\n\n"
        f"Harga GAP {'🔄 Tidak Berubah' if diff == 0 else ('📈 Naik RM%d' % diff if diff > 0 else '📉 Turun RM%d' % abs(diff))}\n\n"
        f"Terendah: RM {g['low']['price']:,.0f} ({d_my(g['low']['date'])})\n"
        f"Tertinggi: RM {g['high']['price']:,.0f} ({d_my(g['high']['date'])})\n\n"
        f"Dikemaskini: {ts}"
    )
    os.makedirs(OUT, exist_ok=True)
    img = f"{OUT}/gap.png"
    try:
        card.gap_card(img, price, p["gap_gram_per_rm100"], trend_text(diff),
                      f"{g['low']['price']:,.0f}", f"{g['high']['price']:,.0f}", ts, series_30(st))
    except Exception as e:  # imej gagal -> teks tetap dihantar
        print("Imej gagal:", e)
        img = None
    send(text, img, "harga-GAP")
    g["last_post"] = price


def mode_jewel(p, st):
    j, ts = p["jewel"], fmt_dt(now_my())
    text = (
        "💎 Harga Emas PG Jewel (Barang Kemas)\n\n"
        "Harga emas PG Jewel (barang kemas) baru sahaja dikemaskini.\n\n"
        f"PG Jewel (Sell)\nEmas 999 = RM {j['999']['sell']:,.0f}\nEmas 916 = RM {j['916']['sell']:,.0f}\n\n"
        f"PG Jewel (Buy)\nEmas 999 = RM {j['999']['buy']:,.0f}\nEmas 916 = RM {j['916']['buy']:,.0f}\n\n"
        f"Dikemaskini: {ts}"
    )
    os.makedirs(OUT, exist_ok=True)
    img = f"{OUT}/jewel.png"
    try:
        card.jewel_card(img, j, ts)
    except Exception as e:
        print("Imej gagal:", e)
        img = None
    send(text, img, "harga-PG-Jewel")


def mode_alert(p, st):
    g = st["gap"]
    price = p["gap_rm_per_gram"]
    thr = float(os.getenv("ALERT_THRESHOLD", "3"))
    base = g.get("last_alert") or g.get("last_post") or price
    diff = price - base
    update_range(st, price, now_my().strftime("%Y-%m-%d"))
    if abs(diff) < thr:
        print(f"Tiada alert: GAP RM{price:.0f}, asas RM{base:.0f}, beza RM{diff:+.0f} (< RM{thr:.0f})")
        g["last_alert"] = base
        return
    if diff > 0:
        text = (
            "🚨🚨🚨 Price Alert 🚨🚨🚨\n\n"
            f"Harga emas tengah NAIK sebanyak RM{diff:,.0f} daripada RM{base:,.0f} kepada RM{price:,.0f} sekarang.\n\n"
            "Make sure topup akaun emas GAP anda sebelum harga dikemaskini nanti."
        )
    else:
        text = (
            "🚨🚨🚨 Price Alert 🚨🚨🚨\n\n"
            f"Harga emas menjunam! Turun RM{abs(diff):,.0f} daripada RM{base:,.0f} kepada RM{price:,.0f} sekarang.\n\n"
            "Peluang untuk tambah tabung simpanan emas sekarang.\n"
            f"Panduan simpan emas: {BELI_LINK}"
        )
    send(text, None, "price-alert")
    g["last_alert"] = price


SEED = {  # graf 30 hari GAP (05/10 - 03/11/2026) daripada graf rujukan Shukri
    "2026-10-05": 589, "2026-10-06": 594, "2026-10-07": 581, "2026-10-08": 589, "2026-10-09": 596,
    "2026-10-10": 597, "2026-10-11": 597, "2026-10-12": 592, "2026-10-13": 594, "2026-10-14": 583,
    "2026-10-15": 588, "2026-10-16": 597, "2026-10-17": 594, "2026-10-18": 592, "2026-10-19": 592,
    "2026-10-20": 588, "2026-10-21": 587, "2026-10-22": 577, "2026-10-23": 571, "2026-10-24": 570,
    "2026-10-25": 569, "2026-10-26": 569, "2026-10-27": 577, "2026-10-28": 573, "2026-10-29": 569,
    "2026-10-30": 552, "2026-10-31": 551, "2026-11-01": 548, "2026-11-02": 560, "2026-11-03": 561,
}


def seed_history(st):
    h = st["gap"].setdefault("history", {})
    for k, v in SEED.items():
        h.setdefault(k, v)
    for k, v in sorted(h.items()):  # betulkan terendah/tertinggi jika sejarah lebih ekstrem
        update_range(st, v, k)


def series_30(st):
    h = st["gap"]["history"]
    ks = sorted(h)[-30:]
    return [(k, h[k]) for k in ks]


def rotate(st, key, items):
    i = st.get(key, 0) % len(items)
    st[key] = i + 1
    return items[i]


def mode_ilmu(p, st):
    items = load(dpath("ilmu.json"), [])
    if not items:
        print("data/ilmu.json kosong")
        return
    t = rotate(st, "ilmu_idx", items)
    send(f"{t['tajuk']}\n\n{t['isi']}\n\n➡️ {SITE}", None, "ilmu-emas")


def source_for(dt):
    """Siang (sebelum 6 petang) & malam bertukar ganti setiap hari: PG Jewel <-> PG Mall."""
    siang = dt.hour < 18
    genap = dt.toordinal() % 2 == 0
    return "jewel" if (genap != siang) else "mall"


def _download_jpg(url, dest):
    try:
        from io import BytesIO
        from PIL import Image
        r = requests.get(url, headers=items.UA, timeout=30)
        r.raise_for_status()
        Image.open(BytesIO(r.content)).convert("RGB").save(dest, "JPEG", quality=92)
        return dest
    except Exception as e:
        print("Gambar item gagal dimuat turun:", e)
        return None


def mode_item(p, st, source=None):
    source = source or source_for(now_my())
    text, img_url = (items.jewel_item if source == "jewel" else items.mall_item)(st)
    os.makedirs(OUT, exist_ok=True)
    img = _download_jpg(img_url, f"{OUT}/item.jpg") if img_url else None
    send(text, img, f"item-{source}")


MODES = {"gap": mode_gap, "jewel": mode_jewel, "alert": mode_alert, "ilmu": mode_ilmu, "item": mode_item,
         "item-jewel": lambda p, st: mode_item(p, st, "jewel"),
         "item-mall": lambda p, st: mode_item(p, st, "mall")}

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in MODES:
        sys.exit(f"Mod mesti salah satu: {', '.join(MODES)}")
    st = load(STATE, {})
    st.setdefault("gap", {"last_post": None, "last_alert": None,
                          "low": {"price": 548, "date": "2026-11-01"},
                          "high": {"price": 764, "date": "2026-01-29"}})
    seed_history(st)
    prices = pgfetch.get_prices() if mode in ("gap", "jewel", "alert") else {}
    MODES[mode](prices, st)
    save(STATE, st)

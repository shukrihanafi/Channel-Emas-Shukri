"""Bot Channel Emas - jana post & hantar ke Telegram (mod separa-auto).

Guna:  python post.py <mod>
Mod:   gap | jewel | alert | ilmu | item
Env:   TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID   (DRY_RUN=1 -> simpan dalam out/ sahaja)
       ALERT_THRESHOLD (RM, lalai 3)
"""
import json, os, sys
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
import pgfetch, card

TZ = ZoneInfo("Asia/Kuala_Lumpur")
STATE = "data/state.json"
OUT = "out"
SITE = "shukriee.com"
BULAN = ["Jan", "Feb", "Mac", "Apr", "Mei", "Jun", "Jul", "Ogos", "Sep", "Okt", "Nov", "Dis"]


def now_my():
    return datetime.now(TZ)


def fmt_dt(dt):
    h = dt.hour % 12 or 12
    return f"{dt.day:02d} {BULAN[dt.month-1]} {dt.year} @ {h}:{dt.minute:02d} {'am' if dt.hour < 12 else 'pm'}"


def load(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except FileNotFoundError:
        return default


def save(path, data):
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
    diff = price - g["last_post"] if g.get("last_post") else 0
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
    card.gap_card(img, price, p["gap_gram_per_rm100"], trend_text(diff),
                  f"{g['low']['price']:,.0f}", f"{g['high']['price']:,.0f}", ts)
    send(text, img, "harga-GAP")
    g["last_post"] = price


def mode_jewel(p, st):
    j, ts = p["jewel"], fmt_dt(now_my())
    text = (
        "💎 Harga Emas PG Jewel\n\n"
        "Harga barang kemas PG Jewel baru sahaja dikemaskini.\n\n"
        f"PG Jewel (Sell)\nEmas 999 = RM {j['999']['sell']:,.0f}\nEmas 916 = RM {j['916']['sell']:,.0f}\n\n"
        f"PG Jewel (Buy)\nEmas 999 = RM {j['999']['buy']:,.0f}\nEmas 916 = RM {j['916']['buy']:,.0f}\n\n"
        f"Dikemaskini: {ts}"
    )
    os.makedirs(OUT, exist_ok=True)
    img = f"{OUT}/jewel.png"
    card.jewel_card(img, j, ts)
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
            f"Panduan simpan emas: {SITE}"
        )
    send(text, None, "price-alert")
    g["last_alert"] = price


def rotate(st, key, items):
    i = st.get(key, 0) % len(items)
    st[key] = i + 1
    return items[i]


def mode_ilmu(p, st):
    items = load("data/ilmu.json", [])
    if not items:
        print("data/ilmu.json kosong")
        return
    t = rotate(st, "ilmu_idx", items)
    send(f"{t['tajuk']}\n\n{t['isi']}\n\n➡️ {SITE}", None, "ilmu-emas")


def mode_item(p, st):
    items = load("data/items.json", [])
    if not items:
        print("data/items.json kosong - tambah item PG Mall/PG Jewel dahulu")
        return
    it = rotate(st, "item_idx", items)
    text = (f"Item {it.get('kedai', 'PG Mall')}\n\nItem: {it['nama']}\n\nHarga: RM {it['harga']}\n\n"
            f"Link: {it['link']}\n\nNice kan? Dapatkan segera dekat link di atas.")
    img = it.get("imej")
    send(text, img if img and os.path.exists(img) else None, "item")


MODES = {"gap": mode_gap, "jewel": mode_jewel, "alert": mode_alert, "ilmu": mode_ilmu, "item": mode_item}

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in MODES:
        sys.exit(f"Mod mesti salah satu: {', '.join(MODES)}")
    st = load(STATE, {})
    st.setdefault("gap", {"last_post": None, "last_alert": None,
                          "low": {"price": 561, "date": "2026-06-30"},
                          "high": {"price": 764, "date": "2026-01-29"}})
    prices = pgfetch.get_prices() if mode in ("gap", "jewel", "alert") else {}
    MODES[mode](prices, st)
    save(STATE, st)

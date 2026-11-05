"""Bot Channel Emas - jana post & hantar ke Telegram (mod separa-auto).

Guna:  python post.py <mod>
Mod:   gap | jewel | alert | ilmu | item | pgitem | berita | berita-test | wa-channels   (item-jewel / item-mall = ujian paksa)
Env:   TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID   (DRY_RUN=1 -> simpan dalam out/ sahaja)
       ALERT_THRESHOLD (RM, lalai 3) - alert + kad GAP apabila harga berubah sekurang-kurangnya nilai ini
"""
import json, os, random, sys
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
import pgfetch, pgitems, card, items, whapi, relay, fb

TZ = ZoneInfo("Asia/Kuala_Lumpur")
STATE = "data/state.json"
OUT = "out"
SITE = "shukriee.com"
CLOSING = ""  # tiada ayat penutup lalai; setiap skrip ada ajakan sendiri
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
CURRENT_MODE = ""


def tg_plain(msg):
    """Mesej ringkas ke Telegram (tanpa penutup & tanpa WhatsApp)."""
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if os.getenv("DRY_RUN") or not (token and chat):
        print(msg)
        return
    requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": chat, "text": msg}, timeout=60)


def wa_auto_for(mode):
    modes = [m.strip() for m in os.getenv("WA_AUTO_MODES", "").split(",") if m.strip()]
    return os.getenv("WA_ENABLED") == "1" and whapi.enabled() and mode.split("-")[0] in modes


def send(text, image=None, label="post", closing=True):
    text = f"{text.rstrip()}\n\n{CLOSING}" if (closing and CLOSING) else text.rstrip()
    os.makedirs(OUT, exist_ok=True)
    stamp = now_my().strftime("%Y%m%d-%H%M%S")
    open(f"{OUT}/{stamp}-{label}.txt", "w", encoding="utf-8").write(text)
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if os.getenv("DRY_RUN") or not (token and chat):
        print(f"--- [{label}] (DRY RUN) ---\n{text}\n[imej: {image}]\n")
        return
    base = f"https://api.telegram.org/bot{token}"
    wa_note = ""
    test_only = CURRENT_MODE.endswith("-test")  # mod ujian: hantar ke Telegram peribadi sahaja
    if not test_only and wa_auto_for(CURRENT_MODE):
        try:
            whapi.post_channel(text, image)
            wa_note = "✅ Sudah dihantar ke WhatsApp Channel (auto)."
        except Exception as e:  # WhatsApp gagal -> Telegram tetap ada untuk hantar manual
            wa_note = f"⚠️ Gagal hantar ke WhatsApp Channel: {e}\nSila hantar manual."
    def push(target):
        # Gambar + caption dalam SATU mesej (supaya IFTTT -> FB Page bawa ayat sekali). Had caption Telegram 1024 aksara.
        if image and len(text) <= 1024:
            with open(image, "rb") as f:
                r = requests.post(f"{base}/sendPhoto", data={"chat_id": target, "caption": text}, files={"photo": f}, timeout=60)
            r.raise_for_status()
            return
        if image:
            with open(image, "rb") as f:
                r = requests.post(f"{base}/sendPhoto", data={"chat_id": target}, files={"photo": f}, timeout=60)
            r.raise_for_status()
        r = requests.post(f"{base}/sendMessage", data={"chat_id": target, "text": text}, timeout=60)
        r.raise_for_status()

    push(chat)  # salinan semakan untuk Shukri (chat peribadi dengan bot)
    # Telegram Channel awam (auto) - bot mesti admin channel
    tg_channel = os.getenv("TELEGRAM_CHANNEL", "").strip()
    if tg_channel and os.getenv("TG_CHANNEL_ENABLED", "1") == "1" and not test_only:
        try:
            push(tg_channel)
            wa_note = (wa_note + "\n" if wa_note else "") + f"✅ Sudah dihantar ke Telegram Channel {tg_channel} (auto)."
        except Exception as e:
            wa_note = (wa_note + "\n" if wa_note else "") + f"⚠️ Gagal hantar ke Telegram Channel {tg_channel}: {e}"
    if fb.enabled() and not test_only:  # Facebook Page (ganti IFTTT)
        try:
            fb.post(text, image)
            wa_note = (wa_note + "\n" if wa_note else "") + "✅ Sudah dihantar ke Facebook Page (auto)."
        except Exception as e:
            wa_note = (wa_note + "\n" if wa_note else "") + f"⚠️ Gagal hantar ke Facebook Page: {e}"
    if wa_note:
        tg_plain(wa_note)


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


def gap_text_and_card(p, st, diff, ts, base=None):
    """Teks kad GAP + imej kad (kongsi antara mode gap dan alert)."""
    g, price = st["gap"], p["gap_rm_per_gram"]
    text = (
        f"Harga GAP {'🔄 Tidak Berubah' if diff == 0 else ('🔴 Naik RM%d' % diff if diff > 0 else '🟢 Turun RM%d' % abs(diff))}\n\n"
        f"HARGA GAP PUBLIC GOLD\n"
        f"RM 100 = {p['gap_gram_per_rm100']} gram\n"
        f"RM {price:,.0f} = 1.0000 gram\n\n"
        f"Terendah: RM {g['low']['price']:,.0f} ({d_my(g['low']['date'])})\n"
        f"Tertinggi: RM {g['high']['price']:,.0f} ({d_my(g['high']['date'])})\n\n"
        f"Jom simpan emas sekarang!\nWhatsApp saya di shukriee.com\n\n"
        f"Dikemaskini: {ts}"
    )
    os.makedirs(OUT, exist_ok=True)
    img = f"{OUT}/gap.png"
    try:
        card.gap_card(img, price, p["gap_gram_per_rm100"], trend_text(diff),
                      f"{g['low']['price']:,.0f}", f"{g['high']['price']:,.0f}", ts, series_30(st, base, price))
    except Exception as e:  # imej gagal -> teks tetap dihantar
        print("Imej gagal:", e)
        img = None
    return text, img


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
    text, img = gap_text_and_card(p, st, diff, fmt_dt(dt), base=prev)
    send(text, img, "harga-GAP")
    g["last_post"] = price
    g["last_alert"] = price     # asas Price Alert sentiasa harga terakhir yang diumumkan


def mode_jewel(p, st):
    j, nonpg, ts = p["jewel"], p.get("nonpg") or {}, fmt_dt(now_my())
    text = (
        "HARGA BARANG KEMAS PG JEWEL & NON-PG GOLD BUYBACK\n\n"
        f"🟡 HARGA PG JUAL\nEmas 999 = RM {j['999']['sell']:,.0f}\nEmas 916 = RM {j['916']['sell']:,.0f}\n\n"
        f"🟡 HARGA PG BELI\nEmas 999 = RM {j['999']['buy']:,.0f}\nEmas 916 = RM {j['916']['buy']:,.0f}\n\n"
    )
    if nonpg:
        text += (
            f"🟡 NON-PG GOLD BUYBACK\nEmas 999 = RM {nonpg.get('999', 0):,.0f}\nEmas 916 = RM {nonpg.get('916', 0):,.0f}\n\n"
            "Nota: Non-PG Gold Buyback ialah harga yang Public Gold tawarkan untuk membeli emas jenama lain.\n\n"
        )
    text += (
        "Anda nak BELI barang kemas dengan harga murah?\n\n"
        "atau...\n\n"
        "Anda nak JUAL barang kemas lama/rosak/patah dengan harga tinggi?\n\n"
        "Semua nya ada di PG Jewel!\n\n"
        "WhatsApp saya sekarang di\nhttps://shukriee.com/pgjewel\n\n"
        f"Dikemaskini: {ts}"
    )
    os.makedirs(OUT, exist_ok=True)
    img = f"{OUT}/jewel.png"
    try:
        card.jewel_card(img, j, ts, nonpg)
    except Exception as e:
        print("Imej gagal:", e)
        img = None
    send(text, img, "harga-PG-Jewel")


ALERT_UP = [
    "🔴‼️HARGA GAP NAIK! ‼️🔴\n\n"
    "Harga GAP sekarang RM{p} segram. Sebelum ini RM{b}, naik sebanyak RM{d}.\n\n"
    "Sentiasa ON notification channel ini untuk pantau harga emas terkini.\n\n"
    "Klik link di bawah panduan simpan emas\n"
    "https://shukriee.com/beliemas",
    "🔴‼️ UPDATE TERKINI HARGA GAP ‼️🔴\n\n"
    "Harga GAP naik RM{d} segram. Daripada RM{b} kepada RM{p}.\n\n"
    "Tahniah kepada anda yang menyimpan emas kerana nilai simpanan anda kini turut meningkat mengikut harga emas semasa.\n\n"
    "Nak konsisten simpan emas? Klik link di bawah\n"
    "https://shukriee.com/beliemas",
    "🔴‼️ HARGA EMAS BERUBAH LAGI! 🔴‼️\n\n"
    "Harga GAP kini RM{p} segram.\n\n"
    "Ada kenaikan sebanyak RM{d} berbanding harga sebelum ini.\n\n"
    "Kongsikan link channel ini kepada circle anda untuk mereka tahu harga emas terkini.\n"
    "http://shukriee.com/channel",
]
ALERT_DOWN = [
    "🟢✅ HARGA GAP TURUN! 🟢✅\n\n"
    "Harga GAP sekarang RM{p} segram. Sebelum ini RM{b}, turun sebanyak RM{d}.\n\n"
    "Ini lah peluang untuk anda topup simpanan emas!\n\n"
    "Klik link di bawah panduan simpan emas\n"
    "https://shukriee.com/beliemas",
    "🟢✅ PELUANG TOPUP SIMPANAN EMAS 🟢✅\n\n"
    "Harga GAP turun RM{d} segram. Daripada RM{b} kepada RM{p}.\n\n"
    "Sekarang RM{p} segram, berbanding RM{b} sebelum ini.\n\n"
    "Anda ada bajet lebih? Jom simpan emas sekarang!\n"
    "Panduan di https://shukriee.com/beliemas",
    "🟢✅ YEAY! HARGA EMAS TURUN! 🟢✅\n\n"
    "Harga GAP kini RM{p} segram.\n\n"
    "Ada penurunan sebanyak RM{d} berbanding harga sebelum ini.\n\n"
    "Jom topup simpanan emas anda!\n\n"
    "Klik link di bawah panduan simpan emas\n"
    "https://shukriee.com/beliemas",
]


BB_COMMON = (
    "Anda boleh KUNCI (LOCK) harga PG Buy terus melalui aplikasi Public Gold. Selepas lock harga, anda perlu hadir ke cawangan "
    "Public Gold berdekatan dalam tempoh 24 jam untuk menyelesaikan urusan jualan.\n\n"
)
BB_LINKS = (
    "📲 Whatsapp saya :\nhttps://shukriee.com/buyback\n\n"
    "🏢 Lokasi cawangan Public Gold :\nhttps://publicgold.com.my/index.php?route=information/information&information_id=branch\n\n"
    "Dikemaskini: {ts}"
)
BB_UP = [
    "😍 PELUANG JUAL EMAS DENGAN HARGA TINGGI! \n\n"
    "Harga emas naik kan? Ini peluang, anda jual emas di Public Gold dengan harga tinggi!\n\n"
    + BB_COMMON +
    "Jika gagal hadir dalam tempoh tersebut, nama anda akan disenarai hitam (blacklist) oleh Public Gold. Pastikan anda jual emas dengan MATLAMAT ok!\n\n"
    + BB_LINKS,
    "💰EMAS LAMA BOLEH JADI DUIT TUNAI! \n\n"
    "Anda ada barang kemas 916 atau 999 yang dah lama tersimpan?\n\n"
    "Jangan biarkan begitu sahaja. Jom jual emas dengan harga belian tinggi di Public Gold sekarang!\n\n"
    + BB_COMMON +
    "Jika gagal hadir dalam tempoh tersebut, nama anda akan disenarai hitam (blacklist) oleh Public Gold.\n\n"
    "Pastikan anda benar-benar bersedia sebelum LOCK harga. Jangan lepaskan peluang untuk manfaatkan nilai emas anda!\n\n"
    + BB_LINKS,
    "🚀 HARGA JUAL EMAS NAIK..!\n\n"
    "Tahu tak, emas yang anda beli beberapa tahun lalu mungkin mempunyai nilai yang jauh tinggi pada hari ini!\n\n"
    "Kalau anda bercadang nak jual emas, boleh jual harga tinggi di Public Gold.\n\n"
    + BB_COMMON +
    "Jika gagal hadir dalam tempoh tersebut, nama anda akan disenarai hitam (blacklist) oleh Public Gold. Pastikan anda jual emas dengan MATLAMAT ok!\n\n"
    + BB_LINKS,
]


def mode_buyback_alert(p, st, ts):
    """Alert Harga PG BELI + NON-PG BUYBACK: dihantar bersama alert GAP NAIK sahaja. Skrip dipilih rawak (elak ulang yang sama)."""
    j, nonpg = p["jewel"], p.get("nonpg") or {}
    last = st.get("bb_last", -1)
    i = random.choice([k for k in range(len(BB_UP)) if k != last] or list(range(len(BB_UP))))
    st["bb_last"] = i
    text = BB_UP[i].replace("{ts}", ts)
    os.makedirs(OUT, exist_ok=True)
    img = f"{OUT}/buyback.png"
    try:
        card.buy_card(img, j, nonpg, ts)
    except Exception as e:
        print("Imej gagal:", e)
        img = None
    send(text, img, "alert-buyback", closing=False)


def mode_alert(p, st):
    """Jalan 24 jam (setiap 30 minit). Jika harga GAP berubah >= ALERT_THRESHOLD (lalai RM3)
    daripada harga terakhir yang diumumkan -> hantar skrip alert + kad GAP sebagai satu hantaran.
    Tiada ayat penutup tambahan (skrip alert ada pautan sendiri)."""
    g, dt = st["gap"], now_my()
    price = p["gap_rm_per_gram"]
    thr = float(os.getenv("ALERT_THRESHOLD", "3"))
    update_range(st, price, dt.strftime("%Y-%m-%d"))
    if dt.hour * 60 + dt.minute < 8 * 60 + 30:  # alert hanya 8:30 pagi - 12 malam
        print(f"Di luar waktu alert ({dt:%H:%M}); harga GAP RM{price:.0f}")
        return
    base = g.get("last_alert") or g.get("last_post") or price
    diff = price - base
    if abs(diff) < thr:
        g["last_alert"] = base
        print(f"Tiada hantaran: GAP RM{price:.0f}, harga diumumkan terakhir RM{base:.0f}, beza RM{diff:+.0f} (< RM{thr:.0f})")
        return
    n = int(st.get("alert_n", 0))
    st["alert_n"] = n + 1
    pool = ALERT_UP if diff > 0 else ALERT_DOWN
    text = pool[n % len(pool)].format(d=f"{abs(diff):,.0f}", b=f"{base:,.0f}", p=f"{price:,.0f}")
    g.setdefault("history", {})[dt.strftime("%Y-%m-%d")] = price
    seed_history(st)
    _, img = gap_text_and_card(p, st, diff, fmt_dt(dt), base=base)
    if diff > 0:  # GAP NAIK -> hantar alert PG Buy + Non-PG Buyback DAHULU, kemudian alert GAP
        try:
            mode_buyback_alert(p, st, fmt_dt(dt))
        except Exception as e:
            print("Alert PG Buy/Non-PG gagal:", e)
    send(text, img, "price-alert", closing=False)
    g["last_alert"] = price
    g["last_post"] = price


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


def series_30(st, base=None, price=None):
    """Siri graf 30 titik. Hari ini diganti dengan 'Tadi' (harga diumumkan terakhir) -> 'Kini'
    supaya arah hujung graf SELARI dengan teks Naik/Turun."""
    h = st["gap"]["history"]
    today = now_my().strftime("%Y-%m-%d")
    if base is None or price is None:
        return [(k, h[k]) for k in sorted(h)[-30:]]
    pts = [(k, h[k]) for k in sorted(h) if k < today][-28:]
    if not pts or pts[-1][1] != base:
        pts.append(("Tadi", base))
    pts.append(("Kini", price))
    return pts


def rotate(st, key, items):
    i = st.get(key, 0) % len(items)
    st[key] = i + 1
    return items[i]


def mode_ilmu(p, st):
    items = load(dpath("ilmu.json"), [])
    if not items:
        print("data/ilmu.json kosong")
        return
    n = int(st.get("ilmu_n", 0)) + 1          # nombor siaran: 1,2,...365,366,...
    t = items[(n - 1) % len(items)]            # lepas 365 pusing balik ke entri 1
    st["ilmu_n"] = n
    # skrip sudah ada ayat ajakan sendiri di hujung, jadi tak tambah CLOSING
    send(f"💡 ILMU #{n} - {t['tajuk']}\n\n{t['isi']}", None, "ilmu-emas", closing=False)


USE_MALL = False  # PG Mall menyekat GitHub (403). Tukar kepada True jika akses PG Mall sudah ada.


def source_for(dt):
    """Sumber item. Kini PG Jewel sahaja; jika USE_MALL=True, siang & malam bertukar ganti setiap hari."""
    if not USE_MALL:
        return "jewel"
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
    try:
        text, img_url = (items.jewel_item if source == "jewel" else items.mall_item)(st)
    except Exception as e:
        if source != "mall":
            raise
        print(f"PG Mall tidak dapat dicapai ({e}); guna item PG Jewel sebagai ganti")
        source = "jewel"
        text, img_url = items.jewel_item(st)
    os.makedirs(OUT, exist_ok=True)
    img = _download_jpg(img_url, f"{OUT}/item.jpg") if img_url else None
    send(text, img, f"item-{source}")


def mode_pgitem(p, st):
    """Item Gold Bar / Dinar / Perak daripada website Public Gold (putar kategori, elak ulang)."""
    ts = fmt_dt(now_my())
    catalog = pgitems.fetch_catalog()
    it = pgitems.pick(st, catalog)
    text = pgitems.pg_text(it, ts)
    os.makedirs(OUT, exist_ok=True)
    img = None
    try:
        from io import BytesIO
        from PIL import Image
        r = requests.get(it["img"], headers=pgitems.UA, timeout=30)
        r.raise_for_status()
        pimg = f"{OUT}/pgitem_src.png"
        Image.open(BytesIO(r.content)).convert("RGBA").save(pimg)
        weight, purity = pgitems.specs(it["name"])
        img = f"{OUT}/pgitem.png"
        card.item_card(img, pimg, {"bar": "GOLD BAR PUBLIC GOLD", "dinar": "DINAR EMAS PUBLIC GOLD",
                                   "silver": "PERAK PUBLIC GOLD"}[it["kind"]], it["name"], it["price"], weight, purity, ts)
    except Exception as e:
        print("Imej item gagal:", e)
        img = None
    send(text, img, f"item-{it['kind']}")


def mode_wa_channels(p, st):
    """Papar senarai Channel WhatsApp (untuk salin ID Channel) ke Telegram."""
    rows = whapi.list_channels()
    if not rows:
        tg_plain("Tiada Channel ditemui. Pastikan nombor bot sudah jadi admin Channel dan sudah dipautkan di Whapi.")
        return
    tg_plain("Senarai Channel WhatsApp:\n\n" + "\n\n".join(f"{n}\nID: {i}\nPeranan: {r}" for i, n, r in rows))


def mode_berita(p, st):
    import news
    news.run(st, send, now_my(), notify=tg_plain)


# Jadual tetap (waktu Malaysia). Alert 20-minit juga menjadi "pengawas": jika hantaran tertinggal (run tersekat di GitHub),
# ia dijalankan semula sendiri dalam tempoh 150 minit selepas masa asal.
SLOTS = [("08:09", "gap"), ("10:09", "pgitem"), ("13:09", "berita"), ("16:09", "jewel"),
         ("18:09", "item"), ("20:09", "gap"), ("21:09", "ilmu"), ("22:39", "pgitem")]


def _since(slot, dt):
    h, m = map(int, slot.split(":"))
    return dt.hour * 60 + dt.minute - (h * 60 + m)


def mark_slot(st, mode, dt):
    done = st.setdefault("slots", {})
    today = dt.strftime("%Y-%m-%d")
    for k in [k for k in done if not k.startswith(today)]:
        del done[k]
    for slot, m in SLOTS:
        if m == mode and f"{today}|{slot}" not in done and 0 <= _since(slot, dt) <= 150:
            done[f"{today}|{slot}"] = dt.strftime("%H:%M")
            return


def watchdog(p, st):
    global CURRENT_MODE
    dt = now_my()
    done = st.setdefault("slots", {})
    today = dt.strftime("%Y-%m-%d")
    for slot, m in SLOTS:
        if f"{today}|{slot}" in done or not (12 <= _since(slot, dt) <= 150):
            continue
        print(f"Pengawas: slot {slot} ({m}) belum dijalankan, jalankan sekarang")
        done[f"{today}|{slot}"] = dt.strftime("%H:%M") + " (pengawas)"
        CURRENT_MODE = m
        try:
            MODES[m](p, st)
        except Exception as e:
            print(f"Pengawas: {m} gagal: {e}")
        finally:
            CURRENT_MODE = "alert"


def mode_relay(p, st):
    n = relay.run(st, tg_plain)
    print(f"Relay: {n} posting disalin.")


MODES = {"relay": mode_relay, "wa-channels": mode_wa_channels, "berita": mode_berita, "berita-test": mode_berita, "gap": mode_gap, "jewel": mode_jewel, "alert": mode_alert, "ilmu": mode_ilmu, "item": mode_item, "pgitem": mode_pgitem,
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
    CURRENT_MODE = mode
    prices = pgfetch.get_prices() if mode in ("gap", "jewel", "alert") else {}
    MODES[mode](prices, st)
    if mode == "alert":
        try:
            relay.run(st, tg_plain)
        except Exception as e:
            print("Relay gagal:", e)
        watchdog(prices, st)
    elif not mode.endswith("-test") and mode != "wa-channels":
        mark_slot(st, mode, now_my())
    save(STATE, st)

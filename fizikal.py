"""Harga emas fizikal Public Gold (Gold Bar 24K + Gold Wafer Dinar 24K): ambil dari website, jana gambar merah-emas + caption."""
import re, requests
from PIL import Image, ImageDraw
import pgfetch, card

BARS = ["5", "10", "20", "50", "100", "250", "1000"]
DINAR = ["1", "5", "10"]
PAGE = "https://publicgold.com.my"
PRODUK = "https://publicgold.com.my/index.php?route=product/category&path=1"


def _n(s):
    return float(s.replace(",", ""))


def parse(text, gap=None):
    """Pulangkan {'bars': {...}, 'dinar': {...}}. Halaman boleh ada salinan lama: pilih blok yang lengkap dan munasabah."""
    best = None
    for m in re.finditer(r"GOLD BAR \(24K\)(.*?)GOLD WAFER[^A-Za-z]{0,10}DINAR[^A-Za-z]{0,10}(.{0,700})", text, re.I | re.S):
        bars = {w: {"sell": _n(s), "buy": _n(b)} for w, s, b in re.findall(r"\b(\d+) gram ([\d,]+) ([\d,]+)", m.group(1))}
        dn = {w: {"sell": _n(s), "buy": _n(b)} for w, s, b in re.findall(r"\b(\d+) Dinar ([\d,]+) ([\d,]+)", m.group(2), re.I)}
        if not (set(BARS) <= set(bars) and set(DINAR) <= set(dn)):
            continue
        bars = {w: bars[w] for w in BARS}
        dn = {w: dn[w] for w in DINAR}
        if gap:  # semakan kewarasan: harga 1000 g / 1000 mesti hampir harga GAP seg gram
            if not (0.8 * gap <= bars["1000"]["sell"] / 1000 <= 1.2 * gap):
                continue
        best = {"bars": bars, "dinar": dn}
        break
    if not best:
        raise ValueError("Jadual Gold Bar / Dinar tidak ditemui atau tidak munasabah - struktur laman mungkin berubah")
    return best


def get_prices():
    r = requests.get(pgfetch.URL, headers=pgfetch.UA, timeout=30)
    r.raise_for_status()
    text = pgfetch._to_text(r.text)
    try:
        gap = pgfetch.parse(text)["gap_rm_per_gram"]
    except Exception:
        gap = None
    return parse(text, gap)


def _fmt(v):
    return f"{v:,.0f}"


def make_card(path, data, ts):
    """Gambar persegi 1080x1080: tajuk, dua jadual, nota, tarikh."""
    W, H = 1080, 1080
    GOLD, GOLD_L, WHITE = card.GOLD, card.GOLD_L, card.WHITE
    im, d = card._bg(H=H, W=W)
    f, B, R = card._f, card.BOLD, card.REG
    def cen(y, t, fo, fill, x0=0, w=W):
        tw = d.textlength(t, font=fo); d.text((x0 + (w - tw) / 2, y), t, font=fo, fill=fill)
    cen(46, "HARGA EMAS FIZIKAL PUBLIC GOLD", f(B, 44), GOLD)
    X0, X1 = 70, W - 70
    cols = [X0, X0 + 330, X0 + 670, X1]
    RH, BH = 44, 46
    def table(y, title, label, rows, unit):
        d.rounded_rectangle([X0, y, X1, y + BH], 14, fill=GOLD)
        cen(y + 5, title, f(B, 26), (92, 8, 16))
        yh = y + BH
        d.rectangle([X0, yh, X1, yh + BH], fill=(120, 14, 24))
        for i, t in enumerate([label, "PG Sell (RM)", "PG Buy (RM)"]):
            cen(yh + 7, t, f(B, 23), GOLD_L, cols[i], cols[i + 1] - cols[i])
        yr = yh + BH
        for n, (k, v) in enumerate(rows):
            top = yr + n * RH
            d.rectangle([X0, top, X1, top + RH], fill=(66, 6, 14) if n % 2 == 0 else (88, 10, 20))
            vals = [f"{k} {unit}", _fmt(v["sell"]), _fmt(v["buy"])]
            for i, t in enumerate(vals):
                cen(top + 7, t, f(B if i else R, 26), (255, 226, 140) if i == 1 else WHITE, cols[i], cols[i + 1] - cols[i])
        yend = yr + len(rows) * RH
        d.rectangle([X0, yh, X1, yend], outline=GOLD, width=3)
        for c in cols[1:3]:
            d.line([(c, yh), (c, yend)], fill=GOLD, width=2)
        for n in range(len(rows) + 1):
            d.line([(X0, yr + n * RH), (X1, yr + n * RH)], fill=GOLD, width=2)
        return yend
    y = table(118, "GOLD BAR (24K)", "Weight", [(k, data["bars"][k]) for k in BARS], "gram")
    y = table(y + 22, "GOLD WAFER - DINAR (24K)", "Dinar", [(k, data["dinar"][k]) for k in DINAR], "Dinar")
    ny = y + 22
    d.text((X0, ny), "Nota :", font=f(B, 24), fill=GOLD)
    d.text((X0 + 110, ny + 1), "PG Sell (RM) : Harga anda beli emas.", font=f(R, 23), fill=WHITE)
    d.text((X0 + 110, ny + 31), "PG Buy (RM) : Harga anda jual emas.", font=f(R, 23), fill=WHITE)
    d.text((X0, ny + 70), "* Harga emas fizikal berubah setiap 20 minit mengikut harga emas semasa dunia", font=f(R, 20), fill=GOLD_L)
    cen(ny + 108, f"Dikemaskini: {ts}", f(R, 26), GOLD_L)
    pw, ph = 300, 54
    x0 = (W - pw) / 2
    py = H - 100
    d.rounded_rectangle([x0, py, x0 + pw, py + ph], 27, fill=(0, 0, 0), outline=GOLD, width=3)
    cen(py + 7, "shukriee.com", f(B, 32), WHITE)
    im.save(path)


def caption(ts):
    return (
        "HARGA EMAS FIZIKAL PUBLIC GOLD\n\n"
        "Selain simpan emas melalui akaun GAP, anda juga boleh simpan emas fizikal Public Gold.\n\n"
        "Rujuk jadual di atas untuk melihat harga emas fizikal.\n\n"
        "Nota :\n\n"
        "1️⃣ Harga berubah setiap 20 minit mengikut harga emas semasa dunia. Harga terkini, rujuk website Public Gold:\n"
        f"{PAGE}\n\n"
        "2️⃣ Klik link di bawah untuk melihat produk emas fizikal:\n"
        f"{PRODUK}\n\n"
        "Jom simpan emas sekarang!\n"
        "WhatsApp saya di shukriee.com\n\n"
        f"Dikemaskini: {ts}"
    )


# Skrip ALERT emas fizikal turun (diputar mengikut alert)
ALERT_DOWN = [
    "🟢 HARGA EMAS FIZIKAL TURUN 🟢\n\n"
    "Ini adalah peluang terbaik untuk anda beli emas fizikal dengan harga murah!\n\n"
    "Boleh beli emas fizikal serendah 1 Dinar (4.25gram) atau 5gram.\n\n"
    "Jom ambil peluang ni sekarang!\n"
    "Panduan di https://shukriee.com/beliemas\n\n"
    "Kalau nak saya bagi cadangan emas yang sesuai dengan bajet anda, boleh terus WhatsApp saya ok!",
    "🟢 BEST SIMPAN EMAS FIZIKAL 🟢\n\n"
    "Anda simpan emas di GAP saja? Kemon! Harga emas turun ni.\n\n"
    "Apa kata kali ini anda tambah simpanan emas fizikal pula?\n\n"
    "Boleh rasa aura best nya pegang emas fizikal di tangan. Serius!\n\n"
    "Panduan beli emas di https://shukriee.com/beliemas\n\n"
    "Kalau nak saya bagi cadangan emas yang sesuai dengan bajet anda, boleh terus WhatsApp saya ok!",
]

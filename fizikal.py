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
    """Gambar 1080x1500: tajuk, dua jadual, nota, tarikh."""
    W, H = 1080, 1500
    GOLD, GOLD_L, WHITE = card.GOLD, card.GOLD_L, card.WHITE
    im, d = card._bg(H=H, W=W)
    f, B, R = card._f, card.BOLD, card.REG
    def cen(y, t, fo, fill, x0=0, w=W):
        tw = d.textlength(t, font=fo); d.text((x0 + (w - tw) / 2, y), t, font=fo, fill=fill)
    cen(62, "HARGA EMAS FIZIKAL", f(B, 62), GOLD)
    cen(138, "PUBLIC GOLD", f(B, 62), GOLD_L)
    X0, X1 = 70, W - 70
    cols = [X0, X0 + 330, X0 + 670, X1]
    RH = 54
    def table(y, title, label, rows, unit):
        d.rounded_rectangle([X0, y, X1, y + 56], 18, fill=GOLD)
        cen(y + 8, title, f(B, 32), (92, 8, 16))
        yh = y + 56
        d.rectangle([X0, yh, X1, yh + 56], fill=(120, 14, 24))
        for i, t in enumerate([label, "PG Sell (RM)", "PG Buy (RM)"]):
            cen(yh + 10, t, f(B, 28), GOLD_L, cols[i], cols[i + 1] - cols[i])
        yr = yh + 56
        for n, (k, v) in enumerate(rows):
            top = yr + n * RH
            d.rectangle([X0, top, X1, top + RH], fill=(66, 6, 14) if n % 2 == 0 else (88, 10, 20))
            vals = [f"{k} {unit}", _fmt(v["sell"]), _fmt(v["buy"])]
            for i, t in enumerate(vals):
                cen(top + 8, t, f(B if i else R, 30), WHITE if i == 0 else (255, 226, 140) if i == 1 else WHITE, cols[i], cols[i + 1] - cols[i])
        yend = yr + len(rows) * RH
        d.rectangle([X0, yh, X1, yend], outline=GOLD, width=3)
        for c in cols[1:3]:
            d.line([(c, yh), (c, yend)], fill=GOLD, width=2)
        for n in range(len(rows) + 1):
            d.line([(X0, yr + n * RH), (X1, yr + n * RH)], fill=GOLD, width=2)
        return yend
    y = table(240, "GOLD BAR (24K)", "Weight", [(k, data["bars"][k]) for k in BARS], "gram")
    y = table(y + 34, "GOLD WAFER - DINAR (24K)", "Dinar", [(k, data["dinar"][k]) for k in DINAR], "Dinar")
    ny = y + 36
    d.text((X0, ny), "Nota :", font=f(B, 28), fill=GOLD)
    d.text((X0, ny + 42), "PG Sell (RM) : Harga anda beli emas.", font=f(R, 27), fill=WHITE)
    d.text((X0, ny + 80), "PG Buy (RM) : Harga anda jual emas.", font=f(R, 27), fill=WHITE)
    d.text((X0, ny + 130), "* Harga emas fizikal berubah setiap 20 minit mengikut", font=f(R, 25), fill=GOLD_L)
    d.text((X0, ny + 164), "   harga emas semasa dunia", font=f(R, 25), fill=GOLD_L)
    cen(H - 190, f"Dikemaskini: {ts}", f(R, 30), GOLD_L)
    pw, ph = 330, 64
    x0 = (W - pw) / 2
    d.rounded_rectangle([x0, H - 135, x0 + pw, H - 135 + ph], 32, fill=(0, 0, 0), outline=GOLD, width=3)
    cen(H - 124, "shukriee.com", f(B, 36), WHITE)
    im.save(path)


def caption(ts):
    return (
        "HARGA EMAS FIZIKAL PUBLIC GOLD\n\n"
        "Selain menyimpan emas melalui akaun GAP, anda juga boleh menyimpan emas fizikal Public Gold.\n\n"
        "Rujuk jadual di atas untuk melihat harga emas fizikal.\n\n"
        "Nota :\n\n"
        "1️⃣ Harga berubah setiap 20 minit mengikut harga emas semasa dunia. "
        f"Untuk harga paling terkini, sila rujuk website rasmi Public Gold: {PAGE}\n\n"
        "2️⃣ Klik link di bawah untuk melihat pilihan produk emas fizikal:\n"
        f"{PRODUK}\n\n"
        "Jom simpan emas sekarang!\n"
        "WhatsApp saya di shukriee.com\n\n"
        f"Dikemaskini: {ts}"
    )

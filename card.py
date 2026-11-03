"""Jana kad harga (imej 1080x1080) tema merah-emas."""
from PIL import Image, ImageDraw, ImageFont

W = H = 1080
RED_DARK, RED = (92, 8, 16), (150, 18, 28)
GOLD, GOLD_L, WHITE = (230, 184, 72), (255, 226, 140), (255, 255, 255)
import os
_SYS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def _find(name, fallback):
    """Cari fon dalam repositori (mana-mana folder); kalau tiada, guna fon sistem."""
    for root, _, files in os.walk("."):
        if name in files:
            return os.path.join(root, name)
    return fallback


BOLD = _find("Poppins-Bold.ttf", _SYS[0])
REG = _find("Poppins-Regular.ttf", _SYS[1])


def _f(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default(size)


def _bg():
    im = Image.new("RGB", (W, H), RED_DARK)
    px = im.load()
    for y in range(H):  # gradient menegak
        t = y / H
        c = tuple(int(RED_DARK[i] * (1 - t) + RED[i] * t) for i in range(3))
        for x in range(W):
            px[x, y] = c
    d = ImageDraw.Draw(im)
    for g in range(0, W, 60):  # grid emas halus
        d.line([(g, 0), (g, H)], fill=(120, 30, 36), width=1)
        d.line([(0, g), (W, g)], fill=(120, 30, 36), width=1)
    d.rounded_rectangle([30, 30, W - 30, H - 30], 28, outline=GOLD, width=5)
    return im, d


def _center(d, y, text, font, fill):
    w = d.textlength(text, font=font)
    d.text(((W - w) / 2, y), text, font=font, fill=fill)


def _footer(d, date_text):
    _center(d, 930, f"Dikemaskini: {date_text}", _f(REG, 30), GOLD_L)
    w, h = 330, 64
    x0 = (W - w) / 2
    d.rounded_rectangle([x0, 985, x0 + w, 985 + h], 32, fill=(0, 0, 0), outline=GOLD, width=3)
    _center(d, 996, "shukriee.com", _f(BOLD, 36), WHITE)


def gap_card(path, per_gram, per100, trend, low, high, date_text):
    im, d = _bg()
    _center(d, 90, "HARGA EMAS GAP", _f(BOLD, 74), GOLD)
    _center(d, 190, "Public Gold", _f(REG, 40), WHITE)
    _center(d, 300, f"RM {per_gram:,.0f}", _f(BOLD, 190), GOLD_L)
    _center(d, 540, "= 1.0000 gram", _f(BOLD, 58), WHITE)
    _center(d, 640, f"RM 100 = {per100} gram", _f(REG, 50), WHITE)
    _center(d, 740, trend, _f(BOLD, 52), GOLD)
    _center(d, 830, f"Terendah RM {low}   |   Tertinggi RM {high}", _f(REG, 32), WHITE)
    _footer(d, date_text)
    im.save(path)


def jewel_card(path, j, date_text):
    im, d = _bg()
    _center(d, 90, "HARGA EMAS PG JEWEL", _f(BOLD, 66), GOLD)
    _center(d, 185, "Harga per gram", _f(REG, 40), WHITE)
    # header jadual
    xs = [130, 400, 720]
    for x, t in zip(xs, ["Emas", "Jual", "Beli"]):
        d.text((x, 290), t, font=_f(BOLD, 48), fill=GOLD)
    d.line([(100, 360), (W - 100, 360)], fill=GOLD, width=3)
    for n, p in enumerate(["999", "916"]):
        y = 400 + n * 220
        d.text((xs[0], y), p, font=_f(BOLD, 80), fill=WHITE)
        d.text((xs[1], y), f"RM {j[p]['sell']:.0f}", font=_f(BOLD, 62), fill=GOLD_L)
        d.text((xs[2], y), f"RM {j[p]['buy']:.0f}", font=_f(BOLD, 62), fill=WHITE)
    _footer(d, date_text)
    im.save(path)

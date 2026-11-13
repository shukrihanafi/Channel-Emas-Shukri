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


def _bg(H=H, W=W):
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


def _chart(path, series, size=(1840, 690)):
    """Graf garis 30 hari gaya emas-merah; harga SETIAP hari dilabel pada graf."""
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm
    from matplotlib.colors import LinearSegmentedColormap

    for p in (BOLD, REG):
        try:
            fm.fontManager.addfont(p)
        except Exception:
            pass
    fam = fm.FontProperties(fname=BOLD).get_name() if os.path.exists(BOLD) else "DejaVu Sans"
    plt.rcParams["font.family"] = fam

    dates = [d for d, _ in series]
    y = np.array([v for _, v in series], float)
    x = np.arange(len(y))
    n = len(y)
    lo_i, hi_i = int(y.argmin()), int(y.argmax())
    span = max(y.max() - y.min(), 10)
    ymin, ymax = y.min() - span * 0.16, y.max() + span * 0.16

    gold, gold_l = "#E6B848", "#FFE28C"
    fig = plt.figure(figsize=(size[0] / 100, size[1] / 100), dpi=100)
    fig.patch.set_alpha(0)
    ax = fig.add_axes([0.04, 0.09, 0.95, 0.89])
    ax.set_facecolor("none")
    for s in ax.spines.values():
        s.set_visible(False)
    ax.grid(axis="y", color="white", alpha=0.13, lw=1, ls=(0, (4, 5)))
    ax.set_axisbelow(True)
    ax.tick_params(colors="#F2D9A0", length=0)
    ax.tick_params(axis="x", labelsize=13)
    ax.tick_params(axis="y", labelsize=15)
    ax.set_xticks(x)
    ax.set_xticklabels([d[8:10] + "/" + d[5:7] if len(d) == 10 and d[4] == "-" else d for d in dates])
    ax.yaxis.set_major_locator(plt.MaxNLocator(5, integer=True))

    grad = np.linspace(0, 1, 256).reshape(-1, 1)
    cm = LinearSegmentedColormap.from_list("g", [(0.9, 0.72, 0.28, 0.0), (0.9, 0.72, 0.28, 0.5)])
    im = ax.imshow(grad, extent=[x[0], x[-1], ymin, ymax], origin="lower", aspect="auto", cmap=cm, zorder=1)
    poly = ax.fill_between(x, y, ymin, facecolor="none", edgecolor="none")
    im.set_clip_path(poly.get_paths()[0], ax.transData)
    ax.set_xlim(-0.6, n - 0.4)
    ax.set_ylim(ymin, ymax)

    for lw, a in ((16, 0.06), (10, 0.10), (6, 0.16)):
        ax.plot(x, y, color=gold, lw=lw, alpha=a, zorder=2, solid_capstyle="round")
    ax.plot(x, y, color=gold_l, lw=3.6, zorder=3, solid_capstyle="round", solid_joinstyle="round")
    ax.scatter(x, y, s=34, color="#FFF4CF", zorder=4)

    # harga setiap hari: di atas titik jika puncak, di bawah jika lembah
    for i in range(n):
        left = y[i - 1] if i > 0 else y[i + 1]
        right = y[i + 1] if i < n - 1 else y[i - 1]
        up = y[i] >= left and y[i] >= right
        special = i in (hi_i, lo_i, n - 1)
        col = "#7CFFB2" if i == hi_i else "#FF9A9A" if i == lo_i else gold_l if i == n - 1 else "#FFF4CF"
        kw = dict(bbox=dict(boxstyle="round,pad=0.28", fc="#3a050b", ec=col, lw=1.5)) if special else {}
        ax.annotate(f"{y[i]:.0f}", (x[i], y[i]), xytext=(0, 15 if up else -24), textcoords="offset points",
                    ha="center", va="bottom" if up else "top", fontsize=16 if special else 14,
                    color=col, zorder=6, **kw)
    ax.scatter([x[hi_i]], [y[hi_i]], s=150, color="#7CFFB2", zorder=5, ec="white", lw=1.5)
    ax.scatter([x[lo_i]], [y[lo_i]], s=150, color="#FF8A8A", zorder=5, ec="white", lw=1.5)
    ax.scatter([x[-1]], [y[-1]], s=620, color=gold, alpha=0.25, zorder=4)
    ax.scatter([x[-1]], [y[-1]], s=200, color="white", ec=gold, lw=3, zorder=6)

    ax.text(0.5, 0.5, "shukriee.com", transform=ax.transAxes, ha="center", va="center",
            rotation=10, fontsize=110, color="white", alpha=0.06, zorder=0)
    fig.savefig(path, transparent=True)
    plt.close(fig)


def _right(d, y, text, font, fill, xr):
    w = d.textlength(text, font=font)
    d.text((xr - w, y), text, font=font, fill=fill)


def _trend(d, y, trend, xr):
    """Arah harga (segi tiga dilukis; fon tiada simbol) rapat ke kanan."""
    up, down = trend.startswith("▲"), trend.startswith("▼")
    label = trend[1:].strip() if (up or down) else trend
    f = _f(BOLD, 46)
    tw = d.textlength(label, font=f)
    if not (up or down):
        _right(d, y, label, f, WHITE, xr)
        return
    tri, gap = 34, 14
    x0 = xr - (tri + gap + tw)
    cy = y + 32
    col = (124, 255, 178) if up else (255, 138, 138)
    pts = [(x0, cy + tri / 2), (x0 + tri, cy + tri / 2), (x0 + tri / 2, cy - tri / 2)] if up else \
          [(x0, cy - tri / 2), (x0 + tri, cy - tri / 2), (x0 + tri / 2, cy + tri / 2)]
    d.polygon(pts, fill=col)
    d.text((x0 + tri + gap, y), label, font=f, fill=WHITE)


def _center_in(d, x0, w, y, text, font, fill):
    tw = d.textlength(text, font=font)
    d.text((x0 + (w - tw) / 2, y), text, font=font, fill=fill)


def gap_card(path, per_gram, per100, trend, low, high, date_text, series):
    """Kad 16:9 (1920x1080): harga semasa + graf 30 hari dengan harga harian + watermark Shukri."""
    CW, CH = 1920, 1080
    im, d = _bg(CH, CW)
    d.text((80, 50), "HARGA EMAS GAP", font=_f(BOLD, 74), fill=GOLD)
    d.text((82, 140), "Public Gold  |  Graf 30 Hari", font=_f(REG, 36), fill=WHITE)
    _right(d, 30, f"RM {per_gram:,.0f}", _f(BOLD, 128), GOLD_L, CW - 80)
    _trend(d, 160, trend, CW - 80)
    chart = os.path.join(os.path.dirname(path) or ".", "_chart.png")
    _chart(chart, series)
    ch = Image.open(chart).convert("RGBA")
    im.paste(ch, (40, 225), ch)
    d.text((80, 916), f"RM 100 = {per100} gram", font=_f(BOLD, 40), fill=WHITE)
    d.text((80, 966), f"Terendah RM {low}   |   Tertinggi RM {high}", font=_f(REG, 30), fill=GOLD_L)
    d.text((80, 1008), f"Dikemaskini: {date_text}", font=_f(REG, 24), fill=(240, 210, 150))
    w, h = 600, 96
    x0, y0 = CW - 80 - w, 940
    d.rounded_rectangle([x0, y0, x0 + w, y0 + h], 48, fill=(0, 0, 0), outline=GOLD, width=3)
    _center_in(d, x0, w, y0 + 8, "Shukri Hanafi (PG032390)", _f(BOLD, 34), WHITE)
    _center_in(d, x0, w, y0 + 50, "shukriee.com", _f(BOLD, 32), GOLD_L)
    im.save(path)


def jewel_card(path, j, date_text, nonpg=None):
    """Kad HARGA BARANG KEMAS ikut jadual rujukan (1080x1080)."""
    nonpg = nonpg or {}
    im, d = _bg()
    _center(d, 70, "HARGA BARANG KEMAS", _f(BOLD, 68), GOLD)
    _center(d, 160, "Public Gold  |  PG Jewel", _f(REG, 32), WHITE)
    xs = [60, 270, 480, 690, 1020]
    y0, y1, y2, y3, y4 = 240, 360, 440, 590, 740
    d.rectangle([xs[0], y0, xs[4], y4], outline=GOLD, width=4)
    d.line([(xs[1], y0), (xs[1], y4)], fill=GOLD, width=3)
    d.line([(xs[3], y0), (xs[3], y4)], fill=GOLD, width=3)
    d.line([(xs[2], y1), (xs[2], y4)], fill=GOLD, width=3)
    for y in (y1, y2, y3):
        d.line([(xs[0], y), (xs[4], y)], fill=GOLD, width=3)
    _center_in(d, xs[0], xs[1] - xs[0], y0 + 40, "EMAS", _f(BOLD, 32), WHITE)
    _center_in(d, xs[0], xs[1] - xs[0], y0 + 74, "JENAMA", _f(BOLD, 32), WHITE)
    _center_in(d, xs[1], xs[3] - xs[1], y0 + 38, "PUBLIC GOLD", _f(BOLD, 44), GOLD_L)
    _center_in(d, xs[3], xs[4] - xs[3], y0 + 24, "BUKAN PUBLIC GOLD", _f(BOLD, 28), (255, 170, 120))
    _center_in(d, xs[3], xs[4] - xs[3], y0 + 66, "(*NON-PG BUYBACK)", _f(BOLD, 28), (255, 170, 120))
    _center_in(d, xs[0], xs[1] - xs[0], y1 + 22, "KETULENAN", _f(BOLD, 28), WHITE)
    _center_in(d, xs[1], xs[2] - xs[1], y1 + 20, "PG JUAL", _f(BOLD, 34), GOLD)
    _center_in(d, xs[2], xs[3] - xs[2], y1 + 20, "PG BELI", _f(BOLD, 34), GOLD)
    _center_in(d, xs[3], xs[4] - xs[3], y1 + 20, "PG BELI", _f(BOLD, 34), GOLD)
    for n, p in enumerate(["999", "916"]):
        yy = (y2 if n == 0 else y3) + 38
        _center_in(d, xs[0], xs[1] - xs[0], yy - 4, p, _f(BOLD, 64), WHITE)
        _center_in(d, xs[1], xs[2] - xs[1], yy + 4, f"RM {j[p]['sell']:.0f}", _f(BOLD, 46), GOLD_L)
        _center_in(d, xs[2], xs[3] - xs[2], yy + 4, f"RM {j[p]['buy']:.0f}", _f(BOLD, 46), WHITE)
        v = nonpg.get(p)
        _center_in(d, xs[3], xs[4] - xs[3], yy + 4, f"RM {v:.0f}" if v else "-", _f(BOLD, 50), (255, 170, 120))
    _center(d, 775, "*Nota : Non-PG Buyback ialah harga Public Gold", _f(REG, 28), WHITE)
    _center(d, 813, "tawarkan untuk membeli emas jenama lain.", _f(REG, 28), WHITE)
    _center(d, 868, "Harga per gram", _f(REG, 26), GOLD_L)
    _footer(d, date_text)
    im.save(path)


def item_card(path, product_img, title, name, price, weight, purity, date_text):
    """Kad item (1080x1080, 1:1) dengan gambar produk BESAR."""
    im, d = _bg()
    _center(d, 50, title, _f(BOLD, 48), GOLD)
    box = 560
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(ov).rounded_rectangle([100, 130, W - 100, 130 + box + 10], 28, fill=(255, 255, 255, 70))
    im = Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")
    d = ImageDraw.Draw(im)
    if product_img:
        try:
            pi = Image.open(product_img).convert("RGBA")
            # buang latar putih yang bersambung dengan tepi imej (supaya serasi dengan box lutsinar)
            rgb = Image.alpha_composite(Image.new("RGBA", pi.size, (255, 255, 255, 255)), pi).convert("RGB")
            for pt in [(0, 0), (pi.width - 1, 0), (0, pi.height - 1), (pi.width - 1, pi.height - 1)]:
                if min(rgb.getpixel(pt)) > 235:
                    ImageDraw.floodfill(rgb, pt, (255, 0, 255), thresh=28)
            px, mpx = rgb.load(), pi.load()
            for yy in range(pi.height):
                for xx in range(pi.width):
                    if px[xx, yy] == (255, 0, 255):
                        mpx[xx, yy] = (255, 255, 255, 0)
            bg = Image.new("RGBA", pi.size, (255, 255, 255, 255))
            flat = Image.alpha_composite(bg, pi).convert("L").point(lambda v: 255 if v < 238 else 0)
            bb = flat.getbbox()
            if bb:  # buang ruang kosong sekeliling produk supaya produk memenuhi box
                m = 4
                pi = pi.crop((max(0, bb[0] - m), max(0, bb[1] - m), min(pi.width, bb[2] + m), min(pi.height, bb[3] + m)))
            sc = min(840 / pi.width, (box - 10) / pi.height)
            pi = pi.resize((max(1, int(pi.width * sc)), max(1, int(pi.height * sc))), Image.LANCZOS)
            cx, cy = (W - pi.width) // 2, 135 + (box - pi.height) // 2
            im.paste(pi, (cx, cy), pi)
        except Exception as e:
            print("Gambar produk gagal:", e)
    f = _f(BOLD, 36)
    words, lines, cur = name.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) > W - 120 and cur:
            lines.append(cur); cur = w
        else:
            cur = t
    lines.append(cur)
    y = 728
    for ln in lines[:2]:
        _center(d, y, ln, f, WHITE)
        y += 42
    _center(d, 805, f"RM {price:,.0f}", _f(BOLD, 84), GOLD_L)
    info = "   |   ".join(x for x in [f"Berat {weight}" if weight else "", f"Ketulenan {purity}" if purity else ""] if x)
    if info:
        _center(d, 907, info, _f(REG, 30), WHITE)
    _center(d, 947, f"Dikemaskini: {date_text}", _f(REG, 24), GOLD_L)
    w, h = 280, 42
    x0 = (W - w) / 2
    d.rounded_rectangle([x0, 985, x0 + w, 985 + h], 23, outline=GOLD, fill=(0, 0, 0), width=3)
    _center(d, 991, "shukriee.com", _f(BOLD, 25), WHITE)
    im.save(path)


def buy_card(path, j, nonpg, date_text):
    """Kad HARGA PG BELI BARANG KEMAS (1080x1080): PUBLIC GOLD vs BUKAN PUBLIC GOLD (*NON-PG BUYBACK)."""
    nonpg = nonpg or {}
    im, d = _bg()
    _center(d, 70, "HARGA PG BELI", _f(BOLD, 72), GOLD)
    _center(d, 156, "BARANG KEMAS", _f(BOLD, 56), GOLD)
    xs = [60, 340, 700, 1020]
    y0, y1, y2, y3, y4 = 260, 400, 490, 640, 790
    d.rectangle([xs[0], y0, xs[3], y4], outline=GOLD, width=4)
    for x in (xs[1], xs[2]):
        d.line([(x, y0), (x, y4)], fill=GOLD, width=3)
    for y in (y1, y2, y3):
        d.line([(xs[0], y), (xs[3], y)], fill=GOLD, width=3)
    _center_in(d, xs[0], xs[1] - xs[0], y0 + 52, "EMAS JENAMA", _f(BOLD, 32), WHITE)
    _center_in(d, xs[1], xs[2] - xs[1], y0 + 52, "PUBLIC GOLD", _f(BOLD, 40), GOLD_L)
    _center_in(d, xs[2], xs[3] - xs[2], y0 + 26, "BUKAN PUBLIC GOLD", _f(BOLD, 28), (255, 170, 120))
    _center_in(d, xs[2], xs[3] - xs[2], y0 + 66, "(*NON-PG BUYBACK)", _f(BOLD, 28), (255, 170, 120))
    _center_in(d, xs[0], xs[1] - xs[0], y1 + 26, "KETULENAN", _f(BOLD, 28), WHITE)
    _center_in(d, xs[1], xs[2] - xs[1], y1 + 22, "PG BELI", _f(BOLD, 36), GOLD)
    _center_in(d, xs[2], xs[3] - xs[2], y1 + 22, "PG BELI", _f(BOLD, 36), GOLD)
    for n, p in enumerate(["999", "916"]):
        yy = (y2 if n == 0 else y3) + 42
        _center_in(d, xs[0], xs[1] - xs[0], yy - 6, p, _f(BOLD, 64), WHITE)
        _center_in(d, xs[1], xs[2] - xs[1], yy + 2, f"RM {j[p]['buy']:.0f}", _f(BOLD, 54), GOLD_L)
        v = nonpg.get(p)
        _center_in(d, xs[2], xs[3] - xs[2], yy + 2, f"RM {v:.0f}" if v else "-", _f(BOLD, 54), (255, 170, 120))
    _center(d, 808, "*Nota : Non-PG Buyback ialah harga Public Gold", _f(REG, 28), WHITE)
    _center(d, 846, "tawarkan untuk membeli emas jenama lain.", _f(REG, 28), WHITE)
    _center(d, 884, "Harga per gram", _f(REG, 24), GOLD_L)
    _footer(d, date_text)
    im.save(path)

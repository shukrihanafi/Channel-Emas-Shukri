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


def _bg(H=H):
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


def _chart(path, series, size=(1000, 600)):
    """Graf garis 30 hari gaya emas-merah dengan gradien, cahaya dan penanda."""
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
    lo_i, hi_i = int(y.argmin()), int(y.argmax())
    ymin, ymax = y.min() - 7, y.max() + 10

    gold, gold_l = "#E6B848", "#FFE28C"
    fig = plt.figure(figsize=(size[0] / 100, size[1] / 100), dpi=100)
    fig.patch.set_alpha(0)
    ax = fig.add_axes([0.075, 0.1, 0.9, 0.86])
    ax.set_facecolor("none")
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xlim(-0.4, len(y) - 0.4)
    ax.set_ylim(ymin, ymax)
    ax.grid(axis="y", color="white", alpha=0.13, lw=1, ls=(0, (4, 5)))
    ax.set_axisbelow(True)
    ax.tick_params(colors="#F2D9A0", labelsize=13, length=0)
    step = 5
    ticks = list(range(len(y) - 1, -1, -step))[::-1]
    ax.set_xticks(ticks)
    ax.set_xticklabels([dates[i][8:10] + "/" + dates[i][5:7] for i in ticks])
    ax.yaxis.set_major_locator(plt.MaxNLocator(5, integer=True))

    # gradien di bawah garis
    grad = np.linspace(0, 1, 256).reshape(-1, 1)
    cm = LinearSegmentedColormap.from_list("g", [(0.9, 0.72, 0.28, 0.0), (0.9, 0.72, 0.28, 0.5)])
    im = ax.imshow(grad, extent=[x[0], x[-1], ymin, ymax], origin="lower", aspect="auto", cmap=cm, zorder=1)
    poly = ax.fill_between(x, y, ymin, facecolor="none", edgecolor="none")
    im.set_clip_path(poly.get_paths()[0], ax.transData)
    ax.set_xlim(-0.4, len(y) - 0.4)
    ax.set_ylim(ymin, ymax)

    # cahaya + garis
    for lw, a in ((16, 0.06), (10, 0.10), (6, 0.16)):
        ax.plot(x, y, color=gold, lw=lw, alpha=a, zorder=2, solid_capstyle="round")
    ax.plot(x, y, color=gold_l, lw=3.6, zorder=3, solid_capstyle="round", solid_joinstyle="round")
    ax.scatter(x, y, s=16, color="#FFF4CF", zorder=4)

    def tag(i, text, color, dy):
        ax.annotate(text, (x[i], y[i]), xytext=(0, dy), textcoords="offset points", ha="center",
                    fontsize=15, color=color, zorder=6,
                    bbox=dict(boxstyle="round,pad=0.35", fc="#3a050b", ec=color, lw=1.4))
    ax.scatter([x[hi_i]], [y[hi_i]], s=110, color="#7CFFB2", zorder=5, ec="white", lw=1.5)
    ax.scatter([x[lo_i]], [y[lo_i]], s=110, color="#FF8A8A", zorder=5, ec="white", lw=1.5)
    tag(hi_i, f"{y[hi_i]:.0f}", "#7CFFB2", 22)
    tag(lo_i, f"{y[lo_i]:.0f}", "#FF9A9A", -34)
    # titik terkini
    ax.scatter([x[-1]], [y[-1]], s=520, color=gold, alpha=0.25, zorder=4)
    ax.scatter([x[-1]], [y[-1]], s=170, color="white", ec=gold, lw=3, zorder=6)
    if len(y) - 1 not in (hi_i, lo_i):
        tag(len(y) - 1, f"{y[-1]:.0f}", gold_l, 24)

    # watermark halus dalam graf
    ax.text(0.5, 0.5, "shukriee.com", transform=ax.transAxes, ha="center", va="center",
            rotation=18, fontsize=64, color="white", alpha=0.07, zorder=0)
    fig.savefig(path, transparent=True)
    plt.close(fig)


def _trend(d, y, trend):
    """Teks arah harga dengan segi tiga dilukis (fon tiada simbol ▲▼)."""
    up, down = trend.startswith("▲"), trend.startswith("▼")
    label = trend[1:].strip() if (up or down) else trend
    f = _f(BOLD, 44)
    tw = d.textlength(label, font=f)
    if not (up or down):
        _center(d, y, label, f, WHITE)
        return
    tri, gap = 34, 16
    x0 = (W - (tri + gap + tw)) / 2
    cy = y + 30
    col = (124, 255, 178) if up else (255, 138, 138)
    pts = [(x0, cy + tri / 2), (x0 + tri, cy + tri / 2), (x0 + tri / 2, cy - tri / 2)] if up else \
          [(x0, cy - tri / 2), (x0 + tri, cy - tri / 2), (x0 + tri / 2, cy + tri / 2)]
    d.polygon(pts, fill=col)
    d.text((x0 + tri + gap, y), label, font=f, fill=WHITE)


def gap_card(path, per_gram, per100, trend, low, high, date_text, series):
    """Kad 1080x1350: harga semasa + graf 30 hari + watermark Shukri."""
    H2 = 1350
    im, d = _bg(H2)
    _center(d, 70, "HARGA EMAS GAP", _f(BOLD, 76), GOLD)
    _center(d, 165, "Public Gold  |  Graf 30 Hari", _f(REG, 36), WHITE)
    _center(d, 225, f"RM {per_gram:,.0f}", _f(BOLD, 150), GOLD_L)
    _trend(d, 405, trend)
    chart = os.path.join(os.path.dirname(path) or ".", "_chart.png")
    _chart(chart, series)
    im.paste(Image.open(chart).convert("RGBA"), (40, 470), Image.open(chart).convert("RGBA"))
    _center(d, 1085, f"RM 100 = {per100} gram", _f(BOLD, 40), WHITE)
    _center(d, 1138, f"Terendah RM {low}   |   Tertinggi RM {high}", _f(REG, 30), GOLD_L)
    _center(d, 1182, f"Dikemaskini: {date_text}", _f(REG, 26), (240, 210, 150))
    w, h = 640, 90
    x0 = (W - w) / 2
    d.rounded_rectangle([x0, 1218, x0 + w, 1218 + h], 45, fill=(0, 0, 0), outline=GOLD, width=3)
    _center(d, 1223, "Shukri Hanafi (PG032390)", _f(BOLD, 34), WHITE)
    _center(d, 1263, "shukriee.com", _f(BOLD, 30), GOLD_L)
    im.save(path)


def jewel_card(path, j, date_text):
    im, d = _bg()
    _center(d, 80, "HARGA EMAS PG JEWEL", _f(BOLD, 66), GOLD)
    _center(d, 165, "(BARANG KEMAS)", _f(BOLD, 52), GOLD_L)
    _center(d, 235, "Harga per gram", _f(REG, 36), WHITE)
    # header jadual
    xs = [130, 400, 720]
    for x, t in zip(xs, ["Emas", "Jual", "Beli"]):
        d.text((x, 310), t, font=_f(BOLD, 48), fill=GOLD)
    d.line([(100, 375), (W - 100, 375)], fill=GOLD, width=3)
    for n, p in enumerate(["999", "916"]):
        y = 420 + n * 210
        d.text((xs[0], y), p, font=_f(BOLD, 80), fill=WHITE)
        d.text((xs[1], y), f"RM {j[p]['sell']:.0f}", font=_f(BOLD, 62), fill=GOLD_L)
        d.text((xs[2], y), f"RM {j[p]['buy']:.0f}", font=_f(BOLD, 62), fill=WHITE)
    _footer(d, date_text)
    im.save(path)

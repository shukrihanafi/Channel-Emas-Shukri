"""Testimoni: ambil siaran #testimoni (gambar perbualan WhatsApp) dari Telegram Channel awam, tutup tarikh/masa dengan
watermark shukriee.com, kemudian hantar. Mod `testimoni` (semua tempat) atau `testimoni-test` (Telegram peribadi sahaja)."""
import html
import io
import os
import random
import re
import sys

import requests

CHANNEL = "kenaliemas"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
_HERE = os.path.dirname(os.path.abspath(__file__))
FONT = next((p for p in (os.path.join(_HERE, "Poppins-Bold.ttf"), os.path.join(_HERE, "fonts", "Poppins-Bold.ttf")) if os.path.exists(p)), "DejaVuSans-Bold.ttf")
MONTHS = r"(jan|feb|mac|mar|apr|mei|may|jun|jul|ogo|aug|sep|okt|oct|nov|dis|dec)[a-z]*"
AMPM_RE = re.compile(r"^(a\.?m\.?|p\.?m\.?)$", re.I)
DATE_RES = [
    re.compile(r"^\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}$"),
    re.compile(r"^\d{4}[/\-]\d{1,2}[/\-]\d{1,2}$"),
    re.compile(r"^" + MONTHS + r"[,.]?$", re.I),
    re.compile(r"^(today|yesterday|hari|semalam|isnin|selasa|rabu|khamis|jumaat|sabtu|ahad|monday|tuesday|wednesday|thursday|friday|saturday|sunday)[,.]?$", re.I),
]


def _clean_caption(raw):
    t = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    t = html.unescape(re.sub(r"<[^>]+>", "", t)).strip()
    lines = [ln for ln in t.split("\n")]
    while lines and (not lines[-1].strip() or re.fullmatch(r"(\s*#\w+)+\s*", lines[-1])):
        lines.pop()  # buang baris hashtag di hujung
    return "\n".join(lines).strip()


def _parse_page(text):
    out = []
    for b in re.split(r'(?=<div class="tgme_widget_message_wrap)', text)[1:]:
        m = re.search(r'data-post="%s/(\d+)"' % CHANNEL, b)
        if not m:
            continue
        photos = re.findall(r"tgme_widget_message_photo_wrap[^>]*background-image:url\('([^']+)'\)", b)
        tx = re.search(r'(?s)<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', b)
        raw = tx.group(1) if tx else ""
        plain = html.unescape(re.sub(r"<[^>]+>", "", raw)).lower()
        out.append({"id": int(m.group(1)), "photos": photos, "raw": raw, "tag": "#testimoni" in plain})
    return out


def _get_page(before=None):
    url = f"https://t.me/s/{CHANNEL}" + (f"?before={before}" if before else "")
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    return _parse_page(r.text)


def list_posts(used=(), forced=None, want=6, tries=30):
    """Siaran #testimoni berserta gambar. Carian Telegram tidak lengkap, jadi halaman saluran diambil pada kedudukan rawak
    (20 siaran setiap halaman) sehingga cukup calon yang belum digunakan. forced = nombor siaran tertentu (ujian)."""
    if forced:
        ps = [p for p in _get_page(int(forced) + 1) if p["id"] == int(forced)]
    else:
        maxid = max(p["id"] for p in _get_page())
        ps, seen = [], set()
        for _ in range(tries):
            for p in _get_page(random.randint(40, maxid)):
                if p["id"] not in seen:
                    seen.add(p["id"])
                    ps.append(p)
            ok = [p for p in ps if p["tag"] and p["photos"] and f"{p['id']}#0" not in used]
            if len(ok) >= want:
                break
    return [{"key": str(p["id"]), "text": _clean_caption(p["raw"]), "photos": p["photos"]} for p in ps if p["tag"] and p["photos"]]


def _to_pil(content):
    from PIL import Image
    return Image.open(io.BytesIO(content)).convert("RGB")


def _ocr_words(img):
    """Perkataan OCR: [(teks, x0, y0, x1, y1)] dalam piksel gambar asal."""
    import pytesseract
    from PIL import ImageOps
    scale = 3 if img.width < 1400 else 2
    big = ImageOps.grayscale(img.resize((img.width * scale, img.height * scale)))
    words = []
    for v in (big, ImageOps.invert(big)):  # teks cerah atas latar gelap dan sebaliknya
        try:
            d = pytesseract.image_to_data(v, config="--psm 11 -l eng", output_type=pytesseract.Output.DICT)
        except Exception as e:
            print("OCR gagal:", str(e)[:100])
            continue
        for i in range(len(d["text"])):
            t = (d["text"][i] or "").strip()
            if t and float(d["conf"][i]) >= 30:
                x, y, w, h = d["left"][i], d["top"][i], d["width"][i], d["height"][i]
                words.append((t, x / scale, y / scale, (x + w) / scale, (y + h) / scale))
    return words


_MON = r"(?:jan|feb|mac|mar|apr|mei|may|jun|jul|ogo|aug|sep|okt|oct|nov|dis|dec)[a-z]*\.?"
DATE_PATTERNS = [
    re.compile(r"\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}"),
    re.compile(r"\d{4}[/\-]\d{1,2}[/\-]\d{1,2}"),
    re.compile(r"\d{1,2}\s*" + _MON + r"\s*,?\s*(?:20\d\d)?", re.I),
    re.compile(_MON + r"\s*\d{1,2}\s*,?\s*(?:20\d\d)?", re.I),
    re.compile(_MON + r"\s*,?\s*20\d\d", re.I),
]
LEAD_RE = re.compile(r"^(today|yesterday|hari\s*ini|semalam|last|updated|update|dikemaskini|tarikh|date)[:,.]*$", re.I)


def find_dates(words):
    """Cari tarikh (bukan masa) dalam senarai perkataan OCR. Kembalikan kotak [(x0,y0,x1,y1)]; masa jam tidak ditutup."""
    rows = []
    for w in sorted(words, key=lambda w: (w[2] + w[4]) / 2):
        cy, h = (w[2] + w[4]) / 2, w[4] - w[2]
        for r in rows:
            if abs(r["cy"] - cy) < max(h, r["h"]) * 0.6:
                r["w"].append(w)
                break
        else:
            rows.append({"cy": cy, "h": h, "w": [w]})
    boxes = []
    for r in rows:
        ws = sorted(r["w"], key=lambda w: w[1])
        uniq = []
        for w in ws:  # buang pendua (dua variasi OCR) pada kedudukan hampir sama
            if not any(abs(w[1] - u[1]) < 4 and w[0].lower() == u[0].lower() for u in uniq):
                uniq.append(w)
        ws = uniq
        text, spans = "", []
        for w in ws:
            spans.append((len(text), len(text) + len(w[0]), w))
            text += w[0] + " "
        for rx in DATE_PATTERNS:
            for m in rx.finditer(text):
                if not re.search(r"[A-Za-z]{3}|\d{1,2}[/.\-]\d", m.group(0)):
                    continue
                hit = [w for s0, e0, w in spans if s0 < m.end() and e0 > m.start()]
                if not hit:
                    continue
                i0 = ws.index(hit[0])
                while i0 > 0 and LEAD_RE.match(ws[i0 - 1][0]):  # "Today," / "Last updated:" di hadapan tarikh
                    i0 -= 1
                grp = ws[i0: ws.index(hit[-1]) + 1]
                boxes.append([min(g[1] for g in grp), min(g[2] for g in grp), max(g[3] for g in grp), max(g[4] for g in grp)])
    merged = []
    for b in sorted(boxes):
        for m in merged:
            if b[0] < m[2] and b[2] > m[0] and b[1] < m[3] and b[3] > m[1]:
                m[:] = [min(m[0], b[0]), min(m[1], b[1]), max(m[2], b[2]), max(m[3], b[3])]
                break
        else:
            merged.append(list(b))
    return merged


def find_boxes(img):
    """Kembalikan (kotak_tarikh, semua_perkataan)."""
    words = _ocr_words(img)
    return find_dates(words), words


def center_watermark(img, words, text="shukriee.com"):
    """Tiada tarikh: letak watermark lutsinar di tengah, di jalur mendatar yang paling kurang tulisan."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    W, H = img.size
    fs = max(16, int(W * 0.07))
    font = ImageFont.truetype(FONT, fs)
    tw = ImageDraw.Draw(img).textlength(text, font=font)
    th = fs * 1.3
    g = np.asarray(img.convert("L")).astype(float)
    gm = np.abs(np.diff(g, axis=1))[:-1, :] + np.abs(np.diff(g, axis=0))[:, :-1]  # tenaga tepi: tinggi di tempat ada tulisan
    best = None
    for k in range(0, 61):
        cy = H * (0.22 + 0.56 * k / 60)
        y0, y1, x0, x1 = int(max(0, cy - th / 2)), int(min(H - 2, cy + th / 2)), int(max(0, (W - tw) / 2)), int(min(W - 2, (W + tw) / 2))
        ov = sum(max(0, min(x1, w[3]) - max(x0, w[1])) * max(0, min(y1, w[4]) - max(y0, w[2])) for w in words) / max(1, (x1 - x0) * (y1 - y0))
        edge = float(gm[y0:y1, x0:x1].mean()) if y1 > y0 and x1 > x0 else 999
        score = edge + ov * 200 + abs(cy - H / 2) / H * 6  # utamakan tengah jika sama
        if best is None or score < best[0]:
            best = (score, cy)
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(lay).text((W / 2, best[1]), text, font=font, fill=(255, 255, 255, 135), anchor="mm",
                             stroke_width=max(1, fs // 14), stroke_fill=(0, 0, 0, 110))
    return Image.alpha_composite(img.convert("RGBA"), lay).convert("RGB")


def cover(img, boxes, text=None):
    """Padam tarikh: isi kotak dengan warna latar sekeliling (tiada tulisan; watermark diletak berasingan)."""
    import numpy as np
    from PIL import ImageDraw
    arr = np.asarray(img).astype(int)
    d = ImageDraw.Draw(img)
    for x0, y0, x1, y1 in boxes:
        pad = max(2, (y1 - y0) * 0.25)
        x0, y0, x1, y1 = int(x0 - pad), int(y0 - pad), int(x1 + pad), int(y1 + pad)
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(img.width, x1), min(img.height, y1)
        r = 4
        ring = np.concatenate([
            arr[max(0, y0 - r):y0, x0:x1].reshape(-1, 3), arr[y1:y1 + r, x0:x1].reshape(-1, 3),
            arr[y0:y1, max(0, x0 - r):x0].reshape(-1, 3), arr[y0:y1, x1:x1 + r].reshape(-1, 3)])
        bg = tuple(int(v) for v in (np.median(ring, axis=0) if len(ring) else (30, 30, 30)))
        d.rectangle([x0, y0, x1, y1], fill=bg)
    return img


def fit_ratio(img):
    """Instagram: nisbah 4:5 hingga 1.91:1. Tambah kanvas gelap jika terlalu tinggi/lebar; hasil JPEG sesuai semua platform."""
    from PIL import Image
    w, h = img.size
    ratio = w / h
    if ratio < 0.8:
        nw = int(h * 0.8)
        can = Image.new("RGB", (nw, h), (11, 20, 26))
        can.paste(img, ((nw - w) // 2, 0))
        img = can
    elif ratio > 1.91:
        nh = int(w / 1.91)
        can = Image.new("RGB", (w, nh), (11, 20, 26))
        can.paste(img, (0, (nh - h) // 2))
        img = can
    if img.width > 1440:
        img = img.resize((1440, int(img.height * 1440 / img.width)))
    return img


def run(st, send, dt, out="out", notify=print):
    n = st.setdefault("testi", {"used": []})
    test = getattr(sys.modules.get("__main__"), "CURRENT_MODE", "").endswith("-test")
    try:
        _f = os.getenv("NEWS_URL", "").strip().lstrip("#")
        posts = list_posts(n["used"], _f if (test and _f.isdigit()) else None)
    except Exception as e:
        print("Senarai testimoni gagal:", str(e)[:200])
        notify("⚠️ Testimoni: gagal baca saluran @kenaliemas: " + str(e)[:120])
        return
    # senarai gambar: (kunci unik, teks, url)
    items = [(f"{p['key']}#{i}", p["text"], u) for p in posts for i, u in enumerate(p["photos"][:1])]
    print(f"Testimoni dijumpai: {len(items)} (gambar), sudah digunakan: {len(n['used'])}")
    if not items:
        notify("⚠️ Tiada siaran #testimoni berserta gambar ditemui di @kenaliemas.")
        return
    fresh = [i for i in items if i[0] not in n["used"]]
    if not fresh:  # semua sudah dikitar: mula pusingan baharu
        print("Semua testimoni sudah dihantar: mula pusingan baharu.")
        n["used"] = []
        fresh = items
    random.shuffle(fresh)
    os.makedirs(out, exist_ok=True)
    for key, text, url in fresh[:8]:
        try:
            r = requests.get(url, headers=UA, timeout=60)
            r.raise_for_status()
            img = _to_pil(r.content)
            boxes, words = find_boxes(img)
        except Exception as e:
            print(f"Testimoni {key} dilangkau: {str(e)[:120]}")
            continue
        if boxes:  # tarikh dibuang terus: ditutup dengan watermark shukriee.com
            img = cover(img, boxes)
        img = center_watermark(img, words)  # watermark lutsinar di tengah, jalur yang tak ganggu tulisan (masa jam tidak ditutup)
        img = fit_ratio(img)
        path = f"{out}/testimoni.jpg"
        img.save(path, "JPEG", quality=92)
        print(f"Testimoni dipilih: {key} (tarikh ditutup: {len(boxes)})")
        cap = text or "Terima kasih atas kepercayaan anda."
        if "shukriee.com" not in cap.lower():
            cap += "\n\nKlik shukriee.com untuk simpan emas!"
        send(cap, path, "testimoni", closing=False)
        if not test:
            n["used"] = (n["used"] + [key])[-400:]
        return
    notify("⚠️ Testimoni: tiada gambar berjaya diproses. Tiada hantaran.")

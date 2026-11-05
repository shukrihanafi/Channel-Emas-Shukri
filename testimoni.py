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
FONT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "Poppins-Bold.ttf")
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


def list_posts(max_pages=6):
    """Semua siaran #testimoni yang ada gambar: [{key, text, photos:[url]}], paling baharu dahulu."""
    out, before = [], None
    for _ in range(max_pages):
        url = f"https://t.me/s/{CHANNEL}?q=%23testimoni" + (f"&before={before}" if before else "")
        r = requests.get(url, headers=UA, timeout=30)
        r.raise_for_status()
        blocks = re.split(r'(?=<div class="tgme_widget_message_wrap)', r.text)[1:]
        ids = []
        for b in blocks:
            m = re.search(r'data-post="%s/(\d+)"' % CHANNEL, b)
            if not m:
                continue
            pid = int(m.group(1))
            ids.append(pid)
            photos = re.findall(r"tgme_widget_message_photo_wrap[^>]*background-image:url\('([^']+)'\)", b)
            tx = re.search(r'(?s)<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', b)
            raw = tx.group(1) if tx else ""
            if photos and "#testimoni" in html.unescape(re.sub(r"<[^>]+>", "", raw)).lower():
                out.append({"key": str(pid), "text": _clean_caption(raw), "photos": photos})
        if not ids or len(ids) < 2:
            break
        nb = min(ids)
        if nb == before:
            break
        before = nb
    seen, res = set(), []
    for p in sorted(out, key=lambda x: -int(x["key"])):
        if p["key"] not in seen:
            seen.add(p["key"])
            res.append(p)
    return res


def _to_pil(content):
    from PIL import Image
    return Image.open(io.BytesIO(content)).convert("RGB")


def find_boxes(img):
    """Cari kotak masa & tarikh dalam gambar dengan OCR. Kembalikan senarai (x0,y0,x1,y1) dalam piksel gambar asal."""
    import pytesseract
    from PIL import ImageOps
    scale = 3 if img.width < 1400 else 2
    big = img.resize((img.width * scale, img.height * scale))
    variants = [ImageOps.grayscale(big), ImageOps.invert(ImageOps.grayscale(big))]
    boxes = []
    for v in variants:
        try:
            d = pytesseract.image_to_data(v, config="--psm 11 -l eng", output_type=pytesseract.Output.DICT)
        except Exception as e:
            print("OCR gagal:", str(e)[:100])
            continue
        n = len(d["text"])
        words = []
        for i in range(n):
            t = (d["text"][i] or "").strip()
            if not t or float(d["conf"][i]) < 30:
                continue
            words.append((t, d["left"][i], d["top"][i], d["width"][i], d["height"][i]))
        for idx, (t, x, y, w, h) in enumerate(words):
            t0 = t.strip("✓✔√ ")
            box = None
            # masa: 6:55, 6:55pm, 6:55 pm, 18:55
            mt = re.match(r"^\(?(\d{1,2})[:.](\d{2})\s*([ap]\.?m\.?)?\)?$", t0, re.I)
            if mt:
                hh, mm, ap = int(mt.group(1)), int(mt.group(2)), mt.group(3)
                valid = mm < 60 and ((ap and 1 <= hh <= 12) or (not ap and hh <= 23 and len(mt.group(1)) == 2) or (not ap and 1 <= hh <= 12))
                if valid and not (hh == 0 and not ap and len(mt.group(1)) == 1):
                    box = [x, y, x + w, y + h]
                    if not ap:  # am/pm sebagai perkataan berasingan di sebelah kanan, baris sama
                        for t2, x2, y2, w2, h2 in words[idx + 1: idx + 3]:
                            if AMPM_RE.match(t2.strip()) and abs(y2 - y) < h and 0 <= x2 - (x + w) < h * 2:
                                box[2] = x2 + w2
                                box[1] = min(box[1], y2)
                                box[3] = max(box[3], y2 + h2)
                                break
            elif any(rx.match(t0) for rx in DATE_RES):
                # tarikh: gabung perkataan berjiran (contoh "11 Oct 2025")
                box = [x, y, x + w, y + h]
                for t2, x2, y2, w2, h2 in words[max(0, idx - 2): idx + 4]:
                    if (t2, x2, y2) != (t, x, y) and abs(y2 - y) < h and abs((x2 + w2 / 2) - (box[0] + box[2]) / 2) < h * 10 and \
                            (re.match(r"^\d{1,4}[,.]?$", t2) or re.match(r"^" + MONTHS + r"[,.]?$", t2, re.I)):
                        box = [min(box[0], x2), min(box[1], y2), max(box[2], x2 + w2), max(box[3], y2 + h2)]
                if re.match(r"^" + MONTHS, t0, re.I):  # nama bulan: hari di kiri dan tahun di kanan mungkin tidak dibaca OCR
                    box[0] -= h * 2.4
                    box[2] += h * 3.4
            if box:
                boxes.append([c / scale for c in box])
        if boxes:
            break  # variasi pertama sudah berjumpa: cukup
    # gabung kotak bertindih
    merged = []
    for b in sorted(boxes):
        for m in merged:
            if b[0] < m[2] and b[2] > m[0] and b[1] < m[3] and b[3] > m[1]:
                m[:] = [min(m[0], b[0]), min(m[1], b[1]), max(m[2], b[2]), max(m[3], b[3])]
                break
        else:
            merged.append(list(b))
    return merged


def cover(img, boxes, text="shukriee.com"):
    """Tutup setiap kotak dengan warna latar sekeliling dan tulis watermark di atasnya."""
    import numpy as np
    from PIL import ImageDraw, ImageFont
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
        # tulisan masa lazimnya di sudut kanan-bawah gelembung: lebarkan ke kiri jika latar rata
        w0, h0 = x1 - x0, y1 - y0
        fs = max(8, int(h0 * 0.62))
        font = ImageFont.truetype(FONT, fs)
        tw = d.textlength(text, font=font)
        need = int(tw + 2 * pad) - w0
        if need > 0:
            lx = max(0, x0 - need)
            strip = arr[y0:y1, lx:x0]
            if strip.size and strip.reshape(-1, 3).std(axis=0).max() < 14:
                x0 = lx
            else:  # tidak muat: kecilkan huruf
                fs = max(7, int(fs * (w0 - pad) / max(tw, 1)))
                font = ImageFont.truetype(FONT, fs)
                tw = d.textlength(text, font=font)
        d.rectangle([x0, y0, x1, y1], fill=bg)
        lum = 0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]
        col = (255, 255, 255) if lum < 140 else (25, 25, 25)
        d.text(((x0 + x1 - tw) / 2, (y0 + y1) / 2), text, font=font, fill=col, anchor="lm")
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
    posts = list_posts()
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
            boxes = find_boxes(img)
        except Exception as e:
            print(f"Testimoni {key} dilangkau: {str(e)[:120]}")
            continue
        if not boxes:
            print(f"Testimoni {key}: tiada masa/tarikh dikesan, dilangkau (takut masa masih nampak)")
            continue
        img = fit_ratio(cover(img, boxes))
        path = f"{out}/testimoni.jpg"
        img.save(path, "JPEG", quality=92)
        print(f"Testimoni dipilih: {key} ({len(boxes)} kawasan ditutup)")
        cap = text or "Terima kasih atas kepercayaan anda."
        if "shukriee.com" not in cap.lower():
            cap += "\n\nKlik shukriee.com untuk simpan emas!"
        send(cap, path, "testimoni", closing=False)
        if not test:
            n["used"] = (n["used"] + [key])[-400:]
        return
    notify("⚠️ Testimoni: tiada gambar yang masa/tarikhnya berjaya dikesan untuk ditutup. Tiada hantaran.")

"""Kata semangat harian (7:09 pagi): skrip 1-100 berturutan, kitar semula. Gambar 1080x1080 merah-emas,
pose Shukri di kiri (dipilih ikut ayat, tidak ulang pose terkini), ayat di tengah/kanan. Tiada AI, tiada kos Claude."""
import os, re
from PIL import Image
import card

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "semangat_data.txt")
POSES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "poses")
W = H = 1080

# pose 1-20 -> kata kunci (huruf kecil)
KEY = {
    1: ["jangan", "anda", "siapa", "sendiri"],
    2: ["betul", "setuju", "baik", "terbaik", "yakin", "percaya"],
    3: ["usaha", "berusaha", "bangkit", "kuat", "kerja keras", "bekerja", "tindakan", "berani"],
    4: ["syukur", "bersyukur", "nikmat", "hargai", "menghargai", "ketenangan", "tenang", "kesihatan"],
    5: ["cukup", "sempurna", "okay", "bagus"],
    6: ["fikir", "berfikir", "cara", "keputusan", "pelajari", "belajar"],
    7: ["simpan", "menyimpan", "duit", "wang", "kewangan", "gaji", "pendapatan", "aset", "kaya"],
    8: ["peluang", "rezeki", "anugerah", "manfaat", "kebaikan", "kebaikan"],
    9: ["doa", "berdoa", "sabar", "bersabar", "ampun"],
    10: ["ilmu", "idea", "kemahiran", "pengalaman", "bijak", "pengetahuan"],
    11: ["potensi", "minda", "kemampuan", "keyakinan", "fokus", "matlamat", "tujuan"],
    12: ["cari", "mencari", "lihat", "nampak", "kelihatan", "alasan"],
    13: ["keluarga", "sayang", "bahagia", "kebahagiaan", "hormati", "orang yang kita sayang"],
    14: ["pendapat orang", "orang akan kata", "pandangan", "orang lain", "didengari", "dengar"],
    15: ["semangat", "disiplin", "konsisten", "bertahan", "teruskan", "terus berusaha", "jangan berhenti", "berputus asa"],
    16: ["rancang", "merancang", "perancangan", "matlamat", "impian", "catat", "target"],
    17: ["masa", "hari ini", "sekarang", "esok", "tunggu", "segera", "sehari", "pagi"],
    18: ["berhenti", "takut", "jangan tunggu", "jangan risau", "zon selesa", "mengalah"],
    19: ["pernah", "kenapa", "apa", "?", "terfikir", "bila"],
    20: ["mulakan", "mula", "langkah", "mari", "jom", "permulaan", "bermula"],
}
RECENT = 6  # jangan guna semula pose dalam 6 hari terakhir


def load_scripts():
    txt = open(DATA, encoding="utf-8").read().replace("\r", "")
    parts = re.split(r"(?m)^\s*(\d{1,3})\.\s*$", txt)
    out = {}
    for i in range(1, len(parts) - 1, 2):
        n = int(parts[i])
        lines = [x.strip() for x in parts[i + 1].strip().split("\n") if x.strip()]
        lines = [x for x in lines if x.lower() != "shukriee.com"]
        if lines and lines[0].lower().startswith("amboi"):
            lines = lines[1:]
        if len(lines) >= 2:
            out[n] = (" ".join(lines[:-1]), lines[-1])  # (ayat, soalan)
    return [out[k] for k in sorted(out)]


def pick_pose(quote, question, recent):
    t = (quote + " " + question).lower()
    score = {}
    for p, kws in KEY.items():
        score[p] = sum(2 if k in t[: len(quote)] else 1 for k in kws if k in t)
    cands = [p for p in range(1, 21) if p not in recent]
    best = max(score[p] for p in cands)
    top = [p for p in cands if score[p] == best]
    if best == 0:  # tiada padanan: ambil pose paling lama tidak digunakan
        ordered = [p for p in range(1, 21) if p not in recent]
        return ordered[(len(recent) * 7) % len(ordered)]
    return top[0]


def _wrap(d, text, font, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= maxw:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


def paras(quote):
    """Pecahkan ayat motivasi kepada perenggan pendek (satu ayat setiap perenggan; jika lebih 3 ayat, dua ayat setiap perenggan)."""
    ss = [x.strip() for x in re.split(r"(?<=[.!?])\s+", quote.strip()) if x.strip()]
    if len(ss) > 3:
        ss = [" ".join(ss[i:i + 2]) for i in range(0, len(ss), 2)]
    return ss or [quote.strip()]


def make_card(path, n, quote, question, pose):
    question = re.sub(r"[^\w\s.,!?'\-]", "", question).strip()
    im, d = card._bg(H=H, W=W)
    f, B, R = card._f, card.BOLD, card.REG
    GOLD, GOLD_L, WHITE = card.GOLD, card.GOLD_L, card.WHITE
    # pose di kiri, bawah
    p = Image.open(os.path.join(POSES, f"p{pose:02d}.png")).convert("RGBA")
    ph = 700
    pw = int(p.width * ph / p.height)
    p = p.resize((pw, ph), Image.LANCZOS)
    X0, X1 = 525, W - 65
    if pw > 470:  # pose lebar: kecilkan
        pw = 470; ph = int(p.height * 470 / p.width); p = p.resize((pw, ph), Image.LANCZOS)
    im.paste(p, (36, H - 33 - ph), p)
    d = card.ImageDraw.Draw(im)
    # teks: Amboi... + perenggan pendek + soalan
    maxw = X1 - X0
    ps = paras(quote)
    size = 46
    while size >= 26:
        fo = f(B, size)
        lh = int(size * 1.34)
        gap = int(size * 0.62)
        qs = f(B, size - 4)
        qh = int((size - 4) * 1.35)
        blocks = [_wrap(d, p, fo, maxw) for p in ps]
        ql = _wrap(d, question, qs, maxw)
        total = 98 + sum(len(b) * lh for b in blocks) + gap * (len(blocks) - 1) + 40 + len(ql) * qh
        if total <= 800:
            break
        size -= 2
    y = max(90, 80 + (800 - total) // 2)
    d.text((X0, y), "Amboi...", font=f(B, 64), fill=GOLD)
    y += 98
    for i, b in enumerate(blocks):
        for ln in b:
            d.text((X0, y), ln, font=fo, fill=WHITE); y += lh
        if i < len(blocks) - 1:
            y += gap
    y += 40
    for ln in ql:
        d.text((X0, y), ln, font=qs, fill=GOLD_L); y += qh
    # label nombor + pill
    pill_w, pill_h = 300, 64
    px, py = X0 + (maxw - pill_w) / 2, H - 33 - 96
    d.rounded_rectangle([px, py, px + pill_w, py + pill_h], 32, fill=(0, 0, 0))
    t = "shukriee.com"; tf = f(B, 30)
    d.text((px + (pill_w - d.textlength(t, font=tf)) / 2, py + 12), t, font=tf, fill=GOLD_L)
    im.save(path)
    return path


def run(st, send, out_dir, test=False):
    scripts = load_scripts()
    k = int(st.get("sm_n", 0)) % len(scripts)
    quote, question = scripts[k]
    recent = list(st.get("sm_recent", []))[-RECENT:]
    pose = pick_pose(quote, question, recent)
    os.makedirs(out_dir, exist_ok=True)
    img = make_card(f"{out_dir}/semangat.png", k + 1, quote, question, pose)
    text = "Amboi...\n\n" + "\n\n".join(paras(quote)) + f"\n\n{question}\n\nshukriee.com"
    print(f"Semangat #{k+1}/{len(scripts)}, pose {pose}")
    send(text, img, "semangat", closing=False)
    if not test:
        st["sm_n"] = (k + 1) % len(scripts)
        st["sm_recent"] = (recent + [pose])[-RECENT:]

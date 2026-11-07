"""Sync gambar dari folder Google Drive awam (broll-library/emas) ke ilmu_img/.
Gambar disalin (dikecilkan ke 1600px); video: diambil satu frame yang sesuai (tajam, tidak gelap/terlalu cerah).
Fail yang sudah diproses direkod dalam ilmu_img/.synced.json supaya tidak dimuat turun semula."""
import os, re, sys, json, subprocess, tempfile
import gdown
from PIL import Image, ImageFilter, ImageStat, ImageOps

FOLDER = "https://drive.google.com/drive/folders/1vtoBFhizVA8tvO023Pvgtrk-LTdYVqoA"
APPROVAL = "https://drive.google.com/drive/folders/1bbf3_iWXuGln2mpUguRFhvDnoyjscRgr"
OUT = "ilmu_img"
MAN = os.path.join(OUT, ".synced.json")
IMG = (".jpg", ".jpeg", ".png", ".webp")
VID = (".mp4", ".mov", ".m4v", ".webm", ".mkv")
FRACS = (0.1, 0.25, 0.4, 0.55, 0.7, 0.85)


def slug(name):
    s = re.sub(r"[^A-Za-z0-9_-]+", "-", os.path.splitext(os.path.basename(name))[0]).strip("-")
    return s[:60] or "gambar"


def free_name(base, fid, used):
    n = base
    if n in used and used[n] != fid:
        n = f"{base}-{fid[:6]}"
    used[n] = fid
    return n


def save_image(src, dst):
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")  # betulkan arah gambar (EXIF)
    im.thumbnail((1600, 1600))
    im.save(dst, "JPEG", quality=88)


def duration(path):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                           capture_output=True, text=True, timeout=120)
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def best_frame(video, dst):
    d = duration(video)
    times = [d * f for f in FRACS] if d > 1 else [0.5]
    best, best_score, mid = None, -1, None
    tmp = tempfile.mkdtemp()
    for i, t in enumerate(times):
        fp = os.path.join(tmp, f"f{i}.jpg")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", video, "-frames:v", "1", "-q:v", "2", fp],
                       capture_output=True, timeout=180)
        if not os.path.exists(fp):
            continue
        im = Image.open(fp).convert("RGB")
        g = im.convert("L")
        mean = ImageStat.Stat(g).mean[0]
        sharp = ImageStat.Stat(g.filter(ImageFilter.FIND_EDGES)).var[0]
        if mid is None:
            mid = fp
        if 35 <= mean <= 225 and sharp > best_score:
            best, best_score = fp, sharp
    pick = best or mid
    if not pick:
        raise RuntimeError("tiada frame")
    save_image(pick, dst)


def compress(src, dst, target_mb=18.5):
    """Kecilkan video supaya di bawah ~19 MB (had 20 MB bot Telegram): bitrate dikira daripada tempoh; cuba semula lebih rendah jika masih besar."""
    d = duration(src) or 30
    for factor in (1.0, 0.8, 0.6):
        vbr = int(max(250_000, target_mb * factor * 8 * 1024 * 1024 / d - 128_000))
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", src, "-vf", "scale='min(1080,iw)':-2", "-c:v", "libx264", "-preset", "veryfast",
               "-b:v", str(vbr), "-maxrate", str(int(vbr * 1.25)), "-bufsize", str(vbr * 2), "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", dst]
        subprocess.run(cmd, check=True, timeout=3000)
        if os.path.getsize(dst) <= 19.5 * 1024 * 1024:
            return dst
    raise RuntimeError("video terlalu panjang untuk dikecilkan ke bawah 20 MB")


def auto_caption(video):
    """Caption automatik: transkrip suara (Whisper kecil, BM) -> Claude Haiku tulis caption format Shukri. Gagal -> caption asas."""
    base = "Amboi...\n\nshukriee.com"
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return base
    try:
        wav = video + ".wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-vn", "-ac", "1", "-ar", "16000", wav], check=True, timeout=600)
        from faster_whisper import WhisperModel
        segs, _ = WhisperModel("small", device="cpu", compute_type="int8").transcribe(wav, language="ms", vad_filter=True)
        text = " ".join(s.text.strip() for s in segs)[:6000]
        if len(text) < 20:
            return base
        import requests
        prompt = ("Tulis caption siaran (Bahasa Melayu, kira-kira 400 aksara, MAKSIMUM 900) untuk video emas Shukri berdasarkan transkrip di bawah. "
                  "Format tetap: baris pertama bermula tepat dengan 'Amboi...' (hook menarik), kemudian isi dalam perenggan pendek dipisahkan baris kosong, "
                  "dan baris terakhir 'shukriee.com'. Jangan reka fakta/angka yang tiada dalam transkrip. Beri caption sahaja.\n\nTRANSKRIP:\n" + text)
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=90,
                          headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                          json={"model": "claude-haiku-5-5", "max_tokens": 1000, "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status()
        out = "".join(b.get("text", "") for b in r.json()["content"]).strip()
        if out.startswith("Amboi...") and out.endswith("shukriee.com") and len(out) <= 1024:
            return out
    except Exception as e:
        print("Auto caption gagal:", str(e)[:200])
    return base


def send_video_for_approval(f, files):
    """Video dalam folder Drive 'video-approval': muat turun, kecilkan jika perlu, hantar ke kumpulan VIDEO APPROVAL dengan butang."""
    ext = os.path.splitext(f.path)[1].lower()
    work = tempfile.mkdtemp()
    src = os.path.join(work, "src" + ext)
    if not gdown.download(id=f.id, output=src, quiet=True):
        raise RuntimeError("muat turun video gagal")
    caption = None
    stem = os.path.splitext(f.path)[0]
    for g in files:  # caption: fail .txt bernama sama dalam folder yang sama
        if g.path.lower().endswith(".txt") and os.path.splitext(g.path)[0] == stem:
            tp = os.path.join(work, "cap.txt")
            if gdown.download(id=g.id, output=tp, quiet=True):
                caption = open(tp, encoding="utf-8").read().strip()[:1024] or caption
    if not caption:
        caption = auto_caption(src)
    out = src
    if os.path.getsize(src) > 19.5 * 1024 * 1024:
        out = compress(src, os.path.join(work, "small.mp4"))
    elif ext != ".mp4":
        out = compress(src, os.path.join(work, "small.mp4"))
    subprocess.run([sys.executable, "send_for_approval.py", out, caption], check=True, timeout=900)


def main():
    os.makedirs(OUT, exist_ok=True)
    man = json.load(open(MAN)) if os.path.exists(MAN) else {}
    used = {v: k for k, v in man.items()}
    files = gdown.download_folder(url=FOLDER, skip_download=True, quiet=True) or []
    print(f"Fail di Drive: {len(files)}; sudah diproses: {len(man)}")
    try:  # folder video-approval (berasingan): hantar video ke kumpulan kelulusan
        af = gdown.download_folder(url=APPROVAL, skip_download=True, quiet=True) or []
    except Exception as e:
        af = []
        print("Folder video-approval tidak dapat dibaca:", str(e)[:200])
    print(f"Fail di video-approval: {len(af)}")
    for f in af:
        if os.path.splitext(f.path)[1].lower() in VID and f.id not in man:
            try:
                send_video_for_approval(f, af)
                man[f.id] = "kelulusan-" + slug(f.path)
                json.dump(man, open(MAN, "w"), indent=1)
                print("KELULUSAN", f.path)
            except Exception as e:
                print("GAGAL kelulusan", f.path, str(e)[:300])
    added = 0
    for f in files:
        ext = os.path.splitext(f.path)[1].lower()
        if "video-approval" in [p.lower() for p in f.path.replace("\\", "/").split("/")][:-1]:  # folder video-approval: hantar untuk kelulusan
            if ext in VID and f.id not in man:
                try:
                    send_video_for_approval(f, files)
                    man[f.id] = "kelulusan-" + slug(f.path)
                    json.dump(man, open(MAN, "w"), indent=1)
                    print("KELULUSAN", f.path)
                except Exception as e:
                    print("GAGAL kelulusan", f.path, str(e)[:300])
            continue
        if f.id in man or ext not in IMG + VID:
            continue
        try:
            tmp = os.path.join(tempfile.mkdtemp(), "src" + ext)
            if not gdown.download(id=f.id, output=tmp, quiet=True):
                raise RuntimeError("muat turun gagal")
            is_vid = ext in VID
            name = free_name(("vid-" if is_vid else "") + slug(f.path), f.id, used)
            dst = os.path.join(OUT, name + ".jpg")
            (best_frame if is_vid else save_image)(tmp, dst)
            man[f.id] = name
            used[name] = f.id
            added += 1
            print("OK", f.path, "->", dst)
            json.dump(man, open(MAN, "w"), indent=1)
            os.remove(tmp)
        except Exception as e:
            print("GAGAL", f.path, str(e)[:200])
    print(f"Baru ditambah: {added}")


if __name__ == "__main__":
    main()

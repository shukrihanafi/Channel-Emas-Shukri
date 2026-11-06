"""Sync gambar dari folder Google Drive awam (broll-library/emas) ke ilmu_img/.
Gambar disalin (dikecilkan ke 1600px); video: diambil satu frame yang sesuai (tajam, tidak gelap/terlalu cerah).
Fail yang sudah diproses direkod dalam ilmu_img/.synced.json supaya tidak dimuat turun semula."""
import os, re, json, subprocess, tempfile
import gdown
from PIL import Image, ImageFilter, ImageStat

FOLDER = "https://drive.google.com/drive/folders/1vtoBFhizVA8tvO023Pvgtrk-LTdYVqoA"
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
    im = Image.open(src).convert("RGB")
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


def main():
    os.makedirs(OUT, exist_ok=True)
    man = json.load(open(MAN)) if os.path.exists(MAN) else {}
    used = {v: k for k, v in man.items()}
    files = gdown.download_folder(url=FOLDER, skip_download=True, quiet=True) or []
    print(f"Fail di Drive: {len(files)}; sudah diproses: {len(man)}")
    added = 0
    for f in files:
        ext = os.path.splitext(f.path)[1].lower()
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

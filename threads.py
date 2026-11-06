"""Auto post ke Threads (@shukrieepg) melalui Threads API. Aktif jika secret THREADS_TOKEN ditetapkan.
Token Threads sah 60 hari; bot menyambungnya (refresh) sendiri setiap 7 hari. Token baharu disimpan
dalam data/state.json dalam bentuk TERSULIT (kunci diterbitkan daripada secret peribadi), jadi repo awam tetap selamat.
Gambar: diunggah sebagai foto Facebook Page yang TIDAK diterbitkan, untuk mendapat URL awam yang Threads boleh muat turun."""
import base64, hashlib, os, re, time
from datetime import datetime, timezone
import requests

API = "https://graph.threads.net"
MAX = 500
PRESET = ""  # teks Threads siap (dijana bersama ringkasan berita); jika ada, tidak perlu panggilan AI kedua


def fmt(body):
    """Susun teks Threads: perenggan kemas, ringkas jika melebihi 500 aksara (buang perenggan hujung), dan sentiasa tamat dengan shukriee.com."""
    tail = "\n\nshukriee.com"
    room = MAX - len(tail)
    lines = [l.rstrip() for l in (body or "").replace("\r", "").split("\n") if "shukriee.com" not in l.lower()]
    ps = [p.strip() for p in re.split(r"\n\s*\n", "\n".join(lines).strip()) if p.strip()]
    out = []
    for p in ps:
        if len("\n\n".join(out + [p])) <= room:
            out.append(p)
            continue
        if not out:  # perenggan pertama pun terlalu panjang: potong pada hujung ayat
            cut = p[:room]
            k = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "), cut.rfind("\n"))
            out.append(cut[:k + 1] if k > room * 0.4 else cut.rsplit(" ", 1)[0] + "…")
        break
    return "\n\n".join(out) + tail


def enabled():
    return bool(os.getenv("THREADS_TOKEN")) and os.getenv("THREADS_AUTO", "1") == "1"


def _fernet(legacy=False):
    """Kunci penyulitan. Baharu: diterbitkan daripada secret THREADS_TOKEN (tidak terjejas jika token bot Telegram ditukar/revoke).
    legacy=True: kunci lama daripada token bot (hanya untuk membaca token yang disimpan sebelum perubahan ini)."""
    from cryptography.fernet import Fernet
    seed = ((os.getenv("TELEGRAM_BOT_TOKEN") or "") if legacy else os.environ["THREADS_TOKEN"].strip()) + "|threads"
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(seed.encode()).digest()))


def _h(env_tok):
    return hashlib.sha256(env_tok.encode()).hexdigest()[:12]


def token(st):
    """Token semasa: yang disambung & disimpan (jika masih berpadanan dengan secret), jika tidak secret asal."""
    env = os.environ["THREADS_TOKEN"].strip()
    s = (st or {}).get("threads") or {}
    if s.get("src") == _h(env) and s.get("enc"):
        for legacy in (False, True):
            try:
                return _fernet(legacy).decrypt(s["enc"].encode()).decode()
            except Exception:
                pass
    return env


def me(tok):
    r = requests.get(f"{API}/v1.0/me", params={"fields": "id,username"}, headers={"Authorization": f"Bearer {tok}"}, timeout=30)
    if r.status_code >= 300:
        raise RuntimeError(f"Threads {r.status_code}: {r.text[:300]}")
    return r.json()


def refresh(st, force=False):
    """Sambung token (60 hari lagi) setiap 7 hari. Kembalikan teks status."""
    env = os.environ["THREADS_TOKEN"].strip()
    s = st.setdefault("threads", {})
    if s.get("src") != _h(env):  # secret baharu ditampal: mula semula
        s.clear()
        s["src"] = _h(env)
    last = s.get("refreshed")
    if not force and last:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).days
        if age < 7:
            return f"token disambung {age} hari lalu"
    tok = token(st)
    r = requests.get(f"{API}/refresh_access_token", params={"grant_type": "th_refresh_token", "access_token": tok}, timeout=30)
    if r.status_code >= 300:
        raise RuntimeError(f"Sambung token Threads gagal {r.status_code}: {r.text[:300]}")
    j = r.json()
    s["enc"] = _fernet().encrypt(j["access_token"].encode()).decode()
    s["refreshed"] = datetime.now(timezone.utc).isoformat()
    s["expires_in_days"] = int(j.get("expires_in", 0)) // 86400
    return f"token disambung, sah {s['expires_in_days']} hari"


def _host_image(path):
    """Foto FB Page tidak diterbitkan -> URL awam gambar."""
    import fb
    pid = os.environ["FB_PAGE_ID"]
    tok = fb.page_token(pid, os.environ["FB_PAGE_TOKEN"])
    with open(path, "rb") as f:
        r = requests.post(f"{fb.GRAPH}/{pid}/photos", data={"published": "false", "temporary": "true", "access_token": tok},
                          files={"source": f}, timeout=(10, 120))
    if r.status_code >= 300:
        raise RuntimeError(f"Hos gambar {r.status_code}: {r.text[:200]}")
    pid_photo = r.json()["id"]
    g = requests.get(f"{fb.GRAPH}/{pid_photo}", params={"fields": "images", "access_token": tok}, timeout=30)
    g.raise_for_status()
    return g.json()["images"][0]["source"]


def _recent_same(h, uid, text, minutes=30):
    """Benar jika Threads sudah ada post dengan teks sama dalam {minutes} minit lalu (elak siaran dua kali). Best-effort."""
    try:
        r = requests.get(f"{API}/v1.0/{uid}/threads", params={"fields": "text,timestamp", "limit": 10}, headers=h, timeout=30)
        if r.status_code >= 300:
            return False
        now = datetime.now(timezone.utc)
        for it in r.json().get("data", []):
            ts = datetime.strptime(it["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
            if (it.get("text") or "").strip() == text.strip() and (now - ts).total_seconds() < minutes * 60:
                return True
    except Exception:
        pass
    return False


def post(st, text, image_path=None):
    tok = token(st)
    h = {"Authorization": f"Bearer {tok}"}
    uid = me(tok)["id"]
    text = fmt(text)
    if _recent_same(h, uid, text):
        print("Threads: post sama sudah ada, dilangkau.")
        return {"skipped": True}
    data = {"text": text, "media_type": "TEXT"}
    if image_path and os.path.exists(image_path):
        data = {"text": text, "media_type": "IMAGE", "image_url": _host_image(image_path)}
    r = requests.post(f"{API}/v1.0/{uid}/threads", data=data, headers=h, timeout=60)
    if r.status_code >= 300:
        raise RuntimeError(f"Threads {r.status_code}: {r.text[:300]}")
    cid = r.json()["id"]
    time.sleep(8)
    for i in range(4):
        p = requests.post(f"{API}/v1.0/{uid}/threads_publish", data={"creation_id": cid}, headers=h, timeout=60)
        if p.status_code < 300:
            return p.json()
        if i < 3:
            time.sleep(8)
    raise RuntimeError(f"Threads publish {p.status_code}: {p.text[:300]}")


def casual(text):
    """Tulis semula berita menjadi post Threads santai (BM) guna Claude Haiku."""
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return None
    prompt = ("Tulis semula berita emas ini sebagai satu post Threads dalam Bahasa Melayu santai, 50-80 patah perkataan, jumlah TIDAK melebihi 400 aksara.\n"
              "Struktur: ayat pembuka yang menarik perhatian (hook), fakta utama berita, sudut pandang orang yang simpan emas, "
              "dan satu soalan penutup kepada pembaca. Maksimum SATU emoji. Susun dalam 3 hingga 4 perenggan pendek dipisahkan baris kosong. Tiada hashtag, tiada pautan, jangan tulis shukriee.com. Jangan reka fakta.\n"
              "Beri teks post sahaja.\n\nBERITA:\n" + text[:3000])
    r = requests.post("https://api.anthropic.com/v1/messages", timeout=90,
                      headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                      json={"model": "claude-haiku-5-5", "max_tokens": 8000, "messages": [{"role": "user", "content": prompt}]})
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json()["content"]).strip()


def gap_text(text):
    """Versi ringkas caption GAP untuk Threads (had 500 aksara)."""
    parts = [p for p in text.split("\n\n") if not p.startswith(("Terendah", "Dikemaskini"))]
    return "\n\n".join(parts)



def summarize(text, limit=450):
    """Ringkaskan teks panjang supaya muat had aksara (guna Claude Haiku). Jika sudah ringkas atau AI gagal, pulangkan teks asal."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return text
    try:
        prompt = (f"Ringkaskan post ini dalam Bahasa Melayu dengan gaya yang sama, jumlah TIDAK melebihi {limit - 60} aksara. "
                  "Kekalkan mesej utama dan fakta penting (angka, harga, tarikh) tanpa mereka fakta. Susun dalam perenggan pendek dipisahkan baris kosong. "
                  "Jangan tulis shukriee.com dan jangan tambah pautan. Beri teks post sahaja.\n\nPOST:\n" + text[:6000])
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=90,
                          headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                          json={"model": "claude-haiku-5-5", "max_tokens": 4000, "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status()
        out = "".join(b.get("text", "") for b in r.json()["content"]).strip()
        return out if out and len(out) <= limit else text
    except Exception:
        return text



def _host_video(path):
    """Video FB Page tidak diterbitkan -> URL awam video. Tunggu video 'ready' (siap diproses) dan semak URL benar-benar boleh diambil."""
    import fb
    pid = os.environ["FB_PAGE_ID"]
    tok = fb.page_token(pid, os.environ["FB_PAGE_TOKEN"])
    with open(path, "rb") as f:
        r = requests.post(f"{fb.GRAPH}/{pid}/videos", data={"published": "false", "access_token": tok}, files={"source": f}, timeout=(10, 600))
    if r.status_code >= 300:
        raise RuntimeError(f"Hos video {r.status_code}: {r.text[:200]}")
    vid = r.json()["id"]
    last = ""
    for _ in range(60):
        g = requests.get(f"{fb.GRAPH}/{vid}", params={"fields": "source,status", "access_token": tok}, timeout=30)
        if g.status_code < 300:
            j = g.json()
            vs = (j.get("status") or {}).get("video_status")
            last = f"status={vs}"
            if j.get("source") and vs in (None, "ready"):
                url = j["source"]
                try:  # semak URL boleh dimuat turun tanpa log masuk
                    c = requests.get(url, headers={"Range": "bytes=0-1023"}, timeout=30)
                    ct = c.headers.get("Content-Type", "")
                    print(f"Hos video: HTTP {c.status_code} {ct} {c.headers.get('Content-Range', '')}")
                    if c.status_code in (200, 206) and ("video" in ct or "octet" in ct):
                        return url
                    last = f"URL tidak sah HTTP {c.status_code} {ct}"
                except Exception as e:
                    last = f"semak URL gagal {e}"
            elif vs == "error":
                raise RuntimeError("Hos video: FB gagal memproses video")
        time.sleep(5)
    raise RuntimeError("Hos video: URL video belum sedia (" + last + ")")


def _host_video_gh(path):
    """URL awam langsung dari cabang 'media' repo awam ini (satu komit sahaja, ditimpa setiap kali, jadi repo tidak membengkak)."""
    import subprocess, tempfile, shutil, time as _t
    repo, gtok = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"]
    name = f"v{int(_t.time())}.mp4"
    d = tempfile.mkdtemp()
    try:
        shutil.copy(path, os.path.join(d, name))
        run = lambda *a: subprocess.run(a, cwd=d, check=True, capture_output=True, text=True)
        run("git", "init", "-q", "-b", "media")
        run("git", "config", "user.name", "channel-bot")
        run("git", "config", "user.email", "bot@users.noreply.github.com")
        run("git", "add", name)
        run("git", "commit", "-q", "-m", "media sementara")
        run("git", "push", "-q", "-f", f"https://x-access-token:{gtok}@github.com/{repo}.git", "media:refs/heads/media")
    finally:
        shutil.rmtree(d, ignore_errors=True)
    url = f"https://raw.githubusercontent.com/{repo}/media/{name}"
    for _ in range(12):
        c = requests.get(url, headers={"Range": "bytes=0-1023"}, timeout=30)
        if c.status_code in (200, 206):
            return url
        time.sleep(5)
    raise RuntimeError("Hos GitHub: URL belum boleh dicapai")


def video_hosts(path):
    """Calon URL video awam mengikut keutamaan: (nama, fungsi pembuat URL)."""
    hosts = [("FB", _host_video)]
    if os.getenv("GITHUB_TOKEN") and os.getenv("GITHUB_REPOSITORY"):
        hosts.append(("GitHub", _host_video_gh))
    return hosts


def post_video(st, text, video_path):
    """Post video ke Threads. Cuba URL dihos FB Page; jika Threads menolak (ERROR), cuba URL GitHub."""
    tok = token(st)
    h = {"Authorization": f"Bearer {tok}"}
    uid = me(tok)["id"]
    if _recent_same(h, uid, fmt(text)):
        print("Threads: post sama sudah ada, dilangkau.")
        return {"skipped": True}
    errs = []
    for label, host in video_hosts(video_path):
        try:
            url = host(video_path)
            r = requests.post(f"{API}/v1.0/{uid}/threads", data={"text": fmt(text), "media_type": "VIDEO", "video_url": url}, headers=h, timeout=60)
            if r.status_code >= 300:
                raise RuntimeError(f"cipta {r.status_code}: {r.text[:200]}")
            cid = r.json()["id"]
            for _ in range(48):  # tunggu Threads siap memproses video
                time.sleep(5)
                g = requests.get(f"{API}/v1.0/{cid}", params={"fields": "status,error_message"}, headers=h, timeout=30)
                s = g.json().get("status") if g.status_code < 300 else None
                if s == "FINISHED":
                    break
                if s == "ERROR":
                    raise RuntimeError("ERROR: " + str(g.json().get("error_message"))[:200])
            last = None
            for i in range(4):
                p = requests.post(f"{API}/v1.0/{uid}/threads_publish", data={"creation_id": cid}, headers=h, timeout=60)
                if p.status_code < 300:
                    return p.json()
                last = p
                time.sleep(8)
            raise RuntimeError(f"publish {last.status_code}: {last.text[:200]}")
        except Exception as e:
            print(f"Threads video ({label}) gagal: {e}")
            errs.append(f"{label}: {str(e)[:200]}")
    raise RuntimeError("Threads video gagal | " + " | ".join(errs))

"""Auto post ke Instagram (@shukrieepg) melalui Instagram API (Unified login). Aktif jika secret IG_TOKEN ditetapkan.
Token jenis system-user: tidak luput. Instagram hanya terima gambar JPEG dengan URL awam, jadi gambar ditukar ke JPEG
dan diunggah sebagai foto Facebook Page yang TIDAK diterbitkan untuk mendapat URL awam."""
import os, re, time
import requests

GRAPH = "https://graph.facebook.com/v21.0"
MAX = 2200
DEFAULT_ID = "17841404089345637"  # @shukrieepg (pengganti jika /me tidak memulangkan id)


def enabled():
    return bool(os.getenv("IG_TOKEN")) and os.getenv("IG_AUTO", "1") == "1"


def _tok():
    return os.environ["IG_TOKEN"].strip()


def fmt(body):
    """Caption IG: perenggan kemas, sentiasa tamat dengan shukriee.com, tidak lebih 2200 aksara."""
    tail = "\n\nshukriee.com"
    room = MAX - len(tail)
    lines = [l.rstrip() for l in (body or "").replace("\r", "").split("\n") if "shukriee.com" not in l.lower()]
    ps = [p.strip() for p in re.split(r"\n\s*\n", "\n".join(lines).strip()) if p.strip()]
    out = []
    for p in ps:
        if len("\n\n".join(out + [p])) > room:
            break
        out.append(p)
    return "\n\n".join(out) + tail


def _get(path, **params):
    params["access_token"] = _tok()
    r = requests.get(f"{GRAPH}/{path}", params=params, timeout=30)
    if r.status_code >= 300:
        raise RuntimeError(f"Instagram {r.status_code}: {r.text[:300]}")
    return r.json()


def me():
    """Pulangkan {id, username}. Cuba /me, jika gagal guna id lalai."""
    uid = os.getenv("IG_USER_ID", "").strip()
    try:
        j = _get("me", fields="id,username")
        if j.get("username"):
            return {"id": j["id"], "username": j["username"]}
    except Exception:
        pass
    uid = uid or DEFAULT_ID
    j = _get(uid, fields="id,username")
    return {"id": j.get("id", uid), "username": j.get("username", "?")}


def _jpeg(path):
    from PIL import Image
    out = path.rsplit(".", 1)[0] + "-ig.jpg"
    im = Image.open(path).convert("RGB")
    w, h = im.size
    ratio = w / h  # IG: 4:5 hingga 1.91:1 (jika di luar, letak latar putih)
    if ratio < 0.8:
        nw, nh = int(h * 0.8), h
    elif ratio > 1.91:
        nw, nh = w, int(w / 1.91)
    else:
        nw, nh = w, h
    if (nw, nh) != (w, h):
        c = Image.new("RGB", (nw, nh), (255, 255, 255))
        c.paste(im, ((nw - w) // 2, (nh - h) // 2))
        im = c
    im.save(out, "JPEG", quality=92)
    return out


def _recent_same(uid, text, minutes=30):
    """Benar jika IG sudah ada media dengan caption sama dalam {minutes} minit lalu. Best-effort (perlukan kebenaran baca media)."""
    try:
        from datetime import datetime, timezone
        j = _get(f"{uid}/media", fields="caption,timestamp", limit=10)
        now = datetime.now(timezone.utc)
        for it in j.get("data", []):
            ts = datetime.strptime(it["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
            if (it.get("caption") or "").strip() == fmt(text).strip() and (now - ts).total_seconds() < minutes * 60:
                return True
    except Exception:
        pass
    return False


def post(text, image_path):
    if not image_path or not os.path.exists(image_path):
        raise RuntimeError("Instagram perlukan gambar; tiada gambar untuk post ini")
    import threads
    uid = me()["id"]
    if _recent_same(uid, text):
        print("Instagram: post sama sudah ada, dilangkau.")
        return {"skipped": True}
    url = threads._host_image(_jpeg(image_path))
    r = requests.post(f"{GRAPH}/{uid}/media", data={"image_url": url, "caption": fmt(text), "access_token": _tok()}, timeout=60)
    if r.status_code >= 300:
        raise RuntimeError(f"Instagram media {r.status_code}: {r.text[:300]}")
    cid = r.json()["id"]
    for _ in range(12):  # tunggu bekas siap
        time.sleep(5)
        try:
            s = _get(cid, fields="status_code").get("status_code")
        except Exception:
            s = None
        if s == "FINISHED":
            break
        if s == "ERROR":
            raise RuntimeError("Instagram bekas media ERROR")
    last = None
    for i in range(4):
        p = requests.post(f"{GRAPH}/{uid}/media_publish", data={"creation_id": cid, "access_token": _tok()}, timeout=60)
        if p.status_code < 300:
            return p.json()
        last = p
        time.sleep(8)
    raise RuntimeError(f"Instagram publish {last.status_code}: {last.text[:300]}")



def diag():
    """Diagnosis token (tanpa dedah token): jenis token, skop, dan apa yang boleh dibaca. Pulangkan teks ringkas."""
    import json
    t = _tok()
    out = []

    def g(host, path, **p):
        p["access_token"] = t
        try:
            r = requests.get(f"{host}/{path}", params=p, timeout=30)
            return f"{r.status_code} {r.text[:350]}"
        except Exception as e:
            return f"ERR {e}"

    fb = "https://graph.facebook.com/v21.0"
    ig = "https://graph.instagram.com/v21.0"
    try:
        d = requests.get(f"{fb}/debug_token", params={"input_token": t, "access_token": t}, timeout=30).json().get("data", {})
        out.append("debug: type=%s app=%s valid=%s exp=%s scopes=%s granular=%s" % (d.get("type"), d.get("application"), d.get("is_valid"), d.get("expires_at"), d.get("scopes"), json.dumps(d.get("granular_scopes"))[:400]))
    except Exception as e:
        out.append(f"debug ERR {e}")
    out.append("fb /me: " + g(fb, "me", fields="id,name"))
    out.append("fb /me/accounts: " + g(fb, "me/accounts", fields="id,name,instagram_business_account"))
    out.append("ig /me: " + g(ig, "me", fields="id,user_id,username"))
    out.append(f"fb /{DEFAULT_ID}: " + g(fb, DEFAULT_ID, fields="id,username"))
    try:  # token Facebook Page sedia ada: adakah ia nampak Instagram yang dipautkan?
        import fb as fbm
        pid = os.environ["FB_PAGE_ID"]
        pt = fbm.page_token(pid, os.environ["FB_PAGE_TOKEN"])
        r = requests.get(f"{fb}/{pid}", params={"fields": "instagram_business_account{id,username}", "access_token": pt}, timeout=30)
        out.append(f"page->ig: {r.status_code} {r.text[:300]}")
        d2 = requests.get(f"{fb}/debug_token", params={"input_token": pt, "access_token": pt}, timeout=30).json().get("data", {})
        out.append("page token scopes: %s" % (d2.get("scopes"),))
    except Exception as e:
        out.append(f"page->ig ERR {str(e)[:200]}")
    return "\n\n".join(out)


def _imgs(folder, pats):
    import glob
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), folder)
    out = []
    for p in pats:
        out += glob.glob(os.path.join(base, p))
    return sorted(out)


def fallback_image():
    """Gambar sandaran dari repo: utamakan folder ilmu_img, jika kosong guna news_img/bar-*; bertukar mengikut hari."""
    import datetime
    fs = _imgs("ilmu_img", ["*.jpg", "*.jpeg", "*.png"]) or _imgs("news_img", ["bar-*.jpg"])
    return fs[datetime.date.today().toordinal() % len(fs)] if fs else None


def ilmu_image(k, n=None):
    """Gambar untuk ilmu: jika ada ilmu_img/k.jpg guna itu; jika tidak, ikut susunan semua gambar (ilmu_img kemudian news_img/bar-*)
    mengikut nombor siaran n, dan ulang dari gambar pertama bila habis."""
    for ext in ("jpg", "jpeg", "png"):
        fs = _imgs("ilmu_img", [f"{k}.{ext}"])
        if fs:
            return fs[0]
    pool = _imgs("ilmu_img", ["*.jpg", "*.jpeg", "*.png"]) + _imgs("news_img", ["bar-*.jpg"])
    if not pool:
        return fallback_image()
    return pool[((n or k) - 1) % len(pool)]



def _status(cid):
    """Pulangkan (status_code, butiran) bekas media IG."""
    try:
        j = _get(cid, fields="status_code,status")
        return j.get("status_code"), j.get("status")
    except Exception as e:
        return None, str(e)[:150]


def _wait_publish(uid, cid, label):
    s, d = None, None
    for _ in range(60):  # tunggu Instagram siap memproses video
        time.sleep(5)
        s, d = _status(cid)
        if s == "FINISHED":
            break
        if s in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram reel {s} ({label}): {d}")
    else:
        raise RuntimeError(f"Instagram reel tamat masa ({label}): {s} {d}")
    last = None
    for i in range(4):
        p = requests.post(f"{GRAPH}/{uid}/media_publish", data={"creation_id": cid, "access_token": _tok()}, timeout=60)
        if p.status_code < 300:
            return p.json()
        last = p
        time.sleep(8)
    raise RuntimeError(f"Instagram reel publish {last.status_code}: {last.text[:300]}")


def _reel_resumable(uid, text, video_path):
    """Muat naik terus fail ke Instagram (tanpa URL awam)."""
    r = requests.post(f"{GRAPH}/{uid}/media", data={"media_type": "REELS", "upload_type": "resumable", "caption": fmt(text),
                      "share_to_feed": "true", "access_token": _tok()}, timeout=60)
    if r.status_code >= 300:
        raise RuntimeError(f"media {r.status_code}: {r.text[:200]}")
    cid = r.json()["id"]
    size = os.path.getsize(video_path)
    with open(video_path, "rb") as f:
        u = requests.post(f"https://rupload.facebook.com/ig-api-upload/v21.0/{cid}",
                          headers={"Authorization": "OAuth " + _tok(), "offset": "0", "file_size": str(size)}, data=f, timeout=(10, 600))
    if u.status_code >= 300 or not u.json().get("success", True):
        raise RuntimeError(f"rupload {u.status_code}: {u.text[:200]}")
    return cid


def _reel_url_with(host):
    def f(uid, text, video_path):
        return _reel_url(uid, text, video_path, host)
    return f


def _reel_url(uid, text, video_path, host=None):
    import threads
    url = (host or threads._host_video)(video_path)
    r = requests.post(f"{GRAPH}/{uid}/media", data={"media_type": "REELS", "video_url": url, "caption": fmt(text), "share_to_feed": "true", "access_token": _tok()}, timeout=60)
    if r.status_code >= 300:
        raise RuntimeError(f"media {r.status_code}: {r.text[:300]}")
    return r.json()["id"]


def post_video(text, video_path):
    """Post video sebagai Reel Instagram: cuba muat naik terus dahulu, jika gagal guna URL video yang dihos di FB Page."""
    uid = me()["id"]
    if _recent_same(uid, text):
        print("Instagram: reel sama sudah ada, dilangkau.")
        return {"skipped": True}
    errs = []
    import threads
    tries = [("muat naik terus", _reel_resumable)] + [(f"URL {n}", _reel_url_with(h)) for n, h in threads.video_hosts(video_path)]
    for label, fn in tries:
        try:
            cid = fn(uid, text, video_path)
            return _wait_publish(uid, cid, label)
        except Exception as e:
            print(f"Instagram reel {label} gagal: {e}")
            errs.append(f"{label}: {str(e)[:220]}")
    raise RuntimeError("Instagram reel gagal | " + " | ".join(errs))


def post_album(text, image_paths):
    """Carousel Instagram (2-10 gambar) dengan satu caption."""
    import threads
    uid = me()["id"]
    kids = []
    for p in image_paths[:10]:
        url = threads._host_image(_jpeg(p))
        r = requests.post(f"{GRAPH}/{uid}/media", data={"image_url": url, "is_carousel_item": "true", "access_token": _tok()}, timeout=60)
        if r.status_code >= 300:
            raise RuntimeError(f"Instagram item {r.status_code}: {r.text[:300]}")
        kids.append(r.json()["id"])
    r = requests.post(f"{GRAPH}/{uid}/media", data={"media_type": "CAROUSEL", "children": ",".join(kids), "caption": fmt(text), "access_token": _tok()}, timeout=60)
    if r.status_code >= 300:
        raise RuntimeError(f"Instagram carousel {r.status_code}: {r.text[:300]}")
    cid = r.json()["id"]
    for _ in range(12):
        time.sleep(5)
        try:
            s = _get(cid, fields="status_code").get("status_code")
        except Exception:
            s = None
        if s == "FINISHED":
            break
        if s == "ERROR":
            raise RuntimeError("Instagram carousel ERROR")
    last = None
    for i in range(4):
        p = requests.post(f"{GRAPH}/{uid}/media_publish", data={"creation_id": cid, "access_token": _tok()}, timeout=60)
        if p.status_code < 300:
            return p.json()
        last = p
        time.sleep(8)
    raise RuntimeError(f"Instagram publish {last.status_code}: {last.text[:300]}")

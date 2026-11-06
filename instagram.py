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


def post(text, image_path):
    if not image_path or not os.path.exists(image_path):
        raise RuntimeError("Instagram perlukan gambar; tiada gambar untuk post ini")
    import threads
    uid = me()["id"]
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
    return "\n\n".join(out)

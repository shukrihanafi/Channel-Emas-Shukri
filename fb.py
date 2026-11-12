"""Post terus ke Facebook Page melalui Graph API (ganti IFTTT). Aktif hanya jika FB_PAGE_TOKEN dan FB_PAGE_ID ditetapkan."""
import json, os
import requests

GRAPH = "https://graph.facebook.com/v21.0"
TOKEN_EXPIRES = ""  # token System User tidak tamat; isi tarikh YYYY-MM-DD jika guna token bertarikh tamat (peringatan bermula 14 hari sebelum)


_PT = {}


def page_token(pid, tok):
    """Token System User/pengguna -> token Page (diperlukan untuk menghantar sebagai Page). Jika gagal, guna token asal."""
    if (pid, tok) in _PT:
        return _PT[(pid, tok)]
    pt = tok
    try:
        r = requests.get(f"{GRAPH}/{pid}", params={"fields": "access_token"},
                         headers={"Authorization": f"Bearer {tok}"}, timeout=30)
        if r.status_code < 300 and r.json().get("access_token"):
            pt = r.json()["access_token"]
    except Exception:
        pass
    _PT[(pid, tok)] = pt
    return pt


def enabled() -> bool:
    return bool(os.getenv("FB_PAGE_TOKEN") and os.getenv("FB_PAGE_ID") and os.getenv("FB_AUTO", "1") == "1")


def post(text, image_path=None, video_path=None):
    """Video / gambar + caption (atau teks sahaja) ke Page. Token dihantar dalam badan permintaan, bukan URL."""
    pid = os.environ["FB_PAGE_ID"]
    tok = page_token(pid, os.environ["FB_PAGE_TOKEN"])
    if video_path and os.path.exists(video_path):
        with open(video_path, "rb") as f:
            r = requests.post(f"{GRAPH}/{pid}/videos", data={"description": text, "access_token": tok, "published": "true"},
                              files={"source": f}, timeout=(10, 600))
    elif image_path and os.path.exists(image_path):
        with open(image_path, "rb") as f:
            r = requests.post(f"{GRAPH}/{pid}/photos", data={"caption": text, "access_token": tok, "published": "true"},
                              files={"source": f}, timeout=(10, 120))
    else:
        r = requests.post(f"{GRAPH}/{pid}/feed", data={"message": text, "access_token": tok}, timeout=(10, 60))
    if r.status_code >= 300:
        raise RuntimeError(f"Facebook {r.status_code}: {r.text[:300]}")
    return r.json()


def check():
    """Semak token Page tanpa menghantar apa-apa: kembalikan (nama_page, tarikh_tamat). Raise jika token tidak sah."""
    from datetime import datetime, timezone
    pid, tok = os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_TOKEN"]
    h = {"Authorization": f"Bearer {tok}"}
    r = requests.get(f"{GRAPH}/{pid}", params={"fields": "name"}, headers=h, timeout=30)
    if r.status_code >= 300:
        raise RuntimeError(f"Facebook {r.status_code}: {r.text[:300]}")
    # Uji hantar tanpa posting awam: gambar 1x1 TIDAK diterbitkan, kemudian dipadam
    import base64
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==")
    ptok = page_token(pid, tok)
    t = requests.post(f"{GRAPH}/{pid}/photos", data={"published": "false", "access_token": ptok}, files={"source": ("t.png", png, "image/png")}, timeout=60)
    if t.status_code >= 300:
        raise RuntimeError(f"Uji hantar gagal, Facebook {t.status_code}: {t.text[:300]}")
    try:
        requests.delete(f"{GRAPH}/{t.json().get('id')}", data={"access_token": ptok}, timeout=30)
    except Exception:
        pass
    exp = "tidak diketahui"
    try:
        d = requests.get(f"{GRAPH}/debug_token", params={"input_token": tok}, headers=h, timeout=30).json().get("data", {})
        e = d.get("expires_at", None)
        if e is not None:
            exp = "tidak tamat" if e == 0 else datetime.fromtimestamp(e, timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        pass
    try:  # Instagram: akaun yang dipaut ke Page + kebenaran token (tanpa menghantar apa-apa)
        hp = {"Authorization": f"Bearer {ptok}"}
        j = requests.get(f"{GRAPH}/{pid}", params={"fields": "instagram_business_account{id,username}"}, headers=hp, timeout=30).json()
        ig = j.get("instagram_business_account") or {}
        d2 = requests.get(f"{GRAPH}/debug_token", params={"input_token": tok}, headers=h, timeout=30).json().get("data", {})
        exp += " | IG=" + str(ig.get("username") or ig.get("id") or ("tiada " + str(j.get("error", {}).get("message", ""))[:100])) \
            + " | skop=" + ",".join(d2.get("scopes", []))
    except Exception as e:
        exp += " | IG semak gagal: " + str(e)[:80]
    return r.json().get("name", "?") + " (uji hantar OK)", exp


def post_album(text, image_paths):
    """Beberapa gambar dalam SATU hantaran Page dengan satu caption."""
    pid = os.environ["FB_PAGE_ID"]
    tok = page_token(pid, os.environ["FB_PAGE_TOKEN"])
    ids = []
    for p in image_paths:
        with open(p, "rb") as f:
            r = requests.post(f"{GRAPH}/{pid}/photos", data={"published": "false", "access_token": tok}, files={"source": f}, timeout=(10, 120))
        if r.status_code >= 300:
            raise RuntimeError(f"Facebook gambar {r.status_code}: {r.text[:300]}")
        ids.append(r.json()["id"])
    data = {"message": text, "access_token": tok}
    for i, fid in enumerate(ids):
        data[f"attached_media[{i}]"] = json.dumps({"media_fbid": fid})
    r = requests.post(f"{GRAPH}/{pid}/feed", data=data, timeout=(10, 60))
    if r.status_code >= 300:
        raise RuntimeError(f"Facebook album {r.status_code}: {r.text[:300]}")
    return r.json()

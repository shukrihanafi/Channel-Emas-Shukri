"""Post terus ke Facebook Page melalui Graph API (ganti IFTTT). Aktif hanya jika FB_PAGE_TOKEN dan FB_PAGE_ID ditetapkan."""
import os
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
    exp = "tidak diketahui"
    try:
        d = requests.get(f"{GRAPH}/debug_token", params={"input_token": tok}, headers=h, timeout=30).json().get("data", {})
        e = d.get("expires_at", None)
        if e is not None:
            exp = "tidak tamat" if e == 0 else datetime.fromtimestamp(e, timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        pass
    return r.json().get("name", "?"), exp

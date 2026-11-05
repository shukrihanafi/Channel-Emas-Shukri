"""Post terus ke Facebook Page melalui Graph API (ganti IFTTT). Aktif hanya jika FB_PAGE_TOKEN dan FB_PAGE_ID ditetapkan."""
import os
import requests

GRAPH = "https://graph.facebook.com/v21.0"


def enabled() -> bool:
    return bool(os.getenv("FB_PAGE_TOKEN") and os.getenv("FB_PAGE_ID") and os.getenv("FB_AUTO", "1") == "1")


def post(text, image_path=None):
    """Gambar + caption (atau teks sahaja) ke Page. Token dihantar dalam badan permintaan, bukan URL."""
    pid, tok = os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_TOKEN"]
    if image_path and os.path.exists(image_path):
        with open(image_path, "rb") as f:
            r = requests.post(f"{GRAPH}/{pid}/photos", data={"caption": text, "access_token": tok, "published": "true"},
                              files={"source": f}, timeout=(10, 120))
    else:
        r = requests.post(f"{GRAPH}/{pid}/feed", data={"message": text, "access_token": tok}, timeout=(10, 60))
    if r.status_code >= 300:
        raise RuntimeError(f"Facebook {r.status_code}: {r.text[:300]}")
    return r.json()

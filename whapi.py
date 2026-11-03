"""Hantar post ke WhatsApp Channel melalui Whapi.cloud (perkhidmatan pihak ketiga, bukan API rasmi Meta)."""
import base64, mimetypes, os
import requests

API = "https://gate.whapi.cloud"


def enabled() -> bool:
    return bool(os.getenv("WHAPI_TOKEN") and os.getenv("WA_CHANNEL_ID"))


def _headers():
    return {"Authorization": f"Bearer {os.environ['WHAPI_TOKEN']}", "Accept": "application/json"}


def list_channels():
    """Senarai Channel yang dilihat nombor bot (untuk dapatkan ID Channel)."""
    r = requests.get(f"{API}/newsletters", params={"count": 100}, headers=_headers(), timeout=60)
    r.raise_for_status()
    j = r.json()
    items = j.get("newsletters") or j.get("channels") or []
    return [(c.get("id"), c.get("name"), c.get("role") or c.get("viewer_meta", {}).get("role", "")) for c in items]


def post_channel(text, image_path=None):
    """Satu post ke Channel: gambar + caption, atau teks sahaja."""
    cid = os.environ["WA_CHANNEL_ID"]
    if image_path and os.path.exists(image_path):
        mime = mimetypes.guess_type(image_path)[0] or "image/png"
        b64 = base64.b64encode(open(image_path, "rb").read()).decode()
        body = {"to": cid, "media": f"data:{mime};name={os.path.basename(image_path)};base64,{b64}", "caption": text}
        r = requests.post(f"{API}/messages/image", json=body, headers=_headers(), timeout=120)
    else:
        r = requests.post(f"{API}/messages/text", json={"to": cid, "body": text}, headers=_headers(), timeout=60)
    if r.status_code >= 300:
        raise RuntimeError(f"Whapi {r.status_code}: {r.text[:300]}")
    return r.json()

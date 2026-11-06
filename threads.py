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


def _fernet():
    from cryptography.fernet import Fernet
    seed = (os.getenv("TELEGRAM_BOT_TOKEN") or "") + "|threads"
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(seed.encode()).digest()))


def _h(env_tok):
    return hashlib.sha256(env_tok.encode()).hexdigest()[:12]


def token(st):
    """Token semasa: yang disambung & disimpan (jika masih berpadanan dengan secret), jika tidak secret asal."""
    env = os.environ["THREADS_TOKEN"].strip()
    s = (st or {}).get("threads") or {}
    if s.get("src") == _h(env) and s.get("enc"):
        try:
            return _fernet().decrypt(s["enc"].encode()).decode()
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


def post(st, text, image_path=None):
    tok = token(st)
    h = {"Authorization": f"Bearer {tok}"}
    uid = me(tok)["id"]
    text = fmt(text)
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

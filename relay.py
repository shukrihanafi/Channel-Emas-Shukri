"""Geganti posting manual Telegram -> WhatsApp Channel (dan Telegram Channel).

A) Shukri post terus di Telegram Channel (bot mesti admin)  -> bot salin ke WhatsApp Channel.
B) Shukri hantar mesej/gambar kepada bot (chat peribadi)    -> bot hantar ke WhatsApp Channel + Telegram Channel.
Mesej bermula dengan "/" diabaikan. Dipanggil dalam larian alert (setiap 20 minit); offset disimpan dalam state.
"""
import os, tempfile
import requests
import whapi


def _fetch_photo(base, token, file_id):
    r = requests.get(f"{base}/getFile", params={"file_id": file_id}, timeout=30)
    r.raise_for_status()
    fp = r.json()["result"]["file_path"]
    data = requests.get(f"https://api.telegram.org/file/bot{token}/{fp}", timeout=60)
    data.raise_for_status()
    path = os.path.join(tempfile.mkdtemp(), os.path.basename(fp))
    open(path, "wb").write(data.content)
    return path


def _tg_push(base, target, text, path):
    if path and len(text) <= 1024:
        with open(path, "rb") as f:
            requests.post(f"{base}/sendPhoto", data={"chat_id": target, "caption": text}, files={"photo": f}, timeout=60).raise_for_status()
        return
    if path:
        with open(path, "rb") as f:
            requests.post(f"{base}/sendPhoto", data={"chat_id": target}, files={"photo": f}, timeout=60).raise_for_status()
    if text:
        requests.post(f"{base}/sendMessage", data={"chat_id": target, "text": text}, timeout=60).raise_for_status()


def run(st, notify=print):
    token, owner = os.getenv("TELEGRAM_BOT_TOKEN"), str(os.getenv("TELEGRAM_CHAT_ID", ""))
    if not token or not owner or not whapi.enabled():
        return 0
    base = f"https://api.telegram.org/bot{token}"
    first = "relay" not in st
    rs = st.setdefault("relay", {"offset": 0})
    r = requests.get(f"{base}/getUpdates", params={"offset": rs["offset"], "timeout": 0,
                     "allowed_updates": '["message","channel_post"]'}, timeout=30)
    r.raise_for_status()
    if first:  # larian pertama: abaikan mesej lama, mula dari sekarang (elak siar mesej lama ke saluran awam)
        ups = r.json().get("result", [])
        rs["offset"] = (ups[-1]["update_id"] + 1) if ups else 0
        print("Relay: titik mula ditetapkan.")
        return 0
    done = 0
    tg_channel = os.getenv("TELEGRAM_CHANNEL", "").strip()
    for u in r.json().get("result", []):
        rs["offset"] = u["update_id"] + 1
        m = u.get("channel_post") or u.get("message")
        if not m:
            continue
        from_channel = "channel_post" in u
        if from_channel:
            uname = "@" + (m["chat"].get("username") or "")
            if tg_channel and uname.lower() != tg_channel.lower():
                continue
        elif str(m["chat"]["id"]) != owner:  # hanya pemilik boleh guna chat peribadi
            continue
        text = (m.get("caption") or m.get("text") or "").strip()
        if text.startswith("/"):
            continue
        path = None
        try:
            if m.get("photo"):
                path = _fetch_photo(base, token, m["photo"][-1]["file_id"])
            elif not text:
                continue  # jenis lain (video, dokumen, dll.) tidak disokong
            whapi.post_channel(text, path)
            dest = "WhatsApp Channel"
            if not from_channel and tg_channel:
                _tg_push(base, tg_channel, text, path)
                dest += f" + Telegram Channel {tg_channel}"
            notify(f"✅ Posting manual disalin ke {dest}.")
            done += 1
        except Exception as e:
            notify(f"⚠️ Gagal salin posting manual: {e}")
    return done

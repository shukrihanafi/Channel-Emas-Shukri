"""Geganti posting manual Telegram -> WhatsApp Channel (dan Telegram Channel).

A) Shukri post terus di Telegram Channel (bot mesti admin)  -> bot salin ke WhatsApp Channel.
B) Shukri hantar mesej/gambar kepada bot (chat peribadi)    -> bot hantar ke WhatsApp Channel + Telegram Channel.
Mesej bermula dengan "/" diabaikan. Dipanggil dalam larian alert (setiap 20 minit); offset disimpan dalam state.
"""
import os, tempfile
import requests
import whapi, fb


def _retry(fn, tries=3):
    """Ulang panggilan rangkaian (Telegram kadang-kadang tamat masa dari GitHub)."""
    import time
    for i in range(tries):
        try:
            return fn()
        except requests.RequestException:
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


def _fetch_photo(base, token, file_id):
    r = _retry(lambda: requests.get(f"{base}/getFile", params={"file_id": file_id}, timeout=(10, 60)))
    r.raise_for_status()
    fp = r.json()["result"]["file_path"]
    data = _retry(lambda: requests.get(f"https://api.telegram.org/file/bot{token}/{fp}", timeout=(10, 90)))
    data.raise_for_status()
    path = os.path.join(tempfile.mkdtemp(), os.path.basename(fp))
    open(path, "wb").write(data.content)
    return path


def _tg_push(base, target, text, path):
    if path and len(text) <= 1024:
        with open(path, "rb") as f:
            _retry(lambda: requests.post(f"{base}/sendPhoto", data={"chat_id": target, "caption": text}, files={"photo": open(path, "rb")}, timeout=(10, 90))).raise_for_status()
        return
    if path:
        with open(path, "rb") as f:
            _retry(lambda: requests.post(f"{base}/sendPhoto", data={"chat_id": target}, files={"photo": open(path, "rb")}, timeout=(10, 90))).raise_for_status()
    if text:
        _retry(lambda: requests.post(f"{base}/sendMessage", data={"chat_id": target, "text": text}, timeout=(10, 60))).raise_for_status()


def run(st, notify=print):
    token, owner = os.getenv("TELEGRAM_BOT_TOKEN"), str(os.getenv("TELEGRAM_CHAT_ID", ""))
    if not token or not owner or not whapi.enabled():
        return 0
    base = f"https://api.telegram.org/bot{token}"
    first = "relay" not in st
    rs = st.setdefault("relay", {"offset": 0})
    r = requests.get(f"{base}/getUpdates", params={"offset": rs["offset"], "timeout": 0,
                     "allowed_updates": '["message","channel_post"]'}, timeout=(10, 60))
    r.raise_for_status()
    if first:  # larian pertama: abaikan mesej lama, mula dari sekarang (elak siar mesej lama ke saluran awam)
        ups = r.json().get("result", [])
        rs["offset"] = (ups[-1]["update_id"] + 1) if ups else 0
        print("Relay: titik mula ditetapkan.")
        return 0
    done = 0
    tg_channel = os.getenv("TELEGRAM_CHANNEL", "").strip()
    for u in r.json().get("result", []):
        uid = u["update_id"]
        m = u.get("channel_post") or u.get("message")
        if not m:
            rs["offset"] = uid + 1
            continue
        from_channel = "channel_post" in u
        if from_channel:
            uname = "@" + (m["chat"].get("username") or "")
            if tg_channel and uname.lower() != tg_channel.lower():
                rs["offset"] = uid + 1
                continue
        elif str(m["chat"]["id"]) != owner:  # hanya pemilik boleh guna chat peribadi
            rs["offset"] = uid + 1
            continue
        text = (m.get("caption") or m.get("text") or "").strip()
        if text.startswith("/") or (not text and not m.get("photo")):  # arahan / jenis tidak disokong
            rs["offset"] = uid + 1
            continue
        try:
            path = _fetch_photo(base, token, m["photo"][-1]["file_id"]) if m.get("photo") else None
            if rs.get("wa_done") != uid:  # elak hantar dua kali ke WhatsApp jika langkah kemudian perlu diulang
                whapi.post_channel(text, path)
                rs["wa_done"] = uid
            dest = "WhatsApp Channel"
            if not from_channel and tg_channel:
                if rs.get("tg_done") != uid:
                    _tg_push(base, tg_channel, text, path)
                    rs["tg_done"] = uid
                dest += f" + Telegram Channel {tg_channel}"
            if fb.enabled():
                if rs.get("fb_done") != uid:
                    fb.post(text, path)
                    rs["fb_done"] = uid
                dest += " + Facebook Page"
            rs["offset"], rs["tries"] = uid + 1, 0
            notify(f"✅ Posting manual disalin ke {dest}.")
            done += 1
        except Exception as e:
            # JANGAN majukan offset: cuba lagi pada larian seterusnya (maksimum 5 kali, lalu dilangkau)
            rs["tries"] = rs.get("tries", 0) + 1
            if rs["tries"] >= 5:
                rs["offset"], rs["tries"] = uid + 1, 0
                notify(f"⚠️ Posting manual gagal disalin selepas 5 percubaan, dilangkau: {e}")
            elif rs["tries"] == 1:
                notify(f"⚠️ Gagal salin posting manual (akan dicuba lagi): {e}")
            break
    return done

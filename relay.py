"""Geganti posting manual Telegram -> WhatsApp Channel (dan Telegram Channel).

A) Shukri post terus di Telegram Channel (bot mesti admin)  -> bot salin ke WhatsApp Channel.
B) Shukri hantar mesej/gambar/video kepada bot (chat peribadi)    -> bot hantar ke WhatsApp Channel + Telegram Channel.
Video disokong sehingga 20 MB (had muat turun bot Telegram). Mesej bermula dengan "/" diabaikan. Dipanggil dalam larian alert (setiap 20 minit); offset disimpan dalam state.
"""
import os, tempfile
import requests
import whapi, fb

MAX_VIDEO = 20 * 1024 * 1024  # had muat turun fail oleh bot Telegram


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


def _fetch_file(base, token, file_id):
    r = _retry(lambda: requests.get(f"{base}/getFile", params={"file_id": file_id}, timeout=(10, 60)))
    r.raise_for_status()
    fp = r.json()["result"]["file_path"]
    data = _retry(lambda: requests.get(f"https://api.telegram.org/file/bot{token}/{fp}", timeout=(10, 90)))
    data.raise_for_status()
    path = os.path.join(tempfile.mkdtemp(), os.path.basename(fp))
    open(path, "wb").write(data.content)
    return path


def _tg_push(base, target, text, path, video=False):
    api, field = ("sendVideo", "video") if video else ("sendPhoto", "photo")
    if path and len(text) <= 1024:
        _retry(lambda: requests.post(f"{base}/{api}", data={"chat_id": target, "caption": text}, files={field: open(path, "rb")}, timeout=(10, 300))).raise_for_status()
        return
    if path:
        _retry(lambda: requests.post(f"{base}/{api}", data={"chat_id": target}, files={field: open(path, "rb")}, timeout=(10, 300))).raise_for_status()
    if text:
        _retry(lambda: requests.post(f"{base}/sendMessage", data={"chat_id": target, "text": text}, timeout=(10, 60))).raise_for_status()


def run(st, notify=print):
    token, owner = os.getenv("TELEGRAM_BOT_TOKEN"), str(os.getenv("TELEGRAM_CHAT_ID", ""))
    if not token or not owner or not whapi.enabled():
        return 0
    base = f"https://api.telegram.org/bot{token}"
    first = "relay" not in st
    rs = st.setdefault("relay", {"offset": 0})
    r = _retry(lambda: requests.get(f"{base}/getUpdates", params={"offset": rs["offset"], "timeout": 0,
                     "allowed_updates": '["message","channel_post"]'}, timeout=(10, 60)))
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
        vid = m.get("video")
        if text.startswith("/") or (not text and not m.get("photo") and not vid):  # arahan / jenis tidak disokong
            rs["offset"] = uid + 1
            continue
        if vid and (vid.get("file_size") or 0) > MAX_VIDEO:  # terlalu besar untuk bot: beritahu, jangan senyap
            rs["offset"], rs["tries"] = uid + 1, 0
            notify(f"⚠️ Video {vid['file_size'] / 1048576:.0f} MB melebihi had 20 MB bot Telegram, tidak disalin. Sila post manual di WhatsApp dan Facebook.")
            continue
        try:
            if vid:
                path = _fetch_file(base, token, vid["file_id"])
            else:
                path = _fetch_file(base, token, m["photo"][-1]["file_id"]) if m.get("photo") else None
            if rs.get("wa_done") != uid:  # elak hantar dua kali ke WhatsApp jika langkah kemudian perlu diulang
                if vid:
                    whapi.post_channel(text, video_path=path)
                else:
                    whapi.post_channel(text, path)
                rs["wa_done"] = uid
            dest = "WhatsApp Channel"
            if not from_channel and tg_channel:
                if rs.get("tg_done") != uid:
                    _tg_push(base, tg_channel, text, path, bool(vid))
                    rs["tg_done"] = uid
                dest += f" + Telegram Channel {tg_channel}"
            if fb.enabled():
                if rs.get("fb_done") != uid:
                    fb.post(text, video_path=path) if vid else fb.post(text, path)
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

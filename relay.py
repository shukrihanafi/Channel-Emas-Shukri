"""Geganti posting manual Telegram -> WhatsApp Channel (dan Telegram Channel).

A) Shukri post terus di Telegram Channel (bot mesti admin)  -> bot salin ke WhatsApp Channel.
B) Shukri hantar mesej/gambar/video kepada bot (chat peribadi)    -> bot hantar ke WhatsApp Channel + Telegram Channel.
Video disokong sehingga 20 MB (had muat turun bot Telegram). Mesej bermula dengan "/" diabaikan. Dipanggil dalam larian alert (setiap 20 minit); offset disimpan dalam state.

C) Video siap edit: dihantar ke chat peribadi OLEH BOT (send_for_approval.py) dengan butang. Tiada apa disiar sehingga Shukri tekan
   Approve sekarang / pilih jadual. Butang diproses di sini (callback_query); item dijadual disimpan dalam state["relay"]["pending"].
"""
import os, tempfile, json
from datetime import datetime, timedelta, timezone
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


MYT = timezone(timedelta(hours=8))


def _now():
    return datetime.now(timezone.utc)


def approval_keyboard(page="main"):
    """Papan butang untuk video menunggu kelulusan. callback_data: ap / n20 / m07 / hr / h{HH} / bk / rj / noop."""
    if page == "hours":
        rows, row = [], []
        for h in range(7, 24):
            row.append({"text": f"{h}:09", "callback_data": f"h{h:02d}"})
            if len(row) == 4:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows.append([{"text": "⬅️ Kembali", "callback_data": "bk"}])
        return {"inline_keyboard": rows}
    return {"inline_keyboard": [
        [{"text": "✅ Approve sekarang", "callback_data": "ap"}],
        [{"text": "🌙 Malam ini 8:09", "callback_data": "n20"}, {"text": "🌅 Esok 7:09 pagi", "callback_data": "m07"}],
        [{"text": "🕒 Pilih masa lain", "callback_data": "hr"}],
        [{"text": "❌ Tolak", "callback_data": "rj"}]]}


def _next_slot(hour, tomorrow=False):
    """Masa MYT HH:09 seterusnya (atau esok) sebagai UTC."""
    now = _now().astimezone(MYT)
    t = now.replace(hour=hour, minute=9, second=0, microsecond=0)
    if tomorrow:
        t = (now + timedelta(days=1)).replace(hour=hour, minute=9, second=0, microsecond=0)
    elif t <= now:
        t += timedelta(days=1)
    return t.astimezone(timezone.utc)


def _tg(base, method, **data):
    """Panggilan Telegram best-effort (jawapan butang boleh tamat tempoh)."""
    try:
        return requests.post(f"{base}/{method}", data=data, timeout=(10, 60))
    except requests.RequestException:
        return None


def _deliver(st, rs, key, text, vid, photo, from_channel, notify, base, token, tg_channel):
    """Hantar satu posting ke semua platform. vid/photo = objek Telegram (ada file_id) atau None. Pulangkan senarai destinasi.
    key = id unik (update_id atau id kelulusan) untuk bendera elak-hantar-dua-kali apabila diulang."""
    if vid:
        path = _fetch_file(base, token, vid["file_id"])
    else:
        path = _fetch_file(base, token, photo[-1]["file_id"]) if photo else None
    if rs.get("wa_done") != key:  # elak hantar dua kali ke WhatsApp jika langkah kemudian perlu diulang
        if vid:
            whapi.post_channel(text, video_path=path)
        else:
            whapi.post_channel(text, path)
        rs["wa_done"] = key
    dest = "WhatsApp Channel"
    if not from_channel and tg_channel:
        if rs.get("tg_done") != key:
            _tg_push(base, tg_channel, text, path, bool(vid))
            rs["tg_done"] = key
        dest += f" + Telegram Channel {tg_channel}"
    if fb.enabled():
        if rs.get("fb_done") != key:
            fb.post(text, video_path=path) if vid else fb.post(text, path)
            rs["fb_done"] = key
        dest += " + Facebook Page"
    # Threads + Instagram: teks panjang diringkaskan, sentiasa tamat dengan shukriee.com. Kegagalan di sini tidak mengulang langkah lain.
    import threads, instagram
    if threads.enabled():
        try:
            if rs.get("th_done") != key:
                rs["th_done"] = key
                tt = threads.summarize(text, 450)
                threads.post_video(st, tt, path) if vid else threads.post(st, tt, path)
            dest += " + Threads"
        except Exception as e:
            notify(f"⚠️ Gagal hantar posting manual ke Threads: {e}")
    if instagram.enabled():
        try:
            if rs.get("ig_done") != key:
                rs["ig_done"] = key
                ic = threads.summarize(text, 1200)
                instagram.post_video(ic, path) if vid else instagram.post(ic, path or instagram.fallback_image())
            dest += " + Instagram"
        except Exception as e:
            notify(f"⚠️ Gagal hantar posting manual ke Instagram: {e}")
    return dest


def _handle_callback(rs, cb, owner, base, notify):
    """Proses satu tekanan butang kelulusan. Tiada penyiaran di sini: hanya masukkan ke giliran 'pending' (due = sekarang atau jadual)."""
    if str(cb.get("from", {}).get("id")) != owner:
        _tg(base, "answerCallbackQuery", callback_query_id=cb["id"], text="Tidak dibenarkan.")
        return
    m = cb.get("message") or {}
    vid, data = m.get("video"), cb.get("data", "")
    chat, mid = m.get("chat", {}).get("id"), m.get("message_id")
    ans = lambda t: _tg(base, "answerCallbackQuery", callback_query_id=cb["id"], text=t)
    mark = lambda markup: _tg(base, "editMessageReplyMarkup", chat_id=chat, message_id=mid, reply_markup=json.dumps(markup))
    done = rs.setdefault("cbdone", [])
    pend = rs.setdefault("pending", {})
    key = f"a{mid}"
    if data == "noop":
        return ans("Sudah diproses.")
    if data == "hr":
        mark(approval_keyboard("hours"))
        return ans("Pilih jam (waktu Malaysia)")
    if data == "bk":
        mark(approval_keyboard())
        return ans("")
    if not vid:
        return ans("Mesej ini bukan video kelulusan.")
    if key in pend or mid in done:
        return ans("Sudah diproses.")
    text = (m.get("caption") or "").strip()
    if data == "rj":
        done.append(mid)
        rs["cbdone"] = done[-50:]
        mark({"inline_keyboard": [[{"text": "❌ Ditolak (tidak disiar)", "callback_data": "noop"}]]})
        return ans("Ditolak, tiada apa disiar.")
    if (vid.get("file_size") or 0) > MAX_VIDEO:
        ans("Video melebihi 20 MB.")
        return notify(f"⚠️ Video {vid['file_size'] / 1048576:.0f} MB melebihi had 20 MB bot Telegram, tidak boleh disiar auto. Sila post manual.")
    if data == "ap":
        due, label = _now(), "✅ Diluluskan, dalam giliran siaran"
    elif data == "n20":
        due = _next_slot(20)
        label = f"⏰ Dijadual {due.astimezone(MYT):%d/%m %H:%M}"
    elif data == "m07":
        due = _next_slot(7, tomorrow=True)
        label = f"⏰ Dijadual {due.astimezone(MYT):%d/%m %H:%M}"
    elif data.startswith("h") and data[1:].isdigit():
        due = _next_slot(int(data[1:]))
        label = f"⏰ Dijadual {due.astimezone(MYT):%d/%m %H:%M}"
    else:
        return ans("Butang tidak dikenali.")
    pend[key] = {"vid": vid, "text": text, "due": due.isoformat(), "tries": 0, "mid": mid}
    done.append(mid)
    rs["cbdone"] = done[-50:]
    mark({"inline_keyboard": [[{"text": label, "callback_data": "noop"}]]})
    ans(label)
    notify(f"{label}. Video akan disiar ke 5 platform pada semakan seterusnya (setiap ~20 minit).")


def _process_pending(st, rs, base, token, tg_channel, notify):
    n = 0
    pend = rs.setdefault("pending", {})
    for key in sorted(pend, key=lambda k: pend[k]["due"]):
        it = pend[key]
        if datetime.fromisoformat(it["due"]) > _now():
            continue
        try:
            dest = _deliver(st, rs, key, it["text"], it["vid"], None, False, notify, base, token, tg_channel)
            del pend[key]
            notify(f"✅ Video lulus disiar ke {dest}.")
            n += 1
        except Exception as e:
            it["tries"] = it.get("tries", 0) + 1
            if it["tries"] >= 5:
                del pend[key]
                notify(f"⚠️ Video lulus gagal disiar selepas 5 percubaan, dibuang daripada giliran: {e}")
            else:
                if it["tries"] == 1:
                    notify(f"⚠️ Gagal siar video lulus (akan dicuba lagi): {e}")
            break
    return n


def run(st, notify=print):
    token, owner = os.getenv("TELEGRAM_BOT_TOKEN"), str(os.getenv("TELEGRAM_CHAT_ID", ""))
    if not token or not owner or not whapi.enabled():
        return 0
    base = f"https://api.telegram.org/bot{token}"
    first = "relay" not in st
    rs = st.setdefault("relay", {"offset": 0})
    r = _retry(lambda: requests.get(f"{base}/getUpdates", params={"offset": rs["offset"], "timeout": 0,
                     "allowed_updates": '["message","channel_post","callback_query"]'}, timeout=(10, 60)))
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
        if "callback_query" in u:  # butang kelulusan video
            try:
                _handle_callback(rs, u["callback_query"], owner, base, notify)
            except Exception as e:
                notify(f"⚠️ Gagal proses butang kelulusan: {e}")
            rs["offset"] = uid + 1
            continue
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
            dest = _deliver(st, rs, uid, text, vid, m.get("photo"), from_channel, notify, base, token, tg_channel)
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
    done += _process_pending(st, rs, base, token, tg_channel, notify)
    return done

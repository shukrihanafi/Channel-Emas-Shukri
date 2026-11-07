"""Geganti posting manual Telegram -> WhatsApp Channel (dan Telegram Channel).

A) Shukri post terus di Telegram Channel (bot mesti admin)  -> bot salin ke WhatsApp Channel.
B) Shukri hantar mesej/gambar/video kepada bot (chat peribadi)    -> bot hantar ke WhatsApp Channel + Telegram Channel.
Video disokong sehingga 20 MB (had muat turun bot Telegram). Mesej bermula dengan "/" diabaikan. Dipanggil dalam larian alert (setiap 20 minit); offset disimpan dalam state.

C) Video siap edit: dihantar ke chat peribadi OLEH BOT (send_for_approval.py) dengan butang. Tiada apa disiar sehingga Shukri tekan
   Approve sekarang / pilih jadual. Butang diproses di sini (callback_query); item dijadual disimpan dalam state["relay"]["pending"].
"""
import os, re, tempfile, json
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


TAGS = ("#BelumPost", "#Approve", "#Tolak")


def send_status(base, chat, tag="#BelumPost"):
    """Mesej status berasingan (hashtag sahaja) dihantar SEBELUM video; video dibalas pada mesej ini. Caption video kekal bersih."""
    resp = _tg(base, "sendMessage", chat_id=chat, text=tag)
    try:
        return resp.json()["result"]["message_id"]
    except Exception:
        return None


def strip_tag(caption):
    lines = (caption or "").rstrip().split("\n")
    if lines and lines[-1].strip() in TAGS:
        lines.pop()
    return "\n".join(lines).rstrip()


DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def approval_keyboard(page="main", kind="video", taken=()):
    """Papan butang kelulusan, hanya 2 pilihan: Approve sekarang (ts) atau Schedule (sc) -> pilih tarikh (sd{off}) -> jam (sh{off}_{HH}) -> minit (sm{off}_{HH}_{MM}).
    Kedua-duanya menyebabkan bot hantar peringatan TikTok manual selepas siaran. (Callback lama ap/n20/m07/hr/h{HH}/rj masih diproses untuk mesej lama.)"""
    back = lambda cb: [{"text": "⬅️ Kembali", "callback_data": cb}]
    if page == "dates":  # tarikh + jam sekali: 3 hari bermula hari ini, jam 11:15 dan 23:15 (slot yang sudah lalu disembunyikan)
        now = _now().astimezone(MYT)
        rows = []
        for i in range(3):
            d = now + timedelta(days=i)
            row = []
            for hh, mm in ((11, 15), (23, 15)):
                if d.replace(hour=hh, minute=mm, second=0, microsecond=0) > now and f"{d:%Y-%m-%d} {hh:02d}:{mm:02d}" not in taken:
                    row.append({"text": f"{('Today', 'Esok', 'Lusa')[i]} @ {hh}{mm:02d}", "callback_data": f"sm{i}_{hh:02d}_{mm:02d}"})
            if row:
                rows.append(row)
        rows.append(back("bk"))
        return {"inline_keyboard": rows}
    if page.startswith("hrs"):
        off = page[3:]
        rows, row = [], []
        for h in range(24):
            row.append({"text": f"{h:02d}", "callback_data": f"sh{off}_{h:02d}"})
            if len(row) == 6:
                rows.append(row)
                row = []
        rows.append(back("sc"))
        return {"inline_keyboard": rows}
    if page.startswith("min"):
        off, hh = page[3:].split("_")
        rows = [[{"text": f"{hh}:{m}", "callback_data": f"sm{off}_{hh}_{m}"} for m in ("00", "15", "30", "45")]]
        rows.append(back(f"sd{off}"))
        return {"inline_keyboard": rows}
    if kind != "video":  # gambar / ayat: tiada TikTok
        return {"inline_keyboard": [
            [{"text": "✅ Approve 5 (Now)", "callback_data": "ts"}],
            [{"text": "⏰ Schedule 5", "callback_data": "sc"}]]}
    return {"inline_keyboard": [
        [{"text": "✅ Approve 5 (Now) + TikTok Manual", "callback_data": "ts"}],
        [{"text": "⏰ Schedule + TikTok Manual", "callback_data": "sc"}]]}


def _tt_status_text(done, text=""):
    """Teks status TikTok yang boleh ditapis: ketik #TikTok_Belum atau #TikTok_Done dalam Telegram untuk senarai semua yang berkenaan."""
    first = next((l.strip() for l in (text or "").splitlines() if l.strip() and not l.strip().lower().startswith(("amboi", "shukriee"))), "")
    head = ("✅ TikTok: SUDAH POST\n#TikTok_Done" if done else "⏳ TikTok: BELUM POST\n#TikTok_Belum")
    return head + (f"\n🎬 {first[:60]}" if first else "")


def _tt_keyboard(done):
    return {"inline_keyboard": [[{"text": "↩️ Batal (belum post)", "callback_data": "ttu"}] if done else
                                [{"text": "✅ Dah post di TikTok", "callback_data": "ttd"}]]}


def tt_reminder(base, owner, text, mid, notify=print):
    """Peringatan TikTok manual: mesej status (#TikTok_Belum) dengan butang 'Dah post', diikuti caption siap salin. Tanpa Claude."""
    sresp = _tg(base, "sendMessage", chat_id=owner, text=_tt_status_text(False, text) + "\n\n"
        "1) Simpan video di atas ke galeri\n2) TikTok > Upload > tampal caption di bawah\n3) Siar atau jadual, kemudian tekan butang di bawah",
        reply_to_message_id=mid, reply_markup=json.dumps(_tt_keyboard(False)))
    cap = (text or "").replace("`", "'")
    _tg(base, "sendMessage", chat_id=owner, text=f"```\n{cap}\n```", parse_mode="Markdown", reply_to_message_id=mid)


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


def _report(base, owner, text):
    """Hantar laporan ke chat bot, pulangkan message_id supaya boleh dipadam bila jadual dibatal / posting dipadam."""
    resp = _tg(base, "sendMessage", chat_id=owner, text=text, disable_web_page_preview="true")
    try:
        return resp.json()["result"]["message_id"]
    except Exception:
        return None


def _unreport(base, owner, rec):
    mid = rec.pop("rep", None)
    if mid:
        _tg(base, "deleteMessage", chat_id=owner, message_id=mid)


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
    # Threads + Instagram: teks panjang diringkaskan, sentiasa tamat dengan shukriee.com.
    # Kegagalan di sini tidak mengulang langkah lain; platform yang gagal dimasukkan ke giliran cuba-semula (rs["redo"]).
    import threads, instagram
    for name, mod in (("th", threads), ("ig", instagram)):
        if not mod.enabled() or rs.get(f"{name}_done") == key:
            continue
        try:
            _post_social(st, name, text, path, bool(vid))
            rs[f"{name}_done"] = key
            dest += " + " + ("Threads" if name == "th" else "Instagram")
        except Exception as e:
            label = "Threads" if name == "th" else "Instagram"
            notify(f"⚠️ Gagal hantar posting manual ke {label}: {e} (akan dicuba lagi automatik)")
            if vid:
                rd = rs.setdefault("redo", {}).setdefault(key, {"vid": vid, "text": text, "plats": [], "tries": 0,
                                                                "due": (_now() + timedelta(minutes=10)).isoformat()})
                if name not in rd["plats"]:
                    rd["plats"].append(name)
    return dest


def _post_social(st, name, text, path, is_video):
    import threads, instagram
    if name == "th":
        tt = threads.summarize(text, 450)
        threads.post_video(st, tt, path) if is_video else threads.post(st, tt, path)
    else:
        ic = threads.summarize(text, 1200)
        instagram.post_video(ic, path) if is_video else instagram.post(ic, path or instagram.fallback_image())


def _process_redo(st, rs, base, token, notify):
    """Cuba semula Threads/Instagram yang gagal (sehingga 3 percubaan tambahan, jarak 10 minit)."""
    redo = rs.get("redo") or {}
    for key in list(redo):
        it = redo[key]
        if datetime.fromisoformat(it["due"]) > _now():
            continue
        path = _fetch_file(base, token, it["vid"]["file_id"])
        for name in list(it["plats"]):
            label = "Threads" if name == "th" else "Instagram"
            try:
                _post_social(st, name, it["text"], path, True)
                rs[f"{name}_done"] = key
                it["plats"].remove(name)
                notify(f"✅ {label} berjaya selepas dicuba semula.")
            except Exception as e:
                it["tries"] += 1
                it["due"] = (_now() + timedelta(minutes=10)).isoformat()
                if it["tries"] >= 3 * len(it["plats"]):
                    it["plats"].remove(name)
                    notify(f"❌ {label} gagal selepas beberapa percubaan: {str(e)[:300]}. Sila post manual ke {label}.")
        if not it["plats"]:
            del redo[key]
        break  # satu item setiap larian (elak larian terlalu lama)


def _vid_obj(m):
    """Objek video daripada mesej Telegram: video biasa, atau fail (document) berjenis video."""
    v = m.get("video")
    if v:
        return v
    d = m.get("document")
    if d and str(d.get("mime_type", "")).startswith("video/"):
        return d
    return None


def _video_to_approval(rs, m, base, notify):
    """Shukri hantar video terus dalam kumpulan MEDIA APPROVAL: bot hantar semula video itu (guna file_id, tanpa muat turun)
    dengan butang Approve / Jadual / Tolak. Video lebih 20 MB tidak boleh dimuat turun bot Telegram: beri panduan (jalan Google Drive)."""
    v = _vid_obj(m)
    if not v:
        return
    chat, mid = m["chat"]["id"], m["message_id"]
    caption = (m.get("caption") or "").strip()[:1024]
    size = v.get("file_size") or 0
    if size > MAX_VIDEO:
        _tg(base, "sendMessage", chat_id=chat, reply_to_message_id=mid, text=(
            f"⚠️ Video ini {size / 1048576:.0f} MB, melebihi had 20 MB yang boleh dimuat turun bot Telegram, jadi bot tidak boleh kecilkan atau siarkannya dari sini.\n\n"
            "Pilihan:\n"
            "1) Hantar semula sebagai VIDEO (bukan Fail) supaya Telegram kecilkan dahulu.\n"
            "2) Letak video di Google Drive: emas > video-approval (caption: fail .txt dengan nama sama). Bot akan kecilkan automatik (kira-kira 30 minit) dan hantar ke sini dengan butang."))
        return
    is_video = bool(m.get("video"))
    method, field = ("sendVideo", "video") if is_video else ("sendDocument", "document")
    data = {"chat_id": chat, field: v["file_id"], "caption": caption, "reply_markup": json.dumps(approval_keyboard())}
    sid = send_status(base, chat)
    if sid:
        data["reply_to_message_id"] = sid
    if is_video:
        data["supports_streaming"] = "true"
    resp = _tg(base, method, **data)
    try:
        _vrec(rs, chat, resp.json()["result"]["message_id"])
    except Exception:
        pass
    if resp is None or resp.status_code >= 300:
        notify(f"⚠️ Gagal sediakan butang kelulusan untuk video dalam kumpulan: {(resp.text[:200] if resp is not None else 'tiada jawapan')}")


def _media_to_approval(rs, m, base, notify):
    """Mesej Shukri dalam kumpulan MEDIA APPROVAL: video, gambar atau ayat. Bot hantar semula dengan butang kelulusan."""
    if _vid_obj(m):
        return _video_to_approval(rs, m, base, notify)
    chat = m["chat"]["id"]
    photo, text = m.get("photo"), (m.get("text") or "").strip()
    if photo:
        method, typ = "sendPhoto", "Image"
        data = {"photo": photo[-1]["file_id"], "caption": (m.get("caption") or "").strip()[:1024]}
    elif text and not text.startswith("/"):
        method, typ = "sendMessage", "Ayat"
        data = {"text": text[:4096], "disable_web_page_preview": "true"}
    else:
        return
    data.update(chat_id=chat, reply_markup=json.dumps(approval_keyboard("main", "other")))
    sid = send_status(base, chat)
    if sid:
        data["reply_to_message_id"] = sid
    resp = _tg(base, method, **data)
    try:
        _vrec(rs, chat, resp.json()["result"]["message_id"])["type"] = typ
    except Exception:
        notify(f"⚠️ Gagal sediakan butang kelulusan untuk {typ} dalam kumpulan: {(resp.text[:200] if resp is not None else 'tiada jawapan')}")


def _msg_link(chat, mid):
    """Pautan terus ke mesej di kumpulan peribadi (hanya ada untuk supergroup, id bermula -100)."""
    s = str(chat)
    return f"https://t.me/c/{s[4:]}/{mid}" if s.startswith("-100") and mid else None


def _handle_callback(rs, cb, owner, base, notify):
    """Proses satu tekanan butang kelulusan. Tiada penyiaran di sini: hanya masukkan ke giliran 'pending' (due = sekarang atau jadual)."""
    if str(cb.get("from", {}).get("id")) != owner:
        _tg(base, "answerCallbackQuery", callback_query_id=cb["id"], text="Tidak dibenarkan.")
        return
    m = cb.get("message") or {}
    vid, data = _vid_obj(m), cb.get("data", "")
    photo = m.get("photo")
    kind = "video" if vid else "other"
    typ = "Video" if vid else ("Image" if photo else "Ayat")
    taken = {datetime.fromisoformat(p["due"]).astimezone(MYT).strftime("%Y-%m-%d %H:%M") for k, p in rs.get("pending", {}).items()
             if k != f"a{m.get('message_id')}"}  # slot jadual yang sudah dipilih oleh posting lain
    kb = lambda page="main": approval_keyboard(page, kind, taken)
    chat, mid = m.get("chat", {}).get("id"), m.get("message_id")
    ans = lambda t: _tg(base, "answerCallbackQuery", callback_query_id=cb["id"], text=t)
    mark = lambda markup: _tg(base, "editMessageReplyMarkup", chat_id=chat, message_id=mid, reply_markup=json.dumps(markup))
    done = rs.setdefault("cbdone", [])
    pend = rs.setdefault("pending", {})
    key = f"a{mid}"
    sid = (m.get("reply_to_message") or {}).get("message_id")

    def retag(tag, markup):  # tukar hashtag pada mesej status berasingan, dan kemas kini butang video
        if sid:
            _tg(base, "editMessageText", chat_id=chat, message_id=sid, text=tag)
        mark(markup)
    if data == "noop":
        return ans("Sudah diproses.")
    if data == "cx":  # batal jadual (hanya jika belum disiar)
        if key in pend:
            del pend[key]
            if mid in done:
                done.remove(mid)
            retag("#BelumPost", kb())
            rec = _vrec(rs, chat, mid)
            rec["status"] = "BelumPost"
            rec.pop("due", None)
            _unreport(base, owner, rec)
            return ans("Jadual dibatalkan")
        return ans("Sudah disiar, tidak boleh dibatalkan.")
    if data in ("ttd", "ttu"):  # status TikTok manual: dah post / batal
        isdone = data == "ttd"
        body = (m.get("text") or "")
        first = next((l[2:].strip() for l in body.splitlines() if l.startswith("🎬")), "")
        steps = body.split("\n\n", 1)[1] if "\n\n" in body else ""
        txt = _tt_status_text(isdone, first) + ("\n\n" + steps if steps else "")
        _tg(base, "editMessageText", chat_id=chat, message_id=mid, text=txt, reply_markup=json.dumps(_tt_keyboard(isdone)))
        vm = (m.get("reply_to_message") or {}).get("message_id")
        if vm:
            rec = _vrec(rs, chat, vm)
            rec["tt"] = "Done" if isdone else "Belum"
            rec["delivered"] = True
            if isdone:
                rec["done_at"] = _now().isoformat()
        return ans("Ditanda: sudah post ✅" if isdone else "Ditanda: belum post")
    if data == "hr":
        mark(kb("dates"))
        return ans("Pilih tarikh")
    if data == "sc":
        mark(kb("dates"))
        return ans("Pilih tarikh")
    if re.fullmatch(r"sd\d+", data):
        mark(kb("hrs" + data[2:]))
        return ans("Pilih jam (waktu Malaysia)")
    if re.fullmatch(r"sh\d+_\d\d", data):
        mark(kb("min" + data[2:]))
        return ans("Pilih minit")
    if data == "bk":
        mark(kb())
        return ans("")
    if not (vid or photo or m.get("text")):
        return ans("Mesej ini bukan media kelulusan.")
    if key in pend or mid in done:
        return ans("Sudah diproses.")
    text = strip_tag((m.get("caption") or m.get("text") or "").strip())
    if data == "rj":
        done.append(mid)
        rs["cbdone"] = done[-50:]
        retag("#Tolak", {"inline_keyboard": [[{"text": "❌ Ditolak (tidak disiar)", "callback_data": "noop"}]]})
        return ans("Ditolak, tiada apa disiar.")
    if vid and (vid.get("file_size") or 0) > MAX_VIDEO:
        ans("Video melebihi 20 MB.")
        return notify(f"⚠️ Video {vid['file_size'] / 1048576:.0f} MB melebihi had 20 MB bot Telegram, tidak boleh disiar auto. Sila post manual.")
    tt = False
    if data == "ap":
        due, label = _now(), "✅ 5 platform sekarang (tiada TikTok)"
    elif data == "ts":
        due, label, tt = _now(), "✅ 5 platform sekarang + 📣 peringatan TikTok", True
    elif re.fullmatch(r"sm\d+_\d\d_\d\d", data):
        off, hh, mm = data[2:].split("_")
        t = (_now().astimezone(MYT) + timedelta(days=int(off))).replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
        if t <= _now().astimezone(MYT):
            mark(kb("dates"))
            return ans("Masa itu sudah lalu, pilih semula.")
        if t.strftime("%Y-%m-%d %H:%M") in taken:
            mark(kb("dates"))
            return ans("Slot itu sudah diambil posting lain, pilih slot lain.")
        due, tt = t.astimezone(timezone.utc), True
        label = f"⏰ Dijadual {t:%d/%m %H:%M} + 📣 peringatan TikTok"
    elif data == "n20" or data == "m07" or (data.startswith("h") and data[1:].isdigit()):
        if data == "n20":
            due = _next_slot(20)
        elif data == "m07":
            due = _next_slot(7, tomorrow=True)
        else:
            due = _next_slot(int(data[1:]))
        label, tt = f"⏰ Dijadual {due.astimezone(MYT):%d/%m %H:%M} + 📣 peringatan TikTok", True
    else:
        return ans("Butang tidak dikenali.")
    if not vid:  # gambar / ayat: tiada peringatan TikTok
        tt = False
        label = label.replace(" + 📣 peringatan TikTok", "")
    pend[key] = {"vid": vid, "photo": photo, "text": text, "due": due.isoformat(), "tries": 0, "mid": mid, "tt": tt, "chat": chat}
    done.append(mid)
    rs["cbdone"] = done[-50:]
    sched = data not in ("ap", "ts")
    rec = _vrec(rs, chat, mid)
    rec["status"], rec["due"], rec["type"] = ("Schedule" if sched else "Approve"), due.isoformat(), typ
    rows = [[{"text": label, "callback_data": "noop"}]] + ([[{"text": "❌ Batal jadual", "callback_data": "cx"}]] if sched else [])
    retag("#Schedule" if sched else "#Approve", {"inline_keyboard": rows})
    ans(label)
    _unreport(base, owner, rec)
    if sched:
        link = _msg_link(chat, mid)
        rec["rep"] = _report(base, owner, f"#Schedule {typ} {label}.\n\n{typ} akan post ke 5 platform pada waktu jadual.\n" + ("Peringatan TikTok akan dihantar selepas itu.\n" if tt else "") + "\n"
                             + (f"{typ} : {link}" if link else f"{typ} : dalam kumpulan MEDIA APPROVAL (tapis #Schedule)"))
    else:
        rec["rep"] = _report(base, owner, f"{label}. {typ} akan disiar ke 5 platform sebentar lagi."
                             + (" Peringatan TikTok akan dihantar selepas itu." if tt else ""))


def _process_pending(st, rs, base, token, tg_channel, notify):
    n = 0
    pend = rs.setdefault("pending", {})
    for key in sorted(pend, key=lambda k: pend[k]["due"]):
        it = pend[key]
        if datetime.fromisoformat(it["due"]) > _now():
            continue
        try:
            dest = _deliver(st, rs, key, it["text"], it.get("vid"), it.get("photo"), False, notify, base, token, tg_channel)
            del pend[key]
            pass
            n += 1
            rec = _vrec(rs, it.get("chat"), it.get("mid"))
            rec["delivered"] = True
            rec["done_at"] = _now().isoformat()
            if it.get("tt"):
                tt_reminder(base, it.get("chat") or os.getenv("TELEGRAM_CHAT_ID", ""), it["text"], it.get("mid"), notify)
                rec["tt"] = "Belum"
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


def _vrec(rs, chat, mid):
    """Rekod status satu video dalam kumpulan MEDIA APPROVAL (untuk laporan pusat)."""
    return rs.setdefault("vids", {}).setdefault(str(mid), {"chat": chat, "mid": mid, "status": "BelumPost", "type": "Video"})


def _dash_text(rs):
    now = _now()
    vids = rs.setdefault("vids", {})
    for key, it in rs.get("pending", {}).items():  # pastikan item dalam giliran ada rekod
        rec = _vrec(rs, it.get("chat"), it.get("mid"))
        if not it.get("vid") and rec.get("type") == "Video":
            rec["type"] = "Image" if it.get("photo") else "Ayat"
        if rec["status"] == "BelumPost" or "due" not in rec:
            rec["status"] = "Schedule" if datetime.fromisoformat(it["due"]) > now + timedelta(minutes=2) else "Approve"
            rec["due"] = it["due"]
    old = lambda v, h: v.get("done_at") and now - datetime.fromisoformat(v["done_at"]) > timedelta(hours=h)
    for k in [k for k, v in vids.items() if (v.get("tt") == "Done" and old(v, 48))
              or (v.get("type", "Video") == "Video" and v.get("delivered") and not v.get("tt"))
              or (v.get("type", "Video") != "Video" and v.get("delivered") and old(v, 48))]:
        del vids[k]
    link = lambda v: _msg_link(v.get("chat"), v.get("mid")) or "(MEDIA APPROVAL)"

    def line(n, v, label):
        if v["status"] == "Schedule" and v.get("due"):
            t = datetime.fromisoformat(v["due"]).astimezone(MYT)
            head = f"⏰ {t:%d/%m} ({DAYS[t.weekday()]}) {t:%H:%M}"
        else:
            head = f"#{v['status']}"
        return f"{n}. {head} {label} : {link(v)}" + (" ✅" if v.get("delivered") and label != "Video" else "")

    order = lambda v: (v["status"] != "Schedule", v.get("due", ""), v["mid"])
    L = ["<b>STATUS MEDIA POSTING</b>", "", "<b>🟡 VIDEO @ 5 PLATFORM</b>", ""]
    prog = sorted((v for v in vids.values() if v.get("type", "Video") == "Video" and not v.get("delivered")), key=order)
    for n, v in enumerate(prog, 1):
        L += [line(n, v, "Video"), ""]
    if not prog:
        L += ["Tiada video dalam proses.", ""]
    else:
        cnt = {}
        for v in prog:
            cnt[v["status"]] = cnt.get(v["status"], 0) + 1
        L += ["✅ Jumlah: " + " , ".join(f"{cnt[s]} {s}" for s in ("Schedule", "Approve", "BelumPost") if s in cnt), ""]
    L += ["", "<b>🔵 VIDEO @ TIKTOK</b>", ""]
    tk = sorted((v for v in vids.values() if v.get("tt")), key=lambda v: (v["tt"] == "Done", v["mid"]))
    for n, v in enumerate(tk, 1):
        L += [f"{n}. #TikTok_{v['tt']} Video : {link(v)}", ""]
    if not tk:
        L += ["Tiada video TikTok dalam senarai.", ""]
    else:
        d = sum(1 for v in tk if v["tt"] == "Done")
        L += [f"✅ Jumlah: {d} Done , {len(tk) - d} Belum", ""]
    L += ["", "<b>🔴 NON VIDEO @ 5 PLATFORM</b>", ""]
    nv = sorted((v for v in vids.values() if v.get("type", "Video") != "Video"), key=lambda v: (bool(v.get("delivered")),) + order(v))
    for n, v in enumerate(nv, 1):
        L += [line(n, v, v["type"]), ""]
    if not nv:
        L += ["Tiada gambar / ayat dalam senarai.", ""]
    else:
        cnt = {}
        for v in nv:
            k = "Done" if v.get("delivered") else v["status"]
            cnt[k] = cnt.get(k, 0) + 1
        L += ["✅ Jumlah: " + " , ".join(f"{cnt[s]} {s}" for s in ("Schedule", "Approve", "BelumPost", "Done") if s in cnt), ""]
    L += ["", "Legend Status :", "#BelumPost", "#Approve", "#Schedule", "#TikTok_Belum", "#TikTok_Done"]
    return "\n".join(L)


def _gone(base, chat, mid):
    """True jika mesej sudah dipadam. Bot tidak dapat peristiwa padam, jadi uji dengan setMessageReaction kosong (tiada kesan nampak)."""
    resp = _tg(base, "setMessageReaction", chat_id=chat, message_id=mid, reaction="[]")
    if resp is None or resp.status_code < 300:
        return False
    try:
        d = resp.json().get("description", "").lower()
    except Exception:
        return False
    return "not found" in d or "message_id_invalid" in d


def _sweep_deleted(rs, base, owner, notify):
    """Sync laporan bila Shukri padam posting asal: buang rekod (dan jadual) yang mesejnya sudah tiada. Sahkan 2 kali berturut-turut."""
    now = _now()
    last = rs.get("sweep_at")
    if last and now - datetime.fromisoformat(last) < timedelta(seconds=3):
        return
    rs["sweep_at"] = now.isoformat()
    vids = rs.get("vids", {})
    for k, v in list(vids.items()):
        if v.get("delivered") or not v.get("chat") or not v.get("mid"):
            continue
        if not _gone(base, v["chat"], v["mid"]):
            v.pop("miss", None)
            continue
        v["miss"] = v.get("miss", 0) + 1
        if v["miss"] < 2:
            continue
        for pk in [pk for pk, it in rs.get("pending", {}).items() if str(it.get("mid")) == str(v["mid"]) and it.get("chat") == v["chat"]]:
            del rs["pending"][pk]
        _unreport(base, owner, v)
        del vids[k]


def _sync_schedule(rs, base, owner):
    """Satu mesej laporan pusat di kumpulan MEDIA APPROVAL; disunting di tempat bila status berubah (boleh di-pin)."""
    chat = rs.get("video_chat")
    if not chat:
        return
    if rs.get("sched_msg") and not rs.get("sched_gone"):  # padam laporan lama di chat bot
        _tg(base, "deleteMessage", chat_id=owner, message_id=rs["sched_msg"])
        rs["sched_gone"] = True
    if not rs.get("title_try"):  # tukar nama kumpulan kepada MEDIA APPROVAL (perlu bot admin dengan kebenaran tukar maklumat kumpulan)
        rs["title_try"] = True
        resp = _tg(base, "setChatTitle", chat_id=chat, title="MEDIA APPROVAL")
        if resp is None or resp.status_code >= 300:
            _tg(base, "sendMessage", chat_id=owner, text="ℹ️ Bot tidak dapat tukar nama kumpulan secara automatik. Sila tukar sendiri kepada MEDIA APPROVAL (Edit nama kumpulan).")
    text = _dash_text(rs)
    d = rs.setdefault("dash", {})
    if d.get("text") == text and d.get("chat") == chat:
        return
    kw = dict(parse_mode="HTML", disable_web_page_preview="true")
    if d.get("mid") and d.get("chat") == chat:
        resp = _tg(base, "editMessageText", chat_id=chat, message_id=d["mid"], text=text, **kw)
        if resp is not None and resp.status_code < 300:
            d["text"] = text
            return
    resp = _tg(base, "sendMessage", chat_id=chat, text=text, **kw)
    try:
        mid = resp.json()["result"]["message_id"]
    except Exception:
        return
    rs["dash"] = {"chat": chat, "mid": mid, "text": text}
    _tg(base, "pinChatMessage", chat_id=chat, message_id=mid, disable_notification="true")


def run(st, notify=print, poll=0):
    token, owner = os.getenv("TELEGRAM_BOT_TOKEN"), str(os.getenv("TELEGRAM_CHAT_ID", ""))
    if not token or not owner or not whapi.enabled():
        return 0
    base = f"https://api.telegram.org/bot{token}"
    first = "relay" not in st
    rs = st.setdefault("relay", {"offset": 0})
    r = _retry(lambda: requests.get(f"{base}/getUpdates", params={"offset": rs["offset"], "timeout": poll,
                     "allowed_updates": '["message","channel_post","callback_query"]'}, timeout=(10, 60 + poll)))
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
        # Daftar chat khas video: pemilik taip /video dalam kumpulan peribadi yang ada bot; video kelulusan dihantar ke situ
        if not from_channel and (m.get("text") or "").strip().lower().split("@")[0] in ("/video", "/video_chat") \
                and str(m.get("from", {}).get("id")) == owner and str(m["chat"]["id"]) != owner:
            rs["video_chat"] = m["chat"]["id"]
            rs["offset"] = uid + 1
            _tg(base, "sendMessage", chat_id=m["chat"]["id"], text="✅ Chat ini didaftarkan untuk video kelulusan. Video siap edit akan sampai di sini dengan butang; hanya selepas tekan butang baru masuk ke channel dan platform lain.")
            continue
        if not from_channel and rs.get("video_chat") and m["chat"]["id"] == rs["video_chat"]:  # kumpulan MEDIA APPROVAL
            rs["offset"] = uid + 1
            if str(m.get("from", {}).get("id")) == owner:
                try:
                    _media_to_approval(rs, m, base, notify)
                except Exception as e:
                    notify(f"⚠️ Gagal proses video dalam kumpulan kelulusan: {e}")
            continue
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
    try:
        _process_redo(st, rs, base, token, notify)
    except Exception as e:
        notify(f"⚠️ Gagal cuba semula Threads/Instagram: {e}")
    try:
        _sweep_deleted(rs, base, owner, notify)
    except Exception as e:
        print("Sweep padam gagal:", e)
    try:
        _sync_schedule(rs, base, owner)
    except Exception as e:
        print("Laporan jadual gagal:", e)
    return done

"""Hantar video siap ke chat KHAS video Shukri (kumpulan peribadi didaftar dengan /video; jika belum didaftar, ke DM). Bukan ke channel.

Guna:  TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... python send_for_approval.py video.mp4 "caption" [--auto] [--tiktok none]
  (tanpa --auto)  video ada butang Approve / Jadual / Tolak; tiada apa disiar sehingga butang ditekan.
  --auto          Shukri minta 'auto post / terus post / approve': video dihantar ke DM tanpa butang (ditanda
                  'Auto-push'), dimasukkan terus ke giliran siaran 5 platform (data/state.json, push ke GitHub).
  --tiktok none   (dengan --auto) langkau peringatan TikTok. Lalai: selepas siar ke 5 platform, bot hantar peringatan TikTok manual
                  + caption siap salin ke DM (Shukri upload sendiri di telefon; tiada Claude terlibat).
Mesej dihantar oleh bot (bukan Shukri), jadi relay.py tidak menyiarkannya sendiri. Had: video <= 20 MB, caption <= 1024 aksara.
"""
import os, sys, json, subprocess, time
import requests
import relay


def _probe(video):
    try:
        o = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
                            "-of", "json", video], capture_output=True, text=True, check=True).stdout
        j = json.loads(o)
        s = j["streams"][0]
        return {"width": s["width"], "height": s["height"], "duration": int(float(j["format"]["duration"]))}
    except Exception:
        return {}


def _enqueue(vid, caption, mid, tt=True, chat=None):
    """Masukkan ke giliran siaran (due = sekarang) dalam data/state.json, push dengan cuba semula jika bertembung dengan bot."""
    here = os.path.dirname(os.path.abspath(__file__))
    git = lambda *a: subprocess.run(["git", *a], cwd=here, capture_output=True, text=True)
    for _ in range(6):
        git("fetch", "-q", "origin", "main")
        git("reset", "-q", "--hard", "origin/main")
        p = os.path.join(here, "data", "state.json")
        st = json.load(open(p))
        rs = st.setdefault("relay", {"offset": 0})
        rs.setdefault("pending", {})[f"a{mid}"] = {"vid": vid, "text": caption, "due": relay._now().isoformat(), "tries": 0, "mid": mid, "tt": tt, "chat": chat}
        json.dump(st, open(p, "w"), ensure_ascii=False, indent=2)
        git("add", "data/state.json")
        git("-c", "user.name=channel-bot", "-c", "user.email=bot@users.noreply.github.com", "commit", "-q", "-m", "auto-push video")
        if git("push", "-q", "origin", "HEAD:main").returncode == 0:
            return True
        time.sleep(5)
    return False


def _register(chat, mid, status="BelumPost"):
    """Daftar video baru dalam rekod laporan pusat (data/state.json), push dengan cuba semula."""
    here = os.path.dirname(os.path.abspath(__file__))
    git = lambda *a: subprocess.run(["git", *a], cwd=here, capture_output=True, text=True)
    for _ in range(6):
        git("fetch", "-q", "origin", "main")
        git("reset", "-q", "--hard", "origin/main")
        p = os.path.join(here, "data", "state.json")
        st = json.load(open(p))
        rs = st.setdefault("relay", {"offset": 0})
        rs.setdefault("vids", {})[str(mid)] = {"chat": chat, "mid": mid, "status": status}
        json.dump(st, open(p, "w"), ensure_ascii=False, indent=2)
        git("add", "data/state.json")
        git("-c", "user.name=channel-bot", "-c", "user.email=bot@users.noreply.github.com", "commit", "-q", "-m", "daftar video kelulusan")
        if git("push", "-q", "origin", "HEAD:main").returncode == 0:
            return True
        time.sleep(5)
    return False


def _video_chat(default):
    """Chat khas video (didaftar dengan /video dalam kumpulan) daripada state.json di origin/main; jika tiada, guna lalai (DM)."""
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        subprocess.run(["git", "fetch", "-q", "origin", "main"], cwd=here, capture_output=True)
        o = subprocess.run(["git", "show", "origin/main:data/state.json"], cwd=here, capture_output=True, text=True, check=True).stdout
        return str(json.loads(o).get("relay", {}).get("video_chat") or default)
    except Exception:
        return default


def main():
    argv = sys.argv[1:]
    tt = True
    if "--tiktok" in argv:
        i = argv.index("--tiktok")
        if argv[i + 1] != "none":
            sys.exit("--tiktok hanya menerima: none")
        tt = False
        del argv[i:i + 2]
    args = [a for a in argv if a != "--auto"]
    auto = "--auto" in argv
    if len(args) < 2:
        sys.exit(__doc__)
    video, caption = args[0], args[1]
    token, chat = os.environ["TELEGRAM_BOT_TOKEN"], _video_chat(os.environ["TELEGRAM_CHAT_ID"])
    size = os.path.getsize(video)
    if size > relay.MAX_VIDEO:
        sys.exit(f"Video {size / 1048576:.1f} MB melebihi 20 MB; kecilkan dahulu.")
    if len(caption) > 1024:
        sys.exit("Caption melebihi 1024 aksara.")
    markup = {"inline_keyboard": [[{"text": "⚡ Auto-push: 5 platform" + (" + 📣 peringatan TikTok" if tt else ""), "callback_data": "noop"}]]} if auto else relay.approval_keyboard()
    sid = None if auto else relay.send_status(f"https://api.telegram.org/bot{token}", chat)
    r = requests.post(f"https://api.telegram.org/bot{token}/sendVideo",
                      data={"chat_id": chat, "caption": caption, **({"reply_to_message_id": sid} if sid else {}), "supports_streaming": "true",
                            "reply_markup": json.dumps(markup), **_probe(video)},
                      files={"video": open(video, "rb")}, timeout=(10, 600))
    print(r.status_code, r.text[:200])
    r.raise_for_status()
    if not auto:
        _register(chat, r.json()["result"]["message_id"])
    if auto:
        m = r.json()["result"]
        ok = _enqueue({"file_id": m["video"]["file_id"], "file_size": m["video"]["file_size"]}, caption, m["message_id"], tt, chat)
        print("Giliran siaran:", "OK" if ok else "GAGAL push state")


if __name__ == "__main__":
    main()

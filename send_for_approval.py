"""Hantar video siap ke chat peribadi Shukri UNTUK KELULUSAN (tiada apa disiar ke platform).

Guna:  TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... python send_for_approval.py video.mp4 "caption" [cover.jpg]
Mesej dihantar oleh bot (bukan Shukri), jadi relay.py tidak menyiarkannya. Hanya selepas butang ditekan, relay.py (larian alert)
memasukkan video ke giliran siaran: Approve sekarang, atau jadual (malam ini 8:09 / esok 7:09 / jam pilihan).
Had: video <= 20 MB (had muat turun bot Telegram), caption <= 1024 aksara.
"""
import os, sys, json
import requests
import relay


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    video, caption = sys.argv[1], sys.argv[2]
    cover = sys.argv[3] if len(sys.argv) > 3 else None
    token, chat = os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"]
    size = os.path.getsize(video)
    if size > relay.MAX_VIDEO:
        sys.exit(f"Video {size / 1048576:.1f} MB melebihi 20 MB; kecilkan dahulu.")
    if len(caption) > 1024:
        sys.exit("Caption melebihi 1024 aksara.")
    files = {"video": open(video, "rb")}
    if cover:
        files["thumbnail"] = open(cover, "rb")
    r = requests.post(f"https://api.telegram.org/bot{token}/sendVideo",
                      data={"chat_id": chat, "caption": caption, "supports_streaming": "true",
                            "reply_markup": json.dumps(relay.approval_keyboard())},
                      files=files, timeout=(10, 600))
    print(r.status_code, r.text[:300])
    r.raise_for_status()


if __name__ == "__main__":
    main()

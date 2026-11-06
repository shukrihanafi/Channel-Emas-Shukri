"""Ujian relay.py dengan Telegram/platform palsu (tiada rangkaian). Jalankan: python tests/test_relay_approval.py"""
import os, sys, json
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.update(TELEGRAM_BOT_TOKEN="T", TELEGRAM_CHAT_ID="42", TELEGRAM_CHANNEL="@kenaliemas")
import relay

calls, updates = [], []
class R:
    def __init__(s, j=None): s._j = j or {}; s.status_code = 200; s.content = b"x"; s.text = ""
    def raise_for_status(s): pass
    def json(s): return s._j
def fget(url, params=None, **k):
    if url.endswith("getUpdates"): return R({"result": updates})
    if url.endswith("getFile"): return R({"result": {"file_path": "v/a.mp4"}})
    return R()
def fpost(url, data=None, files=None, **k):
    calls.append((url.rsplit("/", 1)[-1], data)); return R()
relay.requests.get, relay.requests.post = fget, fpost
class W:  # platform palsu
    posted = []
    @staticmethod
    def enabled(): return True
    @staticmethod
    def post_channel(text, path=None, video_path=None): W.posted.append(("wa", text, video_path))
relay.whapi = W
class F:
    @staticmethod
    def enabled(): return False
relay.fb = F
import threads, instagram
threads.enabled = lambda: False; instagram.enabled = lambda: False
msgs = []
note = msgs.append
def cb(i, data, mid=7, uid=42):
    return {"update_id": i, "callback_query": {"id": f"c{i}", "from": {"id": uid}, "data": data,
            "message": {"message_id": mid, "chat": {"id": 42}, "caption": "Amboi... tes\n\nshukriee.com",
                        "video": {"file_id": "VID", "file_size": 5_000_000}}}}
st = {"relay": {"offset": 0}}
# 1) butang Approve: masuk giliran dan disiar serta-merta, sekali sahaja
updates[:] = [cb(1, "ap"), cb(2, "ap")]
n = relay.run(st, note)
assert n == 1 and len([p for p in W.posted if p[0] == "wa"]) == 1, (n, W.posted)
assert any(c[0] == "sendVideo" and c[1]["chat_id"] == "@kenaliemas" for c in calls), calls
assert st["relay"]["pending"] == {} and st["relay"]["offset"] == 3
# 2) jadual: tidak disiar sebelum masa
W.posted.clear(); calls.clear()
updates[:] = [cb(3, "n20", mid=8)]
assert relay.run(st, note) == 0 and not W.posted
p = st["relay"]["pending"]["a8"]; due = datetime.fromisoformat(p["due"])
assert due > datetime.now(timezone.utc) and due.astimezone(relay.MYT).strftime("%H:%M") == "20:09"
# 3) masa sampai: disiar
p["due"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
updates[:] = []
assert relay.run(st, note) == 1 and W.posted and st["relay"]["pending"] == {}
# 4) Tolak: tiada apa disiar
W.posted.clear()
updates[:] = [cb(4, "rj", mid=9)]
assert relay.run(st, note) == 0 and not W.posted and not st["relay"]["pending"]
# 5) orang lain menekan butang: ditolak
updates[:] = [cb(5, "ap", mid=10, uid=999)]
assert relay.run(st, note) == 0 and not W.posted
# 6) pilih jam: papan jam dipaparkan, tiada siaran
updates[:] = [cb(6, "hr", mid=11)]
assert relay.run(st, note) == 0 and any(c[0] == "editMessageReplyMarkup" for c in calls)
# 7) mesej teks biasa pemilik tetap disalin seperti dahulu
W.posted.clear()
updates[:] = [{"update_id": 7, "message": {"chat": {"id": 42}, "text": "post manual"}}]
assert relay.run(st, note) == 1 and W.posted[0][1] == "post manual"
# 8) TikTok: ap = tiada TikTok; ts/tn/tl masuk giliran TikTok dengan mod betul; jadual = mod 'same'
assert "tiktok" not in st["relay"] or not any(k == "a7" for k in st["relay"]["tiktok"])
updates[:] = [cb(8, "ts", mid=20), cb(9, "tn", mid=21), cb(10, "tl", mid=22), cb(11, "n20", mid=23)]
relay.run(st, note)
tk = st["relay"]["tiktok"]
assert tk["a20"]["mode"] == "slot" and tk["a21"]["mode"] == "now" and tk["a22"]["mode"] == "later", tk
assert tk["a23"]["mode"] == "same" and tk["a23"]["at"] and tk["a23"]["status"] == "wait" and tk["a20"]["vid"]["file_id"] == "VID"
assert tk["a8"]["mode"] == "same" and "a7" not in tk and "a9" not in tk  # n20 lama kini = semua 6; 'ap' dan 'rj' tiada TikTok
assert any("TikTok" in m for m in msgs)
kb = relay.approval_keyboard()
assert {b["callback_data"] for r in kb["inline_keyboard"] for b in r} >= {"ts", "tn", "tl", "ap", "n20", "m07", "hr", "rj"}
print("SEMUA UJIAN LULUS")

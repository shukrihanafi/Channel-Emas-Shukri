import os, sys, shutil
sys.path.insert(0, ".")
os.environ["DRY_RUN"] = "1"
import pgfetch, post
sample = open("tests/sample_text.txt").read()
pgfetch.get_prices = lambda: pgfetch.parse(sample)
mode = sys.argv[1]
if len(sys.argv) > 2:
    os.environ["ALERT_THRESHOLD"] = sys.argv[2]
st = post.load(post.STATE, {})
st.setdefault("gap", {"last_post": None, "last_alert": None,
                      "low": {"price": 561, "date": "2026-06-30"}, "high": {"price": 764, "date": "2026-01-29"}})
if len(sys.argv) > 3: st["gap"]["last_alert"] = float(sys.argv[3]); st["gap"]["last_post"] = float(sys.argv[3])
p = pgfetch.parse(sample) if mode in ("gap","jewel","alert") else {}
post.MODES[mode](p, st)

"""Amaran Telegram bila panggilan API Anthropic gagal kerana kredit habis / kunci bermasalah (sekali setiap larian)."""
import os
import requests

_SENT = False


def check(r, tugas="AI"):
    """Panggil selepas setiap requests.post ke API Anthropic. Hantar amaran jika kredit/kunci bermasalah; tidak melontar ralat."""
    global _SENT
    try:
        txt = (r.text or "")
        bad = r.status_code in (401, 402, 403, 429) or (r.status_code == 400 and "credit" in txt.lower())
        if not bad or _SENT:
            return
        _SENT = True
        tok, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
        if tok and chat:
            requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=30, data={
                "chat_id": chat,
                "text": f"⚠️ Kredit atau kunci API Anthropic bermasalah ({tugas}, kod {r.status_code}). Tugasan AI (berita, Threads, caption video, tajuk, testimoni) mungkin berhenti. "
                        "Semak baki dan top up di platform.claude.com/settings/billing.\n" + txt[:140]})
    except Exception:
        pass

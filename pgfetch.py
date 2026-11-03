"""Ambil & baca harga daripada publicgold.com.my (halaman awam)."""
import html, re, requests

URL = "https://publicgold.com.my/"
UA = {"User-Agent": "Mozilla/5.0 (compatible; PGChannelBot/1.0)"}


def _to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(raw))


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def parse(text: str) -> dict:
    d = {}
    # Masa kemas kini terkini (halaman ada salinan lama 2021 yang tersembunyi)
    from datetime import datetime
    stamps = []
    for m in re.finditer(r"Last Update (\d{2}-[A-Za-z]+-\d{4} \d{2}:\d{2}:\d{2})", text):
        try:
            stamps.append(datetime.strptime(m.group(1), "%d-%b-%Y %H:%M:%S"))
        except ValueError:
            pass
    d["updated"] = max(stamps).isoformat() if stamps else None

    mi = re.search(r"GOLD ACCUMULATION PROGRAM \(24K\)", text, re.I)
    seg = text[mi.start():mi.start() + 400] if mi else ""
    m = re.search(r"RM\s*100\s*=\s*([\d.]+)\s*gram", seg)
    g = re.search(r"RM\s*([\d,.]+)\s*=\s*1\.0000\s*gram", seg)
    if not (m and g):
        raise ValueError("Harga GAP tidak ditemui - struktur laman mungkin berubah")
    d["gap_gram_per_rm100"] = float(m.group(1))
    d["gap_rm_per_gram"] = _num(g.group(1))

    j = re.search(r"PG JEWEL Purity.*?(?=NON-PG GOLD BUYBACK)", text, re.I)
    if not j:
        raise ValueError("Harga PG Jewel tidak ditemui")
    jewel = {}
    for p, sell, buy in re.findall(r"\b(999|916)\s+([\d,.]+)\s+([\d,.]+)", j.group(0)):
        jewel[p] = {"sell": _num(sell), "buy": _num(buy)}
    if set(jewel) != {"999", "916"}:
        raise ValueError("Harga PG Jewel tidak lengkap")
    d["jewel"] = jewel

    bars = {}
    b = re.search(r"GOLD BAR \(24K\).*?(?=GOLD WAFER)", text, re.I)
    if b:
        for w, sell, buy in re.findall(r"\b(\d+) gram ([\d,]+) ([\d,]+)", b.group(0)):
            bars[w] = {"sell": _num(sell), "buy": _num(buy)}
    d["bars"] = bars
    return d


def get_prices() -> dict:
    r = requests.get(URL, headers=UA, timeout=30)
    r.raise_for_status()
    return parse(_to_text(r.text))


if __name__ == "__main__":
    import json
    print(json.dumps(get_prices(), indent=2, ensure_ascii=False))

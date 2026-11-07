"""Simpan data/state.json dengan gabungan 3-hala (asas, versi larian ini, versi terkini di main).
Dua workflow (channel dan relay) boleh jalan serentak; setiap satu hanya menimpa kunci yang DIA ubah."""
import json, subprocess, sys, time

P = "data/state.json"


def sh(*a, check=True):
    return subprocess.run(a, capture_output=True, text=True, check=check)


def merge(base, ours, theirs):
    if ours == theirs:
        return ours
    if ours == base:
        return theirs
    if theirs == base:
        return ours
    if isinstance(ours, dict) and isinstance(theirs, dict):
        b = base if isinstance(base, dict) else {}
        out = {}
        for k in list(theirs) + [k for k in ours if k not in theirs]:
            if k in ours and k in theirs:
                out[k] = merge(b.get(k), ours[k], theirs[k])
            elif k in ours:  # hanya ada pada kita: baharu, atau dipadam oleh pihak lain
                if k in b and ours[k] == b[k]:
                    continue
                out[k] = ours[k]
            else:  # hanya ada pada mereka
                if k in b and theirs[k] == b[k]:
                    continue  # kita padam
                out[k] = theirs[k]
        return out
    return ours  # konflik pada nilai biasa: versi larian ini menang


def main():
    base = json.load(open(sys.argv[1], encoding="utf-8"))
    ours = json.load(open(P, encoding="utf-8"))
    if ours == base:
        print("State tiada perubahan.")
        return
    sh("git", "config", "user.name", "channel-bot")
    sh("git", "config", "user.email", "bot@users.noreply.github.com")
    for i in range(6):
        sh("git", "fetch", "-q", "origin", "main")
        sh("git", "reset", "-q", "--hard", "origin/main")
        theirs = json.load(open(P, encoding="utf-8"))
        merged = merge(base, ours, theirs)
        json.dump(merged, open(P, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        sh("git", "add", P)
        if sh("git", "diff", "--staged", "--quiet", check=False).returncode == 0:
            print("State sudah terkini.")
            return
        sh("git", "commit", "-q", "-m", "kemas kini state")
        if sh("git", "push", "-q", "origin", "HEAD:main", check=False).returncode == 0:
            print("State disimpan.")
            return
        time.sleep(1 + i)
    sys.exit("Gagal simpan state selepas 6 percubaan")


if __name__ == "__main__":
    main()

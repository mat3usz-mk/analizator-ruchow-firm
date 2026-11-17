"""Paczka dla nocnego przeglądu AI: wyniki czuwania z GitHub Actions (te same źródła i ta sama baza),
zaszyfrowane hasłem strony (PAGE_PASSWORD), bo repozytorium jest publiczne.

W GitHub Actions (raz w nocy):
    python -m analizator.paczka zapisz --dane dane --out arch/nocny/paczka.json
W nocnym zadaniu (zmienna PAGE_PASSWORD w środowisku):
    python3 -m analizator.paczka odczytaj --out /tmp/paczka
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import urllib.request

URL = "https://raw.githubusercontent.com/mat3usz-mk/analizator-ruchow-firm/archiwum/nocny/paczka.json"
FILES = ["kandydaci.json", "fronty.json", "podsumowanie.txt", "zrodla.json", "raport_biezacy.html", "czuwanie_stan.json", "alarmy.jsonl", "trafnosc.json"]
ITER = 300_000


def _key(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITER, dklen=32)


def pack(dane: str, password: str) -> dict:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    body = {f: open(os.path.join(dane, f), encoding="utf-8").read() for f in FILES if os.path.exists(os.path.join(dane, f))}
    salt, iv = os.urandom(16), os.urandom(12)
    ct = AESGCM(_key(password, salt)).encrypt(iv, json.dumps(body, ensure_ascii=False).encode("utf-8"), None)
    e = lambda x: base64.b64encode(x).decode()
    return {"s": e(salt), "i": e(iv), "c": e(ct), "n": ITER}


def unpack(blob: dict, password: str) -> dict:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    d = lambda k: base64.b64decode(blob[k])
    return json.loads(AESGCM(_key(password, d("s"))).decrypt(d("i"), d("c"), None))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="analizator.paczka")
    ap.add_argument("tryb", choices=["zapisz", "odczytaj"])
    ap.add_argument("--dane", default="dane")
    ap.add_argument("--out", required=True)
    ap.add_argument("--url", default=URL)
    a = ap.parse_args(argv)
    pw = os.environ.get("PAGE_PASSWORD")
    if not pw:
        print("brak zmiennej PAGE_PASSWORD: paczka niedostępna", file=sys.stderr)
        return 2
    if a.tryb == "zapisz":
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(pack(a.dane, pw), f)
        print("paczka zapisana")
        return 0
    blob = json.loads(urllib.request.urlopen(urllib.request.Request(a.url, headers={"Cache-Control": "no-cache"}), timeout=60).read())
    body = unpack(blob, pw)
    os.makedirs(a.out, exist_ok=True)
    for name, txt in body.items():
        with open(os.path.join(a.out, os.path.basename(name)), "w", encoding="utf-8") as f:
            f.write(txt)
    print(f"odczytano: {', '.join(sorted(body))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

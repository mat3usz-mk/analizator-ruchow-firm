"""Strona z raportem pod stałym adresem (GitHub Pages): zawsze aktualny raport, archiwum dzienne i lista alarmów.

    python -m analizator.strona --dane dane --out strona

`dane/raport_biezacy.html` staje się stroną główną, kopia dnia trafia do `dane/archiwum/RRRR-MM-DD.html`
(archiwum przechodzi między cyklami razem z bazą), a `dane/alerty.log` do `alarmy.html`.
"""
from __future__ import annotations

import argparse
import html
import os
import shutil
from datetime import datetime, timezone

KEEP_DAYS = 120
NAV_CSS = ("<style>.nav{position:sticky;top:0;z-index:9;display:flex;gap:16px;flex-wrap:wrap;padding:10px 16px;"
           "background:var(--card,#fff);border-bottom:1px solid var(--line,#ddd);font:14px system-ui,sans-serif}"
           ".nav a{color:inherit}</style>")


def _nav(prefix: str = "") -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (f'{NAV_CSS}<nav class="nav"><b>Analizator ruchów firm</b><a href="{prefix}index.html">Bieżący raport</a>'
            f'<a href="{prefix}archiwum/index.html">Archiwum dzienne</a><a href="{prefix}alarmy.html">Alarmy</a>'
            f'<span style="opacity:.7">odświeżono {now}, co ok. 30 min</span></nav>')


def _with_nav(page: str, prefix: str = "") -> str:
    i = page.find("<body>")
    return page[:i + 6] + _nav(prefix) + page[i + 6:] if i >= 0 else _nav(prefix) + page


def _shell(title: str, body: str, prefix: str = "") -> str:
    return (f'<!doctype html><html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(title)}</title><style>:root{{--bg:#fafaf8;--fg:#1d1d1b;--card:#fff;--line:#ddd}}'
            f'@media (prefers-color-scheme:dark){{:root{{--bg:#16171a;--fg:#e8e6e1;--card:#202226;--line:#3a3c40}}}}'
            f'body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}}main{{max-width:900px;margin:0 auto;padding:16px}}'
            f'a{{color:inherit}}pre{{white-space:pre-wrap;background:var(--card);border:1px solid var(--line);padding:12px;border-radius:8px}}</style>'
            f'</head><body>{_nav(prefix)}<main><h1>{html.escape(title)}</h1>{body}</main></body></html>')


def build(dane: str, out: str) -> str:
    os.makedirs(os.path.join(out, "archiwum"), exist_ok=True)
    arch = os.path.join(dane, "archiwum")
    os.makedirs(arch, exist_ok=True)
    cur = os.path.join(dane, "raport_biezacy.html")
    if os.path.exists(cur):
        page = open(cur, encoding="utf-8").read()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        shutil.copyfile(cur, os.path.join(arch, f"{today}.html"))  # ostatni raport dnia zostaje w archiwum
        with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
            f.write(_with_nav(page))
    days = sorted((f[:-5] for f in os.listdir(arch) if f.endswith(".html")), reverse=True)
    for old in days[KEEP_DAYS:]:
        os.remove(os.path.join(arch, old + ".html"))
    days = days[:KEEP_DAYS]
    for d in days:
        with open(os.path.join(out, "archiwum", d + ".html"), "w", encoding="utf-8") as f:
            f.write(_with_nav(open(os.path.join(arch, d + ".html"), encoding="utf-8").read(), "../"))
    items = "".join(f'<li><a href="{d}.html">{d}</a></li>' for d in days) or "<li>brak</li>"
    with open(os.path.join(out, "archiwum", "index.html"), "w", encoding="utf-8") as f:
        f.write(_shell("Archiwum dzienne", f"<p>Ostatni raport z każdego dnia.</p><ul>{items}</ul>", "../"))
    log = os.path.join(dane, "alerty.log")
    entries = open(log, encoding="utf-8").read().strip().split("\n\n") if os.path.exists(log) else []
    body = "".join(f"<pre>{html.escape(e)}</pre>" for e in reversed(entries[-200:])) or "<p>Na razie nie było alarmów.</p>"
    with open(os.path.join(out, "alarmy.html"), "w", encoding="utf-8") as f:
        f.write(_shell("Alarmy", "<p>Najnowsze na górze. To wskazówki z wiadomości, nie prognoza ani rekomendacja inwestycyjna.</p>" + body))
    open(os.path.join(out, ".nojekyll"), "w").close()
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="analizator.strona")
    ap.add_argument("--dane", default="dane")
    ap.add_argument("--out", default="strona")
    a = ap.parse_args(argv)
    build(a.dane, a.out)
    pw = os.environ.get("PAGE_PASSWORD", "")
    if not pw:
        # bez hasła nie publikujemy niczego w otwartej postaci
        shutil.rmtree(a.out, ignore_errors=True)
        print("strona: brak sekretu PAGE_PASSWORD, nic nie publikuję")
        return 1
    print(f"strona: zaszyfrowano {protect(a.out, pw)} stron")
    return 0



# --- Hasło: strona jest publiczna, ale każda podstrona leży na serwerze tylko w postaci zaszyfrowanej -------------
# AES-256-GCM, klucz z hasła przez PBKDF2-SHA256 (300 tys. iteracji). Odszyfrowanie dzieje się w przeglądarce (WebCrypto),
# więc bez hasła nie da się odczytać treści, nawet znając adres. Hasło ustawia się jako sekret PAGE_PASSWORD.
ITER = 300_000
LOCK_PAGE = """<!doctype html><html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Analizator ruchów firm</title>
<style>:root{--bg:#fafaf8;--fg:#1d1d1b;--card:#fff;--line:#ccc}@media (prefers-color-scheme:dark){:root{--bg:#16171a;--fg:#e8e6e1;--card:#202226;--line:#3a3c40}}
body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}
form{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:24px;width:min(340px,calc(100vw - 32px));box-sizing:border-box}
input[type=password]{width:100%;box-sizing:border-box;padding:10px;margin:12px 0;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--fg);font-size:16px}
button{width:100%;padding:10px;border:0;border-radius:8px;background:#2f5d8a;color:#fff;font-size:16px;cursor:pointer}#e{color:#c0392b;min-height:1.5em;margin:8px 0 0}</style></head>
<body><form id="f"><b>Analizator ruchów firm</b><br><span style="opacity:.7">Raport chroniony hasłem.</span>
<input type="password" id="p" placeholder="Hasło" autocomplete="current-password" autofocus>
<label><input type="checkbox" id="r"> zapamiętaj na tym urządzeniu</label><button>Otwórz</button><p id="e"></p></form>
<script>
const D=__DATA__;const b=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
async function open_(pw){const k=await crypto.subtle.importKey("raw",new TextEncoder().encode(pw),"PBKDF2",false,["deriveKey"]);
const key=await crypto.subtle.deriveKey({name:"PBKDF2",salt:b(D.s),iterations:D.n,hash:"SHA-256"},k,{name:"AES-GCM",length:256},false,["decrypt"]);
const t=await crypto.subtle.decrypt({name:"AES-GCM",iv:b(D.i)},key,b(D.c));return new TextDecoder().decode(t)}
function get(){try{return sessionStorage.getItem("ap")||localStorage.getItem("ap")}catch(e){return null}}
function put(pw,keep){try{sessionStorage.setItem("ap",pw);if(keep)localStorage.setItem("ap",pw)}catch(e){}}
async function go(pw,keep){const h=await open_(pw);put(pw,keep);document.open();document.write(h);document.close()}
const saved=get();if(saved)go(saved,false).catch(()=>{try{sessionStorage.removeItem("ap");localStorage.removeItem("ap")}catch(e){}});
document.getElementById("f").onsubmit=async ev=>{ev.preventDefault();document.getElementById("e").textContent="Sprawdzam…";
try{await go(document.getElementById("p").value,document.getElementById("r").checked)}catch(e){document.getElementById("e").textContent="Złe hasło."}};
</script></body></html>"""


def encrypt_page(page: str, password: str) -> str:
    import base64
    import hashlib
    import json
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt, iv = os.urandom(16), os.urandom(12)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITER, dklen=32)
    ct = AESGCM(key).encrypt(iv, page.encode("utf-8"), None)
    e = lambda x: base64.b64encode(x).decode()
    return LOCK_PAGE.replace("__DATA__", json.dumps({"s": e(salt), "i": e(iv), "c": e(ct), "n": ITER}))


def protect(out: str, password: str) -> int:
    n = 0
    for root, _, files in os.walk(out):
        for f in files:
            if f.endswith(".html"):
                p = os.path.join(root, f)
                page = open(p, encoding="utf-8").read()
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(encrypt_page(page, password))
                n += 1
    with open(os.path.join(out, "robots.txt"), "w") as fh:
        fh.write("User-agent: *\nDisallow: /\n")
    return n


if __name__ == "__main__":
    raise SystemExit(main())

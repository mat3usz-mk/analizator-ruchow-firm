"""Wysyłka raportów i alarmów e-mailem (SMTP, np. Gmail z hasłem aplikacji).

Wszystko z sekretów / zmiennych środowiskowych, nic w kodzie (repozytorium jest publiczne):
  MAIL_TO        adresy odbiorców oddzielone przecinkami
  SMTP_USER      konto nadawcy (np. adres Gmail)
  SMTP_PASSWORD  hasło aplikacji (Gmail: myaccount.google.com/apppasswords), nie zwykłe hasło
  SMTP_HOST      domyślnie smtp.gmail.com
  SMTP_PORT      domyślnie 465 (SSL)

    python -m analizator.poczta --subject "Temat" --body-file tekst.txt --attach raport.html
Kod wyjścia 0 = wysłano, 1 = nie wysłano (brak ustawień albo błąd).
"""
from __future__ import annotations

import argparse
import mimetypes
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage


def configured() -> bool:
    return all(os.environ.get(k) for k in ("MAIL_TO", "SMTP_USER", "SMTP_PASSWORD"))


def send(subject: str, body: str, attachments: list[str] | None = None) -> bool:
    if not configured():
        print("[poczta] pominięto: brak MAIL_TO / SMTP_USER / SMTP_PASSWORD")
        return False
    to = [a.strip() for a in os.environ["MAIL_TO"].replace(";", ",").split(",") if a.strip()]
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"Analizator ruchów firm <{os.environ['SMTP_USER']}>"
    msg["To"] = os.environ["SMTP_USER"]
    msg["Bcc"] = ", ".join(to)  # odbiorcy nie widzą swoich adresów nawzajem
    msg.set_content(body)
    for path in attachments or []:
        if not os.path.exists(path):
            continue
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        main, sub = ctype.split("/", 1)
        with open(path, "rb") as f:
            msg.add_attachment(f.read(), maintype=main, subtype=sub, filename=os.path.basename(path))
    host = os.environ.get("SMTP_HOST") or "smtp.gmail.com"
    port = int(os.environ.get("SMTP_PORT") or 465)
    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=60) as s:
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=60) as s:
            s.starttls(context=ctx)
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            s.send_message(msg)
    print(f"[poczta] wysłano do {len(to)} odbiorców")
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="analizator.poczta")
    ap.add_argument("--subject", required=True)
    ap.add_argument("--body-file", required=True)
    ap.add_argument("--attach", nargs="*", default=[])
    a = ap.parse_args(argv)
    body = open(a.body_file, encoding="utf-8").read() if os.path.exists(a.body_file) else ""
    try:
        return 0 if send(a.subject, body, a.attach) else 1
    except Exception as e:
        print(f"[poczta] nie wysłano: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

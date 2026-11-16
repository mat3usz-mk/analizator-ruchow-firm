"""Ruch statków (AIS) przez kluczowe cieśniny, z aisstream.io.

Raz dziennie przez kilka minut słuchamy strumienia pozycji statków w wybranych prostokątach,
liczymy unikalne statki (MMSI) i tankowce, zapisujemy pomiar i porównujemy z medianą z 14 ostatnich dni.
Wyraźny spadek (statki omijają trasę) daje sygnał. Wymaga:
- zmiennej środowiskowej AISSTREAM_API_KEY (darmowy klucz z aisstream.io),
- domeny stream.aisstream.io w ustawieniach sieci środowiska.

Biblioteka standardowa Pythona nie ma klienta WebSocket, więc poniżej jest minimalny klient
(RFC 6455) z obsługą proxy HTTPS (CONNECT), bo chmura wychodzi do internetu przez proxy.
"""
from __future__ import annotations

import base64
import json
import os
import socket
import sqlite3
import ssl
import statistics
import struct
import time
import urllib.parse
from datetime import date

# nazwa -> (kod kraju do sygnału, nazwa w tytule, [[lat1, lon1], [lat2, lon2]])
CHOKEPOINTS: dict[str, tuple[str, str, list]] = {
    "hormuz": ("IR", "Strait of Hormuz", [[25.4, 55.5], [27.2, 57.5]]),
    "bab_el_mandeb": ("YE", "Bab el-Mandeb (Red Sea)", [[11.8, 42.6], [13.5, 44.0]]),
    "suez": ("EG", "Suez Canal", [[29.8, 32.2], [31.4, 32.7]]),
    "taiwan_strait": ("TW", "Taiwan Strait", [[22.8, 118.5], [25.5, 120.8]]),
    "bosphorus": ("TR", "Bosphorus (Turkey)", [[40.95, 28.9], [41.25, 29.2]]),
    "danish_straits": ("DK", "Danish straits (Denmark)", [[54.9, 10.0], [56.2, 13.0]]),
    "odesa": ("UA", "Odesa ports (Ukraine)", [[45.8, 29.8], [46.7, 31.2]]),
}


def _connect(host: str, port: int = 443, timeout: float = 20.0) -> ssl.SSLSocket:
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if proxy:
        p = urllib.parse.urlparse(proxy)
        raw = socket.create_connection((p.hostname, p.port or 8080), timeout=timeout)
        auth = ""
        if p.username:
            auth = "Proxy-Authorization: Basic " + base64.b64encode(f"{urllib.parse.unquote(p.username)}:{urllib.parse.unquote(p.password or '')}".encode()).decode() + "\r\n"
        raw.sendall(f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n{auth}\r\n".encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = raw.recv(4096)
            if not chunk:
                break
            resp += chunk
        if b" 200" not in resp.split(b"\r\n", 1)[0]:
            first = resp.split(b"\r\n", 1)[0].decode(errors="ignore")
            raise ConnectionError(f"proxy odmówił CONNECT {host}: {first}")
    else:
        raw = socket.create_connection((host, port), timeout=timeout)
    cafile = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    ctx = ssl.create_default_context(cafile=cafile) if cafile and os.path.exists(cafile) else ssl.create_default_context()
    return ctx.wrap_socket(raw, server_hostname=host)


class WebSocket:
    def __init__(self, url: str, timeout: float = 20.0):
        u = urllib.parse.urlparse(url)
        self.sock = _connect(u.hostname, u.port or 443, timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET {u.path or '/'} HTTP/1.1\r\nHost: {u.hostname}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                           f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\nUser-Agent: analizator-ruchow-firm/0.3\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("serwer zamknął połączenie przy uzgadnianiu WebSocket")
            head += chunk
        status, _, rest = head.partition(b"\r\n\r\n")
        if b" 101" not in status.split(b"\r\n", 1)[0]:
            first = status.split(b"\r\n", 1)[0].decode(errors="ignore")
            raise ConnectionError(f"brak przełączenia na WebSocket: {first}")
        self.buf = rest

    def _read(self, n: int) -> bytes:
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("połączenie zamknięte")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def send(self, text: str, opcode: int = 1) -> None:
        data = text.encode() if isinstance(text, str) else text
        mask = os.urandom(4)
        n = len(data)
        head = bytes([0x80 | opcode])
        if n < 126:
            head += bytes([0x80 | n])
        elif n < 65536:
            head += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            head += bytes([0x80 | 127]) + struct.pack(">Q", n)
        self.sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def recv(self) -> str | None:
        """Zwraca kolejną wiadomość tekstową (sklejając fragmenty) albo None przy zamknięciu."""
        parts = b""
        while True:
            b1, b2 = self._read(2)
            opcode, fin = b1 & 0x0F, b1 & 0x80
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            mask = self._read(4) if b2 & 0x80 else None
            payload = self._read(n)
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if opcode == 8:
                return None
            if opcode == 9:
                self.send(payload, opcode=10)
                continue
            if opcode in (0, 1, 2):
                parts += payload
                if fin:
                    return parts.decode("utf-8", "ignore")

    def close(self) -> None:
        try:
            self.send(b"", opcode=8)
            self.sock.close()
        except Exception:
            pass


def _ship_type(msg: dict) -> int | None:
    sd = (msg.get("Message") or {}).get("ShipStaticData") or {}
    for k in ("Type", "ShipType", "TypeOfShipAndCargo"):
        if isinstance(sd.get(k), int):
            return sd[k]
    return None


def sample(seconds: int = 180, key: str | None = None) -> dict[str, dict]:
    """Słucha strumienia przez `seconds` sekund. Zwraca {cieśnina: {"ships": n, "tankers": n}}."""
    key = key or os.environ.get("AISSTREAM_API_KEY")
    if not key:
        raise RuntimeError("brak AISSTREAM_API_KEY")
    names = list(CHOKEPOINTS)
    boxes = [CHOKEPOINTS[n][2] for n in names]
    ws = WebSocket("wss://stream.aisstream.io/v0/stream")
    ws.send(json.dumps({"APIKey": key, "BoundingBoxes": boxes, "FilterMessageTypes": ["PositionReport", "ShipStaticData"]}))
    ws.sock.settimeout(15)
    ships: dict[str, set] = {n: set() for n in names}
    types: dict[int, int] = {}
    pos: dict[int, tuple[float, float]] = {}
    end = time.time() + seconds
    try:
        while time.time() < end:
            try:
                raw = ws.recv()
            except socket.timeout:
                continue
            if raw is None:
                break
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if "error" in msg:
                raise RuntimeError(f"aisstream: {msg['error']}")
            meta = msg.get("MetaData") or {}
            mmsi = meta.get("MMSI")
            lat, lon = meta.get("latitude", meta.get("Latitude")), meta.get("longitude", meta.get("Longitude"))
            if mmsi is None:
                continue
            t = _ship_type(msg)
            if t is not None:
                types[mmsi] = t
            if lat is None or lon is None:
                continue
            pos[mmsi] = (lat, lon)
            for n in names:
                (a0, o0), (a1, o1) = CHOKEPOINTS[n][2]
                if min(a0, a1) <= lat <= max(a0, a1) and min(o0, o1) <= lon <= max(o0, o1):
                    ships[n].add(mmsi)
    finally:
        ws.close()
    return {n: {"ships": len(s), "tankers": sum(1 for m in s if 80 <= types.get(m, 0) <= 89)} for n, s in ships.items()}


def fetch(con: sqlite3.Connection, days: int = 7, seconds: int = 180) -> list[dict]:
    """Zapisuje dzisiejszy pomiar i zwraca sygnały przy spadku o połowę względem mediany z 14 dni."""
    con.executescript("CREATE TABLE IF NOT EXISTS metrics (source TEXT, key TEXT, day TEXT, value REAL, PRIMARY KEY (source, key, day));")
    today = date.today().isoformat()
    counts = sample(seconds)
    out = []
    for n, v in counts.items():
        code, label, _ = CHOKEPOINTS[n]
        for kind in ("ships", "tankers"):
            con.execute("INSERT OR REPLACE INTO metrics VALUES (?,?,?,?)", (f"ais_{kind}", n, today, float(v[kind])))
        con.commit()
        for kind, word in (("ships", "Ship traffic"), ("tankers", "Tanker traffic")):
            hist = [x for (x,) in con.execute("SELECT value FROM metrics WHERE source=? AND key=? AND day<? ORDER BY day DESC LIMIT 14",
                                               (f"ais_{kind}", n, today))]
            if len(hist) < 7:
                continue
            med = statistics.median(hist)
            if med >= 8 and v[kind] <= 0.5 * med:
                drop = round(100 * (1 - v[kind] / med))
                out.append({"url": f"https://aisstream.io/#{n}", "date": today, "source": "ais", "domain": "aisstream.io", "lang": "en",
                            "title": f"{word} through {label} down {drop}% vs 14-day norm ({v[kind]} vs {med:.0f} vessels); tankers avoid route (AIS)"})
    print("  [ais] " + ", ".join(f"{n}: {v['ships']} statków/{v['tankers']} tankowców" for n, v in counts.items()))
    return out

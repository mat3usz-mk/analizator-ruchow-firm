"""Oferty pracy dużych firm według kraju: codzienny zapis do własnej historii (darmowej historii ofert nie ma).

Firmy publikują oferty przez publiczne systemy rekrutacyjne (Workday, SmartRecruiters, Greenhouse, Lever). Raz dziennie
zapisujemy, ile ofert ma każda firma w każdym kraju. Po kilku miesiącach da się sprawdzić, czy firmy zamykają albo
otwierają rekrutację w danym kraju przed wydarzeniami (np. wygaszanie zatrudnienia przed wyjściem z rynku).

    python -m analizator.oferty --sprawdz                       # które firmy odpowiadają
    python -m analizator.oferty --out archiwum/2026-11-18/oferty.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import time
import urllib.request
from collections import Counter
from datetime import date

UA = "analizator-ruchow-firm/0.11 (github.com/mat3usz-mk/analizator-ruchow-firm)"

# (firma, sektor, system, parametry). Lista kandydatów; tryb --sprawdz pokazuje, które naprawdę odpowiadają.
FIRMY: list[tuple[str, str, str, tuple]] = [
    # Workday: (tenant, serwer wdN, strona)
    ("Nvidia", "technologia", "workday", ("nvidia", "wd5", "NVIDIAExternalCareerSite")),
    ("Intel", "technologia", "workday", ("intel", "wd1", "External")),
    ("Salesforce", "technologia", "workday", ("salesforce", "wd12", "External_Career_Site")),
    ("Mastercard", "finanse", "workday", ("mastercard", "wd1", "CorporateCareers")),
    ("Boeing", "lotnictwo i zbrojenia", "workday", ("boeing", "wd1", "EXTERNAL_CAREERS")),
    ("Northrop Grumman", "zbrojenia", "workday", ("ngc", "wd1", "Northrop_Grumman_External_Site")),
    ("RTX", "zbrojenia", "workday", ("globalhr", "wd5", "REC_RTX_Ext_Gateway")),
    ("Chevron", "energia", "workday", ("chevron", "wd5", "jobs")),
    ("Baker Hughes", "energia", "workday", ("bakerhughes", "wd5", "BakerHughes")),
    ("Halliburton", "energia", "workday", ("halliburton", "wd5", "HalliburtonCareers")),
    ("GE Vernova", "energia", "workday", ("gevernova", "wd5", "Vernova_ExternalSite")),
    ("GE Aerospace", "lotnictwo i zbrojenia", "workday", ("geaerospace", "wd5", "GE_ExternalSite")),
    ("Citi", "finanse", "workday", ("citi", "wd5", "2")),
    ("Walmart", "handel", "workday", ("walmart", "wd5", "WalmartExternal")),
    ("Pfizer", "farmacja", "workday", ("pfizer", "wd1", "PfizerCareers")),
    ("Shell", "energia", "workday", ("shell", "wd3", "ShellCareers")),
    ("BP", "energia", "workday", ("bpinternational", "wd3", "bpCareers")),
    ("ConocoPhillips", "energia", "workday", ("conocophillips", "wd1", "External")),
    ("Caterpillar", "przemysł", "workday", ("cat", "wd5", "CaterpillarCareers")),
    ("Cargill", "żywność i zboża", "workday", ("cargill", "wd5", "Cargill")),
    ("ADM", "żywność i zboża", "workday", ("adm", "wd5", "External")),
    ("Bunge", "żywność i zboża", "workday", ("bunge", "wd1", "Bunge_Careers")),
    ("Honeywell", "przemysł", "workday", ("honeywell", "wd5", "Honeywell")),
    ("3M", "przemysł", "workday", ("3m", "wd1", "Search")),
    ("Visa", "finanse", "smartrecruiters", ("Visa",)),
    ("Bosch", "przemysł", "smartrecruiters", ("BoschGroup",)),
    ("IKEA", "handel", "smartrecruiters", ("IKEA",)),
    ("Palantir", "zbrojenia", "lever", ("palantir",)),
    ("Anduril", "zbrojenia", "greenhouse", ("andurilindustries",)),
    ("Stripe", "finanse", "greenhouse", ("stripe",)),
    ("Airbnb", "turystyka", "greenhouse", ("airbnb",)),
    ("Coinbase", "finanse", "greenhouse", ("coinbase",)),
]


def _req(url: str, body: dict | None = None, timeout: int = 40):
    data = json.dumps(body).encode() if body is not None else None
    h = {"User-Agent": UA, "Accept": "application/json"}
    if data:
        h["Content-Type"] = "application/json"
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h), timeout=timeout).read())


def _country_of(loc: str) -> str:
    """Z napisu miejsca („Warsaw, Poland”, „London, UK”) bierzemy ostatni człon jako kraj."""
    loc = (loc or "").strip()
    if not loc:
        return "?"
    return loc.split(",")[-1].strip() or "?"


def workday(tenant: str, wd: str, site: str) -> Counter:
    url = f"https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    r = _req(url, {"limit": 1, "offset": 0, "searchText": "", "appliedFacets": {}})
    out = Counter()
    for f in r.get("facets", []):
        vals = f.get("values", [])
        # facety bywają zagnieżdżone (grupa → lista); szukamy tej o krajach
        for g in [f] + [v for v in vals if isinstance(v, dict) and "values" in v]:
            if "country" in (g.get("facetParameter", "") + g.get("descriptor", "")).lower():
                for v in g.get("values", []):
                    if "count" in v:
                        out[v.get("descriptor", "?")] += int(v["count"])
    if not out:
        out["razem"] = int(r.get("total", 0))
    return out


def smartrecruiters(company: str, cap: int = 3000) -> Counter:
    out, off = Counter(), 0
    while off < cap:
        r = _req(f"https://api.smartrecruiters.com/v1/companies/{company}/postings?limit=100&offset={off}")
        items = r.get("content", [])
        for p in items:
            out[(p.get("location") or {}).get("country", "?").upper()] += 1
        off += len(items)
        if not items or off >= int(r.get("totalFound", 0)):
            break
        time.sleep(0.3)
    return out


def greenhouse(board: str) -> Counter:
    r = _req(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs")
    return Counter(_country_of((j.get("location") or {}).get("name", "")) for j in r.get("jobs", []))


def lever(company: str) -> Counter:
    r = _req(f"https://api.lever.co/v0/postings/{company}?mode=json")
    out = Counter()
    for p in r:
        c = p.get("country") or _country_of((p.get("categories") or {}).get("location", ""))
        out[c] += 1
    return out


SYSTEMS = {"workday": workday, "smartrecruiters": smartrecruiters, "greenhouse": greenhouse, "lever": lever}


def collect(firms=FIRMY) -> tuple[list[tuple], dict[str, str]]:
    rows, status = [], {}
    for name, sector, system, params in firms:
        try:
            c = SYSTEMS[system](*params)
            status[name] = f"ok {sum(c.values())} ofert, {len(c)} krajów"
            rows += [(name, sector, k, v) for k, v in sorted(c.items())]
        except Exception as e:
            status[name] = f"błąd: {str(e)[:80]}"
        time.sleep(0.5)
    return rows, status


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="analizator.oferty")
    ap.add_argument("--out", default="")
    ap.add_argument("--sprawdz", action="store_true")
    a = ap.parse_args(argv)
    rows, status = collect()
    for k, v in status.items():
        print(f"  {k}: {v}", flush=True)
    if a.sprawdz:
        top = Counter()
        for n, _, c, v in rows:
            top[c] += v
        print("najczęstsze kraje:", top.most_common(25))
    if a.out and rows:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["dzien", "firma", "sektor", "kraj", "ofert"])
            w.writerows((date.today().isoformat(), *r) for r in rows)
        print(f"zapisano {len(rows)} wierszy do {a.out}")
    ok = sum(1 for v in status.values() if v.startswith("ok"))
    print(f"odpowiedziało {ok} z {len(status)} firm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

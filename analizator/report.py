"""Raport HTML (jeden plik, bez zależności) + CSV."""
from __future__ import annotations

import csv
import html
from datetime import datetime

import json
import os

from .score import CountryAssessment, category_label, country_name
from .skutki import fronts, implications, indices

CSS = """
:root{--bg:#fafaf8;--fg:#1d1d1b;--muted:#6b6b66;--card:#fff;--line:#e4e3de;--low:#5b8a5b;--mid:#c08a1e;--high:#b4442f;--bar:#7a8fa6}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ecebe6;--muted:#9a9993;--card:#20201e;--line:#34332f;--low:#7fb07f;--mid:#e0ad45;--high:#e0705a;--bar:#8fa4bb}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:980px;margin:0 auto;padding:24px 16px 64px}h1{font-size:24px;margin:0 0 4px}.muted{color:var(--muted)}
.warn{border-left:3px solid var(--mid);padding:10px 14px;background:var(--card);margin:16px 0;border-radius:4px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:16px;margin:14px 0}
.head{display:flex;flex-wrap:wrap;gap:12px;align-items:baseline;justify-content:space-between}
.idx{font-size:28px;font-weight:650;font-variant-numeric:tabular-nums}.lvl{font-weight:600}
.wysoki{color:var(--high)}.podwyższony{color:var(--mid)}.niski{color:var(--low)}
.stats{display:flex;flex-wrap:wrap;gap:18px;font-size:13px;color:var(--muted);margin:6px 0 10px}
.q{color:var(--high);font-weight:600;font-size:12px}.r{color:var(--muted);font-size:12px}
.imp{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px;margin-top:10px}
.imp div{border:1px solid var(--line);border-radius:6px;padding:8px 10px;font-size:13.5px}.imp h4{margin:0 0 4px;font-size:13px}
.tag{display:inline-block;font-size:12px;border:1px solid var(--line);border-radius:999px;padding:1px 8px;margin:2px 4px 2px 0}
ul{padding-left:18px;margin:6px 0}li{margin:3px 0}a{color:inherit}svg{display:block;max-width:100%}
details summary{cursor:pointer;color:var(--muted);font-size:13px}
"""


def _spark(weekly: list[tuple[str, float]]) -> str:
    if not weekly:
        return ""
    w, h, n = 300, 44, len(weekly)
    mx = max(v for _, v in weekly) or 1
    bw = w / n
    bars = "".join(
        f'<rect x="{i * bw + 1:.1f}" y="{h - v / mx * (h - 2):.1f}" width="{max(bw - 2, 1):.1f}" height="{v / mx * (h - 2):.1f}" '
        f'fill="var(--bar)" opacity="{0.5 if i < n - 3 else 1}"><title>{d}: {v}</title></rect>'
        for i, (d, v) in enumerate(weekly)
    )
    return f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="wynik tygodniowy">{bars}</svg>'


def _insider_html(rows: list[dict]) -> str:
    if not rows:
        return ""
    fmt = lambda v: "brak" if v is None else f"${v / 1e6:.1f} mln"
    tr = "".join(f"<tr><td>{r['ticker']}</td><td>{fmt(r['sell'])}</td><td>{fmt(r['sell_norm'])}</td><td>{fmt(r['buy'])}</td>"
                 f"<td>{'<b class=q>nietypowo duża sprzedaż</b>' if r['unusual'] else ''}</td></tr>" for r in rows)
    return f"""<section class="card"><h2 style="margin:0 0 6px;font-size:19px">Insiderzy w USA (Form 4, ostatnie 14 dni)</h2>
<p class="muted" style="margin:0 0 8px">Sprzedaż i zakup akcji przez zarząd i dużych udziałowców spółek zbrojeniowych i energetycznych.
Sprzedaż ma wiele zwykłych powodów (podatki, opcje), więc liczy się tylko wyraźne odchylenie od normy. Nie wpływa na indeks krajów.</p>
<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:14px"><tr><th align=left>Spółka</th><th align=left>Sprzedaż</th>
<th align=left>Norma</th><th align=left>Zakup</th><th></th></tr>{tr}</table></div></section>"""


def to_html(results: list[CountryAssessment], n_articles: int, n_signals: int, title: str = "Analizator ruchów firm",
            insiders: list[dict] | None = None) -> str:
    e = html.escape
    cards = []
    for r in results:
        ev = "".join(
            f'<li><span class="muted">{x["date"]}</span> · <b>{e(category_label(x["category"]))}</b> · '
            f'{"<span class=q>cichy sygnał</span> · " if x.get("quiet") else ""}{"<span class=r>reakcja na zdarzenie</span> · " if x.get("reactive") else ""}'
            f'{_quality_badge(x)}'
            f'{"<a href=" + chr(34) + e(x["url"]) + chr(34) + " target=_blank rel=noopener>" if x.get("url") else ""}{e(x["title"])}{"</a>" if x.get("url") else ""}</li>'
            for x in r.evidence
        )
        imp_html = ""
        if r.level != "niski" or r is results[0]:
            exposed = sorted({x["company"] for x in r.evidence if x.get("company") and x.get("actor") == "firma"})
            imp = implications(r.country, r.categories, exposed, r.level)
            li = lambda xs: "<ul>" + "".join(f"<li>{e(x)}</li>" for x in xs) + "</ul>" if xs else '<p class="muted">brak danych</p>'
            imp_html = f"""<details open><summary>Możliwe skutki, jeśli napięcie wzrośnie (hipotezy, nie rekomendacja inwestycyjna)</summary>
  <p style="margin:6px 0">{e(", ".join(imp["roles"]) or "brak profilu kraju w bazie")}</p>
  {li(imp["hints"])}
  <div class="imp"><div><h4>Indeksy i notowania: typowo w górę ▲</h4>{li(imp["idx_up"])}</div><div><h4>Indeksy i notowania: typowo w dół ▼</h4>{li(imp["idx_down"])}</div></div>
  <div class="imp"><div><h4>Mogą zyskać</h4>{li(imp["up"])}</div><div><h4>Mogą stracić</h4>{li(imp["down"] + [f"firmy wymienione w dowodach: {', '.join(exposed)}"] if exposed else imp["down"])}</div>
  <div><h4>Możliwe decyzje państw</h4>{li(imp["effects"])}</div></div></details>"""
        co = "".join(f"<li>{e(category_label(a))} + {e(category_label(b))} ({n} firm)</li>" for a, b, n in r.co_occurring)
        cards.append(f"""
<section class="card">
  <div class="head"><h2 style="margin:0;font-size:19px">{e(country_name(r.country))} <span class="muted" style="font-size:13px">{r.country}</span></h2>
  <div><span class="idx">{r.index:.0f}</span><span class="muted">/100</span> · <span class="lvl {r.level}">{r.level}</span>
  · <span class="muted">pewność danych: {r.confidence}</span>{_prob_html(r)}</div></div>
  <div class="stats"><span>ostatnie tygodnie: {r.recent_score}/tydz.</span><span>tło (mediana): {r.baseline}</span>
  <span>odchylenie: {r.zscore:+.1f}σ</span><span>firm: {r.companies}</span><span>państw: {r.states}</span>
  <span>cichych sygnałów: {r.quiet}</span><span>sygnały priorytetowe: {r.priority}</span><span>ruchy wyprzedzające: {r.proactive_share:.0%}</span></div>
  {_unconfirmed_html(r)}
  {_spark(r.weekly)}
  <div style="margin-top:8px">{"".join(f'<span class="tag">{e(category_label(c))}</span>' for c in r.categories) or '<span class="muted">brak aktywnych sygnałów</span>'}</div>
  {f'<p style="margin:10px 0 0"><b>Ruchy występujące razem:</b></p><ul>{co}</ul>' if co else ''}
  {imp_html}
  <details {"open" if r.level != "niski" else ""}><summary>Dowody ({len(r.evidence)})</summary><ul>{ev or '<li class="muted">brak</li>'}</ul></details>
</section>""")
    return f"""<!doctype html><html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><style>{CSS}</style></head><body><main>
<h1>{e(title)}</h1>
<div class="muted">Wygenerowano {datetime.now():%Y-%m-%d %H:%M} · {n_articles} artykułów · {n_signals} sygnałów</div>
<div class="warn"><b>Jak to czytać.</b> Indeks 0–100 pokazuje, jak bardzo obecne ruchy firm w danym kraju odbiegają od normy
i jak szeroko się rozkładają (wiele różnych firm i typów decyzji). To <b>wskazówka, gdzie warto się przyjrzeć</b>, a nie
prawdopodobieństwo wydarzenia. Przy małej pewności danych wynik może być przypadkowy. Zawsze sprawdź dowody poniżej.
<br><b>Chłodna ocena.</b> Artykuły z językiem strachu, spekulacją, z tabloidów, źródeł propagandowych, płatnych komunikatów
i treści sponsorowanych ważą mniej, a raporty „rynkowe” są pomijane. Alarm (indeks od 40) wymaga potwierdzenia w źródle
pierwotnym albo w dwóch niezależnych, rzeczowych mediach.
<br><b>Cichy sygnał</b> to ruch wyprzedzający opisany tylko przez 1–2 wiarygodne źródła. <b>Reakcja na zdarzenie</b> opisuje coś, co już
się dzieje (atak, awaria), więc waży mało. Sekcja skutków to typowe reakcje z podobnych sytuacji w przeszłości, nie rekomendacja inwestycyjna.</div>
{_fronts_html(results)}
{''.join(cards) or '<p>Brak sygnałów z przypisanym krajem.</p>'}
{_insider_html(insiders or [])}
</main></body></html>"""


_CLASS_PL = {"tabloid": "tabloid", "propaganda": "źródło propagandowe", "komunikat_prasowy": "komunikat prasowy (płatny)",
             "sponsorowany": "treść sponsorowana"}


def _quality_badge(x: dict) -> str:
    """Oznaczenie artykułu, który waży mniej: emocje, spekulacja, tabloid, propaganda, treść sponsorowana."""
    tags = []
    if x.get("source_class"):
        tags.append(_CLASS_PL.get(x["source_class"], x["source_class"]))
    if x.get("emotion", 0) >= 0.5:
        tags.append("język emocji")
    elif x.get("emotion", 0) >= 0.25:
        tags.append("spekulacja")
    if not tags:
        return ""
    why = html.escape("; ".join(x.get("quality_reasons") or []))
    return f'<span class=r title="{why}">{html.escape(", ".join(tags))}: waga obniżona</span> · '


def _unconfirmed_html(r) -> str:
    note = getattr(r, "model_note", "")
    if note == "model nie potwierdza":
        return ('<p class="muted" style="margin:8px 0 0"><b>Model nie potwierdza.</b> Ręczny indeks przekroczył próg, ale model uczony '
                'na historii daje zbyt niską szansę wydarzenia, więc to nie jest alarm (w teście takie przypadki były zwykle fałszywe).</p>')
    if note == "podniesione przez model":
        return ('<p style="margin:8px 0 0"><b>Alarm z modelu.</b> Ręczny indeks jest niski, ale model uczony na historii daje '
                'wyjątkowo wysoką szansę wydarzenia.</p>')
    if not r.unconfirmed:
        return ""
    return ('<p class="muted" style="margin:8px 0 0"><b>Niepotwierdzone.</b> Indeks obcięty poniżej progu alarmu, bo ruch widać '
            f'tylko w {r.confirmations} rzetelnym źródle (potrzebne źródło pierwotne albo dwa niezależne, rzeczowe media).</p>')


def _prob_html(r) -> str:
    if r.prob is None:
        return ""
    from .ucz import load_model
    h = (load_model() or {}).get("horyzont_dni", 60)
    return (f' · <b title="Regresja logistyczna uczona na wydarzeniach 2015–2024, sprawdzona na 2025–2026. To nadal przybliżenie.">'
            f'szansa wydarzenia w {h} dni wg modelu: {r.prob:.0%}</b>')


def _fronts_html(results) -> str:
    fr = fronts(results)
    if not fr:
        return ""
    e = html.escape
    rows = "".join(
        f"<li><b>{e(f['nazwa'])}</b>: " + ", ".join(f"{e(country_name(c))} {i}" for c, i in f["kraje"])
        + (f" · <span class=muted>{e(', '.join(category_label(c) for c in f['kategorie']))}</span>" if f["kategorie"] else "")
        + (f"<br><span class=muted>▲ {e('; '.join(f['idx_up']))}</span>" if f["idx_up"] else "")
        + (f"<br><span class=muted>▼ {e('; '.join(f['idx_down']))}</span>" if f["idx_down"] else "")
        + "</li>" for f in fr)
    return (f'<section class="card"><h2 style="margin:0;font-size:19px">Fronty (sygnały jednego kryzysu w kilku krajach)</h2>'
            f'<p class="muted" style="margin:6px 0">Tylko zestawienie. Indeksy krajów liczone są osobno.</p><ul>{rows}</ul></section>')


def to_csv(results: list[CountryAssessment], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["kraj", "indeks", "poziom", "pewnosc", "wynik_ostatni", "tlo", "z", "firmy", "kategorie", "indeksy_w_gore", "indeksy_w_dol", "szansa_model"])
        for r in results:
            ix = indices(r.country, r.level)
            w.writerow([r.country, r.index, r.level, r.confidence, r.recent_score, r.baseline, r.zscore, r.companies, ";".join(r.categories),
                        ";".join(ix["up"]), ";".join(ix["down"]), "" if r.prob is None else r.prob])


def to_candidates_json(results: list[CountryAssessment], path: str, top: int = 8) -> None:
    """Materiał dla codziennego przeglądu AI: najważniejsze kraje i ich dowody."""
    out = []
    for r in results[:top]:
        out.append({
            "kraj": r.country, "nazwa": country_name(r.country), "indeks": r.index, "poziom": r.level, "pewnosc": r.confidence,
            "kategorie": r.categories, "niepotwierdzone": r.unconfirmed, "potwierdzenia": r.confirmations, "szansa_model": r.prob, "indeksy_w_gore": indices(r.country, r.level)["up"],
            "indeksy_w_dol": indices(r.country, r.level)["down"], "ciche_sygnaly": r.quiet, "udzial_wyprzedzajacych": r.proactive_share,
            "dowody": [{"data": x["date"].isoformat(), "kategoria": x["category"], "tytul": x["title"], "url": x.get("url"),
                        "firma": x.get("company"), "aktor": x.get("actor"), "cichy": x.get("quiet"), "reakcja": x.get("reactive"),
                        "zrodlo": x.get("domain"), "emocje": x.get("emotion"),
                        "klasa_zrodla": x.get("source_class")} for x in r.evidence],
        })
    fr = [{k: v for k, v in f.items() if k != "klucz"} for f in fronts(results)]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    with open(os.path.join(os.path.dirname(path), "fronty.json"), "w", encoding="utf-8") as f:
        json.dump(fr, f, ensure_ascii=False, indent=1)

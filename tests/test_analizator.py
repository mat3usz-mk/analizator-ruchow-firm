import unittest
from datetime import date, timedelta

from analizator import demo
from analizator.score import assess, extract_signals
from analizator.signals import classify, detect_company, detect_countries


class TestSignals(unittest.TestCase):
    def cats(self, title):
        return {(s.category, s.country) for s in classify(title)}

    def test_evacuation(self):
        self.assertIn(("ewakuacja_personelu", "UA"), self.cats("Siemens evacuates non-essential staff from Ukraine"))

    def test_insurance(self):
        self.assertIn(("ubezpieczenia_finanse", "UA"), self.cats("Insurers cancel war risk cover for planes flying over Ukraine"))

    def test_exit(self):
        self.assertIn(("wyjscie_z_rynku", "RU"), self.cats("Shell to exit Russia, pulls out of Gazprom joint ventures"))

    def test_polish(self):
        self.assertIn(("wyjscie_z_rynku", "BY"), self.cats("Orlen wycofuje się z Białorusi"))
        self.assertIn(("ewakuacja_personelu", "UA"), self.cats("Firma ewakuuje pracowników z Kijowa"))

    def test_energy(self):
        self.assertIn(("energia_surowce", "UA"), self.cats("Gazprom did not book additional transit capacity via Ukraine"))

    def test_negation_weakens(self):
        sig = classify("Carlsberg denies plans to exit Russia")
        self.assertTrue(sig and all(s.negated and s.weight < 1.5 for s in sig))

    def test_no_signal(self):
        self.assertEqual(classify("Apple unveils new iPhone in California"), [])

    def test_country_guards(self):
        self.assertNotIn("IN", detect_countries("Factory in Indiana suspends operations"))
        self.assertNotIn("NE", detect_countries("Shell sells assets in Nigeria"))

    def test_company(self):
        self.assertEqual(detect_company("BP Group sells stake in Rosneft"), "BP Group")
        self.assertEqual(detect_company("Maersk halts shipments to Russia"), "Maersk")
        self.assertIsNone(detect_company("Russia halts gas exports"))
        self.assertEqual(detect_company("anything about uniper", watchlist=["Uniper"]), "Uniper")


class TestPrecision(unittest.TestCase):
    def test_sport_and_politics_ignored(self):
        self.assertEqual(classify("Luca Marini withdraws from Qatar GP"), [])
        self.assertEqual(classify("Rybakina withdraws from Tokyo, Fernandez advances to semifinals"), [])
        self.assertEqual(classify("Patriotic Union of Kurdistan Withdraws from Regional Government"), [])

    def test_reactive_is_weak(self):
        sig = classify("Astarta suspends operations at soybean plant after Russian airstrike")
        self.assertTrue(sig and all(s.reactive and s.weight < 1.5 for s in sig))

    def test_polish_negation(self):
        sig = classify("Saudi Aramco nie wycofuje się z Polski")
        self.assertTrue(sig and all(s.negated for s in sig))

    def test_target_country_over_home_country(self):
        sig = classify("Poland's Orlen cancels LNG supply contract with Qatar after force majeure")
        self.assertEqual({s.country for s in sig}, {"QA"})

    def test_state_actor(self):
        sig = classify("US Embassy in Riyadh Orders Non-Essential Staff to Leave Saudi Arabia")
        self.assertTrue(sig and sig[0].actor == "panstwo" and sig[0].country == "SA")

    def test_new_categories(self):
        self.assertIn(("wstrzymane_inwestycje", "RS"), {(s.category, s.country) for s in classify("Stellantis puts Serbia plant investment on hold")})
        self.assertIn(("przeplywy_finansowe", "TW"), {(s.category, s.country) for s in classify("Foxconn moves headquarters out of Taiwan")})

    def test_title_case_company(self):
        self.assertEqual(detect_company("Orlen Terminates 2009 QatarEnergy LNG Contract After Months of Force Majeure"), "Orlen")

    def test_quiet_signal_and_clustering(self):
        arts = [
            {"title": "Acme Corp evacuates non-essential staff from Moldova", "date": "2026-11-10", "domain": "lloydslist.com", "url": "a"},
            {"title": "Beta Group to reduce exposure to Moldova", "date": "2026-11-10", "domain": "x.com", "url": "b"},
        ] + [{"title": f"Beta Group to reduce exposure to Moldova, report {i}", "date": "2026-11-11", "domain": f"site{i}.com", "url": f"c{i}"} for i in range(5)]
        sig = extract_signals(arts)
        acme = [x for x in sig if x["company"] == "Acme Corp"][0]
        beta = [x for x in sig if x["company"] == "Beta Group"]
        self.assertTrue(acme["quiet"])
        self.assertFalse(any(x["quiet"] for x in beta), "szeroko opisana historia nie jest cicha")
        self.assertEqual(len({x["story"] for x in beta}), 1)

    def test_implications(self):
        from analizator.skutki import implications
        imp = implications("TW", ["ewakuacja_personelu"], ["Foxconn"])
        self.assertTrue(imp["up"] and imp["down"] and imp["effects"] and imp["hints"])


class TestScoring(unittest.TestCase):
    def test_demo_ranks_escalation_over_noise(self):
        today = date(2026, 11, 14)
        res = assess(extract_signals(demo.generate(today)), today=today)
        by = {r.country: r for r in res}
        self.assertEqual(res[0].country, "MD")
        self.assertGreater(by["MD"].index, 70)
        self.assertLess(by["TR"].index, 40, "jedna głośna firma nie powinna dawać wysokiego alarmu")

    def test_repeated_articles_count_once(self):
        today = date(2026, 11, 14)
        arts = [{"title": "Acme Corp suspends operations in Serbia", "date": (today - timedelta(days=i % 3)).isoformat(), "url": f"u{i}"} for i in range(50)]
        res = assess(extract_signals(arts), today=today)
        self.assertEqual(res[0].companies, 1)
        self.assertLessEqual(res[0].recent_score, 3.0)


class TestSec(unittest.TestCase):
    def test_ascii_user_agent(self):
        import os
        from analizator.sources import sec_user_agent
        os.environ["SEC_USER_AGENT"] = "Jan Łękaś jan@example.com"
        try:
            self.assertEqual(sec_user_agent(), "Jan Lekas jan@example.com")
        finally:
            del os.environ["SEC_USER_AGENT"]

    def test_sentence_check_rejects_noise(self):
        from analizator.sources import sec_sentence
        t = ("We are headquartered in Atlanta, Georgia. Risks include the war in Ukraine. "
             "Our force majeure clauses apply generally. The Company suspended its operations in Israel and evacuated staff.")
        self.assertIsNone(sec_sentence(t, '"force majeure"', "Ukraine"))
        self.assertIn("Israel", sec_sentence(t, '"suspended operations"', "Israel"))


class TestV03(unittest.TestCase):
    def cats(self, t):
        return {(x.category, x.country) for x in classify(t)}

    def test_aviation_and_state(self):
        self.assertIn(("lotnictwo_przestrzen", "PK"), self.cats("Air France, Lufthansa suspend operations in Pakistani airspace amid India-Pakistan tensions"))
        self.assertIn(("lotnictwo_przestrzen", "VE"), self.cats("Six airlines suspend flights to Venezuela amid FAA warning"))
        self.assertIn(("ewakuacja_personelu", "IQ"), self.cats("US orders departure of non-emergency staff from Iraq embassy"))

    def test_sport_cased(self):
        self.assertEqual(classify("Sabalenka pulls out of Qatar Open"), [])

    def test_business_exit_without_context_is_weak(self):
        sig = classify("Intel scraps plans for Poland plant")
        self.assertTrue(sig and sig[0].weight < 1.5)

    def test_primary_source_titles(self):
        self.assertIn(("ostrzezenia_panstw", "LB"), self.cats("US State Department raises travel advisory for Lebanon to Level 4: Do Not Travel (from Level 3); travel warning"))
        self.assertIn(("lotnictwo_przestrzen", "IR"), self.cats("Air traffic over Iran down 72% vs 14-day norm (12 aircraft vs 43); airlines avoid airspace (OpenSky)"))
        self.assertIn(("sankcje", "RU"), self.cats("OFAC sanctions action: Russia-related Designations"))
        self.assertIn(("wyjscie_z_rynku", "UA"), self.cats("ORLEN: Zawieszenie działalności spółki zależnej na Ukrainie z powodu sytuacji bezpieczeństwa"))

    def test_sec_noise_is_damped(self):
        from analizator.score import _damp_sec
        today = date(2026, 11, 14)
        rows = []
        for w in range(30):  # stały szum: 3 raporty o Chinach co tydzień
            for k in range(3):
                d = today - timedelta(weeks=w)
                rows.append({"date": d, "country": "CN", "source": "sec", "key": f"f{k}", "weight": 2.0})
        damped = _damp_sec(rows, 26, 3.0)
        self.assertTrue(all(x["weight"] == 0 for x in damped if x["date"] == today))

    def test_snapshot_change_detection(self):
        import sqlite3
        from analizator import pierwotne
        con = pierwotne._con(sqlite3.connect(":memory:"))
        con.execute("INSERT INTO snapshots VALUES ('travel_us','LB','3','2026-01-01')")
        self.assertEqual(pierwotne._changed(con, "travel_us", "LB", "4"), "3")
        self.assertIsNone(pierwotne._changed(con, "travel_us", "IL", "2"))


class TestAis(unittest.TestCase):
    def test_websocket_frame_decoding(self):
        from analizator.ais import WebSocket
        ws = WebSocket.__new__(WebSocket)
        payload = b'{"MetaData":{"MMSI":1}}'
        # ramka tekstowa w dwóch fragmentach + ping pomiędzy (serwer nie maskuje)
        sent = []

        class FakeSock:
            def sendall(self, b): sent.append(b)
            def recv(self, n): return b""
        ws.sock = FakeSock()
        ws.buf = bytes([0x01, 5]) + payload[:5] + bytes([0x89, 0]) + bytes([0x80, len(payload) - 5]) + payload[5:]
        self.assertEqual(ws.recv(), payload.decode())
        self.assertTrue(sent and sent[0][0] == 0x8A, "na ping odpowiadamy pong")

    def test_ship_type(self):
        from analizator.ais import _ship_type
        self.assertEqual(_ship_type({"Message": {"ShipStaticData": {"Type": 84}}}), 84)


class TestBacktest(unittest.TestCase):
    def test_replay_and_evaluate_on_demo(self):
        from analizator.backtest import evaluate, replay
        today = date(2026, 11, 14)
        sig = extract_signals(demo.generate(today))
        idx = replay(sig, today - timedelta(weeks=20), today)
        # wydarzenie w Mołdawii tuż po eskalacji, nic w Serbii
        events = [{"data": today - timedelta(days=1), "kraj": "MD", "opis": "test", "zrodlo": ""}]
        ev = evaluate(idx, events, threshold=40, horizon=60)
        self.assertEqual(ev["events"][0]["status"], "trafione")
        self.assertGreater(ev["events"][0]["lead"], 0)
        # brak wycieku z przyszłości: 10 tygodni wcześniej Mołdawia była spokojna
        early = [v for (c, t), v in idx.items() if c == "MD" and t < today - timedelta(weeks=8)]
        self.assertTrue(early and max(early) < 40)


class TestV05(unittest.TestCase):
    def test_indices_specific_and_unique(self):
        from analizator.skutki import indices
        ix = indices("TW", "wysoki")
        self.assertTrue(ix["down"][0].startswith("TAIEX"))
        self.assertIn("PHLX Semiconductor (SOX)", ix["down"])
        self.assertEqual(sum(x.startswith("TAIEX") for x in ix["down"]), 1)
        self.assertTrue(any("Brent" in x for x in indices("IR")["up"]))

    def test_fronts_group_neighbours(self):
        from analizator.skutki import fronts
        from types import SimpleNamespace as N
        res = [N(country="IR", index=80, priority=1, categories=["lotnictwo_przestrzen"]),
               N(country="AE", index=45, priority=0, categories=["lancuch_dostaw"]), N(country="PL", index=50, priority=0, categories=[])]
        fr = fronts(res)
        self.assertEqual([f["klucz"] for f in fr][:1], ["zatoka"])
        self.assertFalse(any(f["klucz"] == "flanka" for f in fr), "jeden kraj to jeszcze nie front")

    def test_watch_alerts_only_on_change(self):
        from analizator.czuwanie import changes
        today = date(2026, 11, 14)
        res = assess(extract_signals(demo.generate(today)), today=today)
        first, st = changes(res, {}, today)
        self.assertEqual(first, [], "pierwszy cykl tylko ustala punkt odniesienia")
        calm = {"kraje": {k: {"indeks": 5, "poziom": "niski"} for k in st["kraje"]}, "widziane": st["widziane"]}
        alerts, st2 = changes(res, calm, today)
        self.assertTrue(any("(MD)" in a for a in alerts), "wzrost poziomu daje alarm")
        again, _ = changes(res, st2, today)
        self.assertEqual(again, [], "bez zmian nie ma powtórnych powiadomień")


class TestUczenie(unittest.TestCase):
    def test_fit_learns_signal_and_auc(self):
        import random
        from analizator.ucz import auc, fit, predict
        rnd = random.Random(1)
        X = [[rnd.random(), rnd.random()] for _ in range(600)]
        y = [int(x[0] + 0.1 * rnd.random() > 0.8) for x in X]
        m = fit(X, y, iters=300)
        self.assertGreater(m["w"][0], abs(m["w"][1]) * 3, "model powinien nauczyć się, że liczy się pierwsza cecha")
        self.assertGreater(auc([predict(m, x) for x in X], y), 0.9)
        self.assertEqual(auc([0.1, 0.2, 0.3], [0, 0, 1]), 1.0)

    def test_features_match_names(self):
        from analizator.ucz import FEATURES, features
        r = assess(extract_signals(demo.generate(date(2026, 11, 14))), today=date(2026, 11, 14), use_model=False)[0]
        self.assertEqual(len(features(r)), len(FEATURES))


if __name__ == "__main__":
    unittest.main()


class TestV04Filters(unittest.TestCase):
    def test_disaster_evacuation_ignored(self):
        self.assertEqual(classify("Wildfire forces evacuation of hundreds in Japan"), [])
        self.assertEqual(classify("WWII bomb find triggers mass evacuation in Germany"), [])

    def test_embassy_evacuation_kept(self):
        cats = {(s.category, s.country) for s in classify("US evacuates non-essential staff from Beirut embassy amid Iran tensions")}
        self.assertIn(("ewakuacja_personelu", "LB"), cats)

    def test_exit_without_security_context_is_weak(self):
        sig = classify("Intel withdraws from Poland project")
        self.assertTrue(all(s.weight < 1.0 for s in sig))

    def test_sec_conditional_and_repeats_dropped(self):
        arts = [
            {"title": "Acme Corp: Operations in Israel may be suspended due to force majeure", "date": "2026-01-02", "source": "sec", "url": "a"},
            {"title": "Acme Corp: The company suspended operations in Russia and declared force majeure", "date": "2026-01-03", "source": "sec", "url": "b"},
            {"title": "Acme Corp: The company suspended operations in Russia and declared force majeure", "date": "2026-04-03", "source": "sec", "url": "c"},
        ]
        urls = {s["url"] for s in extract_signals(arts)}
        self.assertNotIn("a", urls)
        self.assertIn("b", urls)
        self.assertNotIn("c", urls)

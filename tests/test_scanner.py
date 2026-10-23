from datetime import date

import yaml

from scanner.calendario import Calendario, Finestra, pasqua
from scanner.classifica import classifica
from scanner.fonti import ryanair
from scanner.main import carica_config, esegui


def cal():
    return Calendario("giorni_liberi.yaml")


def test_pasqua():
    assert pasqua(2027) == date(2027, 3, 28)
    assert pasqua(2026) == date(2026, 4, 5)


def test_weekend_normale():
    fin = cal().finestre(date(2026, 10, 26), 3, 2, 4)
    w = [f for f in fin if f.andata == date(2026, 11, 6)][0]
    assert (w.ritorno, w.tipo, w.vincolo_orario_andata) == (date(2026, 11, 8), "weekend", True)


def test_ponte_immacolata():
    fin = cal().finestre(date(2026, 11, 20), 4, 2, 4)
    p = [f for f in fin if f.tipo == "ponte"][0]
    assert (p.andata, p.ritorno, p.notti) == (date(2026, 12, 4), date(2026, 12, 8), 4)


def test_giorno_extra_moglie_allunga_il_weekend():
    c = Calendario(dati={"extra_moglie": ["2026-11-16"]})
    fin = c.finestre(date(2026, 11, 1), 4, 2, 4)
    assert Finestra(date(2026, 11, 13), date(2026, 11, 16), True, "ponte") in fin


def test_non_liberi_ha_la_precedenza():
    c = Calendario(dati={"extra_moglie": ["2026-11-16"], "non_liberi": ["2026-11-16"]})
    fin = c.finestre(date(2026, 11, 1), 4, 2, 4)
    assert all(f.ritorno != date(2026, 11, 16) for f in fin)


def test_ryanair_filtra_orari_e_italia():
    cfg = carica_config()
    f = Finestra(date(2026, 11, 6), date(2026, 11, 8), True, "weekend")

    def fare(iata, paese, out, inn, prezzo):
        return {"outbound": {"arrivalAirport": {"iataCode": iata, "countryName": paese,
                                                "name": iata, "city": {"name": iata}},
                             "departureDate": f"2026-11-06T{out}:00", "arrivalDate": "2026-11-06T22:00:00"},
                "inbound": {"departureDate": f"2026-11-08T{inn}:00", "arrivalDate": "2026-11-08T21:30:00"},
                "summary": {"price": {"value": prezzo}}}

    dati = {"fares": [fare("BUD", "Hungary", "18:00", "19:00", 49.9),
                      fare("TRN", "Italy", "18:00", "19:00", 20),     # Italia esclusa
                      fare("KRK", "Poland", "07:00", "19:00", 30),    # parte troppo presto
                      fare("CRL", "Belgium", "18:00", "09:00", 25)]}  # rientro a qualsiasi ora: ok
    out = ryanair.interpreta(dati, f, cfg, "2026-10-23")
    assert [o.destinazione for o in out] == ["BUD", "CRL"]
    assert out[0].prezzo_totale == round(49.9 * 4, 2)
    assert "teens=1" in out[0].link


def test_classifica_una_per_citta():
    base = {"tipo": "weekend", "persone": 4, "paese": "", "destinazione": "X", "fonte": "google"}
    voci = [dict(base, finestra="a", citta="Budapest", prezzo_persona=40),
            dict(base, finestra="b", citta="Budapest", prezzo_persona=45),
            dict(base, finestra="a", citta="Tirana", prezzo_persona=60)]
    assert [v["citta"] for v in classifica(voci, 5, True)] == ["Budapest", "Tirana"]
    assert len(classifica(voci, 5, False)) == 3


def test_prova_completa_senza_internet():
    testo = esegui(prova=True, manda=False, oggi=date(2026, 10, 23))
    assert "🥇" in testo and "5️⃣" in testo
    assert len(testo) <= 4000


def test_config_valida():
    with open("config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    assert all(len(k) == 3 and k.isupper() for k in cfg["destinazioni"])


def test_ryanair_rientro_entro_le_5_del_giorno_dopo():
    cfg = carica_config()
    f = Finestra(date(2026, 11, 6), date(2026, 11, 8), True, "weekend")

    def fare(iata, arrivo):
        return {"outbound": {"arrivalAirport": {"iataCode": iata, "countryName": "X", "name": iata},
                             "departureDate": "2026-11-06T18:00:00", "arrivalDate": "2026-11-06T20:00:00"},
                "inbound": {"departureDate": "2026-11-08T23:00:00", "arrivalDate": arrivo},
                "summary": {"price": {"value": 50}}}

    dati = {"fares": [fare("AAA", "2026-11-09T01:30:00"), fare("BBB", "2026-11-09T06:10:00")]}
    assert [o.destinazione for o in ryanair.interpreta(dati, f, cfg, "2026-10-23")] == ["AAA"]


def test_aeroporti_alternativi_solo_se_conviene():
    from scanner.classifica import filtra_convenienti
    base = {"tipo": "weekend", "persone": 4, "paese": "", "destinazione": "X", "fonte": "ryanair",
            "finestra": "a"}
    voci = [dict(base, citta="Budapest", prezzo_persona=60, partenza="BRI"),           # 240
            dict(base, citta="Budapest", prezzo_persona=40, partenza="NAP", costo_extra=75),  # 235: no
            dict(base, citta="Praga", prezzo_persona=80, partenza="BRI"),              # 320
            dict(base, citta="Praga", prezzo_persona=30, partenza="BDS", costo_extra=35),     # 155: sì
            dict(base, citta="Edimburgo", prezzo_persona=50, partenza="NAP", costo_extra=75)]  # da Bari no
    tenute = {(v["citta"], v["partenza"]) for v in filtra_convenienti(voci, 60)}
    assert ("Budapest", "NAP") not in tenute
    assert ("Praga", "BDS") in tenute and ("Edimburgo", "NAP") in tenute


def test_orari_adattati_per_napoli():
    from scanner.main import configurazioni_partenza
    nap = [x for x, _ in configurazioni_partenza(carica_config()) if x["partenza"] == "NAP"][0]
    assert nap["orari"]["andata_dopo"] == "17:20"
    assert nap["orari"]["rientro_a_bari_entro_giorno_dopo"] == "03:40"

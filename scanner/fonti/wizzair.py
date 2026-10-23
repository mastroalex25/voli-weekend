"""Tariffe pubbliche Wizz Air (calendario "timetable" del sito).

Wizz cambia spesso il numero di versione della sua API e a volte blocca le
richieste che arrivano da server: il programma lo gestisce e, se fallisce,
lo scrive in fondo al messaggio Telegram.
"""
from __future__ import annotations

import re
import time
from datetime import timedelta

import requests

from ..calendario import Finestra
from ..modello import Offerta

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://wizzair.com",
    "Referer": "https://wizzair.com/",
    "Content-Type": "application/json",
}


def base_url(sess: requests.Session) -> str:
    tentativi = []
    for url in ("https://wizzair.com/buildnumber", "https://wizzair.com/it-it"):
        try:
            r = sess.get(url, timeout=20)
            m = re.search(r"be\.wizzair\.com/(\d+(?:\.\d+)+)", r.text)
            if m:
                return f"https://be.wizzair.com/{m.group(1)}"
            tentativi.append(f"{url} -> HTTP {r.status_code}: {r.text[:120]!r}")
        except Exception as e:
            tentativi.append(f"{url} -> {type(e).__name__}: {e}")
    raise RuntimeError("versione API non trovata; " + " | ".join(tentativi))


def destinazioni(sess: requests.Session, base: str, partenza: str) -> list[dict]:
    dati = sess.get(f"{base}/Api/asset/map?languageCode=it-it", timeout=30).json()
    for c in dati.get("cities", []):
        if c.get("iata") == partenza:
            nomi = {x.get("iata"): x for x in dati.get("cities", [])}
            return [nomi.get(k["iata"], {"iata": k["iata"]}) for k in c.get("connections", [])]
    return []


class Cambi:
    """Converte in euro (il ritorno Wizz è spesso in valuta locale)."""
    def __init__(self, sess):
        self.sess, self.cache = sess, {"EUR": 1.0}

    def in_euro(self, importo: float, valuta: str) -> float | None:
        if valuta not in self.cache:
            try:
                r = self.sess.get(f"https://api.frankfurter.app/latest?from={valuta}&to=EUR", timeout=15)
                self.cache[valuta] = float(r.json()["rates"]["EUR"])
            except Exception:
                self.cache[valuta] = None
        tasso = self.cache[valuta]
        return importo * tasso if tasso else None


def _miglior_volo(voli: list[dict], dopo: str | None, cambi: Cambi) -> tuple[float, str] | None:
    migliori = []
    for v in voli:
        prezzo = (v.get("price") or {}).get("amount")
        if not prezzo or v.get("priceType") == "soldOut":
            continue
        orari = [d[11:16] for d in v.get("departureDates", []) if len(d) >= 16]
        if dopo:
            orari = [h for h in orari if h >= dopo]
        if not orari:
            continue
        eur = cambi.in_euro(float(prezzo), (v.get("price") or {}).get("currencyCode", "EUR"))
        if eur:
            migliori.append((eur, orari[0]))
    return min(migliori) if migliori else None


def link_prenotazione(dest: str, f: Finestra, cfg: dict) -> str:
    n = int(cfg["passeggeri"]["adulti"]) + int(cfg["passeggeri"]["ragazzi_12_15"])
    return (f"https://wizzair.com/it-it/booking/select-flight/{cfg['partenza']}/{dest}/"
            f"{f.andata.isoformat()}/{f.ritorno.isoformat()}/{n}/0/0/null")


def cerca_tutto(finestre: list[Finestra], cfg: dict, oggi: str) -> tuple[list[Offerta], list[str]]:
    offerte, errori = [], []
    sess = requests.Session()
    sess.headers.update(HEADERS)
    try:
        base = base_url(sess)
        rotte = destinazioni(sess, base, cfg["partenza"])
    except Exception as e:
        return [], [f"Wizz Air non raggiungibile: {type(e).__name__}: {e}"[:700]]
    escludi = {x.lower() for x in cfg.get("escludi_paesi", [])}
    rotte = [r for r in rotte if str(r.get("countryCode", "")).lower() not in escludi]
    cambi = Cambi(sess)
    persone = int(cfg["passeggeri"]["adulti"]) + int(cfg["passeggeri"]["ragazzi_12_15"])
    o = cfg["orari"]

    for rotta in rotte:
        dest = rotta.get("iata")
        andate, ritorni = [], []
        # una chiamata ogni ~6 settimane per rotta invece di una per finestra
        inizio, fine = min(f.andata for f in finestre), max(f.ritorno for f in finestre)
        while inizio <= fine:
            stop = min(fine, inizio + timedelta(days=41))
            corpo = {
                "flightList": [
                    {"departureStation": cfg["partenza"], "arrivalStation": dest,
                     "from": inizio.isoformat(), "to": stop.isoformat()},
                    {"departureStation": dest, "arrivalStation": cfg["partenza"],
                     "from": inizio.isoformat(), "to": stop.isoformat()},
                ],
                "priceType": "regular", "adultCount": 1, "childCount": 0, "infantCount": 0,
            }
            try:
                time.sleep(1.0)   # Wizz rifiuta le richieste troppo ravvicinate
                r = sess.post(f"{base}/Api/search/timetable", json=corpo, timeout=30)
                if r.status_code in (429, 503):
                    time.sleep(8)
                    r = sess.post(f"{base}/Api/search/timetable", json=corpo, timeout=30)
                r.raise_for_status()
                dati = r.json()
                andate += dati.get("outboundFlights", [])
                ritorni += dati.get("returnFlights", [])
            except Exception as e:
                errori.append(f"Wizz {dest} {inizio}: {type(e).__name__}"[:200])
                if len(errori) >= 5 and not offerte:
                    return offerte, errori + ["Wizz Air: interrotto, richieste rifiutate"]
            inizio = stop + timedelta(days=1)

        def del_giorno(voli, giorno):
            g = giorno.isoformat()
            return [v for v in voli if str(v.get("departureDate", ""))[:10] == g]

        for f in finestre:
            andata = _miglior_volo(del_giorno(andate, f.andata),
                                   o["andata_dopo"] if f.vincolo_orario_andata else None, cambi)
            ritorno = _miglior_volo(del_giorno(ritorni, f.ritorno), o["ritorno_partenza_dopo"], cambi)
            if not (andata and ritorno):
                continue
            offerte.append(Offerta(
                fonte="wizzair", finestra=f.chiave, tipo=f.tipo, destinazione=dest,
                citta=rotta.get("shortName", dest), paese=rotta.get("countryName", rotta.get("countryCode", "")),
                prezzo_persona=round(andata[0] + ritorno[0], 2), persone=persone,
                compagnie=["Wizz Air"], scali=0,
                andata=f"partenza {andata[1]}", ritorno=f"partenza {ritorno[1]}",
                link=link_prenotazione(dest, f, cfg), aggiornato=oggi,
            ))
    return offerte, errori

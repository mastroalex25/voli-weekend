"""Tariffe pubbliche Ryanair (le stesse usate dalla pagina "tariffe più basse").

Una sola chiamata per finestra restituisce la tariffa più bassa verso TUTTE
le destinazioni servite da Bari, quindi costa pochissimo e copre anche
città non presenti nella lista di config.yaml.
Endpoint non ufficiale: se Ryanair lo cambia, il programma lo segnala su
Telegram e continua con le altre fonti.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import requests

from ..calendario import GIORNI, Finestra
from ..modello import Offerta

URL = "https://services-api.ryanair.com/farfnd/v4/roundTripFares"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept": "application/json",
}


def _hm(s: str) -> str:
    return s[11:16] if s and len(s) >= 16 else ""


def parametri(f: Finestra, cfg: dict) -> dict:
    o = cfg["orari"]
    return {
        "departureAirportIataCode": cfg["partenza"],
        "outboundDepartureDateFrom": f.andata.isoformat(),
        "outboundDepartureDateTo": f.andata.isoformat(),
        "inboundDepartureDateFrom": f.ritorno.isoformat(),
        "inboundDepartureDateTo": f.ritorno.isoformat(),
        "outboundDepartureTimeFrom": o["andata_dopo"] if f.vincolo_orario_andata else "00:00",
        "outboundDepartureTimeTo": "23:59",
        "inboundDepartureTimeFrom": o["ritorno_partenza_dopo"],
        "inboundDepartureTimeTo": "23:59",
        "currency": "EUR",
        "market": "it-it",
        "adultPaxCount": 1,
    }


def link_prenotazione(dest: str, f: Finestra, cfg: dict) -> str:
    p = cfg["passeggeri"]
    return ("https://www.ryanair.com/it/it/trip/flights/select?"
            f"adults={p['adulti']}&teens={p['ragazzi_12_15']}&children=0&infants=0"
            f"&dateOut={f.andata.isoformat()}&dateIn={f.ritorno.isoformat()}"
            f"&isConnectedFlight=false&isReturn=true&discount=0"
            f"&originIata={cfg['partenza']}&destinationIata={dest}")


def interpreta(dati: dict, f: Finestra, cfg: dict, oggi: str) -> list[Offerta]:
    o = cfg["orari"]
    persone = int(cfg["passeggeri"]["adulti"]) + int(cfg["passeggeri"]["ragazzi_12_15"])
    escludi = {x.lower() for x in cfg.get("escludi_paesi", [])}
    out = []
    for fare in dati.get("fares", []):
        ob, ib = fare.get("outbound") or {}, fare.get("inbound") or {}
        arr = ob.get("arrivalAirport") or {}
        paese = arr.get("countryName", "")
        if paese.lower() in escludi or str(arr.get("countryCode", "")).lower() in escludi:
            continue
        # doppio controllo degli orari, nel caso l'API ignori i filtri
        if f.vincolo_orario_andata and _hm(ob.get("departureDate", "")) < o["andata_dopo"]:
            continue
        if _hm(ib.get("departureDate", "")) < o["ritorno_partenza_dopo"]:
            continue
        limite = o.get("rientro_a_bari_entro_giorno_dopo")
        arrivo = ib.get("arrivalDate", "")[:16]
        if limite and arrivo and arrivo > f"{(f.ritorno + timedelta(days=1)).isoformat()}T{limite}":
            continue
        prezzo = (fare.get("summary") or {}).get("price", {}).get("value")
        if prezzo is None:
            prezzo = ob.get("price", {}).get("value", 0) + ib.get("price", {}).get("value", 0)
        if not prezzo:
            continue
        citta = (arr.get("city") or {}).get("name") or arr.get("name", arr.get("iataCode", "?"))
        dest = arr.get("iataCode", "?")
        out.append(Offerta(
            fonte="ryanair", finestra=f.chiave, tipo=f.tipo, destinazione=dest,
            citta=citta, paese=paese, prezzo_persona=float(prezzo), persone=persone,
            compagnie=["Ryanair"], scali=0,
            andata=f"{_hm(ob.get('departureDate',''))} → {_hm(ob.get('arrivalDate',''))}",
            ritorno=f"{_hm(ib.get('departureDate',''))} → {_hm(ib.get('arrivalDate',''))}",
            link=link_prenotazione(dest, f, cfg),
            nota=f"aeroporto: {arr.get('name', dest)}",
            aggiornato=oggi,
        ))
    return out


def cerca_tutto(finestre: list[Finestra], cfg: dict, oggi: str) -> tuple[list[Offerta], list[str]]:
    offerte, errori = [], []
    sess = requests.Session()
    sess.headers.update(HEADERS)
    for f in finestre:
        try:
            r = sess.get(URL, params=parametri(f, cfg), timeout=30)
            r.raise_for_status()
            offerte += interpreta(r.json(), f, cfg, oggi)
        except Exception as e:
            errori.append(f"Ryanair {f.chiave}: {type(e).__name__}: {e}"[:200])
            if len(errori) >= 5 and not offerte:
                errori.append("Ryanair: interrotto, l'API sembra non rispondere")
                break
    return offerte, errori

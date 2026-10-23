"""Prezzi da Google Flights tramite la libreria non ufficiale fast-flights.

Copre tutte le compagnie, scali compresi. Un'interrogazione per coppia
(finestra, destinazione): per questo il numero di ricerche al giorno è limitato
e le destinazioni vengono controllate a rotazione.
"""
from __future__ import annotations

import logging
import time

from ..calendario import Finestra
from ..modello import Offerta

log = logging.getLogger(__name__)


def _ora(t: tuple[int, int]) -> str:
    return f"{t[0]:02d}:{t[1]:02d}"


def cerca(finestra: Finestra, dest: str, nome: str, cfg: dict, oggi: str) -> Offerta | None:
    from fast_flights import FlightQuery, Passengers, create_query, get_flights
    from fast_flights.exceptions import FlightsNotFound

    o = cfg["orari"]
    h_andata = int(o["andata_dopo"].split(":")[0]) if finestra.vincolo_orario_andata else None
    h_rit = int(o["ritorno_partenza_dopo"].split(":")[0]) or None
    h_arr = min(23, int(o["ritorno_arrivo_entro"].split(":")[0])) if o.get("ritorno_arrivo_entro") else None
    citta, _, paese = nome.partition(",")

    q = create_query(
        flights=[
            FlightQuery(date=finestra.andata.isoformat(), from_airport=cfg["partenza"],
                        to_airport=dest, earliest_departure_hour=h_andata),
            FlightQuery(date=finestra.ritorno.isoformat(), from_airport=dest,
                        to_airport=cfg["partenza"], earliest_departure_hour=h_rit,
                        latest_arrival_hour=h_arr),
        ],
        trip="round-trip",
        passengers=Passengers(adults=1),   # prezzo a persona, poi x4
        language="it",
        currency="EUR",
        max_stops=cfg["ricerca"]["max_scali"],
        carry_on_bags=1 if cfg["bagaglio"]["trolley_cabina"] else 0,
    )
    try:
        risultati = get_flights(q)
    except FlightsNotFound:
        return None

    validi = [r for r in risultati if r.price and r.flights]
    if not validi:
        return None
    best = min(validi, key=lambda r: r.price)
    primo, ultimo = best.flights[0], best.flights[-1]
    return Offerta(
        fonte="google",
        finestra=finestra.chiave,
        tipo=finestra.tipo,
        destinazione=dest,
        citta=citta.strip(),
        paese=paese.strip(),
        prezzo_persona=float(best.price),
        persone=_persone(cfg),
        compagnie=list(best.airlines),
        scali=len(best.flights) - 1,
        andata=f"{_ora(primo.departure.time)} → {_ora(ultimo.arrival.time)}",
        ritorno="orari sul link",
        link=q.url(),
        nota="prezzo a persona ×4 (stima)",
        aggiornato=oggi,
    )


def _persone(cfg: dict) -> int:
    p = cfg["passeggeri"]
    return int(p["adulti"]) + int(p["ragazzi_12_15"])


def cerca_tutto(lavori: list[tuple[Finestra, str, str]], cfg: dict, oggi: str) -> tuple[list[Offerta], list[str], list[str]]:
    """Esegue le ricerche in sequenza. Si ferma dopo troppi errori di fila
    (segno che Google sta bloccando) per non peggiorare la situazione."""
    offerte, errori, controllati, di_fila = [], [], [], 0
    pausa = float(cfg["ricerca"]["pausa_tra_ricerche_sec"])
    for finestra, dest, nome in lavori:
        try:
            off = cerca(finestra, dest, nome, cfg, oggi)
            di_fila = 0
            controllati.append(f"{finestra.chiave}|{dest}")
            if off:
                offerte.append(off)
        except Exception as e:  # rete, blocchi, cambi di formato della pagina
            di_fila += 1
            errori.append(f"{dest} {finestra.chiave}: {type(e).__name__}: {e}"[:200])
            log.warning("Google %s %s: %s", dest, finestra.chiave, e)
            if di_fila >= 8:
                errori.append("Google: interrotto dopo 8 errori consecutivi")
                break
        time.sleep(pausa)
    return offerte, errori, controllati

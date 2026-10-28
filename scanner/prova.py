"""Dati finti per provare il programma senza andare su internet."""
from __future__ import annotations

import random

from .modello import Offerta

CITTA = [("BUD", "Budapest", "Ungheria", "Ryanair"), ("SOF", "Sofia", "Bulgaria", "Wizz Air"),
         ("PRG", "Praga", "Rep. Ceca", "Ryanair"), ("ATH", "Atene", "Grecia", "Aegean"),
         ("KRK", "Cracovia", "Polonia", "Ryanair"), ("VIE", "Vienna", "Austria", "Austrian"),
         ("LIS", "Lisbona", "Portogallo", "TAP"), ("MLA", "La Valletta", "Malta", "Ryanair")]


def offerte_finte(finestre, cfg, oggi: str) -> list[Offerta]:
    rnd = random.Random(42)
    persone = int(cfg["passeggeri"]["adulti"]) + int(cfg["passeggeri"]["ragazzi_12_15"])
    out = []
    for f in finestre:
        for dest, citta, paese, comp in rnd.sample(CITTA, 4):
            fonte = {"Ryanair": "ryanair", "Wizz Air": "wizzair"}.get(comp, "google")
            out.append(Offerta(
                fonte=fonte, finestra=f.chiave, tipo=f.tipo, destinazione=dest, citta=citta,
                paese=paese, prezzo_persona=float(rnd.randint(35, 260)) + 0.99, persone=persone,
                compagnie=[comp], scali=0 if fonte != "google" else rnd.choice([0, 1]),
                andata="18:20 → 20:05", ritorno="19:10 → 20:55",
                link="https://www.google.com/travel/flights", aggiornato=oggi))
    return out

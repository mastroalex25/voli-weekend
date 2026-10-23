"""Avvio: python -m scanner.main [--prova] [--no-telegram]

--prova        non va su internet: usa dati di esempio (per controllare il messaggio)
--no-telegram  stampa il messaggio invece di inviarlo
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

import yaml

from . import telegram
from .calendario import Calendario
from .classifica import Archivio, classifica, migliori_ponti

QUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
log = logging.getLogger("scanner")


def carica_config() -> dict:
    with open(os.path.join(QUI, "config.yaml"), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def esegui(prova: bool = False, manda: bool = True, oggi: date | None = None) -> str:
    cfg = carica_config()
    oggi = oggi or datetime.now(ZoneInfo("Europe/Rome")).date()
    oggi_s = oggi.isoformat()
    r = cfg["ricerca"]

    cal = Calendario(os.path.join(QUI, "giorni_liberi.yaml"))
    finestre = cal.finestre(oggi, r["settimane_avanti"], r["giorni_minimi_preavviso"], r["notti_max_finestra"])
    log.info("%d finestre di viaggio", len(finestre))

    archivio = Archivio(os.path.join(QUI, "data", "prezzi_prova.json" if prova else "prezzi.json"))
    archivio.pulisci(oggi, {f.chiave for f in finestre}, r["validita_cache_giorni"])

    riassunto, avvisi, errori_dettaglio = [], [], []
    if prova:
        from .prova import offerte_finte
        archivio.aggiorna(offerte_finte(finestre, cfg, oggi_s))
        riassunto.append("dati di PROVA, nessuna ricerca reale")
    else:
        fonti = cfg["fonti"]
        if fonti.get("ryanair"):
            from .fonti import ryanair
            off, err = ryanair.cerca_tutto(finestre, cfg, oggi_s)
            errori_dettaglio.extend(err)
            _registra(archivio, "ryanair", off, err, oggi_s, riassunto, avvisi, f"Ryanair {len(off)} tariffe")
        if fonti.get("wizzair"):
            from .fonti import wizzair
            off, err = wizzair.cerca_tutto(finestre, cfg, oggi_s)
            errori_dettaglio.extend(err)
            _registra(archivio, "wizzair", off, err, oggi_s, riassunto, avvisi, f"Wizz {len(off)} tariffe")
        if fonti.get("google_flights"):
            from .fonti import google
            lavori = [(f, d, n) for f in finestre for d, n in cfg["destinazioni"].items()]
            # rotazione: prima le coppie mai controllate o controllate da più tempo,
            # a parità le date più vicine
            lavori.sort(key=lambda x: (archivio.ultimo_controllo(x[0].chiave, x[1]), x[0].andata))
            lavori = lavori[: int(r["google_max_ricerche_giorno"])]
            off, err, controllati = google.cerca_tutto(lavori, cfg, oggi_s)
            errori_dettaglio.extend(err)
            archivio.aggiorna(off)
            archivio.segna_controllati(controllati, oggi_s)
            riassunto.append(f"Google {len(lavori)} ricerche")
            if err:
                avvisi.append(f"Google: {len(err)} errori (es. {err[0][:90]})")

    archivio.salva()
    if not prova:
        with open(os.path.join(QUI, "data", "diagnostica.txt"), "w", encoding="utf-8") as fh:
            fh.write(f"{oggi_s}\n" + ", ".join(riassunto) + "\n\n" + "\n".join(errori_dettaglio[:60]) + "\n")
    voci = archivio.offerte()
    top = classifica(voci, cfg["classifica"]["top"], cfg["classifica"]["una_volta_per_citta"])
    ponti = migliori_ponti(voci, cfg["classifica"]["sezione_ponti"])
    testo = telegram.componi(top, ponti, {"riassunto": ", ".join(riassunto), "avvisi": avvisi}, oggi, cfg)

    if manda:
        token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
        if not (token and chat):
            raise SystemExit("Mancano TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID")
        telegram.invia(testo, token, chat)
    return testo


def _registra(archivio, fonte, off, err, oggi_s, riassunto, avvisi, etichetta):
    if off:
        # la fonte ha risposto: le sue vecchie tariffe non viste oggi sono esaurite
        archivio.voci = {k: v for k, v in archivio.voci.items()
                         if not (v["fonte"] == fonte and v.get("aggiornato") != oggi_s)}
    archivio.aggiorna(off)
    riassunto.append(etichetta)
    if err:
        avvisi.append(f"{fonte}: {len(err)} errori (es. {err[-1][:90]})")


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--prova", action="store_true")
    p.add_argument("--no-telegram", action="store_true")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    testo = esegui(prova=a.prova, manda=not a.no_telegram)
    if a.no_telegram:
        print(testo)


if __name__ == "__main__":
    sys.exit(main())

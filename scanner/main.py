"""Avvio: python -m scanner.main [--prova] [--no-telegram]

--prova        non va su internet: usa dati di esempio (per controllare il messaggio)
--no-telegram  stampa il messaggio invece di inviarlo
"""
from __future__ import annotations

import argparse
import copy
import logging
import os
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

import yaml

from . import telegram
from .calendario import Calendario
from .classifica import Archivio, classifica, filtra_convenienti, migliori_ponti

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
        partenze = configurazioni_partenza(cfg)
        for fonte, attiva in (("ryanair", fonti.get("ryanair")), ("wizzair", fonti.get("wizzair"))):
            if not attiva:
                continue
            modulo = __import__(f"scanner.fonti.{fonte}", fromlist=["cerca_tutto"])
            totale = 0
            for c, extra in partenze:
                off, err = modulo.cerca_tutto(finestre, c, oggi_s)
                _etichetta(off, c, extra)
                errori_dettaglio.extend(f"[{c['partenza']}] {e}" for e in err)
                _registra(archivio, fonte, c["partenza"], off, err, oggi_s, avvisi)
                totale += len(off)
            riassunto.append(f"{fonte.capitalize()} {totale} tariffe")
        if fonti.get("google_flights"):
            from .fonti import google
            n_alt = max(1, len(partenze) - 1)
            ricerche = 0
            for c, extra in partenze:
                quota = (int(r["google_max_ricerche_giorno"]) if c["partenza"] == cfg["partenza"]
                         else int(r.get("google_max_ricerche_alternativi", 0)) // n_alt)
                if quota <= 0:
                    continue
                lavori = [(f, d, n) for f in finestre for d, n in cfg["destinazioni"].items()]
                # rotazione: prima le coppie mai controllate o controllate da più tempo,
                # a parità le date più vicine
                lavori.sort(key=lambda x: (archivio.ultimo_controllo(x[0].chiave, c["partenza"], x[1]),
                                           x[0].andata))
                lavori = lavori[:quota]
                off, err, controllati = google.cerca_tutto(lavori, c, oggi_s)
                _etichetta(off, c, extra)
                errori_dettaglio.extend(f"[{c['partenza']}] {e}" for e in err)
                archivio.aggiorna(off)
                archivio.segna_controllati(controllati, oggi_s)
                ricerche += len(lavori)
                if err:
                    avvisi.append(f"Google {c['partenza']}: {len(err)} errori")
            riassunto.append(f"Google {ricerche} ricerche")

    archivio.salva()
    if not prova:
        with open(os.path.join(QUI, "data", "diagnostica.txt"), "w", encoding="utf-8") as fh:
            fh.write(f"{oggi_s}\n" + ", ".join(riassunto) + "\n\n" + "\n".join(errori_dettaglio[:60]) + "\n")
    voci = filtra_convenienti(archivio.offerte(), float(cfg.get("risparmio_minimo", 0)))
    top = classifica(voci, cfg["classifica"]["top"], cfg["classifica"]["una_volta_per_citta"])
    ponti = migliori_ponti(voci, cfg["classifica"]["sezione_ponti"])
    testo = telegram.componi(top, ponti, {"riassunto": ", ".join(riassunto), "avvisi": avvisi}, oggi, cfg)

    if manda:
        token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
        if not (token and chat):
            raise SystemExit("Mancano TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID")
        telegram.invia(testo, token, chat)
    return testo


def _sposta(hhmm: str, minuti: int) -> str:
    h, m = map(int, hhmm.split(":"))
    t = max(0, min(23 * 60 + 59, h * 60 + m + minuti))
    return f"{t // 60:02d}:{t % 60:02d}"


def configurazioni_partenza(cfg: dict) -> list[tuple[dict, dict]]:
    """Bari più gli aeroporti alternativi, con orari adattati al tempo di guida in più."""
    out = [(cfg, {"costo_extra": 0, "nome": "Bari"})]
    for codice, alt in (cfg.get("aeroporti_alternativi") or {}).items():
        c = copy.deepcopy(cfg)
        c["partenza"] = codice
        minuti = int(alt.get("minuti_extra", 0))
        o = c["orari"]
        o["andata_dopo"] = _sposta(o["andata_dopo"], minuti)
        if o.get("rientro_a_bari_entro_giorno_dopo"):
            o["rientro_a_bari_entro_giorno_dopo"] = _sposta(o["rientro_a_bari_entro_giorno_dopo"], -minuti)
        out.append((c, alt))
    return out


def _etichetta(offerte, c, extra) -> None:
    for o in offerte:
        o.partenza = c["partenza"]
        o.costo_extra = float(extra.get("costo_extra", 0))


def _registra(archivio, fonte, partenza, off, err, oggi_s, avvisi):
    if off:
        # la fonte ha risposto: le sue vecchie tariffe non viste oggi sono esaurite
        archivio.voci = {k: v for k, v in archivio.voci.items()
                         if not (v["fonte"] == fonte and v.get("partenza", "BRI") == partenza
                                 and v.get("aggiornato") != oggi_s)}
    archivio.aggiorna(off)
    if err:
        avvisi.append(f"{fonte} {partenza}: {len(err)} errori (es. {err[-1][:90]})")


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

"""Archivio prezzi (per vedere se un prezzo sale o scende) e classifica finale."""
from __future__ import annotations

import json
import os
import re
from datetime import date, timedelta

from .calendario import Finestra
from .modello import Offerta


def _norm(citta: str) -> str:
    c = re.split(r"[-(/,]", citta.lower())[0].strip()
    return {"paris": "parigi", "london": "londra", "lisbon": "lisbona", "vienna": "vienna",
            "prague": "praga", "warsaw": "varsavia", "brussels": "bruxelles",
            "budapest": "budapest", "athens": "atene", "bucharest": "bucarest",
            "cracow": "cracovia", "krakow": "cracovia", "seville": "siviglia",
            "barcelona": "barcellona", "copenhagen": "copenaghen", "munich": "monaco"}.get(c, c)


class Archivio:
    def __init__(self, percorso: str):
        self.percorso = percorso
        self.voci: dict[str, dict] = {}
        self.controlli: dict[str, str] = {}   # "finestra|dest" -> ultima ricerca Google
        if os.path.exists(percorso):
            with open(percorso, encoding="utf-8") as fh:
                dati = json.load(fh)
            self.voci = dati.get("offerte", {})
            self.controlli = dati.get("controlli_google", {})

    def pulisci(self, oggi: date, finestre_valide: set[str], validita_giorni: int) -> None:
        limite = (oggi - timedelta(days=validita_giorni)).isoformat()
        self.voci = {k: v for k, v in self.voci.items()
                     if v["finestra"] in finestre_valide and v.get("aggiornato", "") >= limite}
        self.controlli = {k: v for k, v in self.controlli.items()
                          if k.split("|")[0] in finestre_valide}

    def ultimo_controllo(self, finestra: str, dest: str) -> str:
        return self.controlli.get(f"{finestra}|{dest}", "")

    def segna_controllati(self, coppie: list[str], oggi: str) -> None:
        for c in coppie:
            self.controlli[c] = oggi
            # se oggi Google non ha trovato nulla, il vecchio prezzo non vale più
            vecchia = self.voci.get(f"{c}|google")
            if vecchia and vecchia.get("aggiornato") != oggi:
                del self.voci[f"{c}|google"]

    def aggiorna(self, offerte: list[Offerta]) -> None:
        for o in offerte:
            vecchia = self.voci.get(o.chiave)
            d = o.to_dict()
            if vecchia:
                if vecchia.get("aggiornato") != o.aggiornato:
                    d["prezzo_prec"] = vecchia["prezzo_persona"]
                else:
                    d["prezzo_prec"] = vecchia.get("prezzo_prec")
                d["minimo"] = min(vecchia.get("minimo", vecchia["prezzo_persona"]), o.prezzo_persona)
            else:
                d["prezzo_prec"], d["minimo"] = None, o.prezzo_persona
            self.voci[o.chiave] = d

    def salva(self) -> None:
        os.makedirs(os.path.dirname(self.percorso) or ".", exist_ok=True)
        with open(self.percorso, "w", encoding="utf-8") as fh:
            json.dump({"offerte": self.voci, "controlli_google": self.controlli},
                      fh, ensure_ascii=False, indent=1, sort_keys=True)

    def offerte(self) -> list[dict]:
        return list(self.voci.values())


def classifica(voci: list[dict], top: int, una_per_citta: bool) -> list[dict]:
    # per ogni (finestra, città) tengo la fonte più economica
    migliori: dict[tuple, dict] = {}
    for v in voci:
        k = (v["finestra"], _norm(v["citta"]))
        if k not in migliori or v["prezzo_persona"] < migliori[k]["prezzo_persona"]:
            migliori[k] = v
    ordinate = sorted(migliori.values(), key=lambda v: (v["prezzo_persona"] * v["persone"], v["finestra"]))
    if not una_per_citta:
        return ordinate[:top]
    out, viste = [], set()
    for v in ordinate:
        c = _norm(v["citta"])
        if c not in viste:
            viste.add(c)
            out.append(v)
        if len(out) == top:
            break
    return out


def migliori_ponti(voci: list[dict], n: int) -> list[dict]:
    """Il prezzo migliore per ciascun ponte/vacanza, una riga per finestra."""
    per_finestra: dict[str, dict] = {}
    for v in voci:
        if v["tipo"] == "weekend":
            continue
        f = v["finestra"]
        if f not in per_finestra or v["prezzo_persona"] < per_finestra[f]["prezzo_persona"]:
            per_finestra[f] = v
    return sorted(per_finestra.values(), key=lambda v: v["finestra"])[:n]


def finestra_da_chiave(chiave: str, tipo: str) -> Finestra:
    a, r = chiave.split("_")
    return Finestra(date.fromisoformat(a), date.fromisoformat(r), True, tipo)

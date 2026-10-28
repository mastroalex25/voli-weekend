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
            "barcelona": "barcellona", "copenhagen": "copenaghen", "munich": "monaco",
            "la valletta": "malta", "valletta": "malta", "larnaca": "cipro"}.get(c, c)


class Archivio:
    def __init__(self, percorso: str):
        self.percorso = percorso
        self.voci: dict[str, dict] = {}
        self.controlli: dict[str, str] = {}   # "finestra|dest" -> ultima ricerca Google
        self.mostrate: dict[str, dict] = {}   # città -> {"data", "costo"} dell'ultima volta in top
        if os.path.exists(percorso):
            with open(percorso, encoding="utf-8") as fh:
                dati = json.load(fh)
            # le chiavi senza aeroporto di partenza sono del vecchio formato: si scartano
            self.voci = {k: v for k, v in dati.get("offerte", {}).items() if k.count("|") == 3}
            self.controlli = {k: v for k, v in dati.get("controlli_google", {}).items() if k.count("|") == 2}
            self.mostrate = dati.get("mostrate", {})

    def pulisci(self, oggi: date, finestre_valide: set[str], validita_giorni: int) -> None:
        limite = (oggi - timedelta(days=validita_giorni)).isoformat()
        self.voci = {k: v for k, v in self.voci.items()
                     if v["finestra"] in finestre_valide and v.get("aggiornato", "") >= limite}
        self.controlli = {k: v for k, v in self.controlli.items()
                          if k.split("|")[0] in finestre_valide}

    def ultimo_controllo(self, finestra: str, partenza: str, dest: str) -> str:
        return self.controlli.get(f"{finestra}|{partenza}|{dest}", "")

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
            json.dump({"offerte": self.voci, "controlli_google": self.controlli,
                       "mostrate": self.mostrate},
                      fh, ensure_ascii=False, indent=1, sort_keys=True)

    def segna_mostrate(self, voci: list[dict], oggi: str) -> None:
        for v in voci:
            self.mostrate[_norm(v["citta"])] = {"data": oggi, "costo": round(costo(v))}

    def offerte(self) -> list[dict]:
        return list(self.voci.values())


def costo(v: dict) -> float:
    """Costo reale per la famiglia: voli + extra auto se si parte da un altro aeroporto."""
    return v["prezzo_persona"] * v["persone"] + v.get("costo_extra", 0)


def filtra_convenienti(voci: list[dict], risparmio_minimo: float) -> list[dict]:
    """Tiene i voli da aeroporti alternativi solo se valgono il viaggio in auto."""
    base: dict[tuple, float] = {}
    for v in voci:
        if v.get("partenza", "BRI") == "BRI":
            k = (v["finestra"], _norm(v["citta"]))
            base[k] = min(base.get(k, float("inf")), costo(v))
    out = []
    for v in voci:
        if v.get("partenza", "BRI") == "BRI":
            out.append(v)
            continue
        riferimento = base.get((v["finestra"], _norm(v["citta"])))
        if riferimento is None or costo(v) <= riferimento - risparmio_minimo:
            v = dict(v, risparmio=None if riferimento is None else round(riferimento - costo(v)))
            out.append(v)
    return out


def classifica(voci: list[dict], top: int, una_per_citta: bool) -> list[dict]:
    # per ogni (finestra, città) tengo l'opzione più economica
    migliori: dict[tuple, dict] = {}
    for v in voci:
        k = (v["finestra"], _norm(v["citta"]))
        if k not in migliori or costo(v) < costo(migliori[k]):
            migliori[k] = v
    ordinate = sorted(migliori.values(), key=lambda v: (costo(v), v["finestra"]))
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


def classifica_etichettata(voci: list[dict], top: int, mostrate: dict) -> list[dict]:
    """Classifica pura per prezzo (niente viene nascosto), con un'etichetta per
    riconoscere le città mai proposte e quelle scese di prezzo."""
    out = []
    for v in classifica(voci, top, True):
        m = mostrate.get(_norm(v["citta"]))
        if not m:
            v = dict(v, mai_proposta=True)
        elif costo(v) < m["costo"] - 1:
            v = dict(v, calo_da_proposta=round(m["costo"] - costo(v)))
        else:
            v = dict(v, gia_proposta=True)
        out.append(v)
    return out


def migliori_ponti(voci: list[dict], n: int) -> list[dict]:
    """Il prezzo migliore per ciascun ponte/vacanza, una riga per finestra."""
    per_finestra: dict[str, dict] = {}
    for v in voci:
        if v["tipo"] == "weekend":
            continue
        f = v["finestra"]
        if f not in per_finestra or costo(v) < costo(per_finestra[f]):
            per_finestra[f] = v
    return sorted(per_finestra.values(), key=lambda v: v["finestra"])[:n]


def finestra_da_chiave(chiave: str, tipo: str) -> Finestra:
    a, r = chiave.split("_")
    return Finestra(date.fromisoformat(a), date.fromisoformat(r), True, tipo)

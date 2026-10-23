"""Calcola le finestre di viaggio: weekend, ponti e spezzoni delle vacanze lunghe.

Regola di base: la famiglia è libera quando è libera la moglie (insegnante).
Il marito e i ragazzi si adattano. Un viaggio parte la sera del giorno
lavorativo che precede il blocco libero (dopo l'orario impostato) e rientra
la sera dell'ultimo giorno libero.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import yaml

GIORNI = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]
MESI = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]


def pasqua(anno: int) -> date:
    """Domenica di Pasqua (algoritmo di Gauss/Meeus)."""
    a = anno % 19
    b, c = divmod(anno, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mese = (h + l - 7 * m + 114) // 31
    giorno = (h + l - 7 * m + 114) % 31 + 1
    return date(anno, mese, giorno)


def festivi_nazionali(anno: int) -> set[date]:
    fissi = [(1, 1), (1, 6), (4, 25), (5, 1), (6, 2), (8, 15), (11, 1), (12, 8), (12, 25), (12, 26)]
    giorni = {date(anno, m, g) for m, g in fissi}
    if anno >= 2026:  # San Francesco, festa nazionale dal 2026
        giorni.add(date(anno, 10, 4))
    giorni.add(pasqua(anno) + timedelta(days=1))  # Pasquetta
    return giorni


def _espandi(voci: list | None) -> set[date]:
    out: set[date] = set()
    for v in voci or []:
        s = str(v).strip()
        if ".." in s:
            a, b = (date.fromisoformat(x.strip()) for x in s.split(".."))
            while a <= b:
                out.add(a)
                a += timedelta(days=1)
        elif s:
            out.add(date.fromisoformat(s))
    return out


@dataclass(frozen=True)
class Finestra:
    andata: date
    ritorno: date
    vincolo_orario_andata: bool  # True = si parte dopo l'orario impostato
    tipo: str                    # weekend | ponte | vacanza

    @property
    def notti(self) -> int:
        return (self.ritorno - self.andata).days

    @property
    def chiave(self) -> str:
        return f"{self.andata.isoformat()}_{self.ritorno.isoformat()}"

    def etichetta(self) -> str:
        def f(d: date) -> str:
            return f"{GIORNI[d.weekday()]} {d.day} {MESI[d.month - 1]}"
        return f"{f(self.andata)} → {f(self.ritorno)} ({self.notti} notti)"


class Calendario:
    def __init__(self, percorso_giorni_liberi: str | None = None, dati: dict | None = None):
        if dati is None:
            with open(percorso_giorni_liberi, encoding="utf-8") as fh:
                dati = yaml.safe_load(fh) or {}
        self.extra = _espandi(dati.get("scuola_puglia")) | _espandi(dati.get("extra_moglie"))
        self.non_liberi = _espandi(dati.get("non_liberi"))
        self._festivi: dict[int, set[date]] = {}

    def festivo(self, d: date) -> bool:
        if d.year not in self._festivi:
            self._festivi[d.year] = festivi_nazionali(d.year)
        return d in self._festivi[d.year]

    def libero(self, d: date) -> bool:
        if d in self.non_liberi:
            return False
        return d.weekday() >= 5 or self.festivo(d) or d in self.extra

    def blocchi_liberi(self, dal: date, al: date) -> list[tuple[date, date]]:
        blocchi, inizio = [], None
        d = dal
        while d <= al + timedelta(days=30):  # chiude i blocchi a cavallo della fine
            if self.libero(d):
                inizio = inizio or d
            else:
                if inizio:
                    blocchi.append((inizio, d - timedelta(days=1)))
                    inizio = None
                if d > al:
                    break
            d += timedelta(days=1)
        return [(a, b) for a, b in blocchi if a <= al]

    def finestre(self, oggi: date, settimane: int, preavviso: int, notti_max: int) -> list[Finestra]:
        primo = oggi + timedelta(days=preavviso)
        ultimo = oggi + timedelta(weeks=settimane)
        risultato: list[Finestra] = []
        for inizio, fine in self.blocchi_liberi(primo - timedelta(days=7), ultimo):
            giorni = (fine - inizio).days + 1
            if giorni < 2:
                continue
            vigilia = inizio - timedelta(days=1)  # giorno lavorativo: si parte la sera
            if giorni <= notti_max:
                tipo = "weekend" if (giorni == 2 and inizio.weekday() == 5) else "ponte"
                candidati = [Finestra(vigilia, fine, True, tipo)]
            else:
                candidati = []
                partenza = vigilia
                while partenza + timedelta(days=notti_max) <= fine:
                    candidati.append(Finestra(partenza, partenza + timedelta(days=notti_max),
                                              partenza == vigilia, "vacanza"))
                    partenza += timedelta(days=2)
                ultima = Finestra(fine - timedelta(days=notti_max), fine, False, "vacanza")
                if ultima not in candidati:
                    candidati.append(ultima)
            risultato += [f for f in candidati if primo <= f.andata <= ultimo]
        return sorted(set(risultato), key=lambda f: (f.andata, f.ritorno))

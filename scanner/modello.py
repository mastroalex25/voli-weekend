from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Offerta:
    fonte: str              # google | ryanair | wizzair
    finestra: str           # chiave "AAAA-MM-GG_AAAA-MM-GG"
    tipo: str               # weekend | ponte | vacanza
    destinazione: str       # codice aeroporto
    citta: str
    paese: str
    prezzo_persona: float   # andata+ritorno, EUR
    persone: int
    compagnie: list[str] = field(default_factory=list)
    scali: int = 0
    andata: str = ""        # "Ven 18:05 → 20:15"
    ritorno: str = ""
    link: str = ""
    nota: str = ""
    aggiornato: str = ""    # data ISO dell'ultima verifica

    @property
    def prezzo_totale(self) -> float:
        return round(self.prezzo_persona * self.persone, 2)

    @property
    def chiave(self) -> str:
        return f"{self.finestra}|{self.destinazione}|{self.fonte}"

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Offerta":
        return Offerta(**{k: v for k, v in d.items() if k in Offerta.__dataclass_fields__})

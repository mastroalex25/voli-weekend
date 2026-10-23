"""Composizione e invio del messaggio Telegram (HTML)."""
from __future__ import annotations

import html
from datetime import date

import requests

from .classifica import finestra_da_chiave

MEDAGLIE = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
FONTI = {"google": "Google Flights", "ryanair": "Ryanair.com", "wizzair": "Wizzair.com"}


def _euro(x: float) -> str:
    return f"{x:,.0f} €".replace(",", ".")


def _tendenza(v: dict) -> str:
    prec = v.get("prezzo_prec")
    if not prec:
        return "🆕 nuovo"
    diff = (v["prezzo_persona"] - prec) * v["persone"]
    if abs(diff) < 1:
        return "= stabile"
    return f"🔻 {_euro(-diff)} da ieri" if diff < 0 else f"🔺 {_euro(diff)} da ieri"


def _riga(v: dict, simbolo: str) -> str:
    e = html.escape
    f = finestra_da_chiave(v["finestra"], v["tipo"])
    tot = v["prezzo_persona"] * v["persone"]
    extra = v.get("costo_extra", 0)
    scali = "diretto" if v.get("scali", 0) == 0 else f"{v['scali']} scalo"
    minimo = v.get("minimo")
    record = " · ⭐ minimo visto" if v.get("prezzo_prec") and minimo and v["prezzo_persona"] <= minimo else ""
    righe = [
        f"{simbolo} <b>{e(v['citta'])}</b> ({e(v['paese'])}) — <b>{_euro(tot)}</b> "
        f"<i>({_euro(v['prezzo_persona'])}/pers.)</i>",
        f"📅 {f.etichetta()} · {v['tipo']}",
        f"🛫 {e(v.get('andata',''))}   🛬 {e(v.get('ritorno',''))}",
        f"{e(', '.join(v.get('compagnie', [])))} · {scali} · {_tendenza(v)}{record}",
    ]
    if v.get("partenza", "BRI") != "BRI":
        nomi = {"BDS": "Brindisi", "NAP": "Napoli"}
        risp = v.get("risparmio")
        risp_txt = f" · risparmi {_euro(risp)} rispetto a Bari" if risp else " · da Bari non c'è"
        righe.insert(1, f"🚗 <b>Parte da {nomi.get(v['partenza'], v['partenza'])}</b>: "
                        f"con auto e parcheggio ({_euro(extra)}) = <b>{_euro(tot + extra)}</b>{risp_txt}")
    if v.get("nota"):
        righe.append(f"<i>{e(v['nota'])}</i>")
    righe.append(f'<a href="{e(v["link"], quote=True)}">Verifica su {FONTI.get(v["fonte"], v["fonte"])}</a>')
    return "\n".join(righe)


def componi(top: list[dict], ponti: list[dict], stato: dict, oggi: date, cfg: dict) -> str:
    bag = "trolley in cabina" if cfg["bagaglio"]["trolley_cabina"] else "solo borsa piccola"
    persone = int(cfg["passeggeri"]["adulti"]) + int(cfg["passeggeri"]["ragazzi_12_15"])
    parti = [
        f"✈️ <b>Voli da Bari (+ Brindisi/Napoli se convengono) — {oggi.strftime('%d/%m/%Y')}</b>",
        f"<i>Totale a/r per {persone} persone, {bag}, max {cfg['ricerca']['max_scali']} scalo</i>",
        "",
    ]
    if not top:
        parti.append("Nessun volo trovato oggi con i filtri impostati.")
    for i, v in enumerate(top):
        parti += [_riga(v, MEDAGLIE[i]), ""]
    if ponti:
        parti += ["🌉 <b>Migliori ponti e vacanze</b>"]
        for v in ponti:
            f = finestra_da_chiave(v["finestra"], v["tipo"])
            da = "" if v.get("partenza", "BRI") == "BRI" else f" (da {v['partenza']}, auto inclusa)"
            parti.append(f"• {f.etichetta()}: <b>{html.escape(v['citta'])}</b> "
                         f"{_euro(v['prezzo_persona'] * v['persone'] + v.get('costo_extra', 0))}{da} "
                         f'(<a href="{html.escape(v["link"], quote=True)}">link</a>)')
        parti.append("")
    parti.append(f"<i>Controllato oggi: {stato['riassunto']}</i>")
    if stato.get("avvisi"):
        parti.append("⚠️ " + html.escape(" | ".join(stato["avvisi"]))[:600])
    testo = "\n".join(parti)
    return testo if len(testo) <= 4000 else testo[:3990] + "…"


def invia(testo: str, token: str, chat_id: str) -> None:
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": testo, "parse_mode": "HTML",
              "disable_web_page_preview": True},
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(f"Telegram ha risposto {r.status_code}: {r.text[:300]}")

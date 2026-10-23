# ✈️ Scanner voli weekend da Bari

Ogni mattina cerca i voli andata/ritorno da Bari per **4 persone**:
- **weekend**: partenza venerdì dopo le 16:00, rientro domenica sera;
- **ponti e vacanze**: calcolati da festivi nazionali, calendario scolastico Puglia e giorni extra del calendario di tua moglie.

Manda su **Telegram** la **top 5**, una città per volta, con tendenza del prezzo rispetto a ieri. Aggiunge in fondo i migliori ponti.

**Fonti**
- Google Flights, tutte le compagnie, scali compresi.
- Tariffe pubbliche Ryanair.
- Tariffe pubbliche Wizz Air.

Gira gratis su **GitHub Actions**, senza bisogno del PC acceso.

---

## Attivazione (circa 15 minuti, una volta sola)

### 1. Crea il bot Telegram
1. Su Telegram cerca **@BotFather** → `/newbot` → scegli un nome, per esempio *Voli Mastromauro*, e uno username che finisce in `bot`.
2. BotFather ti dà un **token** del tipo `123456:ABC-...`. Tienilo da parte, è una password.
3. Apri il tuo nuovo bot e premi **Avvia**, oppure scrivigli "ciao".
4. Apri nel browser `https://api.telegram.org/bot<TOKEN>/getUpdates`, sostituendo il tuo token.
5. Cerca `"chat":{"id":123456789` e annota quel numero: è il **chat id**.
   - Vuoi ricevere i messaggi anche su un gruppo di famiglia? Aggiungi il bot al gruppo, scrivi un messaggio e rifai il punto 4. L'id del gruppo inizia con `-`.

### 2. Crea il repository su GitHub
1. Vai su https://github.com/new, con l'account **mastroalex25**.
2. Nome: `voli-weekend`, visibilità **Private**, nessun README.
3. Carica i file di questa cartella (*Add file → Upload files*), oppure chiedi a Claude di caricarli.

### 3. Inserisci i segreti
Nel repository: **Settings → Secrets and variables → Actions → New repository secret**
- `TELEGRAM_BOT_TOKEN` = il token del punto 1
- `TELEGRAM_CHAT_ID` = il chat id del punto 1

### 4. Prova
1. Apri la scheda **Actions** → *Scanner voli weekend* → **Run workflow**.
2. Spunta "Usa dati di prova" e avvialo: deve arrivarti un messaggio Telegram con dati finti.
3. Rilancialo **senza** la spunta: questa è la prima ricerca vera, dura circa 15-25 minuti.

Da qui in poi parte da solo ogni giorno alle 7:17 in estate, alle 6:17 in inverno.

---

## Cose che puoi cambiare (dal sito GitHub, icona ✏️)

| File | Cosa |
|---|---|
| `config.yaml` | orari, bagaglio, scali, settimane da guardare, destinazioni, paesi esclusi |
| `giorni_liberi.yaml` | calendario di tua moglie (`extra_moglie`) e giorni in cui non è libera (`non_liberi`) |

## Da sapere
- **Prezzi Google** = prezzo a persona × 4 (stima). Ryanair e Wizz: tariffa base a persona × 4.
  - Il prezzo finale per 4 può salire di qualche euro se restano pochi posti a quella tariffa. Il link "Verifica" serve a questo.
- **Bagaglio**: prezzi con la sola borsa piccola sotto il sedile.
  - Se vi serve il trolley da 10 kg, metti `trolley_cabina: true`.
  - Google lo stima; sulle tariffe Ryanair e Wizz va aggiunto a parte, circa 20-40 € a tratta a persona.
- **Google** ha un limite di ricerche al giorno (`google_max_ricerche_giorno`). Le coppie data-destinazione vengono controllate a rotazione, quindi in 2-3 giorni il quadro è completo.
- Ryanair, Wizz e Google non offrono API ufficiali gratuite. Se una fonte cambia formato, il messaggio Telegram mostra un ⚠️ con la fonte in errore e il programma continua con le altre.
- Lo storico dei prezzi è salvato in `data/prezzi.json` (commit giornaliero automatico).

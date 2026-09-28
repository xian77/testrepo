# JobPilot

Assistente personale per la ricerca di lavoro. Funziona da riga di comando:

1. **Monitora** le offerte da API pubbliche (Remotive, Arbeitnow, board Greenhouse e Lever delle aziende che ti interessano, qualsiasi feed RSS).
2. **Valuta la compatibilità** con il tuo profilo: filtri obbligatori (parole chiave, esclusioni, sede/remoto, RAL) più un punteggio 0-100; se abiliti Claude, anche un'analisi del CV rispetto all'annuncio.
3. **Si candida**: se l'annuncio indica un indirizzo email, invia lettera di presentazione e CV via SMTP. Se invece serve un form sul sito, prepara in `packets/` un pacchetto con link, lettera e risposte standard da incollare.
4. **Monitora la posta** (IMAP): collega ogni risposta alla candidatura giusta e la classifica (conferma di ricezione, richiesta di informazioni, test tecnico, colloquio, rifiuto, offerta). Poi aggiorna lo stato.
5. **Gestisce le prime fasi**: prepara bozze di risposta (per esempio agli inviti a colloquio, con le tue disponibilità), che puoi inviare con un comando o in automatico per le categorie che scegli. Invia anche un solo sollecito dopo N giorni senza risposta.

## Installazione

```bash
pip install -e .            # oppure: pip install -r requirements.txt
pip install -e ".[ai]"      # se vuoi usare Claude
jobpilot init               # crea config.yaml
```

Modifica `config.yaml`: profilo, competenze, criteri, sorgenti e casella email. Metti nella stessa cartella `cv.pdf` (allegato) e, se vuoi, `cv.txt` (testo del CV per l'analisi con Claude).

Le password vanno nelle variabili d'ambiente, non nel file:

```bash
export JOBPILOT_EMAIL_PASSWORD="..."   # Gmail: crea una "password per le app"
export ANTHROPIC_API_KEY="..."         # solo con llm.enabled: true
```

## Uso

```bash
jobpilot scan                 # cerca e valuta nuove offerte
jobpilot list matched         # offerte compatibili in attesa di decisione
jobpilot show 3fa9c1          # dettagli, motivazioni del punteggio, cronologia
jobpilot letter 3fa9c1        # genera o rigenera la lettera (--file per usare la tua)
jobpilot approve 3fa9c1 7b2e  # approva
jobpilot skip 91cc02          # scarta
jobpilot --dry-run apply      # prova senza inviare nulla
jobpilot apply                # invia le candidature approvate
jobpilot mail                 # legge la posta e aggiorna gli stati
jobpilot replies              # bozze di risposta da rivedere
jobpilot send-reply "<message-id>" [--file risposta.txt]
jobpilot followups [--send]   # solleciti
jobpilot status               # riepilogo
jobpilot run --interval 60    # ciclo completo ogni 60 minuti
```

Per l'esecuzione pianificata puoi usare cron: `0 * * * * cd ~/jobpilot && jobpilot run --once`.

### Modalità

- `apply.mode: review` (predefinita): JobPilot trova, valuta e prepara, ma sei tu ad approvare ogni candidatura.
- `apply.mode: auto`: approva e invia da solo le offerte con punteggio ≥ `auto_min_score`, entro `max_per_day` candidature al giorno, e manda i solleciti. Le risposte alle email partono in automatico solo per le categorie elencate in `email.auto_reply_categories`.

Ti consiglio di partire in `review` con `--dry-run` e di passare ad `auto` solo quando i punteggi ti sembrano affidabili.

## Stati di una candidatura

`matched` → `approved` → `applied` / `manual_pending` → `acknowledged` → `info_requested` / `assessment` → `interview` → `offer` o `rejected`

Un'email non fa mai tornare indietro lo stato: una conferma di ricezione che arriva dopo un invito a colloquio non lo sovrascrive. `set-status` permette correzioni manuali.

## Limiti e scelte di progetto

- **LinkedIn, Indeed e simili non vengono automatizzati.** I loro termini d'uso vietano lo scraping e i bot, e un account segnalato è un danno per chi cerca lavoro. Puoi però usare i feed RSS delle ricerche salvate, quando il portale li offre, oppure aggiungere il board Greenhouse o Lever dell'azienda.
- I form di candidatura online (Workday, Greenhouse, ecc.) non vengono compilati da soli: cambiano da azienda ad azienda e spesso hanno captcha. JobPilot prepara il materiale e tu completi l'invio in un minuto.
- Claude non inventa esperienze nelle lettere e non accetta offerte né condivide dati sensibili nelle risposte. Il contenuto delle email viene trattato come dato, non come istruzione.
- Senza Claude tutto funziona lo stesso, con regole (parole chiave in italiano e inglese) e template.

## Test

```bash
pip install pytest && pytest
```

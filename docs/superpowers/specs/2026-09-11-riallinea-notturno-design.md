# Riallineamento notturno documentazione ↔ codice, con pi locale

**Data:** 2026-09-11 · **Stato:** design approvato dal proprietario, spec da rivedere · **Esecutore previsto:** pi (implementazione), sonnet (revisione)

## 1. Perché

La retrospettiva delle sessioni (24 agosto → 11 settembre, `docs/superpowers/retrospettive/2026-09-10-sessioni-agosto-settembre.md`) e il proprietario convergono su un guasto: le ricerche che precedono spec e piani poggiano su documentazione in parte falsa, e ciò che si scopre in esecuzione non torna nei documenti.

Lo strumento contro la deriva esiste già, `/riallinea` (`.claude/skills/riallinea/SKILL.md`, `scripts/riallinea.py`), ma nessuno lo lancia:
- due rapporti in quattro settimane (`docs/superpowers/allineamento/2026-08-14.md`, `2026-09-10.md`), contro l'obiettivo «trovato entro una settimana» della sua spec (`docs/superpowers/specs/2026-08-14-agente-riallineamento-design.md:37`);
- nessun cron, nessuna GitHub Action, e il `Jenkinsfile` non ha uno stadio documentale.

La raccolta costa poco (`--da HEAD~20`: 3,5 s, 165 simboli, 238 citazioni): il costo vero è il modello che verifica le citazioni.

## 2. Decisioni del proprietario (2026-09-11)

| Domanda | Decisione |
|---|---|
| Quale approccio | Il minimo: solo `/riallinea` notturno. Intestazioni con prova, indice generato, memoria snellita e controllo delle premesse sono **rinviati**. |
| Chi esegue | **pi locale su WSL** (Qwen su gx10): costo token zero, PC e gx10 accesi di notte. |
| Quanto può cambiare da solo | **Branch + PR**: committa solo ciò che la lista chiusa della skill ammette; tutto il resto va nel rapporto. Niente arriva a `main` senza revisione. |
| Design in sei punti | Approvato. Orario 02:17. Un giro fallito lascia un log in WSL **e** un commento su una issue GitHub dedicata. |

## 3. Perimetro

**Dentro:**
- ogni notte, `/riallinea` in modo `diff` sui commit arrivati su `origin/main` dall'ultimo giro notturno riuscito;
- PR con le correzioni dimostrabili e il rapporto.

**Fuori:**
- **I branch di lavoro.** I lotti lanciano `/riallinea` a fine lotto, come il 3B (`a976266`).
- **Lo sweep `--completo`.** È parziale per costruzione: tetto di 300 al Livello 3 su ~5.722 citazioni.
- **La memoria.** La skill la legge per i riferimenti morti e non la modifica mai.
- **`main` locale.** È 62 commit avanti a `origin/main` (merge del lotto 1 non pubblicato). Pubblicare è una decisione del proprietario, e un branch notturno basato sul `main` locale pubblicherebbe quei commit dentro la PR.
- **Le proposte degli approcci 1 e 2.**

## 4. Architettura

Tre pezzi, ciascuno sostituibile senza toccare gli altri:

```
Pianificatore attività di Windows (02:17 ogni notte)
  └─ wsl.exe -d Ubuntu -u peter -- ~/riallinea-notte/bin/riallinea_notte.sh
       └─ runner bash: precondizioni, worktree fresco, stato, controlli, push, PR, notifica
            └─ pi -p --provider gx10 --skill <worktree>/.claude/skills/riallinea  (verifica e commit locali)
```

- **Perché il Pianificatore di Windows e non cron in WSL.** Con `systemd=true` cron è attivo, ma WSL si spegne quando resta inattivo (nessun `vmIdleTimeout` in `.wslconfig`): di notte un cron interno non partirebbe. `wsl.exe` lanciato da Windows avvia WSL.
- **Perché il runner è installato fuori dal repo** (`~/riallinea-notte/bin/`). L'albero principale cambia branch, e un branch senza lo script farebbe fallire il giro. Il sorgente versionato resta `scripts/riallinea_notte.sh`; `scripts/riallinea_notte.sh --installa` si copia in `~/riallinea-notte/bin/` e stampa, senza eseguirlo, il comando `schtasks` da lanciare.
- **Perché il runner fa push e PR, non pi.** I controlli che decidono se pubblicare (§5, passo 7) non si delegano al modello che ha prodotto le modifiche.

## 5. Il giro notturno, passo per passo

Cartella di lavoro `~/riallinea-notte/`: `bin/`, `stato/STATO.json`, `log/<AAAA-MM-GG>.log`, `wt/<AAAA-MM-GG>/`. Ogni passo scrive nel log una riga con ora, passo ed esito.

1. **Lock.** `flock -n ~/riallinea-notte/lock`: se un giro è ancora in corso, esce con codice 0 e una riga di log. Non è un fallimento.
2. **Precondizioni.** Esistenza di `git`, `gh` e `pi`. Poi `gh auth status`. Poi gx10 raggiungibile **senza mandare un prompt**, con `pi auth check --provider gx10 --json --no-refresh` e, se non basta a provare la raggiungibilità, una `GET` del modello con Bearer passato da stdin, mai in argv. Una precondizione mancante è un fallimento (§7).
3. **Intervallo.**
   - `git -C ~/DEV/budget fetch origin main` (sola lettura sull'albero principale: aggiorna i ref remoti, non tocca il suo working tree).
   - Da `stato/STATO.json` si legge `ultimo_sha`. **Primo giro:** il file non esiste, e l'installazione lo inizializza con l'`ultimo_sha` del `docs/superpowers/allineamento/STATO.json` di `origin/main` in quel momento. Il primo giro recupera così l'arretrato dal 14 agosto, una volta sola.
   - Se `ultimo_sha..origin/main` è vuoto: riga «niente di nuovo», stato invariato, uscita 0.
4. **Worktree fresco.** `git -C ~/DEV/budget worktree add --detach ~/riallinea-notte/wt/<data> origin/main`, poi `git switch -c riallinea/notte-<data>` dentro il worktree. Mai l'albero principale. Il worktree di un giro precedente fallito si rimuove a questo punto, non prima.
5. **Raccolta.** Nel worktree: `python3 scripts/riallinea.py --da <ultimo_sha> --a origin/main --stato ~/riallinea-notte/stato/STATO.json > <wt>/.riallinea-notte.json`. Zero citazioni: riga di log, stato avanzato a `origin/main`, worktree rimosso, uscita 0.
6. **pi.** `timeout 2h pi -p --provider gx10 --no-session --skill <wt>/.claude/skills/riallinea` con il prompt di §6, dalla radice del worktree. Codice di uscita diverso da 0, o timeout: fallimento.
7. **Controlli prima di pubblicare.** Tutti obbligatori; il primo che fallisce ferma il giro.
   - worktree pulito: `git status --porcelain` vuoto;
   - `git diff --name-only origin/main..HEAD` contiene solo `CLAUDE.md` e percorsi sotto `docs/`;
   - i messaggi di commit sono esattamente `docs(allineamento): correzioni dimostrabili` e/o `docs(allineamento): rapporto <data>`;
   - esiste `docs/superpowers/allineamento/<data>-notte.md`;
   - `docs/superpowers/allineamento/STATO.json` **non** è modificato: lo stato notturno vive fuori dal repo.
8. **Decisione di pubblicare.**
   - Se il rapporto non ha correzioni e ha zero voci «Da decidere», non si apre nessuna PR: il rapporto resta nel log, lo stato avanza.
   - Altrimenti: `git push -u origin riallinea/notte-<data>`, poi `gh pr create --base main --head riallinea/notte-<data>`. Titolo «Riallineamento notturno <data>: N correzioni, M da decidere». Corpo: i conteggi e le voci «Da decidere» del rapporto.
9. **Stato.** Solo dopo il passo 8 riuscito: `python3 scripts/riallinea.py --registra <sha di origin/main usato> --modo diff --data <data> --stato ~/riallinea-notte/stato/STATO.json`.
10. **Pulizia.** Worktree rimosso (`git worktree remove`), branch locale cancellato solo se pubblicato, log più vecchi di 30 giorni cancellati.

## 6. Il prompt di pi

Il prompt è un file versionato, `scripts/riallinea_notte.prompt.md`, passato come messaggio. Dice:
- **Segui la skill caricata alla lettera**, con tre deroghe scritte:
  1. il rapporto si chiama `docs/superpowers/allineamento/<data>-notte.md`;
  2. i commit vanno sul branch corrente, non su `main`, e **non si fa push**;
  3. **non si esegue `--registra`**: lo fa il runner.
- **Le citazioni** sono in `.riallinea-notte.json`, prodotto dal runner: non si rilancia la raccolta.
- **Si verificano tutte**, come la skill chiede in modo `diff`. Se il tempo o il contesto non bastano, il rapporto lo dichiara in testa, con le citazioni non guardate: mai un campione silenzioso.
- **Vincoli invariati della skill:**
  - la lista chiusa;
  - piani e spec datati mai riscritti, solo annotati in coda;
  - `git add` per nome, mai `-A` o `.`;
  - messaggio di commit da file;
  - la memoria non si tocca.
- **Mai file fuori da `docs/` e `CLAUDE.md`.** Il runner lo controlla e scarta il giro.

## 7. Fallimenti e notifica

Un fallimento è qualunque uscita non 0 dei passi 2-9, un timeout, o un controllo del passo 7 non superato.

- **Log:** `~/riallinea-notte/log/<data>.log`, completo.
- **Issue:** un commento sulla issue dedicata «Riallineamento notturno: giri falliti» (label `documentation`), creata una volta dall'installazione, con data, passo fallito e codice d'uscita. Niente righe del log nel commento: potrebbero contenere testo letto dal repo o dall'ambiente.
- **Stato:** non avanza. Il giro dopo copre anche l'intervallo perso.
- **Worktree:** resta al suo posto fino al giro successivo, per l'ispezione.

Un PC o un gx10 spenti non producono un fallimento visibile, perché il giro non parte o si ferma alle precondizioni. Il segnale è l'assenza di PR e di log per quella data, e il giro dopo recupera l'intervallo.

## 8. Rischi e controlli

| Rischio | Controllo |
|---|---|
| pi modifica codice, o scrive fuori dalla lista chiusa | Il passo 7 rifiuta file fuori da `docs/`/`CLAUDE.md`; la lista chiusa la giudica la revisione della PR, non il runner |
| pi campiona senza dirlo | Obbligo del prompt di dichiarare le citazioni non guardate; la revisione confronta i conteggi del rapporto con `.riallinea-notte.json` |
| Una push su un branch fa ripartire Jenkins | Il job «Budget» builda da `main` (memoria `staging-deployment-topology`): una push su `riallinea/notte-*` non dovrebbe rilasciare nulla. **Da verificare al primo giro reale**, guardando il job dopo la push |
| `main` non è protetto su GitHub (API: «Branch not protected») | Oggi la regola «niente su `main` senza PR» la garantisce solo il runner. La protezione di `main` resta una decisione del proprietario, fuori da questa spec |
| gx10 conteso con le pi diurne | Orario notturno; `flock` impedisce due giri sovrapposti |
| Chiavi | Nessuna chiave nel runner: pi le risolve da `models.json` come oggi; il Bearer di un eventuale controllo HTTP passa da stdin |

## 9. Verifica dell'implementazione

- **`riallinea_notte.sh --prova --da <sha> --a <sha>`**: esegue i passi 1-7 su un intervallo dato e si ferma prima del passo 8 (niente push, PR, issue né stato).
  - Accettazione: un giro di prova su un intervallo reale di `origin/main` con almeno una citazione produce `<data>-notte.md` e supera il passo 7.
  - Controllo negativo: un file fuori da `docs/`, creato apposta nel worktree di prova, fa fallire il passo 7.
- **`--installa`**: copia il runner, inizializza lo stato e crea la issue di notifica se manca. La creazione del task di Windows (`schtasks`) la esegue il proprietario, o il coordinatore con la sua approvazione esplicita.
- **Primo giro reale:** il giro notturno successivo all'installazione, sull'arretrato dal 14 agosto. Il coordinatore legge log, PR e job Jenkins la mattina dopo.

## 10. Consegna

Un piano con i task: runner con `--prova` e `--installa`, prompt, installazione, giro di prova. Implementazione a pi, revisione sonnet per task (decisione del proprietario sui modelli, 2026-09-11). Nessuna modifica a `scripts/riallinea.py` né alla skill: se servisse, è un rilievo da portare al proprietario.

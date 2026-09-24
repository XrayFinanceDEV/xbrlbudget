# Report infrannuale (PDF)

Il documento che la tab Stampa consegna con «Scarica PDF». Riproduce il layout del report preparato dal committente
(`INFRANNUALE RIVISITATO.pdf`, fuori da git) con i numeri del motore, per qualunque scenario infrannuale. Sostituisce
nell'interfaccia il report intermedio Typst, che resta nel codice (`POST …/infrannuale/report/pdf`).

**Dove sta:**
- `backend/app/renderers/infrannuale/`: ReportLab + matplotlib, sul pacchetto `business_plan` che riusa senza
  modificarlo.
- Servizio `services/infrannuale_pdf_service.py`.
- Rotta `POST /companies/{id}/scenarios/{sid}/infrannuale/pdf`, corpo `{}`. Risponde 400 per uno scenario non
  infrannuale o senza i bilanci del periodo, 404 per uno scenario di un altro utente.
- Frontend: `downloadInfrannualePdf`, `hooks/use-infrannuale-download.ts`, `components/pratica/StampaContent.tsx`.

**Da dove vengono i numeri:** solo da `assemble_intermedio` (il modello del vecchio report intermedio), attraverso
`data.from_intermedio`.
- Gli indicatori (DSCR, PFN, PFN/EBITDA, margini, ROI/ROE/ROS, oneri) sono quelli di `crisi_infrannuale` per periodo;
  per il 6M sono su base annualizzata.
- Capitale circolante commerciale = crediti verso clienti (entro e oltre) + rimanenze − fornitori, dai prospetti.
- Colonne: C (consuntivo), 6M, Ann. (solo nel CE, e solo se il periodo è parziale), F (se la proiezione esiste).
  Senza proiezione le colonne F spariscono e la copertina scrive «forecast non ancora generato».

**Esito e colori:**
- Il punteggio 0–1 del motore della crisi dà l'esito: sotto 0,33 «oltre soglia», sotto 0,66 «attenzione», altrimenti
  «in soglia». La soglia 0,66 è ricavata dal riferimento.
- La classe si colora per codice: A teal, B e C arancio, D rosso.

**Testi:** `narrative.py`, regole con soglie in `SOGLIE`, nessuna chiamata AI. Su AMBIENTA i testi coincidono con
quelli del committente, e `tests/test_inf_narrative.py` ne fissa i principali parola per parola.

**Banco di prova:**
- `tests/test_inf_banco.py` confronta le sezioni 2, 4 e 7 con le pagine 4, 6 e 9 del riferimento: tolleranze
  8 / 3 / 2 pt, scarto misurato 0,2 pt. Controlla anche le cifre, perché il fixture è AMBIENTA (575/17) letta dal DB.
- `tests/test_inf_document.py` rende tutti gli scenari infrannuali del DB locale.
- `tools/infrannuale/confronta.py` affianca le 13 pagine al riferimento per la verifica con la vision.
- Il PDF del committente va in `tests/.banco-infrannuale/riferimento.pdf` (gitignored); senza, il banco si salta.

**Trappole:**
- Il pacchetto `business_plan` si estende, non si modifica: dopo ogni modifica comune `test_bp_*.py` deve restare
  verde, banco del Business plan compreso.
- La copertina ha altezza fissa: due passate costruiscono l'indice, e se le pagine si spostano `render_infrannuale`
  solleva `IndexShifted`.


**Il Word (.docx):** «Scarica Word» chiama `POST …/infrannuale/docx`, stesso corpo e stessi errori della rotta PDF.
Non è un secondo renderer: `backend/app/renderers/docx_export.py` traduce in `python-docx` gli stessi flowable che le
sezioni danno al PDF, quindi un testo corretto nel codice cambia PDF e Word insieme. Testi e tabelle sono
modificabili, i grafici sono i PNG del PDF (`layout.chart` li conserva in `Image.png`), copertina e intestazioni
vengono da `cover_lines` e `page_texts`, le stesse funzioni che usa il PDF. L'indice non ha numeri di pagina (in
Word si spostano alla prima correzione). I commenti corretti nel Word restano nel file: l'app non li rilegge.
Trappole:
- un flowable che il traduttore non conosce solleva `TypeError`: una primitiva nuova in `layout.py` va insegnata
  anche a `docx_export.translate`, o il Word di quella sezione si rompe. `tests/test_docx_report.py` confronta ogni
  riga di testo del PDF col Word, su AMBIENTA e sugli scenari fuori dal banco;
- `python-docx` sta in `backend/requirements.txt` di proposito: nel venv arrivava solo con docling, codice morto;
- Word non incorpora Lato: sul PC senza il font usa il suo ripiego, e il documento resta corretto.

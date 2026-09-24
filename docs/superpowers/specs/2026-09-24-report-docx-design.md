# Export Word (.docx) del Business plan e del report infrannuale — design

**Data:** 2026-09-24 · **Branch:** `feat/report-docx` (worktree `../budget-report-docx`, da main 2e8e992)

## 1. Perché

L'utente scarica i due report ReportLab (Business plan su /report, infrannuale nella tab Stampa) e vuole
**correggere qualche commento** prima di consegnarli. Il PDF non si modifica: serve lo stesso documento in Word.

Decisioni del proprietario (2026-09-24):
- i report sono **il Business plan e l'infrannuale**; il dossier Typst resta solo PDF;
- il Word porta **gli stessi contenuti** del PDF — testi e tabelle modificabili, grafici come immagini, stessi
  colori e font — con l'impaginazione di Word, non identica al PDF;
- strada **A**: un traduttore unico dagli elementi del PDF a Word; niente conversione PDF→Word, niente sezioni
  scritte due volte.

## 2. Architettura

Le sezioni dei due report restano le uniche fonti del contenuto: ogni `SectionSpec.build(data, pages)` restituisce
già una lista di flowable ReportLab. Un modulo nuovo, `backend/app/renderers/docx_export.py`, li traduce in un
documento `python-docx`:

```
SECTIONS ──build(data, {})──► flowable ──docx_export.translate──► Document ──save──► bytes
                           └──► ReportLab (invariato) ──► PDF
```

Un testo corretto nel codice cambia PDF e Word insieme; il Word non ha un catalogo suo.

### 2.1 Traduzione degli elementi

| Flowable | In Word |
|---|---|
| `Paragraph` | paragrafo con i run del suo markup: `<b>` grassetto, `<font color>` colore, `<br/>` a capo, entità (`&nbsp;`, `&amp;`) decodificate; dimensione, colore, grassetto e allineamento dallo stile (`ParagraphStyle`) |
| `Table` | tabella Word con le stesse righe e colonne, larghezze proporzionali a `colWidths`; `BACKGROUND` e `TEXTCOLOR` dei `TableStyle` sulle celle; `SPAN` fuse; la prima riga ripetuta a ogni pagina quando è un'intestazione (`repeatRows`) |
| cella: `Paragraph`, stringa, lista di flowable, `Table` annidata | contenuto della cella, con le tabelle annidate come tabelle annidate (riquadri, pannelli, schede) |
| `Image` (grafici matplotlib, 220 dpi) | immagine alla larghezza stampata nel PDF (pt → EMU) |
| `Spacer` | spazio dopo il paragrafo precedente (nessun paragrafo vuoto) |
| `PageBreak` fra sezioni | interruzione di pagina |
| `SectionStart`, `NextPageTemplate`, `KeepTogether`, `CondPageBreak` | contenuto interno tradotto, il resto ignorato |
| `_InUnaPagina` (Allegato A infrannuale) | la tabella a `scale=1.0`: in Word la pagina non va stretta |

Un flowable di tipo **sconosciuto** fa fallire la traduzione con un errore esplicito (`TypeError` col nome del
tipo), mai un silenzio: una sezione che perde un pezzo nel Word è il difetto da non avere. Il test su tutti gli
scenari lo tiene fermo.

### 2.2 Copertina, intestazione, piè di pagina

Le due copertine sono disegnate sul canvas (`draw_cover_band`), non come flowable. I loro testi escono in una
funzione pura per report, `cover_lines(data) -> CoverLines(eyebrow, name, title, subtitle, subtitle2)`, usata sia
da `draw_cover_band` sia dal Word: nessun testo duplicato. Nel Word la copertina è una fascia navy (tabella a una
cella, sfondo navy, testo bianco) seguita dai flowable della sezione `copertina` (numeri chiave e indice).

L'**indice** nel Word non ha numeri di pagina: le sezioni si costruiscono con `pages={}`, e la colonna pagina resta
vuota. In Word le pagine si spostano alla prima correzione; un numero sbagliato è peggio di nessuno.

Intestazione e piè di pagina di Word ripetono quelli del PDF (nome azienda a sinistra, titolo a destra, «BOZZA»
se il Business plan è in bozza; «Riservato e confidenziale · legenda» e il numero di pagina come campo `PAGE`).
La prima pagina ha intestazione diversa (vuota), come nel PDF.

### 2.3 Pagina e caratteri

A4, margini uguali al PDF (`LM`, 55 sopra, 40 sotto). Font `Lato` con ripiego dichiarato sul PC dell'utente:
`python-docx` non incorpora i font, e senza Lato Word usa il suo ripiego; il documento resta corretto.
Colori dalla palette `business_plan.theme`.

## 3. Rotte e servizi

Due rotte gemelle di quelle PDF, stesse dipendenze, stessi errori, stesso corpo:

- `POST /companies/{company_id}/scenarios/{scenario_id}/business-plan/docx` — `BusinessPlanPdfRequest`
  (`document_state`), 404/409 come la PDF;
- `POST /companies/{company_id}/scenarios/{scenario_id}/infrannuale/docx` — `InfrannualePdfRequest`, 400/404 come
  la PDF.

Media type `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, `Content-Disposition` con
nome `.docx` (RFC 5987 + ripiego ASCII), `ETag`, `no-store`. I servizi (`business_plan_pdf_service`,
`infrannuale_pdf_service`) guadagnano una funzione `render_docx` accanto a `render`, che condivide assemblaggio,
cancelli e nomi file (estensione a parte). Nessuna AI, nessuna scrittura sul DB.

`python-docx==1.2.0` entra in `backend/requirements.txt`: oggi è nel venv solo come dipendenza di docling.

## 4. Frontend

- `lib/api.ts`: `downloadBusinessPlanDocx`, `downloadInfrannualeDocx` (stesso schema delle PDF).
- Tab Stampa (`StampaContent.tsx`): pulsante «Scarica Word» accanto a «Scarica PDF».
- /report: «Scarica Word» visibile solo col modello «Business plan» (il dossier Typst non ha il Word).
- Gli hook di download si generalizzano sul formato invece di duplicarsi.

I commenti corretti nel Word restano nel file: l'app non li rilegge.

## 5. Verifica

- **Unità** (`tests/test_docx_export.py`): markup dei paragrafi (grassetto, colore, entità, a capo), tabella con
  sfondi e span, tabella annidata, immagine, flowable sconosciuto → `TypeError`.
- **Completezza** su AMBIENTA (Business plan e infrannuale) e sugli scenari infrannuali D2M (23) e AIC (3, 5):
  ogni testo di paragrafo e di cella del PDF (`fitz`, per pagina) compare nel `.docx` (letto con `python-docx`, testo
  normalizzato negli spazi), a parte numeri di pagina, intestazioni e piè di pagina ripetuti; numero di immagini =
  numero di grafici; il file si riapre con `python-docx` senza errori.
- **Rotte**: 200 con il media type giusto e il file che si apre; 404 altrui; 400/409 come le PDF; 422 su campo in
  più.
- **Frontend**: Vitest sulle due funzioni api e sulla visibilità del pulsante su /report.

## 6. Fuori perimetro

Dossier Typst in Word; rilettura del Word nell'app; impaginazione identica al PDF; incorporare Lato nel `.docx`.

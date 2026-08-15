# Upload tracking — ritrovare il file che ha prodotto il numero sbagliato

Quando un utente segnala «il mio bilancio è sbagliato», l'unica cosa che permette di
riprodurre il difetto è **il file esatto che ha caricato**. Ogni import lo salva su disco e ne
registra l'esito in tabella; tre endpoint di amministrazione lo ritrovano e lo riscaricano.

## 1. Che cosa viene tracciato, e quando

`save_upload` (`backend/app/services/upload_tracker.py`) è chiamato **prima** che il parser
parta, così anche un crash dell'estrattore lascia una riga. Gli endpoint che lo chiamano sono
**quattro**, non tre: `/import/xbrl`, `/import/csv`, `/import/pdf` e `/import/pdf-ocr`
(`backend/app/api/v1/imports.py:148, 295, 431, 576`).

Rispetto ai controlli di proprietà e di limite (`validate_company_owned_by_user`,
`check_company_limit`) l'ordine **non è lo stesso sulle quattro route**:

| route | ordine | `except HTTPException` |
|---|---|---|
| `/import/xbrl` | `save_upload` **poi** i controlli | ri-solleva, **senza** `mark_error` (`:211`) |
| `/import/pdf` | `save_upload` **poi** i controlli | ri-solleva, **senza** `mark_error` (`:483`) |
| `/import/csv` | i controlli **poi** `save_upload` | ri-solleva, senza `mark_error` (`:326`) |
| `/import/pdf-ocr` | i controlli **poi** `save_upload` | marca `error` e ri-solleva (`:671-673`) |

Su `xbrl` e `pdf` una richiesta respinta per proprietà o per limite aziende lascia quindi **il
file su disco e una riga `pending` per sempre**: uno stato `pending` vecchio non significa
«import interrotto a metà», può essere un 403 o un 404. Su `pdf-ocr` la divergenza è
deliberata e commentata sul posto («an unauthorized request must not create a pending upload
row for a company the caller does not own», `imports.py:564-570`): quella route fa partire un
lavoro OCR pesante, e non lo si traccia prima di sapere che il chiamante ha diritto di farlo
partire.

Gli errori del tracker sono **inghiottiti**: `save_upload` restituisce `None` e ogni funzione
riparte da `if record is None: return`. Tracciare non deve mai far fallire un import — e non lo fa
nemmeno quando il disco è pieno.

## 2. Dove finisce il file

```
{UPLOAD_ROOT}/{user_id}/{YYYY-MM}/{YYYYMMDDTHHMMSS}_{8 hex}.{ext}
```

`UPLOAD_ROOT` è una variabile d'ambiente; il default è `data/uploads/` sotto la radice del
progetto (`upload_tracker.py:27`). L'`user_id` è ripulito carattere per carattere (solo
alfanumerici, `-` e `_`, troncato a 64) e diventa `_anonymous` quando manca. Il nome originale
non viene riusato sul filesystem: sta solo nella colonna `filename`.

## 3. La riga in `uploaded_files`

| colonna | note |
|---|---|
| `user_id`, `user_email` | l'email è catturata dal JWT al momento del caricamento, troncata a 255 |
| `company_id` | può essere `NULL` all'inizio; `mark_success` lo riempie se l'import ne ha creata una |
| `filename`, `file_type`, `file_size` | `file_type` è `xbrl` \| `csv` \| `pdf` \| **`pdf_ocr`** — sono **quattro** valori, non tre, e la colonna è `String(10)` |
| `storage_path` | percorso assoluto sul server |
| `status` | `pending` \| `success` \| `error` |
| `error_message` | `TipoEccezione: messaggio`, troncato a 2.000 caratteri |
| `error_traceback` | traceback completo, troncato a 10.000 caratteri |
| `uploaded_at` | UTC |

Il modello è `UploadedFile` in `database/models.py:1090`. Il filtro `file_type=pdf` di
`/admin/uploads` è un'uguaglianza esatta, quindi **non** raccoglie gli import OCR: quelli si
chiedono con `file_type=pdf_ocr`.

Su un database di produzione già esistente la tabella nasce da `migrate_db.py`: `NEW_TABLES`
la crea solo se `sqlite_master` non la conosce già (`migrate_db.py:205-213`), e `MIGRATIONS`
aggiunge `user_email` a chi ha la tabella nella forma precedente.

## 4. Gli endpoint di amministrazione

Tutti e tre sotto `/api/v1`, protetti da `require_admin` (`backend/app/api/v1/admin.py:28`):
l'header `X-Admin-Key` deve corrispondere alla variabile d'ambiente `ADMIN_API_KEY`. Se la
variabile non è impostata la risposta è **503** («Admin API is not configured»), non 403: un
ambiente senza chiave non espone l'API in sola lettura, la spegne.

| endpoint | che cosa restituisce |
|---|---|
| `GET /admin/uploads` | elenco filtrato, più recenti prima |
| `GET /admin/uploads/{id}` | la riga completa, **compreso `error_traceback` e `storage_path`** |
| `GET /admin/uploads/{id}/download` | il file originale (`FileResponse`), `410` se non è più su disco |

I filtri di `GET /admin/uploads` sono sette più il tetto: `user_id` (uguaglianza esatta),
`user_email` (sottostringa case-insensitive), `file_type`, `status`, `company_id`, `since`,
`until`, e `limit` (default 100, massimo 500).

L'elenco **non** porta il traceback né il percorso di storage: quelli stanno solo sul dettaglio
per id. Il flusso tipico è quello scritto nella docstring della route: elenco per utente →
si sceglie l'id che corrisponde alla lamentela → download.

Questi endpoint non sono usati dal frontend nell'iframe. Sono uno strumento da riga di comando
per chi mantiene il servizio.

## 5. Ritenzione

`scripts/cleanup_uploads.py` cancella **file e riga** più vecchi della finestra, da eseguire
una volta al giorno via cron (la riga di crontab è nella docstring dello script). La finestra è
90 giorni, sovrascrivibile con `UPLOAD_RETENTION_DAYS`.

Lo script conta separatamente i file cancellati e quelli **già mancanti** (`already_missing`):
un file sparito dal disco non blocca la cancellazione della riga. Un `already_missing` alto
significa che qualcuno sta ripulendo `data/uploads/` a mano, e che i download per quei periodi
risponderanno `410`.

## 6. File chiave

| File | Che cosa contiene |
|---|---|
| `database/models.py` | il modello `UploadedFile` |
| `backend/app/services/upload_tracker.py` | `save_upload`, `mark_success`, `mark_error`, `UPLOAD_ROOT` |
| `backend/app/api/v1/imports.py` | i quattro punti di chiamata, uno per endpoint di import |
| `backend/app/api/v1/admin.py` | il router e `require_admin` |
| `migrate_db.py` | creazione della tabella e colonna `user_email` sui DB esistenti |
| `scripts/cleanup_uploads.py` | il lavoro di ritenzione |

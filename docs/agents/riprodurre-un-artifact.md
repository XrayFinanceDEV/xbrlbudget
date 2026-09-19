# Riprodurre un artifact

Quando il proprietario consegna un artifact — un'anteprima di report, un prototipo di pagina, un
mockup — e chiede di riprodurlo, questo è il metodo. Regola del proprietario, 2026-09-19, scritta
dopo il dossier PDF: due giorni di lavoro orchestrato e un giorno per rifarne la forma.

## 1. Il layout è la consegna

**Un artifact di report è un esempio di report accettabile, non perfetto.** Numeri, titoli e testi
del campione sono dimostrativi e non sono il punto. Ciò che conta di più è la **presentazione**:
impaginazione, tipo e griglia delle tabelle, la grammatica della pagina — KPI in colonna a
sinistra, grafico a destra, tabella sotto, commento in fondo — tipo di grafico, corpi e pesi.

Un brief che descrive solo il contenuto («KPI + grafico margini + tabella CE 9 righe») produce
contenuto giusto e pagina sbagliata, senza che nessuno se ne accorga: è esattamente ciò che è
successo a M2-02, 54 pagine derivate dal modello dati invece delle 33 dell'artifact, con 229 test
verdi sopra.

## 2. Copiare vuol dire copiare

«Ispirato a», «illustra il livello di dettaglio», «le sue N pagine non sono un vincolo» non si
scrivono in una spec o in un piano quando il proprietario ha chiesto di copiare. Nel dossier quella
frase è nata nella nota di rilascio dell'artifact, è passata nella spec venti minuti dopo e da lì
in ogni brief: gli agenti hanno obbedito al piano.

Se una parte è davvero libera si dichiara **voce per voce**, e lo decide il proprietario:
**vincolante** (forma della pagina, blocchi e loro ordine, tipo di grafico, colonne, stile) ·
**riferimento** (titoli e testi scritti a misura del campione) · **non vincolante** (i numeri, che
vengono dal modello).

## 3. Pilota prima del ventaglio

Non si distribuiscono 33 pagine a quattro agenti in parallelo. **Prima le 5 pagine executive, un
solo agente**; poi si guarda il PDF; poi si **riscrive il contratto dei worker** con quello che il
pilota ha insegnato; poi il resto, in parallelo. Aspettare 32 pagine per scoprire che il lavoro ha
preso la strada sbagliata costa il doppio del lavoro, e lo costa tutto insieme.

## 4. La verifica è con gli occhi — e «guarda» non è un criterio

Si rende la pagina (`pdftoppm -r 60`) e si **guarda** accanto alla pagina dell'artifact, con la
vision, non solo con `pdftotext`. Ma l'ordine «guardale accanto alla v4» è già stato dato a quattro
agenti in parallelo e non ha fermato la divergenza: serve l'**elenco di che cosa confrontare** —
forma della pagina, blocchi in ordine, `kind` del grafico, numero e nomi delle serie, unità,
colonne e righe delle tavole, numero di KPI, corpi tipografici.

Quell'elenco si **estrae** dall'artifact, non si trascrive a occhio: quando è stato trascritto, 3
righe su 21 erano sbagliate (un `chart()` senza `kind` è a barre, non a linee) e un brief sbagliato
si moltiplica per il numero di agenti che lo leggono insieme.

## 5. Se l'artifact ha un generatore, il contratto si genera

Il modello è M2-02G: `tools/dossier_contract/extract_v4_contract.py` legge il generatore
dell'anteprima e scrive `contracts/dossier_page_contract.json` (33 pagine, blocchi in ordine) e
`contracts/dossier_style_contract.json` (corpi, pesi, colori, margini); `--check` fallisce se i JSON
divergono dal sorgente, identificato per sha256. `tests/test_dossier_contract_conformance.py`
confronta **pagina per pagina**, e le pagine non ancora adeguate sono `xfail` dichiarati con la
ragione a fianco: quell'elenco **è** la lista di lavoro, e una pagina che diventa conforme senza
uscire da quell'elenco fa fallire la suite.

Senza generatore, l'elenco si scrive a mano una volta sola, dal PDF, e diventa lo stesso JSON.

## 6. L'accettazione si misura su dati veri

Una fixture sintetica non ha la forma del caso reale: nel dossier non aveva chiusura né storico, e
ha nascosto tavole a 4 colonne invece di 5, due grafici mai disegnati e una pagina inesistente. Il
proprietario giudica un export vero (AMBIENTA, azienda 575, scenario 18) — il collaudo pure.

## 7. Una divergenza non si autorizza dentro un task

«Metto un grafico per pagina invece di due perché manca il componente pannello» non è una nota nella
ricevuta: è una decisione sulla forma, e va al coordinatore. Un worker che scopre di non poter
rispettare il contratto si ferma e lo dice.

---

Dove è già accaduto: `docs/superpowers/plans/2026-09-13-report-finale-e-pdf-typst.md` (decisione
2026-09-17 e task M2-02B/M2-02D/M2-02G, aggiunti tutti dopo la consegna del task che avrebbero
dovuto guidare) e `docs/testing/M2-02G-contratto.md`.

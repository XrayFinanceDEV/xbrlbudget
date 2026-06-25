# Tassonomia - Mappatura Voci di Bilancio IV Direttiva CEE

Reference document for the Italian statutory financial statement mapping used by the XBRL Budget system.

All accounts follow the **IV Direttiva CEE** (Schema di Bilancio artt. 2424–2425 Codice Civile), as adopted by Italian OIC (Organismo Italiano di Contabilità).

Supported XBRL taxonomies: `2011-01-04`, `2014-11-17`, `2015-12-14`, `2016-11-14`, `2017-07-06`, `2018-11-04`
Supported formats: Bilancio Ordinario, Abbreviato, Micro

---

## Stato Patrimoniale (Balance Sheet — art. 2424 C.C.)

### Attivo (Assets)

| Code | Campo DB | Voce IV CEE | Descrizione | Note |
|------|----------|-------------|-------------|------|
| **sp01** | `sp01_crediti_soci` | A) | Crediti verso soci per versamenti ancora dovuti | Rarely used |
| **sp02** | `sp02_immob_immateriali` | B.I) | Immobilizzazioni immateriali | Avviamento, brevetti, costi di impianto, concessioni |
| **sp03** | `sp03_immob_materiali` | B.II) | Immobilizzazioni materiali | Terreni, fabbricati, impianti, attrezzature |
| **sp04** | `sp04_immob_finanziarie` | B.III) | Immobilizzazioni finanziarie | Partecipazioni, crediti, titoli |
| **sp05** | `sp05_rimanenze` | C.I) | Rimanenze | Materie prime, WIP, prodotti finiti, acconti |
| **sp06** | `sp06_crediti_breve` | C.II) entro | Crediti esigibili entro l'esercizio successivo | Include imposte anticipate. Somma di: verso clienti, tributari, verso altri, ecc. |
| **sp07** | `sp07_crediti_lungo` | C.II) oltre | Crediti esigibili oltre l'esercizio successivo | Stessa composizione di sp06 ma con scadenza >12 mesi |
| **sp08** | `sp08_attivita_finanziarie` | C.III) | Attività finanziarie che non costituiscono immobilizzazioni | Titoli, partecipazioni non durevoli |
| **sp09** | `sp09_disponibilita_liquide` | C.IV) | Disponibilità liquide | Depositi bancari, assegni, cassa |
| **sp10** | `sp10_ratei_risconti_attivi` | D) | Ratei e risconti attivi | Proventi maturati, costi pagati anticipatamente |

**Totale Attivo = sp01 + sp02 + sp03 + sp04 + sp05 + sp06 + sp07 + sp08 + sp09 + sp10**

### Passivo (Liabilities & Equity)

| Code | Campo DB | Voce IV CEE | Descrizione | Note |
|------|----------|-------------|-------------|------|
| **sp11** | `sp11_capitale` | A.I) | Capitale sociale | Solo capitale sottoscritto, NON incluso in riserve |
| **sp12** | `sp12_riserve` | A.II–VIII) | Riserve (aggregate) | Somma di: sovrapprezzo azioni (II), rivalutazione (III), riserva legale (IV), statutarie (V), altre riserve (VI), copertura flussi (VII), utili portati a nuovo (VIII), riserva negativa azioni proprie |
| **sp13** | `sp13_utile_perdita` | A.IX) | Utile (perdita) dell'esercizio | Deve coincidere con voce 21) del Conto Economico |
| **sp14** | `sp14_fondi_rischi` | B) | Fondi per rischi e oneri | Trattamento di quiescenza, imposte differite, strumenti derivati, altri fondi |
| **sp15** | `sp15_tfr` | C) | Trattamento di fine rapporto di lavoro subordinato | TFR maturato |
| **sp16** | `sp16_debiti_breve` | D) entro | Debiti esigibili entro l'esercizio successivo | Aggregato. Dettaglio: banche, fornitori, tributari, previdenza, altri |
| **sp17** | `sp17_debiti_lungo` | D) oltre | Debiti esigibili oltre l'esercizio successivo | Stessa composizione di sp16 ma con scadenza >12 mesi |
| **sp18** | `sp18_ratei_risconti_passivi` | E) | Ratei e risconti passivi | Costi maturati, ricavi riscossi anticipatamente |

**Totale Passivo = sp11 + sp12 + sp13 + sp14 + sp15 + sp16 + sp17 + sp18**

**Vincolo: Totale Attivo = Totale Passivo** (tolleranza €0.01)

### Dettaglio Debiti (Breakdown per natura)

Per il calcolo del cashflow e della PFN (Posizione Finanziaria Netta), i debiti breve/lungo sono ulteriormente suddivisi:

| Code | Tipo | Descrizione | Categoria |
|------|------|-------------|-----------|
| sp16a / sp17a | `debiti_banche` | Debiti verso banche | Finanziario |
| sp16b / sp17b | `debiti_altri_finanz` | Debiti verso altri finanziatori | Finanziario |
| sp16c / sp17c | `debiti_obbligazioni` | Obbligazioni | Finanziario |
| sp16d / sp17d | `debiti_fornitori` | Debiti verso fornitori | Operativo |
| sp16e / sp17e | `debiti_tributari` | Debiti tributari | Operativo |
| sp16f / sp17f | `debiti_previdenza` | Debiti verso istituti di previdenza | Operativo |
| sp16g / sp17g | `altri_debiti` | Altri debiti | Operativo |

---

## Conto Economico (Income Statement — art. 2425 C.C.)

### A) Valore della Produzione

| Code | Campo DB | Voce IV CEE | Descrizione | Note |
|------|----------|-------------|-------------|------|
| **ce01** | `ce01_ricavi_vendite` | 1) | Ricavi delle vendite e delle prestazioni | Fatturato principale |
| **ce02** | `ce02_variazioni_rimanenze` | 2) | Variazioni delle rimanenze di prodotti in corso di lavorazione, semilavorati e finiti | Positivo = incremento scorte. Da NON confondere con voce 11) |
| **ce03** | `ce03_lavori_interni` | 4) | Incrementi di immobilizzazioni per lavori interni | Capitalizzazione costi interni |
| **ce04** | `ce04_altri_ricavi` | 5) | Altri ricavi e proventi | Include contributi in conto esercizio |

**Valore della Produzione (VP) = ce01 + ce02 + ce03 + ce04**

### B) Costi della Produzione

| Code | Campo DB | Voce IV CEE | Descrizione | Note |
|------|----------|-------------|-------------|------|
| **ce05** | `ce05_materie_prime` | 6) | Per materie prime, sussidiarie, di consumo e di merci | Nel forecasting: 60% variabile, 40% fisso |
| **ce06** | `ce06_servizi` | 7) | Per servizi | Consulenze, utenze, manutenzioni, trasporti. Nel forecasting: 60% variabile, 40% fisso |
| **ce07** | `ce07_godimento_beni` | 8) | Per godimento di beni di terzi | Affitti, leasing, noleggi |
| **ce08** | `ce08_costi_personale` | 9) Totale | Totale costi per il personale | Somma di: salari (a), oneri sociali (b), TFR (c), quiescenza (d), altri (e) |
| **ce08a** | `ce08a_tfr_accrual` | 9c) | Trattamento di fine rapporto (sotto-voce) | Dettaglio di ce08, usato per calcolo ammortamenti nel forecasting |
| **ce09** | `ce09_ammortamenti` | 10) Totale | Totale ammortamenti e svalutazioni | Somma di: ammort. immateriali (a), materiali (b), svalut. immobilizzazioni (c), svalut. crediti (d) |
| **ce09a** | `ce09a_ammort_immateriali` | 10a) | Ammortamento delle immobilizzazioni immateriali | Dettaglio di ce09 |
| **ce09b** | `ce09b_ammort_materiali` | 10b) | Ammortamento delle immobilizzazioni materiali | Dettaglio di ce09 |
| **ce09c** | `ce09c_svalutazioni` | 10c) | Altre svalutazioni delle immobilizzazioni | Dettaglio di ce09 |
| **ce09d** | `ce09d_svalutazione_crediti` | 10d) | Svalutazioni dei crediti compresi nell'attivo circolante | Dettaglio di ce09 |
| **ce10** | `ce10_var_rimanenze_mat_prime` | 11) | Variazioni delle rimanenze di materie prime, sussidiarie, di consumo e merci | Da NON confondere con voce 2). Questa è in sezione B (costi), voce 2 è in sezione A (ricavi) |
| **ce11** | `ce11_accantonamenti` | 12) | Accantonamenti per rischi | Fondi rischi operativi |
| **ce11b** | `ce11b_altri_accantonamenti` | 13) | Altri accantonamenti | Accantonamenti non classificati come rischi |
| **ce12** | `ce12_oneri_diversi` | 14) | Oneri diversi di gestione | Imposte indirette, sanzioni, sopravvenienze passive |

**Costi della Produzione (COPRO) = ce05 + ce06 + ce07 + ce08 + ce09 + ce10 + ce11 + ce11b + ce12**

### Aggregati Intermedi

| Aggregato | Formula | Descrizione |
|-----------|---------|-------------|
| **EBITDA (MOL)** | VP − (ce05 + ce06 + ce07 + ce08 + ce10 + ce11 + ce12) | Margine Operativo Lordo — esclude ammortamenti e svalutazioni |
| **EBIT (RO)** | VP − COPRO | Risultato Operativo |

### C) Proventi e Oneri Finanziari

| Code | Campo DB | Voce IV CEE | Descrizione | Note |
|------|----------|-------------|-------------|------|
| **ce13** | `ce13_proventi_partecipazioni` | 15) | Proventi da partecipazioni | Dividendi |
| **ce14** | `ce14_altri_proventi_finanziari` | 16) | Altri proventi finanziari | Interessi attivi, proventi da titoli |
| **ce15** | `ce15_oneri_finanziari` | 17) | Interessi e altri oneri finanziari | Interessi passivi bancari, oneri su finanziamenti |
| **ce16** | `ce16_utili_perdite_cambi` | 17-bis) | Utili e perdite su cambi | Differenze cambio realizzate e da valutazione |

**Risultato Finanziario = ce13 + ce14 − ce15 + ce16**

### D) Rettifiche di Valore di Attività Finanziarie

| Code | Campo DB | Voce IV CEE | Descrizione |
|------|----------|-------------|-------------|
| **ce17** | `ce17_rettifiche_attivita_fin` | D) Totale | Totale rettifiche di valore di attività e passività finanziarie |
| ce17a | `ce17a_rivalutazioni` | 18) | Rivalutazioni di partecipazioni, immobilizzazioni finanziarie, titoli |
| ce17b | `ce17b_svalutazioni` | 19) | Svalutazioni di partecipazioni, immobilizzazioni finanziarie, titoli |

### E) Proventi e Oneri Straordinari (pre-D.Lgs. 139/2015)

| Code | Campo DB | Voce IV CEE | Descrizione | Note |
|------|----------|-------------|-------------|------|
| **ce18** | `ce18_proventi_straordinari` | 20) | Proventi straordinari | Eliminato dal D.Lgs. 139/2015, presente solo in bilanci pre-2016 |
| **ce19** | `ce19_oneri_straordinari` | 21) | Oneri straordinari | Eliminato dal D.Lgs. 139/2015, presente solo in bilanci pre-2016 |

### Imposte e Risultato

| Code | Campo DB | Voce IV CEE | Descrizione | Note |
|------|----------|-------------|-------------|------|
| **ce20** | `ce20_imposte` | 22) | Imposte sul reddito dell'esercizio, correnti, differite e anticipate | Include IRES + IRAP. Somma di: correnti, differite, anticipate |

**Risultato prima delle imposte = EBIT + Risultato Finanziario + ce17 + (ce18 − ce19)**

**Utile (Perdita) dell'esercizio = Risultato prima delle imposte − ce20**

---

## Fonti Dati (Import Sources)

### XBRL Import

- File `.xbrl` / `.xml` conformi alle tassonomie XBRL-ITCC
- Il parser auto-rileva la versione della tassonomia (2011–2018) e il tipo di schema (Ordinario/Abbreviato/Micro)
- Mappatura a 2 livelli:
  1. **V2 (priority-based):** Prova fino a 5 tag XBRL alternativi per campo, con fallback su somma di dettagli
  2. **V1 (legacy):** Mappatura diretta tag→campo
  3. **Riconciliazione:** Confronto con aggregati (TotaleCrediti, TotaleDebiti) per catturare voci mancanti
- Il `period_months` viene auto-rilevato dai contesti XBRL (date inizio/fine)
- Configurazione in `data/taxonomy_mapping.json` (V1) e `data/taxonomy_mapping_v2.json` (V2)

### PDF Import (Claude Haiku LLM)

- File PDF con bilancio in formato IV CEE (Stato Patrimoniale + Conto Economico)
- Supporta bilancio Ordinario, Abbreviato, Micro
- Supporta formato "Stampa dettaglio voci" (report ERP con voci di dettaglio)
- Supporta formato "Situazione Contabile" (parser deterministico, senza LLM)
- Estrazione singolo anno o doppia colonna (anno corrente + anno precedente)
- Post-elaborazione con 4 validatori:
  1. **Crediti:** Corregge split entro/oltre, include imposte anticipate mancanti
  2. **Patrimonio netto:** Verifica sp11+sp12+sp13 = PN atteso dal passivo
  3. **Debiti:** Verifica sp16+sp17 = Debiti attesi dal passivo (eseguito dopo patrimonio netto per evitare errori a cascata)
  4. **Imposte CE:** Cross-check ce20 con risultato ante imposte e utile da SP

### CSV Import (formato TEBE)

- File CSV con righe denominate in italiano
- Mappatura diretta nome riga → campo sp/ce
- Configurazione nella sezione `csv_simplified_mapping` di `data/taxonomy_mapping.json`

---

## Relazioni e Vincoli Contabili

### Vincoli di Bilancio (Balance Sheet)

```
Totale Attivo   = sp01 + sp02 + sp03 + sp04 + sp05 + sp06 + sp07 + sp08 + sp09 + sp10
Totale Passivo  = sp11 + sp12 + sp13 + sp14 + sp15 + sp16 + sp17 + sp18
Totale Attivo   = Totale Passivo  (pareggio di bilancio)

Patrimonio Netto (PN) = sp11 + sp12 + sp13
Capitale Circolante Netto (CCN) = (sp05 + sp06 + sp08 + sp09) − sp16
Posizione Finanziaria Netta (PFN) = (sp16a + sp17a + sp16b + sp17b + sp16c + sp17c) − sp09
```

### Vincoli Conto Economico

```
VP   = ce01 + ce02 + ce03 + ce04
COPRO = ce05 + ce06 + ce07 + ce08 + ce09 + ce10 + ce11 + ce11b + ce12
EBIT  = VP − COPRO
Risultato ante imposte = EBIT + (ce13 + ce14 − ce15 + ce16) + ce17 + (ce18 − ce19)
Utile netto = Risultato ante imposte − ce20

sp13 (utile da SP) = Utile netto (da CE)
```

### Cross-check SP ↔ CE

| Voce SP | Voce CE | Relazione |
|---------|---------|-----------|
| sp13 (utile/perdita) | voce 21) utile netto | Devono coincidere |
| sp15 (TFR) | ce08a (accantonamento TFR) | TFR_fine = TFR_inizio + ce08a − utilizzi |
| sp14 (fondi rischi) | ce11 + ce11b (accantonamenti) | Fondi_fine = Fondi_inizio + accantonamenti − utilizzi |

---

## Principali Tag XBRL per Campo

Elenco dei tag XBRL più comuni per ciascun campo (priority_1 dalla mappatura V2):

### Stato Patrimoniale

| Campo | Tag XBRL (priority_1) |
|-------|-----------------------|
| sp02 | `itcc-ci:TotaleImmobilizzazioniImmateriali` |
| sp03 | `itcc-ci:TotaleImmobilizzazioniMateriali` |
| sp04 | `itcc-ci:TotaleImmobilizzazioniFinanziarie` |
| sp05 | `itcc-ci:TotaleRimanenze` |
| sp06 | `itcc-ci:TotaleCreditiIscrittiAttivoCircolanteQuotaScadenteEntroEsercizio` |
| sp07 | `itcc-ci:TotaleCreditiIscrittiAttivoCircolanteQuotaScadenteOltreEsercizio` |
| sp08 | `itcc-ci:TotaleAttivitaFinanziarieNonCostituisconoImmobilizzazioni` |
| sp09 | `itcc-ci:TotaleDisponibilitaLiquide` |
| sp10 | `itcc-ci:AttivoRateiRisconti` |
| sp11 | `itcc-ci:PatrimonioNettoCapitale` |
| sp12 | `itcc-ci-2018-11-04:Riserve` (oppure somma dettagli con `accumulate_all`) |
| sp13 | `itcc-ci:PatrimonioNettoUtilePerditaEsercizio` |
| sp14 | `itcc-ci:TotaleFondiRischiOneri` |
| sp15 | `itcc-ci:TrattamentoFineRapportoLavoroSubordinato` |
| sp16 | `itcc-ci:TotaleDebitiQuotaScadenteEntroEsercizio` |
| sp17 | `itcc-ci:TotaleDebitiQuotaScadenteOltreEsercizio` |
| sp18 | `itcc-ci:PassivoRateiRisconti` |

### Conto Economico

| Campo | Tag XBRL (priority_1) |
|-------|-----------------------|
| ce01 | `itcc-ci:ValoreProduzioneRicaviVenditePrestazioni` |
| ce02 | `itcc-ci:ValoreProduzioneVariazioniRimanenze` |
| ce03 | `itcc-ci:ValoreProduzioneIncrementoImmobilizzazioniLavoriInterni` |
| ce04 | `itcc-ci:ValoreProduzioneAltriRicaviProventiTotaleAltriRicaviProventi` |
| ce05 | `itcc-ci:CostiProduzioneMateriePrimeSussidiarieConsumoMerci` |
| ce06 | `itcc-ci:CostiProduzioneServizi` |
| ce07 | `itcc-ci:CostiProduzioneGodimentoBeniTerzi` |
| ce08 | `itcc-ci:CostiProduzionePersonaleTotaleCostiPersonale` |
| ce08a | `itcc-ci:CostiProduzionePersonaleTrattamentoFineRapporto` |
| ce09 | `itcc-ci:CostiProduzioneAmmortamentiSvalutazioniTotaleAmmortamentiSvalutazioni` |
| ce10 | `itcc-ci:CostiProduzioneVariazioniRimanenzeMateriePrimeSussidiarieConsumoMerci` |
| ce11 | `itcc-ci:CostiProduzioneAccantonamentiRischi` |
| ce11b | `itcc-ci:CostiProduzioneAltriAccantonamenti` |
| ce12 | `itcc-ci:CostiProduzioneOneriDiversiGestione` |
| ce13 | `itcc-ci:ProventiOneriFinanziariProventiPartecipazioniTotaleProventiPartecipazioni` |
| ce14 | `itcc-ci:ProventiOneriFinanziariAltriProventiFinanziariTotaleAltriProventiFinanziari` |
| ce15 | `itcc-ci:ProventiOneriFinanziariInteressiAltriOneriFinanziariTotaleInteressiAltriOneriFinanziari` |
| ce16 | `itcc-ci:ProventiOneriFinanziariUtiliPerditeCambi` |
| ce17 | `itcc-ci:TotaleRettificheValoreAttivitaPassivitaFinanziarie` |
| ce20 | `itcc-ci:ImposteRedditoEsercizioCorrentiDifferiteAnticipateTotaleImposteRedditoEsercizioCorrentiDifferiteAnticipate` |

### Tag Aggregati (per riconciliazione, non mappati direttamente)

| Tag | Uso |
|-----|-----|
| `TotaleAttivo` | Verifica totale attivo |
| `TotalePassivo` | Verifica totale passivo |
| `TotaleCrediti` | Riconciliazione sp06+sp07 |
| `TotaleDebiti` | Riconciliazione sp16+sp17 |
| `TotalePatrimonioNetto` | Riconciliazione sp11+sp12+sp13 |
| `TotaleValoreProduzione` | Riconciliazione VP |
| `TotaleCostiProduzione` | Riconciliazione COPRO |
| `DifferenzaValoreCostiProduzione` | Verifica EBIT |
| `RisultatoPrimaImposte` | Verifica risultato ante imposte |
| `UtilePerditaEsercizio` | Verifica utile netto |

---

## File di Configurazione

| File | Contenuto |
|------|-----------|
| `data/taxonomy_mapping.json` | Mappatura V1 (diretta) + mappatura CSV |
| `data/taxonomy_mapping_v2.json` | Mappatura V2 (priority-based) con dettagli e riconciliazione |
| `importers/xbrl_parser_enhanced.py` | Parser XBRL con riconciliazione debiti/crediti |
| `importers/pdf_extractor_llm.py` | Estrazione PDF con Claude Haiku + validatori |
| `importers/csv_importer.py` | Import CSV formato TEBE |
| `importers/situazione_contabile_parser.py` | Parser deterministico per bilanci di verifica |
| `database/models.py` | Modelli ORM con proprietà calcolate (VP, COPRO, EBIT, MOL, utile netto) |

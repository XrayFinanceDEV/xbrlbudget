"""Verdetti sull'import: rifiuti, avvisi, classificazione dello sbilancio, stato di validazione, anno precedente.

Spostato da importers/pdf_importer.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import logging
import re
from decimal import Decimal
from typing import Any, Dict, NamedTuple, Optional
from importers.import_pdf.riassunti import (
    _euro_it, _is_aggregated_summary, _summary_internal_contradiction,
)

# il nome di prima: i filtri e i test sui log non cambiano
logger = logging.getLogger("importers.pdf_importer")


def _validation_report_payload(q, reliability=None) -> Dict[str, Any]:
    """JSON-safe persisted form of the immutable accounting validation."""
    payload = {
        "arithmetic_balanced": abs(q.sbilancio) <= Decimal("0.01"),
        "income_result_consistent": q.utile_match,
        "hierarchy_consistent": q.hierarchy_consistent,
        "semantic_valid": q.semantic_valid,
        "masked": q.masked,
        "is_empty": q.is_empty,
        "totale_attivo": str(q.totale_attivo),
        "totale_passivo": str(q.totale_passivo),
        "sbilancio": str(q.sbilancio),
        "utile_ce": None if q.utile_ce is None else str(q.utile_ce),
        "sp13": str(q.sp13),
        "plug_residual": str(q.plug_residual),
        "hierarchy_differences": {
            key: str(value) for key, value in q.hierarchy_differences.items()
        },
        "warnings": list(q.warnings),
    }
    if reliability is not None:
        payload["critical_accounts"] = reliability.to_dict()
    return payload

def _avviso_risultato_ricostruito(importo) -> str:
    return (
        "RISULTATO ESERCIZIO PRECEDENTE RICOSTRUITO DAI TOTALI: il documento stampa la "
        "didascalia del risultato dell'esercizio precedente ma l'importo non e' leggibile; "
        f"€{_euro_it(Decimal(str(importo)))} e' stato ricostruito come differenza dei totali "
        "dello Stato Patrimoniale meno l'utile del Conto Economico (verificato dai suoi "
        "totali) e messo negli utili portati a nuovo. Verificarlo in Rettifiche.")

def _avvisi_fondi_snello(diag: dict) -> list[str]:
    """Gli avvisi sui fondi che l'importatore ha dichiarato nel suo diag."""
    avvisi = []
    gia_nettati = diag.get('fondi_gia_nettati')
    if gia_nettati:
        # la voce stampava gia' il netto: il fondo letto a parte non si sottrae una seconda volta
        avvisi.append(
            'FONDO GIA\' NETTATO: la voce stampa gia\' il valore al netto del fondo, che non e\' '
            'stato sottratto una seconda volta ('
            + ', '.join(f'{q[:-2]} {v}' for q, v in gia_nettati) + ').')
    non_dettagliato = diag.get('valore_produzione_non_dettagliato')
    if non_dettagliato:
        # decisione del proprietario 2026-11-19: la voce A senza dettaglio va nei ricavi delle vendite
        avvisi.append(
            'VALORE DELLA PRODUZIONE NON DETTAGLIATO: il documento stampa solo il totale di A) '
            '(' + ', '.join(non_dettagliato) + '), messo per intero nei ricavi delle vendite (ce01). '
            'Se comprende variazioni delle rimanenze, incrementi o altri ricavi, ripartirlo in Rettifiche.')
    tagliate = diag.get('immobilizzazioni_negative_tagliate')
    if tagliate:
        # budget_1452: i fondi degli immateriali (1.086,25) superano il costo storico (1.000)
        avvisi.append(
            'FONDO OLTRE IL COSTO STORICO: il fondo ammortamento supera il valore lordo del '
            'cespite (' + ', '.join(f'{campo} eccedenza {v}' for campo, v in tagliate)
            + '). E\' un errore del documento: l\'immobilizzazione netta e\' stata portata a '
            'zero e l\'eccedenza resta come sbilancio dichiarato - correggere in Rettifiche.')
    return avvisi

# Decisione del proprietario (2026-11-19): uno sbilancio oltre meta' del totale attivo non e' un bilancio da
# rettificare, e' una lettura non riuscita («non ha senso importare con sbilanci cosi' elevati»).
_SBILANCIO_MASSIMO_QUOTA = Decimal("0.5")

# Un totale attivo stampato sotto un quarto del lato piu' grande letto non fa da base: e' un totale letto male
# (budget_1753, prima della correzione dei sotto-totali: 11,36 € contro milioni).
_QUOTA_MINIMA_TOTALE_STAMPATO = Decimal("0.25")

def _rifiuta_lettura_non_riuscita(file_path: str, qd, income_data=None) -> str | None:
    """Uno sbilancio oltre la meta' del totale attivo stampato (o, senza un totale stampato credibile, del lato piu'
    grande letto) e' una lettura fallita: manca meta' del bilancio o piu', e Rettifiche non e' lo strumento per
    ricostruirlo (budget_1786: 105 milioni di sbilancio su un attivo di circa 9). Si rifiuta col motivo, invece di
    salvare numeri senza senso. Uno sbilancio piu' piccolo resta importato con l'avviso, come sempre.
    Lo sbilancio si misura sui totali col loro segno: un passivo letto negativo (il meno stampato davanti alle
    passivita' e preso per un saldo) e' una lettura sbagliata, e togliergli il segno ne nasconderebbe lo sbilancio
    vero - un attivo di 100 e un passivo di -60 non quadrano di 40 ma di 160.

    Eccezione (proprietario, 2026-11-23): se il documento stampa un totale dei costi della produzione piu' alto
    delle voci lette e quella differenza riporta lo sbilancio sotto la soglia, non si rifiuta: restituisce l'avviso
    da mostrare all'utente (None quando non c'e' nulla da dire)."""
    att, pas = Decimal(qd.totale_attivo or 0), Decimal(qd.totale_passivo or 0)
    sbilancio = abs(att - pas)
    letto = max(abs(att), abs(pas))
    base = letto
    try:
        from importers.import_snello.verifica import totali_stampati
        stampato = totali_stampati(file_path).get("totale_attivo")
        if stampato is not None and Decimal(stampato) >= _QUOTA_MINIMA_TOTALE_STAMPATO * letto:
            base = Decimal(stampato)
    except Exception:
        pass
    nascosti = _costi_produzione_non_mostrati(file_path, income_data) if income_data else None
    avviso = None
    # l'avviso solo se quei costi spiegano lo sbilancio (aggiungerli lo riduce), mai su un divario estraneo
    if nascosti is not None and abs(att - pas + nascosti[2]) < sbilancio:
        stampato, letto, differenza = nascosti
        avviso = ("COSTI DELLA PRODUZIONE NON DETTAGLIATI: il documento stampa un totale dei costi della produzione "
                  f"(B) di €{_euro_it(stampato)}, ma le voci lette sommano €{_euro_it(letto)}: "
                  f"€{_euro_it(differenza)} di costi non hanno una riga nel documento (o non sono stati letti) e "
                  "lo sbilancio ne deriva. Inserire quei costi nelle loro voci in Rettifiche.")
    if base <= 0 or sbilancio <= _SBILANCIO_MASSIMO_QUOTA * base:
        return avviso
    if avviso is not None and abs(att - pas + nascosti[2]) <= _SBILANCIO_MASSIMO_QUOTA * base:
        # Decisione del proprietario (2026-11-23, «per ora importiamo con eccezione»): lo sbilancio e' spiegato
        # da costi che il documento mette nel totale di B senza stamparne le righe (budget_1790). Si importa con
        # lo sbilancio dichiarato e l'avviso coi numeri stampati, mai un tappo: la ripartizione e' dell'utente.
        return avviso
    negativo = _totale_attivo_stampato_negativo(file_path)
    if negativo is not None:
        # budget_1810: una colonna senza saldi (conti azzerati, restano solo i fondi) stampa un totale attivo
        # negativo. Il rifiuto e' lo stesso; il motivo dice che cosa c'e' nel documento, non uno sbilancio.
        raise PDFImportError(
            "Documento non importabile: il totale attivo stampato e' negativo "
            f"(€-{_euro_it(negativo)}), quindi la colonna letta non e' uno stato patrimoniale (conti azzerati, "
            "periodo o anno sbagliato). Il bilancio non e' stato importato.")
    raise PDFImportError(
        "Lettura non riuscita: lo stato patrimoniale letto non quadra di "
        f"€{_euro_it(sbilancio)} (attivo €{_euro_it(att)}, passivo €{_euro_it(pas)}), piu' della meta' del "
        f"totale attivo (€{_euro_it(base)}). Non e' un bilancio da correggere in Rettifiche: il documento non e' "
        "stato letto correttamente e non e' stato importato.")

_TOTALE_ATTIVO_NEGATIVO = re.compile(
    r"totale\s+(?:dello\s+)?(?:stato\s+patrimoniale\s*[-–]?\s*)?attiv[oita']*\s*:?\s*"
    r"(?:-\s*(?P<pre>\d{1,3}(?:\.\d{3})*,\d{2})|(?P<post>\d{1,3}(?:\.\d{3})*,\d{2})[ \t]*-(?![ \t]*\d))",
    re.I)

def _totale_attivo_stampato_negativo(file_path: str) -> Decimal | None:
    """Il valore assoluto del primo «Totale attivo» stampato col segno meno (davanti o dietro), se c'e'.
    Serve solo a dire il motivo giusto di un rifiuto gia' deciso: non cambia mai un esito."""
    try:
        import fitz
        with fitz.open(file_path) as doc:
            testo = "\n".join(p.get_text() for p in doc)
    except Exception:
        return None
    m = _TOTALE_ATTIVO_NEGATIVO.search(testo)
    if not m:
        return None
    return Decimal((m.group("pre") or m.group("post")).replace(".", "").replace(",", "."))

_TOTALE_COSTI_PRODUZIONE = re.compile(
    r"totale\s+costi\s+della\s+produzione\s*(?:\(\s*b\s*\))?\s*:?\s*(?P<v>\d{1,3}(?:\.\d{3})*(?:,\d{2})?)(?![\d,])",
    re.I)

_CAMPI_COSTI_PRODUZIONE = ("ce05", "ce06", "ce07", "ce08", "ce09", "ce10", "ce11", "ce12")

def _costi_produzione_non_mostrati(file_path: str, income_data) -> tuple[Decimal, Decimal, Decimal] | None:
    """(totale B stampato, somma delle voci B lette, differenza) quando il documento stampa un totale dei costi della
    produzione piu' alto delle voci lette; altrimenti None. Lo schema «BILANCIO PER FORMULA» (budget_1772/1774/1790)
    stampa il totale di B ma solo tre delle sue righe: le altre sono nel totale e non compaiono."""
    try:
        import fitz
        with fitz.open(file_path) as doc:
            testo = "\n".join(p.get_text() for p in doc)
    except Exception:
        return None
    m = _TOTALE_COSTI_PRODUZIONE.search(testo)
    if not m:
        return None
    stampato = Decimal(m.group("v").replace(".", "").replace(",", "."))
    letto = Decimal(0)
    for pref in _CAMPI_COSTI_PRODUZIONE:
        aggregato = [k for k in (income_data or {}) if k.split("_")[0] == pref]
        if aggregato:
            letto += sum((Decimal(income_data[k] or 0) for k in aggregato), Decimal(0))
        else:
            letto += sum((Decimal(v or 0) for k, v in (income_data or {}).items()
                          if re.fullmatch(pref + r"[a-z]", k.split("_")[0])), Decimal(0))
    differenza = stampato - letto
    if differenza <= 0:
        return None
    return stampato, letto, differenza

def _rifiuta_passivo_non_letto(bs) -> None:
    """Un attivo letto con il passivo tutto a zero non e' un bilancio sbilanciato: e' una lettura
    mancante (budget_1423/1418, vLLM che ometteva sp11-sp18 e pydantic che li riempiva a zero).
    Salvarlo come "squadrato" consegnerebbe all'utente un passivo inventato a zero."""
    if not bs:
        return
    from importers.iv_cee_hierarchy import _ATTIVO_FIELDS, _PASSIVO_FIELDS
    attivo = sum((abs(Decimal(bs.get(k, 0) or 0)) for k in _ATTIVO_FIELDS), Decimal(0))
    passivo = sum((abs(Decimal(bs.get(k, 0) or 0)) for k in _PASSIVO_FIELDS), Decimal(0))
    if attivo > 0 and passivo == 0:
        raise PDFImportError(
            "Lettura del passivo mancante: il modello ha restituito l'attivo "
            f"(€{_euro_it(attivo)}) ma nessuna voce del passivo. Il bilancio non e' stato "
            "importato; riprovare l'import.")

class PDFImportError(Exception):
    """Exception raised when PDF import fails."""
    pass

_UNBALANCED_WARNING_PREFIX = "BILANCIO SBILANCIATO"

# Sbilancio che una scansione letta dall'OCR puo' avere ed essere importata con avviso:
# oltre, l'OCR ha perso colonne o totali (decisione del proprietario, 2026-10-14).
_SCANSIONE_SBILANCIO_AMMESSO = Decimal("0.05")

_UNBALANCED_WARNING_SUFFIX = (
    "Il bilancio è stato importato così com'è: correggilo in Rettifiche "
    "prima di calcolare la proiezione."
)

class BalanceFailureVerdict(NamedTuple):
    """Esito della diagnosi su un bilancio che non supera ``validate_balance``.

    Esattamente uno dei due campi e' valorizzato. ``hard_error`` significa che
    non c'e' nulla che l'utente possa correggere in Rettifiche (estrazione
    vuota, documento che non e' uno schema IV-CEE, totali letti dall'OCR e
    quindi inaffidabili di per se'). ``warning`` significa che il bilancio e'
    leggibile ma non quadra: si importa e si corregge a mano.
    """
    hard_error: Optional[str]
    warning: Optional[str]

def _it_amount(value: Decimal) -> str:
    """Formattazione italiana: 1.234.567,89."""
    return f"{value:,.2f}".replace(',', '#').replace('.', ',').replace('#', '.')

def _declared_totals_contradiction(file_path: str, text: Optional[str]) -> Optional[str]:
    """Diagnosi pura: il documento sorgente contraddice se stesso, Attivo dichiarato !=
    Passivo dichiarato (oltre 2 euro). Legge solo i totali che il documento stampa
    (``_declared_control_totals``), non tocca alcun valore contabile e non impedisce
    l'estrazione: e' il chiamante che decide come proseguire (Task 17, decisione del
    proprietario 2026-09-27 — «se il bilancio non e' quadrato deve essere comunque
    importato con avviso»: questi documenti non si scartano piu' prima di scegliere un
    estrattore, si importano con questo avviso). None quando i totali dichiarati
    mancano, non sono leggibili o coincidono.
    """
    try:
        from importers.pdf_extractor_llm import _declared_control_totals
        source_controls = _declared_control_totals(file_path, text=text)
    except Exception as source_control_error:
        # Controllo best-effort: totali non leggibili non bloccano ne' dichiarano nulla.
        logger.info(
            "IV-CEE source preflight unavailable (%s: %s)",
            type(source_control_error).__name__, source_control_error,
        )
        return None
    source_attivo = source_controls.get("attivo")
    source_passivo = source_controls.get("passivo")
    if source_attivo is None or source_passivo is None:
        return None
    source_difference = abs(source_attivo - source_passivo)
    if source_difference <= Decimal("2"):
        return None
    return (
        f"{_UNBALANCED_WARNING_PREFIX}: il bilancio sorgente non quadra prima "
        f"dell'importazione: Totale Attivo €{_euro_it(source_attivo)} != Totale "
        f"Passivo €{_euro_it(source_passivo)} (scarto €{_euro_it(source_difference)}). "
        f"{_UNBALANCED_WARNING_SUFFIX}"
    )

def _avviso_risultato_in_apertura(bs: Dict[str, Any]) -> str:
    """Verifica progressiva il cui saldo d'apertura non riapre il risultato dell'anno prima
    (budget_680): l'importo e' messo negli utili (perdite) portati a nuovo e si dichiara."""
    v = Decimal(str(bs['_risultato_anno_prima_apertura']))
    voce = "perdita" if v < 0 else "utile"
    def e(k):
        try:
            return f"€{_euro_it(Decimal(str(bs[k])))}"
        except Exception:
            return "n/d"
    return (f"RISULTATO DELL'ANNO PRIMA NON DESTINATO: nella colonna d'apertura del bilancio di "
            f"verifica attività ({e('_apertura_attivo')}) e passività ({e('_apertura_passivo')}) "
            f"differiscono di €{_euro_it(abs(v))}, la stessa cifra che sbilancia il saldo finale: "
            f"è la {voce} dell'anno prima non riaperta. È stata messa negli utili (perdite) portati "
            f"a nuovo — verificare in Rettifiche")

def _avviso_risultato_anno_prima_conti(bs: Dict[str, Any]) -> str:
    """Un conto "utile (perdita) d'esercizio" fra i conti del patrimonio, diverso dal risultato
    del periodo (COLOMBO 2026): e' il risultato dell'anno prima non ancora destinato."""
    v = Decimal(str(bs['_risultato_anno_prima_conti']))
    voce = "perdita" if v < 0 else "utile"
    try:
        periodo = f"€{_euro_it(Decimal(str(bs.get('sp13_utile_perdita', bs.get('sp13', 0)))))}"
    except Exception:
        periodo = "n/d"
    return (f"RISULTATO DELL'ANNO PRIMA NON DESTINATO: il conto {voce} d'esercizio di "
            f"€{_euro_it(abs(v))} fra i conti del patrimonio non è il risultato del periodo "
            f"({periodo}): è il risultato dell'anno prima non ancora destinato, ed è stato messo "
            f"negli utili (perdite) portati a nuovo — verificare in Rettifiche")

def _snello_squadrato_reason(report: Dict[str, Any]) -> str:
    """Avviso per un risultato dell'importatore con esito 'squadrato' (Task 17): lo
    scarto e' quello MISURATO dall'importatore stesso (``report['misura']['corrente']``),
    mai ricalcolato qui — puo' venire dall'attivo/passivo del foglio ricostruito, dal
    confronto CE/SP, o dal confronto coi totali stampati dal documento (quest'ultimo non
    e' visto da ``mapper.validate_balance``, che guarda solo gli aggregati del foglio)."""
    misura = (report.get("misura") or {}).get("corrente") or {}

    def _fmt(chiave: str) -> str:
        valore = misura.get(chiave)
        if valore is None:
            return "n/d"
        try:
            return f"€{_euro_it(Decimal(str(valore)))}"
        except Exception:
            return str(valore)

    if report.get("causa") == "ce_non_letto":
        c = report.get("ce_non_letto") or {}
        try:
            massa, ris, tot, letti = (f"€{_euro_it(Decimal(str(c[k])))}" for k in
                                      ("massa", "risultato", "totale_costi", "costi_letti"))
        except Exception:
            massa = ris = tot = letti = "n/d"
        return (
            f"{_UNBALANCED_WARNING_PREFIX}: nel conto economico mancano {massa} di costi che il "
            f"PDF disegna come grafica e non come testo (TOTALE COSTI stampato {tot}, conti "
            f"letti {letti}). Lo Stato Patrimoniale quadra con il risultato stampato dal "
            f"documento ({ris}). Inserisci i costi mancanti in Rettifiche prima di calcolare "
            f"la proiezione.")
    if report.get("causa") == "documento_sbilanciato":
        # Nessuna rilettura e' avvenuta: il documento si contraddice da solo e le voci lette lo
        # riproducono (Task 25 round 2: i totali; Task 27: il risultato SP/CE). Una frase per
        # contraddizione; un rapporto senza ``contraddizioni`` e' quello dei totali, come prima.
        tipi = report.get("contraddizioni") or [{"tipo": "totali"}]
        frasi = []
        for c in tipi:
            if c.get("tipo") == "verifica":
                try:
                    dare, avere, diff = (f"€{_euro_it(abs(Decimal(str(c[k]))))}"
                                         for k in ("dare", "avere", "differenza"))
                except Exception:
                    dare = avere = diff = "n/d"
                frasi.append(
                    f"i totali stampati dal bilancio di verifica non pareggiano: dare {dare} "
                    f"(attività e costi), avere {avere} (passività e ricavi), differenza {diff}, "
                    f"e le voci lette li riproducono (spesso è il risultato dell'anno prima non "
                    f"ancora destinato).")
                continue
            if c.get("tipo") == "risultato":
                try:
                    sp, ce, diff = (f"€{_euro_it(Decimal(str(c[k])))}" for k in ("sp", "ce", "differenza"))
                except Exception:
                    sp = ce = diff = "n/d"
                frasi.append(
                    f"il risultato dell'esercizio stampato nello Stato Patrimoniale ({sp}) e quello "
                    f"stampato nel Conto Economico ({ce}) differiscono di {diff}, e le voci lette "
                    f"li riproducono.")
            else:
                try:
                    scarto = f"€{_euro_it(abs(Decimal(str(misura.get('scarto_sp')))))}"
                except Exception:
                    scarto = "n/d"
                frasi.append(
                    f"il Totale Attivo e il Totale Passivo stampati dal documento differiscono di "
                    f"{scarto}, e le voci lette li riproducono.")
        solo_totali = all(c.get("tipo") != "risultato" for c in tipi)
        chiusura = ("Il bilancio è stato importato così com'è: correggilo in Rettifiche oppure "
                    "carica una versione quadrata del bilancio." if solo_totali else
                    "Il bilancio è stato importato così com'è (bilancio squadrato di partenza): "
                    "correggilo in Rettifiche oppure carica una versione coerente del bilancio.")
        return f"{_UNBALANCED_WARNING_PREFIX}: {' '.join(frasi)} {chiusura}"
    _precedente = (" L'anno precedente (colonna comparativa) non è stato importato: "
                   "puoi inserirlo in Rettifiche."
                   if report.get("precedente") == "non_letto_dalla_lettura_deterministica" else "")
    return (
        f"{_UNBALANCED_WARNING_PREFIX}: l'importatore resta oltre soglia dopo "
        f"l'unica rilettura (scarto Attivo/Passivo {_fmt('scarto_sp')}, scarto CE/SP "
        f"{_fmt('scarto_ce')}, scarto sui totali stampati dal documento "
        f"{_fmt('scarto_stampati')}). {_UNBALANCED_WARNING_SUFFIX}{_precedente}"
    )

def _classify_balance_failure(
    balance_sheet_data: Dict[str, Decimal],
    *,
    is_scanned: bool,
    ocr_source: bool,
    is_trial_balance: bool,
    sample_text: str,
    file_path: str,
    ocr_text: Optional[str],
    cifre_da_vision: bool = False,
) -> BalanceFailureVerdict:
    """Decide se un fallimento di ``validate_balance`` blocca o solo avvisa.

    L'ordine conta: le diagnosi irrecuperabili girano per prime, cosi' un
    documento che non e' importabile non viene salvato come "sbilanciato".
    """
    # 1. Testo OCR: i totali stessi possono essere letti male, quindi non si puo'
    #    dichiarare sbilanciato il documento sorgente. Non quando le cifre le ha lette la
    #    vision dalle immagini: allora e' uno sbilancio di lettura come su un PDF di
    #    testo, si importa con l'avviso e l'utente lo corregge in Rettifiche (ERREGI).
    if (is_scanned or ocr_source) and cifre_da_vision and \
            balance_sheet_data.get('totale_attivo', Decimal('0')) != Decimal('0'):
        from importers.iv_cee_hierarchy import check_quadratura, eur_it
        _q = check_quadratura(balance_sheet_data)
        return BalanceFailureVerdict(
            None,
            f"{_UNBALANCED_WARNING_PREFIX}: le cifre sono lette dalle immagini della "
            f"scansione e lo Stato Patrimoniale non quadra (attivo {eur_it(_q.totale_attivo)}, "
            f"passivo {eur_it(_q.totale_passivo)}). {_UNBALANCED_WARNING_SUFFIX}",
        )
    if (is_scanned or ocr_source) and \
            balance_sheet_data.get('totale_attivo', Decimal('0')) != Decimal('0'):
        # Uno sbilancio piccolo su una scansione letta dall'OCR (MinerU o locale) si
        # importa con l'avviso: si blocca il previsionale, mai il salvataggio (decisione
        # del proprietario, 2026-10-14). Oltre la soglia l'OCR ha perso colonne o totali
        # e il file non si dichiara sbilanciato.
        from importers.iv_cee_hierarchy import check_quadratura, eur_it
        _q = check_quadratura(balance_sheet_data)
        _ta = Decimal(str(balance_sheet_data.get('totale_attivo') or 0))
        _tp = Decimal(str(balance_sheet_data.get('totale_passivo') or 0))
        # lo scarto peggiore fra aggregati e totali dichiarati
        _scarto = max(abs(_q.sbilancio), abs(_ta - _tp),
                      abs(_q.totale_attivo - _ta), abs(_q.totale_passivo - _tp))
        _base = max(abs(_q.totale_attivo), abs(_q.totale_passivo), abs(_ta), abs(_tp))
        if _base > 0 and _scarto <= _base * _SCANSIONE_SBILANCIO_AMMESSO:
            # attivo e passivo degli aggregati, cioe' di cio' che si salva: i totali
            # dichiarati dal lettore possono pareggiare fra loro mentre gli aggregati no, e
            # l'avviso citava "attivo X, passivo X" accanto a uno scarto (budget_689)
            return BalanceFailureVerdict(
                None,
                f"{_UNBALANCED_WARNING_PREFIX}: scansione letta dall'OCR, lo Stato "
                f"Patrimoniale non quadra di {eur_it(_scarto)} (attivo "
                f"{eur_it(_q.totale_attivo or _ta)}, passivo {eur_it(_q.totale_passivo or _tp)}): "
                "verificare le righe lette. "
                f"{_UNBALANCED_WARNING_SUFFIX}",
            )
    if is_scanned or ocr_source:
        return BalanceFailureVerdict(
            "Il documento è una scansione contabile, ma l'OCR non ha "
            "ricostruito in modo affidabile colonne, gerarchie e totali. "
            "Il file sorgente non viene dichiarato sbilanciato: serve una "
            "lettura OCR strutturata oppure un PDF con testo selezionabile.",
            None,
        )

    # 2. Estrazione vuota: non c'e' niente da rettificare.
    if balance_sheet_data.get('totale_attivo', Decimal('0')) == Decimal('0'):
        return BalanceFailureVerdict(
            "Nessun dato estratto dal documento: lo Stato Patrimoniale "
            "risulta vuoto (Totale Attivo pari a zero). Verificare che il "
            "file contenga un prospetto leggibile.",
            None,
        )

    # 3. Riepilogo aggregato: manca lo schema IV-CEE, non la quadratura.
    if not is_trial_balance and _is_aggregated_summary(sample_text):
        contradiction = _summary_internal_contradiction(sample_text)
        if contradiction:
            # Task 17 (decisione del proprietario, 2026-09-27): un documento internamente
            # incoerente con i propri totali stampati non e' piu' un errore duro — si
            # importa comunque, con questo stesso testo diagnostico come avviso, e
            # l'utente lo corregge in Rettifiche.
            return BalanceFailureVerdict(
                None,
                f"{_UNBALANCED_WARNING_PREFIX}: {contradiction} {_UNBALANCED_WARNING_SUFFIX}",
            )
        return BalanceFailureVerdict(
            "Formato non supportato: il documento è un riepilogo aggregato per "
            "macro-voci, non uno schema di bilancio IV-CEE (art. 2424/2425) "
            "importabile. Carica il prospetto di Stato Patrimoniale e Conto "
            "Economico completo.",
            None,
        )

    # 4. Tutto il resto e' uno sbilancio correggibile. Il messaggio d'errore
    #    che prima bloccava e' la migliore diagnosi disponibile: diventa il
    #    testo dell'avviso, cosi' l'utente sa cosa cercare in Rettifiche.
    try:
        from importers.pdf_extractor_llm import _declared_control_totals
        controls = _declared_control_totals(file_path, text=ocr_text)
        source_attivo = controls.get('attivo')
        source_passivo = controls.get('passivo')
    except Exception:
        source_attivo = source_passivo = None

    if source_attivo is not None and source_passivo is not None:
        # In a two-sided ledger, the liabilities footer often EXCLUDES the
        # profit printed immediately below. That is not a source imbalance.
        printed_profit = controls.get('utile') or -(controls.get('perdita') or Decimal('0'))
        if not printed_profit and controls.get('pareggio') == source_attivo:
            # Some ledgers label profit "ECCEDENZA (UTILE)". Reuse the
            # independently cross-footed source controls, without another LLM.
            from importers.ledger_evidence import prepare_ledger
            from importers.detail_enrichment import collect_source_rows
            try:
                _, source_audit = prepare_ledger(collect_source_rows(file_path))
            except (OSError, ValueError, RuntimeError):
                source_audit = {}
            if source_audit.get('status') == 'ready':
                printed_profit = Decimal(source_audit['controls']['bs_profit'])
        if (printed_profit and abs(source_attivo-source_passivo-printed_profit)<=Decimal('.01')
                and controls.get('pareggio') == source_attivo):
            source_passivo += printed_profit
        difference = abs(source_attivo - source_passivo)
        if difference > Decimal('2'):
            detail = (
                "il bilancio sorgente non quadra già nel documento: Totale "
                f"Attivo €{_it_amount(source_attivo)} != Totale Passivo "
                f"€{_it_amount(source_passivo)} (scarto €{_it_amount(difference)})"
            )
        else:
            detail = (
                "i totali Attivo e Passivo stampati coincidono, ma le "
                "componenti patrimoniali estratte non li ricostruiscono"
            )
    else:
        detail = (
            "il bilancio non quadra oppure il documento non contiene "
            "dettaglio sufficiente per ricostruire Attivo, Passivo e "
            "Patrimonio netto"
        )

    return BalanceFailureVerdict(
        None,
        f"{_UNBALANCED_WARNING_PREFIX}: {detail}. {_UNBALANCED_WARNING_SUFFIX}",
    )

# Sbilancio che i gate di import considerano rumore di arrotondamento (budget_305: 1,82 EUR): sotto non c'e' avviso
# all'utente, quindi nemmeno le frasi del lettore. E' piu' larga della tolleranza di arrotondamento del lettore
# (`diagnosi.TOLLERANZA_ARROTONDAMENTO`, 1 EUR, sui singoli blocchi): per l'innesco vale la maggiore.
_TOL_QUADRATURA = Decimal("2")

def _resolve_validation_status(warning_free: bool, forecastable: bool) -> str:
    """Stato di validazione a tre vie.

    Invariante: lo stato e' ``unbalanced`` esattamente quando all'utente e'
    stato mostrato un avviso "BILANCIO SBILANCIATO" (``warning_free=False``,
    cioe' ``unbalanced_reason`` non era ``None``) — stato e avviso non
    possono mai essere in disaccordo. Deliberatamente NON e' derivato dalla
    tolleranza rigorosa di ``arithmetic_balanced`` (0,01 €): i gate che
    generano l'avviso (``validate_balance``, ``check_quadratura(tol=2)``)
    usano tolleranze piu' larghe, quindi uno sbilancio nella fascia
    (0,01 €; 2,00 €] — rumore che i gate considerano accettabile (vedi
    budget_305, scarto 1,82 €) — non deve produrre uno stato "unbalanced"
    senza alcun avviso a spiegarlo.
    """
    if not warning_free:
        return "unbalanced"
    return "verified" if forecastable else "review_required"

def _should_import_prior(
    fresh_balances: bool, is_empty: bool, *, has_existing: bool
) -> bool:
    """Se salvare l'anno di raffronto appena estratto.

    Un anno vuoto non si importa mai: non c'e' nulla da rettificare. Un anno
    sbilanciato si importa SOLO se non ne esiste gia' uno: meglio uno storico
    da correggere che nessuno storico (senza anno di raffronto il wizard
    infrannuale non parte), ma mai al prezzo di degradare un record buono.
    """
    if is_empty:
        return False
    if fresh_balances:
        return True
    return not has_existing

def _avviso_comparato_non_letto(
    prior_fiscal_year: Optional[int],
    *,
    stampa_comparato: bool,
    prior_imported: bool,
    gia_avvisato: bool,
    has_existing: bool,
) -> Optional[str]:
    """L'avviso per un comparato stampato nel PDF che l'import non ha salvato (#60).

    Un lettore che non sa leggere la colonna dell'anno precedente (es. il prospetto
    a quattro colonne «corrente | comparato | scostamento | %», dove il parser
    deterministico legge solo la corrente) non la inventa: ma tacere che c'era
    farebbe sparire l'anno di riferimento senza che l'utente lo sappia. Niente
    avviso se l'anno e' stato importato, se un avviso sul precedente c'e' gia', o
    se il documento non stampa alcun comparato (un infrannuale monocolonna).
    """
    if prior_fiscal_year is None or not stampa_comparato or prior_imported or gia_avvisato:
        return None
    seguito = (
        f"resta quello gia' presente per il {prior_fiscal_year}"
        if has_existing
        else f"importa il bilancio {prior_fiscal_year} a parte se ti serve come anno di riferimento"
    )
    return (
        f"ANNO PRECEDENTE NON IMPORTATO [{prior_fiscal_year}]: il documento stampa una colonna "
        f"comparativa, ma non e' stato possibile leggerla in modo affidabile; {seguito}."
    )

def _single_year_read_prior_column(
    single_bs: Optional[Dict[str, Decimal]],
    dual_current_bs: Optional[Dict[str, Decimal]],
    dual_prior_bs: Optional[Dict[str, Decimal]],
) -> bool:
    """True quando l'estrattore a UN anno ha letto la colonna di RAFFRONTO.

    Su un bilancio annuale comparato le due colonne sono omogenee (2025 / 2024) e
    l'estrattore a un anno prende quella corrente. Su un INFRANNUALE comparato non lo
    sono — 9 mesi contro 12 — e la colonna di raffronto e' la piu' "completa" delle
    due: se il prompt la preferisse, l'anno corrente uscirebbe con i numeri dell'anno
    sbagliato. Un bilancio letto dall'anno sbagliato e' internamente coerente: quadra,
    e nessun cancello di quadratura lo vede. Lo vede solo il confronto con la colonna
    che il passaggio a due anni etichetta esplicitamente come comparato.

    Il criterio e' l'IDENTITA', non la somiglianza: leggere due volte la stessa colonna
    da' gli stessi importi al centesimo, mentre un attivo a 9 mesi e uno a 12 si
    somigliano senza mai coincidere. Da qui la tolleranza dell'euro (la stessa di
    ``validate_balance``) e le tre ancore minime non nulle.

    Serve una CONTRADDIZIONE per un verdetto positivo, mai un'assenza: senza comparato,
    con troppe poche ancore, o quando il passaggio a due anni restituisce due colonne
    uguali (e quindi il confronto non distingue nulla), la risposta e' False — «non lo
    so» non fa scartare la lettura.
    """
    if not single_bs or not dual_current_bs or not dual_prior_bs:
        return False

    tolerance = Decimal("1.00")

    def _anchorable(container, key):
        value = container.get(key)
        return isinstance(value, Decimal)

    anchors = [
        key
        for key, value in dual_prior_bs.items()
        # Le chiavi diagnostiche (``_plug_residual``, ``_ce_sp_difference``) non sono
        # poste di bilancio: contarle come ancore impedirebbe di riconoscere due
        # letture della stessa colonna con residui diversi.
        if not key.startswith("_")
        and isinstance(value, Decimal)
        and value != 0
        and _anchorable(single_bs, key)
        and _anchorable(dual_current_bs, key)
    ]
    if len(anchors) < 3:
        return False

    if any(abs(single_bs[key] - dual_prior_bs[key]) > tolerance for key in anchors):
        return False

    return any(
        abs(dual_current_bs[key] - dual_prior_bs[key]) > tolerance for key in anchors
    )

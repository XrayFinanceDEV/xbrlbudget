"""Ripescaggio di voci stampate che l'estrazione perde: ratei passivi, scadenze dei debiti, immobilizzazioni.

Spostato da importers/pdf_extractor_llm.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import fitz
import logging
import re
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from importers.estrazione_llm.modelli import (
    _parse_it_number,
)
from importers.estrazione_llm.colonne import (
    _ColumnAnchors, _GEOMETRIC_NUMBER_RE, _document_comparative_centers, _page_column_anchors,
    _row_code_words, _split_current_prior, _text_line_groups,
)
from importers.estrazione_llm.pagine import (
    find_section_pages,
)

# il nome di prima: i filtri e i test sui log non cambiano
logger = logging.getLogger("importers.pdf_extractor_llm")


# Voci di SP che l'estrattore lineare puo' perdere per intero pur essendo
# STAMPATE, e che si rileggono dalla riga di prospetto senza dedurre nulla.
# ``E) Ratei e risconti`` del passivo e' l'unica registrata perche' e' l'unica
# provata: sul bilancio riclassificato UE di AMB AMBIENTA sp18 usciva 0 contro
# 178.663,25 stampati, mentre il ``D)`` dell'attivo arrivava regolarmente in sp10.
# La lettera di voce distingue i due lati (art. 2424: D attivo, E passivo), le due
# parole obbligatorie distinguono la voce di legge dai suoi conti di dettaglio
# ("RATEI PASSIVI", "RISCONTI PASSIVI", che ne portano una sola).
# Il LATO del prospetto a cui appartiene ciascuna voce ripescabile: i prefissi
# dei campi dell'art. 2424 che stanno dalla stessa parte. Il ripiego aggiunge
# massa MANCANTE, non massa mal classificata: se l'importo stampato e' gia'
# altrove sullo stesso lato, l'estrazione l'ha letto e archiviato male —
# riscriverlo qui lo conterebbe due volte, e la correzione e' in Rettifiche.
_SP_PASSIVO_PREFIXES = (
    'sp11', 'sp12', 'sp13', 'sp14', 'sp15', 'sp16', 'sp17', 'sp18',
)

_MISSING_SP_ROWS = {
    'sp18_ratei_risconti_passivi': (
        re.compile(r"^E[.)]?$", re.I),
        ('ratei', 'risconti'),
        _SP_PASSIVO_PREFIXES,
    ),
}

def _field_already_holding(
    current: Dict[str, Decimal],
    amount: Decimal,
    target: str,
    side_prefixes: Tuple[str, ...],
) -> Optional[str]:
    """Il campo dello STESSO LATO che porta gia' esattamente ``amount``.

    ``None`` quando nessuno lo porta. Una coincidenza fra due voci di pari
    importo fa rinunciare al ripesco: e' il verso prudente — si rinuncia a
    scrivere e lo si dichiara, invece di rischiare di contare due volte il
    lato senza che alcuna chiave lo nomini.
    """
    for field, value in current.items():
        if field == target or not field.startswith(side_prefixes):
            continue
        try:
            if Decimal(value) == amount:
                return field
        except Exception:
            continue
    return None

def _recover_printed_sp_rows(
    file_path: str, current_bs: Dict[str, Decimal]
) -> Dict[str, Decimal]:
    """Rilegge dalla fonte una voce di SP stampata che l'estrazione ha perso.

    E' un RIPIEGO, non un tappo: l'importo esiste, e' stampato nella colonna
    dell'anno corrente della propria riga di prospetto e viene letto li'. Nessun
    valore viene mai ricavato da un divario di quadratura, e la voce viene toccata
    solo quando l'estrazione la dichiara a zero: un importo gia' estratto, anche
    diverso, resta com'e' (e il divario lo dichiara `_unclassified_mass`).
    """
    current = dict(current_bs)
    try:
        doc = fitz.open(file_path)
    except Exception:
        return current
    try:
        selected_sp_pages, _ = find_section_pages(file_path)
    except Exception:
        selected_sp_pages = set()
    recovered: List[Tuple[str, str]] = []
    skipped: List[Tuple[str, str, str]] = []
    document_centers = _document_comparative_centers(doc)
    try:
        for page in doc:
            if selected_sp_pages and page.number not in selected_sp_pages:
                continue
            words = page.get_text('words', sort=True)
            anchors = _page_column_anchors(words, document_centers)
            for line in _text_line_groups(words):
                labels = [word for word in line if float(word[0]) < 350]
                label_text = ' '.join(str(word[4]).casefold() for word in labels)
                codes = _row_code_words(labels)
                if not codes:
                    continue
                numbers = [
                    word for word in line
                    if float(word[0]) > 350
                    and _GEOMETRIC_NUMBER_RE.fullmatch(str(word[4]).strip())
                ]
                if not numbers:
                    continue
                for field, (
                    code_re, required_words, side_prefixes
                ) in _MISSING_SP_ROWS.items():
                    if current.get(field, Decimal('0')) != 0:
                        continue
                    if not all(token in label_text for token in required_words):
                        continue
                    if not any(code_re.fullmatch(code) for code in codes):
                        continue
                    if anchors is not None:
                        candidates, _ = _split_current_prior(numbers, anchors)
                    else:
                        # Colonna unica: la riga porta un solo importo, che e'
                        # quello dell'anno stampato. Piu' di uno senza ancore di
                        # colonna e' ambiguo e non si tocca nulla.
                        candidates = list(numbers)
                    parsed = [_parse_it_number(str(word[4])) for word in candidates]
                    parsed = [value for value in parsed if value is not None]
                    if not parsed or any(value != parsed[0] for value in parsed[1:]):
                        continue
                    if parsed[0] == 0:
                        continue
                    gia_presente = _field_already_holding(
                        current, parsed[0], field, side_prefixes
                    )
                    if gia_presente is not None:
                        skipped.append(
                            (field, gia_presente, str(parsed[0]))
                        )
                        continue
                    current[field] = parsed[0]
                    recovered.append((field, str(parsed[0])))
    finally:
        doc.close()
    if recovered:
        logger.warning(
            "SP source recovery: voci stampate assenti dall'estrazione, rilette "
            "dalla riga di prospetto: %s", recovered,
        )
    if skipped:
        logger.warning(
            "SP source recovery rinunciata: l'importo stampato e' gia' presente "
            "in un altro campo dello stesso lato del prospetto, quindi e' massa "
            "gia' estratta e mal classificata, non massa mancante. La si "
            "corregge in Rettifiche: %s",
            [
                f"{campo} non scritto: {importo} e' gia' in {altrove}"
                for campo, altrove, importo in skipped
            ],
        )
    return current

# D) Debiti dell'art. 2424: numero di voce di legge -> (sotto-campo entro,
# sotto-campo oltre). I numeri di voce sono statutari e identici su ogni
# bilancio italiano, quindi la mappa e' un dato di legge, non un'euristica.
# Le voci senza un sotto-campo proprio (6 acconti, 8 titoli di credito, 9-11-bis
# gruppo, 14 altri debiti) finiscono nel secchio generico: mai sull'aggregato,
# perche' `projection_common.base_bank_debt` assegna alle BANCHE qualunque
# scarto fra sp16/sp17 e la somma dei loro dettagli, e il residuo diventa debito
# bancario fantasma con tanto di piano di rimborso.
_DEBT_ITEM_FIELDS = {
    '1': ('sp16c_debiti_obbligazioni_breve', 'sp17c_debiti_obbligazioni_lungo'),
    '2': ('sp16c_debiti_obbligazioni_breve', 'sp17c_debiti_obbligazioni_lungo'),
    '3': ('sp16b_debiti_altri_finanz_breve', 'sp17b_debiti_altri_finanz_lungo'),
    '4': ('sp16a_debiti_banche_breve', 'sp17a_debiti_banche_lungo'),
    '5': ('sp16b_debiti_altri_finanz_breve', 'sp17b_debiti_altri_finanz_lungo'),
    '7': ('sp16d_debiti_fornitori_breve', 'sp17d_debiti_fornitori_lungo'),
    '12': ('sp16e_debiti_tributari_breve', 'sp17e_debiti_tributari_lungo'),
    '13': ('sp16f_debiti_previdenza_breve', 'sp17f_debiti_previdenza_lungo'),
}

_DEBT_GENERIC_FIELDS = ('sp16g_altri_debiti_breve', 'sp17g_altri_debiti_lungo')

_DEBT_DETAIL_FIELDS = tuple(sorted({
    field
    for pair in list(_DEBT_ITEM_FIELDS.values()) + [_DEBT_GENERIC_FIELDS]
    for field in pair
}))

_DEBT_SECTION_CODE_RE = re.compile(r"^D[.)]?[,]?$", re.I)

# La lettera di voce e' un confine di sezione solo se MAIUSCOLA: alcuni
# layout letterano lo spacchettamento per scadenza (`a) esigibili entro…`),
# e con `re.I` quella `a)` chiudeva la sezione alla prima riga utile.
_SECTION_CODE_RE = re.compile(r"^[A-Z][.)]?[,]?$")

_DEBT_ITEM_CODE_RE = re.compile(
    r"^(\d+(?:-(?:bis|ter|quater|quinquies))?)\)[,]?$", re.I
)

def _row_current_amount(line, anchors: _ColumnAnchors) -> Optional[Decimal]:
    """L'importo della colonna dell'anno CORRENTE di una riga di prospetto.

    ``None`` quando la riga non ne porta uno, o quando le celle attribuite a
    quella colonna non concordano: un'ambiguita' non si risolve scegliendo.
    """
    numbers = [
        word for word in line
        if float(word[0]) > 350
        and _GEOMETRIC_NUMBER_RE.fullmatch(str(word[4]).strip())
    ]
    if not numbers:
        return None
    current_numbers, _ = _split_current_prior(numbers, anchors)
    parsed = [_parse_it_number(str(word[4])) for word in current_numbers]
    parsed = [value for value in parsed if value is not None]
    if not parsed or any(value != parsed[0] for value in parsed[1:]):
        return None
    return parsed[0]

def _split_printed_debt_maturities(
    file_path: str, current_bs: Dict[str, Decimal]
) -> Dict[str, Decimal]:
    """Rilegge la ripartizione entro/oltre del D) Debiti dove il documento la stampa.

    Il totale dei debiti puo' quadrare mentre la RIPARTIZIONE e' sbagliata:
    ``sp16`` e ``sp17`` stanno entrambi nel passivo, quindi nessuna quadratura
    vede lo spostamento. Lo vedono CCN, current ratio e il circolante di Altman
    — e spostare debito dal breve al lungo fa risultare gli indici di liquidita'
    MIGLIORI del vero. E' un errore che attraversa un confine di KPI.

    Il blocco pero' si auto-valida: le righe ``- entro`` / ``- oltre`` stampate
    cross-footano al ``D) Debiti`` stampato. Questa lettura ha quindi il proprio
    totale di controllo e non deve fidarsi dell'estrazione LLM. E' un RIPIEGO
    lecito, non un plug: la massa e' stampata e letta nella propria riga, e
    senza il cross-foot non si tocca nulla — resta allora la regola prudenziale,
    debito senza scadenza dichiarata a breve.
    """
    current = dict(current_bs)
    try:
        doc = fitz.open(file_path)
    except Exception:
        return current
    try:
        selected_sp_pages, _ = find_section_pages(file_path)
    except Exception:
        selected_sp_pages = set()
    document_centers = _document_comparative_centers(doc)
    printed_total: Optional[Decimal] = None
    per_field: Dict[str, Decimal] = {}
    entro_total = oltre_total = Decimal('0')
    item: Optional[str] = None
    in_debiti = closed = False
    try:
        for page in doc:
            if closed:
                break
            if selected_sp_pages and page.number not in selected_sp_pages:
                continue
            words = page.get_text('words', sort=True)
            anchors = _page_column_anchors(words, document_centers)
            if anchors is None:
                continue
            for line in _text_line_groups(words):
                labels = [word for word in line if float(word[0]) < 350]
                label_text = ' '.join(str(word[4]).casefold() for word in labels)
                codes = _row_code_words(labels)
                code = codes[0] if codes else ''
                amount = _row_current_amount(line, anchors)
                if not in_debiti:
                    # La lettera di voce distingue i due lati (art. 2424: D
                    # attivo = ratei e risconti, D passivo = debiti), e la
                    # parola "debiti" distingue l'una dall'altra.
                    if (
                        _DEBT_SECTION_CODE_RE.fullmatch(code)
                        and 'debiti' in label_text
                        and 'ratei' not in label_text
                        and amount is not None
                    ):
                        in_debiti, printed_total = True, amount
                    continue
                # La riga di scadenza si riconosce PRIMA del confine di
                # sezione: e' il pattern piu' specifico, e un layout che la
                # lettera (`a) esigibili entro…`) altrimenti chiuderebbe la
                # scansione proprio sulla riga che si vuole leggere.
                index = None
                if 'esercizio successivo' in label_text:
                    if 'entro' in label_text:
                        index = 0
                    elif 'oltre' in label_text:
                        index = 1
                if index is None:
                    if _SECTION_CODE_RE.fullmatch(code) and code[0] != 'D':
                        # La lettera di voce successiva chiude la sezione. Le
                        # scadenze dei CREDITI stanno fuori di qui, e restano
                        # fuori.
                        closed = True
                        break
                    item_match = _DEBT_ITEM_CODE_RE.fullmatch(code)
                    if item_match:
                        item = item_match.group(1).casefold()
                    continue
                if item is None or amount is None:
                    continue
                field = _DEBT_ITEM_FIELDS.get(item, _DEBT_GENERIC_FIELDS)[index]
                per_field[field] = per_field.get(field, Decimal('0')) + amount
                if index == 0:
                    entro_total += amount
                else:
                    oltre_total += amount
    finally:
        doc.close()

    if printed_total is None or not per_field:
        return current
    if abs(entro_total + oltre_total - printed_total) > Decimal('0.01'):
        logger.warning(
            "Scadenze D) Debiti ignorate: le righe entro/oltre stampate sommano "
            "%s contro %s del totale stampato. Senza cross-foot questa lettura "
            "non ha un totale di controllo, e una ripartizione senza prova "
            "sarebbe inventata: si tiene quella dell'estrazione.",
            entro_total + oltre_total, printed_total,
        )
        return current

    for field in _DEBT_DETAIL_FIELDS:
        current[field] = per_field.get(field, Decimal('0'))
    current['sp16_debiti_breve'] = entro_total
    current['sp17_debiti_lungo'] = oltre_total
    logger.warning(
        "Scadenze D) Debiti rilette dalle righe stampate (cross-foot %s sul "
        "totale stampato): sp16=%s, sp17=%s",
        printed_total, entro_total, oltre_total,
    )
    return current

# Le quattro voci di legge che il layout riclassificato stampa con il proprio
# dettaglio, e i sotto-campi dell'art. 2424 in cui va ciascun numero di voce.
# Il numero di voce e' statutario; a distinguere i due `I.` (Immobilizzazioni
# Immateriali e Rimanenze) e' l'ETICHETTA, mai il solo numero romano — e
# "materiali" e' una sottostringa di "immateriali", quindi nemmeno la sola
# parola basta: serve la coppia (numero romano, parole obbligatorie).
_FIXED_ASSET_SECTIONS = (
    (
        'sp02_immob_immateriali',
        re.compile(r"^I[.)]?[,]?$"),
        ('immobilizzazioni', 'immateriali'),
        {
            '1': 'sp02a_costi_impianto', '2': 'sp02b_costi_sviluppo',
            '3': 'sp02c_brevetti', '4': 'sp02d_concessioni',
            '5': 'sp02e_avviamento', '6': 'sp02f_immob_in_corso',
            '7': 'sp02g_altre_immob_imm',
        },
        'sp02g_altre_immob_imm',
        (
            'sp02a_costi_impianto', 'sp02b_costi_sviluppo', 'sp02c_brevetti',
            'sp02d_concessioni', 'sp02e_avviamento', 'sp02f_immob_in_corso',
            'sp02g_altre_immob_imm',
        ),
    ),
    (
        'sp03_immob_materiali',
        re.compile(r"^II[.)]?[,]?$"),
        ('immobilizzazioni', 'materiali'),
        {
            '1': 'sp03a_terreni_fabbricati', '2': 'sp03b_impianti_macchinari',
            '3': 'sp03c_attrezzature', '4': 'sp03d_altri_beni',
            '5': 'sp03e_immob_in_corso',
        },
        'sp03d_altri_beni',
        (
            'sp03a_terreni_fabbricati', 'sp03b_impianti_macchinari',
            'sp03c_attrezzature', 'sp03d_altri_beni', 'sp03e_immob_in_corso',
        ),
    ),
    (
        'sp04_immob_finanziarie',
        re.compile(r"^III[.)]?[,]?$"),
        ('immobilizzazioni', 'finanziarie'),
        # B.III.2 «crediti» ha entro/oltre e il documento non li separa a
        # questo livello: vanno all'OLTRE. E' il verso prudenziale per un
        # credito — l'opposto di quello dei debiti — perche' anticiparne
        # l'incasso abbellirebbe la liquidita' invece di peggiorarla.
        {
            '1': 'sp04a_partecipazioni', '2': 'sp04c_crediti_immob_lungo',
            '3': 'sp04d_altri_titoli', '4': 'sp04e_strumenti_derivati_attivi',
        },
        'sp04d_altri_titoli',
        (
            'sp04a_partecipazioni', 'sp04b_crediti_immob_breve',
            'sp04c_crediti_immob_lungo', 'sp04d_altri_titoli',
            'sp04e_strumenti_derivati_attivi',
        ),
    ),
    (
        'sp05_rimanenze',
        re.compile(r"^I[.)]?[,]?$"),
        ('rimanenze',),
        {
            '1': 'sp05a_materie_prime', '2': 'sp05b_prodotti_in_corso',
            '3': 'sp05c_lavori_in_corso', '4': 'sp05d_prodotti_finiti',
            '5': 'sp05e_acconti',
        },
        'sp05e_acconti',
        (
            'sp05a_materie_prime', 'sp05b_prodotti_in_corso',
            'sp05c_lavori_in_corso', 'sp05d_prodotti_finiti', 'sp05e_acconti',
        ),
    ),
)

_ROMAN_CODE_RE = re.compile(r"^(?:I{1,3}|IV|VI{0,3}|IX|X)[.)]?[,]?$")

_STATUTORY_ITEM_CODE_RE = re.compile(
    r"^(\d+(?:-(?:bis|ter|quater|quinquies))?)\)[,]?$", re.I
)

def _recover_printed_fixed_asset_details(
    file_path: str, current_bs: Dict[str, Decimal]
) -> Dict[str, Decimal]:
    """Rilegge i sotto-campi di immobilizzazioni e rimanenze dove sono STAMPATI.

    Sullo schema di legge puro le immobilizzazioni sono nette per definizione e
    non c'e' nulla da spacchettare; questo layout invece stampa la gerarchia
    completa, con il costo storico e il fondo ammortamento di ciascun cespite e
    con la riga di voce di legge GIA' NETTA (``4) Concessioni…`` vale 48.618,07,
    cioe' 61.605,00 meno 12.986,93). Si legge quella riga, e non i conti
    sottostanti: si sommano i mastri OPPURE le foglie, mai entrambi.

    Senza i sotto-campi ``hierarchy_consistent`` fallisce anche su
    un'estrazione pulita, quindi ``semantic_valid`` e ``forecastable`` restano
    falsi e la proiezione non parte.

    Il controllo e' il totale che il documento stampa per la voce: i dettagli
    letti devono cross-footare a quello. Senza, non si scrive nulla —
    ``sp02``/``sp03``/``sp04`` sono ``TIER0_FIELDS`` e non sono mai una
    destinazione di ripiego: il buco si colma leggendo i dettagli, non
    redistribuendo l'aggregato.
    """
    current = dict(current_bs)
    try:
        doc = fitz.open(file_path)
    except Exception:
        return current
    try:
        selected_sp_pages, _ = find_section_pages(file_path)
    except Exception:
        selected_sp_pages = set()
    document_centers = _document_comparative_centers(doc)
    # Una voce per volta: aggregato -> (totale stampato, {campo: importo}).
    letti: Dict[str, Tuple[Decimal, Dict[str, Decimal], Tuple[str, ...]]] = {}
    sezione: Optional[Tuple[str, Dict[str, str], str, Tuple[str, ...]]] = None
    printed_total = Decimal('0')
    voci: Dict[str, Decimal] = {}

    def _chiudi():
        if sezione is not None and voci:
            letti[sezione[0]] = (printed_total, dict(voci), sezione[3])

    try:
        for page in doc:
            if selected_sp_pages and page.number not in selected_sp_pages:
                continue
            words = page.get_text('words', sort=True)
            anchors = _page_column_anchors(words, document_centers)
            if anchors is None:
                continue
            for line in _text_line_groups(words):
                labels = [word for word in line if float(word[0]) < 350]
                label_text = ' '.join(str(word[4]).casefold() for word in labels)
                codes = _row_code_words(labels)
                code = codes[0] if codes else ''
                amount = _row_current_amount(line, anchors)

                aperta = None
                for (
                    aggregate, roman_re, required, fields, generic, siblings
                ) in _FIXED_ASSET_SECTIONS:
                    if not roman_re.fullmatch(code):
                        continue
                    if not all(token in label_text for token in required):
                        continue
                    if aggregate == 'sp03_immob_materiali' and 'immateriali' in label_text:
                        continue
                    aperta = (aggregate, fields, generic, siblings, amount)
                    break
                if aperta is not None:
                    _chiudi()
                    sezione = aperta[:4]
                    printed_total = aperta[4] if aperta[4] is not None else Decimal('0')
                    voci = {}
                    continue

                if sezione is None:
                    continue
                # Un altro numero romano o una lettera di voce chiudono il blocco.
                if _ROMAN_CODE_RE.fullmatch(code) or _SECTION_CODE_RE.fullmatch(code):
                    _chiudi()
                    sezione, voci, printed_total = None, {}, Decimal('0')
                    continue
                item_match = _STATUTORY_ITEM_CODE_RE.fullmatch(code)
                if item_match is None or amount is None:
                    # "Costo storico", "Fondo ammortamento" e le righe di conto
                    # sono la stessa massa vista a un altro livello: entrano nel
                    # totale della voce, non accanto ad esso.
                    continue
                field = sezione[1].get(item_match.group(1).casefold(), sezione[2])
                voci[field] = voci.get(field, Decimal('0')) + amount
        _chiudi()
    finally:
        doc.close()

    recovered: List[Tuple[str, str]] = []
    for aggregate, (total, fields, siblings) in letti.items():
        somma = sum(fields.values(), Decimal('0'))
        if total <= 0:
            # Non e' un cross-foot fallito: su molti layout IV-CEE la riga in
            # numero romano non porta alcun importo (il totale sta su una riga
            # "Totale …" a parte, che non ha codice di voce). Manca il controllo,
            # quindi non si scrive — ma il messaggio deve dirlo, o chi legge il
            # log va a cercare un divario che non esiste.
            logger.debug(
                "Dettaglio di %s non applicato: la riga di voce non stampa un "
                "totale contro cui misurare le %s voci lette.",
                aggregate, len(fields),
            )
            continue
        if abs(somma - total) > Decimal('0.01'):
            logger.warning(
                "Dettaglio di %s ignorato: le voci stampate sommano %s contro %s "
                "del totale di voce stampato. Senza cross-foot mancherebbe il "
                "controllo, e un TIER0 non si riempie per differenza.",
                aggregate, somma, total,
            )
            continue
        if any(current.get(field, Decimal('0')) != 0 for field in siblings):
            # Si riempie solo una sezione che l'estrazione ha lasciato del tutto
            # vuota. Basta UN fratello gia' valorizzato — anche non stampato, ed
            # e' il caso di `sp04b_crediti_immob_breve` — perche' scrivere le
            # voci lette e poi fissare l'aggregato al totale di voce lasci i
            # dettagli a sommare piu' dell'aggregato: `hierarchy_consistent`
            # fallirebbe, cioe' proprio la condizione che qui si ripara, e
            # `reconcileSubfields` conterebbe due volte quella massa.
            continue
        estratto = current.get(aggregate, Decimal('0'))
        if estratto != 0 and abs(estratto - total) > Decimal('0.01'):
            # La guardia sui fratelli porta i soli DETTAGLI: l'aggregato non
            # e' fra loro, e senza questo controllo `current[aggregate] =
            # total` lo riscriveva comunque. sp02/sp03/sp04/sp05 sono
            # `TIER0_FIELDS` e non sono mai una destinazione di ripiego: un
            # aggregato gia' estratto e DIVERSO dal totale di voce stampato
            # e' un divario da dichiarare, non da tappare — scriverlo
            # sposterebbe il totale attivo di quella differenza e un foglio
            # che quadrava non quadrerebbe piu'. Quando invece i due
            # coincidono la scrittura e' un no-op e la sezione si dettaglia.
            logger.warning(
                "Dettaglio di %s ignorato: l'estrazione porta gia' %s, contro "
                "%s del totale di voce stampato. Un TIER0 gia' valorizzato non "
                "si riscrive: il divario si dichiara e si corregge in "
                "Rettifiche.",
                aggregate, estratto, total,
            )
            continue
        for field, value in fields.items():
            current[field] = value
            recovered.append((field, str(value)))
        current[aggregate] = total
    if recovered:
        logger.warning(
            "SP source recovery: sotto-campi di immobilizzazioni/rimanenze riletti "
            "dalle righe di voce stampate: %s", recovered,
        )
    return current

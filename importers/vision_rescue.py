"""Riscatto vision per sezione — route C (situazione contabile / sezioni contrapposte).

Quando la catena route C finisce con un foglio che non quadra, le pagine della sezione
che non torna vengono rese a immagine e rilette in vision: il numero giusto e' STAMPATO
sulla pagina, e' il text layer a non arrivarci (mastri disegnati come vettori, ordine di
stream rotto, importi corrotti).

Questo modulo non conosce il DB, non importa pdf_importer e non decide nulla da solo:
legge, misura, e restituisce. Il cancello di accettazione (accept_rescue) e' qui perche'
e' puro; l'innesco e la ri-esecuzione della catena stanno in pdf_importer.

Spec: docs/superpowers/specs/2026-08-14-riscatto-vision-route-c-design.md
"""
import base64
import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Sequence, Tuple

import fitz
import pydantic

logger = logging.getLogger(__name__)

# Oltre questo numero di pagine il riscatto non parte: il costo cresce, la resa cala,
# e il file resta dichiarato non quadrato invece di spendere una chiamata enorme con
# poca speranza. Sui file noti la sezione ha 2 pagine.
MAX_RESCUE_PAGES = 8
RESCUE_DPI = 200

Z = Decimal("0")


@dataclass(frozen=True)
class VisionRow:
    code: str
    description: str
    amount: Decimal
    column: str          # 'left' | 'right'


@dataclass(frozen=True)
class VisionSection:
    section: str                              # 'sp' | 'ce'
    rows: Tuple[VisionRow, ...]
    totals: Dict[str, Optional[Decimal]]      # left / right / utile / perdita


class _VisionMastro(pydantic.BaseModel):
    codice: str = ""
    descrizione: str = ""
    importo: str = ""
    colonna: str = ""


class _VisionSectionModel(pydantic.BaseModel):
    mastri: List[_VisionMastro] = []
    totale_sinistra: Optional[str] = None
    totale_destra: Optional[str] = None
    utile: Optional[str] = None
    perdita: Optional[str] = None


_SP_SYSTEM_PROMPT = """Sei un perito contabile che TRASCRIVE una pagina di stato patrimoniale
a sezioni contrapposte di una situazione contabile italiana (piano dei conti CoGe).

REGOLE ASSOLUTE:
1. TRASCRIVI, non calcolare. Non sommare, non dedurre, non correggere nulla.
2. Riporta SOLO le righe di MASTRO — i conti il cui codice ha il MINOR numero di cifre
   nella pagina. Le righe di dettaglio (codice piu' lungo) vanno IGNORATE: il mastro
   porta gia' l'intero importo della voce.
3. La COLONNA e' decisiva: 'left' per la colonna di sinistra (ATTIVITA'), 'right' per
   quella di destra (PASSIVITA'). Se un conto compare su entrambe le colonne, riportalo
   due volte con i rispettivi importi.
4. Le righe di TOTALE non vanno in 'mastri': vanno nei campi totale_sinistra
   (TOTALE ATTIVITA'/ATTIVO), totale_destra (TOTALE PASSIVITA'/PASSIVO), utile e perdita.
5. Riporta gli importi ESATTAMENTE come stampati, formato italiano (1.234.567,89).
   Se un importo non e' leggibile, lascia la stringa vuota.
6. Se un campo di totale non e' stampato sulla pagina, lascialo assente."""

_CE_SYSTEM_PROMPT = """Sei un perito contabile che TRASCRIVE una pagina di conto economico
a sezioni contrapposte di una situazione contabile italiana (piano dei conti CoGe).

REGOLE ASSOLUTE:
1. TRASCRIVI, non calcolare. Non sommare, non dedurre, non correggere nulla.
2. Riporta SOLO le righe di MASTRO — i conti il cui codice ha il MINOR numero di cifre
   nella pagina. Le righe di dettaglio (codice piu' lungo) vanno IGNORATE: il mastro
   porta gia' l'intero importo della voce.
3. La COLONNA e' decisiva: 'left' per la colonna dei COSTI, 'right' per quella dei
   RICAVI.
4. Le righe di TOTALE non vanno in 'mastri': vanno nei campi totale_sinistra
   (TOTALE COSTI), totale_destra (TOTALE RICAVI), utile e perdita.
5. Riporta gli importi ESATTAMENTE come stampati, formato italiano (1.234.567,89).
   Se un importo non e' leggibile, lascia la stringa vuota.
6. Se un campo di totale non e' stampato sulla pagina, lascialo assente."""

_TOOL_NAME = "trascrivi_sezione"


def parse_amount(raw: Optional[str]) -> Optional[Decimal]:
    """Importo in formato italiano -> Decimal. None quando non e' un numero."""
    if raw is None:
        return None
    s = str(raw).strip().replace("\u00a0", " ")   # spazio unificatore
    if not s:
        return None
    negative = s.startswith("-") or (s.startswith("(") and s.endswith(")"))
    s = re.sub(r"[^0-9.,]", "", s)
    if not s:
        return None
    # Formato italiano: '.' migliaia, ',' decimali. Senza virgola il '.' resta
    # separatore di migliaia (un CoGe non stampa mai decimali col punto).
    s = s.replace(".", "").replace(",", ".") if "," in s else s.replace(".", "")
    try:
        value = Decimal(s)
    except InvalidOperation:
        return None
    return -value if negative else value


_LEFT_TOKENS = ("left", "sinistra", "sx", "dare", "attivo", "costi")
_RIGHT_TOKENS = ("right", "destra", "dx", "avere", "passivo", "ricavi")


def normalize_column(raw: Optional[str]) -> Optional[str]:
    """'left' / 'right' dalla colonna dichiarata dal modello, None se non riconosciuta.

    Il prompt chiede 'left'/'right', ma il prompt e' in italiano: un modello che
    risponde 'sinistra' finirebbe su "right" con un confronto per prefisso, e ogni
    riga dell'attivo si ribalterebbe sul passivo. La colonna e' verita' sul lato
    (FIXING-IMPORT.md §1.3): se non e' riconoscibile la riga si scarta, non si
    indovina.
    """
    token = (raw or "").strip().lower()
    if not token:
        return None
    for candidate in _LEFT_TOKENS:
        if token.startswith(candidate):
            return "left"
    for candidate in _RIGHT_TOKENS:
        if token.startswith(candidate):
            return "right"
    return None


def mastro_level_rows(rows: Sequence[VisionRow],
                      totals: Optional[Dict[str, Optional[Decimal]]] = None
                      ) -> Tuple[VisionRow, ...]:
    """Tiene le righe al livello MASTRO, scartando i dettagli.

    I dettagli (codice piu' lungo) la vision li sbaglia — sono le righe con gli importi
    corrotti nel testo sorgente — e non servono, perche' il mastro porta gia' l'intero
    importo della voce. Il filtro e' deterministico e non si fida della sola obbedienza
    del modello alla regola 2 del prompt. Le righe senza codice (totali intercettati per
    errore) sono scartate.

    **La profondita' del codice e' solo un'ipotesi; il totale stampato e' il giudice.**
    Stessa regola di `_select_dedup` in situazione_contabile_parser: si enumerano le
    partizioni candidate (una per ogni lunghezza di codice osservata, dalla piu' corta)
    e si tiene la prima che ricostruisce i totali di colonna LETTI sulla pagina. Prendere
    il minimo e basta si e' rotto sul file vero: su budget_624 la vision trascrive i
    peer di uno stesso livello con un numero di cifre diverso (`7301500` accanto a
    `73015005`), il minimo scartava due mastri buoni — 'Oneri sociali' 41.453,72 e
    'Amm.to immobilizzazioni materiali' 4.656,95 — e i costi ricostruiti mancavano
    46.110,67 sul totale stampato, quindi il cancello respingeva un riscatto corretto
    in 2 esecuzioni su 3. Non e' un allentamento: la partizione scelta deve ora tornare
    ai totali del documento, che e' un vincolo in PIU', non in meno.

    Senza totali utilizzabili (o se nessuna partizione riconcilia) resta il minimo di
    prima, e a decidere e' il cancello di accettazione come sempre.
    """
    digits = {}
    for idx, row in enumerate(rows):
        only = re.sub(r"\D", "", row.code or "")
        if only:
            digits[idx] = len(only)
    if not digits:
        return ()

    def _upto(max_len: int) -> Tuple[VisionRow, ...]:
        return tuple(r for idx, r in enumerate(rows)
                     if idx in digits and digits[idx] <= max_len)

    levels = sorted(set(digits.values()))
    anchors = [(side, (totals or {}).get(side)) for side in ("left", "right")]
    anchors = [(side, value) for side, value in anchors if value]
    if anchors:
        for level in levels:
            kept = _upto(level)
            if all(abs(sum((r.amount for r in kept if r.column == side), Z) - value)
                   <= reconcile_tolerance(value) for side, value in anchors):
                return kept
    return _upto(levels[0])


def render_section_images(file_path: str, pages: Sequence[int],
                          dpi: int = RESCUE_DPI) -> List[str]:
    """Le pagine indicate rese in PNG base64. Solleva se il PDF non si apre."""
    images: List[str] = []
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    with fitz.open(file_path) as doc:
        for p in sorted(pages):
            if 0 <= p < len(doc):
                pix = doc[p].get_pixmap(matrix=matrix)
                images.append(base64.standard_b64encode(pix.tobytes("png")).decode("ascii"))
    return images


def _build_tool_schema() -> dict:
    return {
        "name": _TOOL_NAME,
        "description": "Registra i mastri e i totali trascritti dalla sezione.",
        "input_schema": _VisionSectionModel.model_json_schema(),
    }


def read_section(file_path: str, pages: Sequence[int], section: str,
                 client=None, images: Optional[List[str]] = None) -> Optional[VisionSection]:
    """Rilegge in vision le pagine di una sezione. None su QUALUNQUE problema.

    Un solo tentativo: un riscatto che fallisce non viene ritentato, ne' con un prompt
    diverso ne' a risoluzione maggiore. `client` e `images` sono iniettabili perche' i
    test non facciano rete ne' aprano un PDF.
    """
    pages = list(pages)
    if not pages:
        return None
    if len(pages) > MAX_RESCUE_PAGES:
        logger.info(f"Riscatto vision: sezione {section} di {len(pages)} pagine, oltre il "
                    f"tetto di {MAX_RESCUE_PAGES} — non tentato")
        return None
    try:
        from config import PDF_LLM_MODEL, PDF_LLM_MAX_TOKENS

        if images is None:
            images = render_section_images(file_path, pages)
        if not images:
            return None
        if client is None:
            import anthropic
            client = anthropic.Anthropic()

        content: List[dict] = [
            {"type": "image",
             "source": {"type": "base64", "media_type": "image/png", "data": img}}
            for img in images
        ]
        content.append({
            "type": "text",
            "text": (f"Trascrivi la sezione ({'stato patrimoniale' if section == 'sp' else 'conto economico'}) "
                     f"da queste pagine usando lo strumento {_TOOL_NAME}."),
        })

        response = client.messages.create(
            model=PDF_LLM_MODEL,
            max_tokens=PDF_LLM_MAX_TOKENS,
            system=_SP_SYSTEM_PROMPT if section == "sp" else _CE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
            tools=[_build_tool_schema()],
            tool_choice={"type": "tool", "name": _TOOL_NAME},
        )
        payload = next((b.input for b in response.content if b.type == "tool_use"), None)
        if payload is None:
            logger.warning("Riscatto vision: nessun blocco tool_use nella risposta")
            return None
        parsed = _VisionSectionModel.model_validate(payload)
    except Exception as err:
        logger.warning(f"Riscatto vision saltato ({type(err).__name__}: {err})")
        return None

    rows: List[VisionRow] = []
    for m in parsed.mastri:
        amount = parse_amount(m.importo)
        column = normalize_column(m.colonna)
        if amount is None or amount == Z or column is None:
            continue
        rows.append(VisionRow(code=(m.codice or "").strip(),
                              description=(m.descrizione or "").strip(),
                              amount=amount, column=column))
    totals = {
        "left": parse_amount(parsed.totale_sinistra),
        "right": parse_amount(parsed.totale_destra),
        "utile": parse_amount(parsed.utile),
        "perdita": parse_amount(parsed.perdita),
    }
    # I totali si leggono PRIMA delle righe perche' sono loro a giudicare quale
    # partizione di codici e' il livello mastro (vedi mastro_level_rows).
    return VisionSection(section=section,
                         rows=mastro_level_rows(rows, totals),
                         totals=totals)


# --------------------------------------------------------------- il cancello

# La stessa tolleranza di _select_dedup / _reconcile_trial_to_declared: non una nuova.
_TOL_ABS = Decimal("50")
_TOL_PCT = Decimal("0.005")
# I totali stampati o tornano al centesimo o sono stati letti male: qui non si
# tollera nulla, e' un'identita' contabile, non una riconciliazione.
_COHERENCE_TOL = Decimal("0.05")


def reconcile_tolerance(total: Decimal) -> Decimal:
    return max(_TOL_ABS, abs(total) * _TOL_PCT)


def vision_result(sec: VisionSection) -> Optional[Decimal]:
    """Il risultato d'esercizio con segno, dedotto dall'identita' che ha VALIDATO.

    Un documento puo' stampare sia una riga "utile" sia una riga "perdita" (una delle
    due e' spesso del periodo precedente, o e' una didascalia sempre presente col
    valore a zero). Scegliere l'utile per primo e' indovinare: se la coerenza dei
    totali e' stata verificata dal ramo della PERDITA, il risultato ha segno opposto e
    il foglio ne esce con l'utile ribaltato. Qui il segno lo decide l'identita' che
    torna, non l'ordine delle chiavi. None quando i totali non sono coerenti.
    """
    left, right = sec.totals.get("left"), sec.totals.get("right")
    if left is None or right is None:
        return None
    utile = sec.totals.get("utile") or Z
    perdita = sec.totals.get("perdita") or Z
    if sec.section == "sp":
        # attivo + perdita == passivo, oppure attivo == passivo + utile.
        if abs((left + perdita) - right) <= _COHERENCE_TOL:
            return -perdita
        if abs(left - (right + utile)) <= _COHERENCE_TOL:
            return utile
        return None
    # ce: costi + utile == ricavi, oppure costi == ricavi + perdita — la
    # convenzione di segno e' l'opposto dello SP (qui e' il "right" a crescere
    # con l'utile, non il "left"), non la stessa formula riusata.
    if abs((left + utile) - right) <= _COHERENCE_TOL:
        return utile
    if abs(left - (right + perdita)) <= _COHERENCE_TOL:
        return -perdita
    return None


def totals_are_coherent(sec: VisionSection) -> bool:
    """I totali LETTI dalla vision tornano fra loro?

    SP: attivo + perdita == passivo, oppure attivo == passivo + utile.
    CE: costi + utile == ricavi, oppure costi == ricavi + perdita.

    E' questa coerenza interna che autorizza a preferirli alle ancore di testo quando
    quelle si contraddicono (budget_623: il testo legge un passivo che il PDF non
    stampa). Senza entrambi i totali di colonna non c'e' identita' da verificare.
    Definita su vision_result cosi' le due non possono divergere.
    """
    return vision_result(sec) is not None


def section_anchor(sec: VisionSection,
                   declared: Dict[str, Optional[Decimal]]) -> Optional[Decimal]:
    """Il totale stampato contro cui misurare la sezione ricostruita.

    Preferisce il totale letto in vision quando i totali vision sono coerenti fra loro;
    altrimenti ricade sulle ancore di testo. None quando nessuno dei due insiemi e'
    utilizzabile — e allora il riscatto si scarta, non si accetta al buio.
    """
    if totals_are_coherent(sec):
        left = sec.totals.get("left")
        if left:
            return left
    if sec.section == "sp":
        for key in ("attivo", "pareggio", "passivo"):
            value = (declared or {}).get(key)
            if value:
                return value
        return None
    value = (declared or {}).get("costi")
    return value or None


def _badness(q) -> Decimal:
    """Quanto un foglio e' lontano dall'essere in ordine, in una cifra sola.

    Sbilancio e residuo non classificato sono la stessa specie di male — massa che
    non si spiega — e vanno sommati, non confrontati uno a uno. Trattandoli come tre
    confronti indipendenti, un riscatto che azzera il residuo ma lascia un piccolo
    sbilancio veniva RIFIUTATO: cioe' proprio il caso "QUADRATURA MASCHERATA" per cui
    il riscatto esiste. Sommandoli, 200 di residuo che diventano 10 di sbilancio sono
    un miglioramento, mentre dimezzare il residuo triplicando lo sbilancio non lo e'.

    Nota su _plug_residual: `build_sp_from_vision` lo AZZERA per costruzione — e' un
    asserto, non una misura. Sul percorso SP il chiamante (pdf_importer) lo ricalcola con
    `_reconcile_trial_to_declared`, ma quella funzione misura qualcosa solo se ha
    un'ancora INDIPENDENTE (i totali stampati letti dal testo). Quando non ce l'ha, lo
    zero asserito arriva qui intatto: vedi `residual_measured` in accept_rescue, che in
    quel caso impedisce di incassarlo. Sul percorso CE il foglio non viene toccato,
    quindi il residuo e' identico su before/after e non pesa nel confronto.
    """
    return abs(q.sbilancio) + abs(q.plug_residual)


def accept_rescue(section: str, rebuilt_total: Decimal, sec: VisionSection,
                  declared: Dict[str, Optional[Decimal]],
                  before, after,
                  residual_measured: bool = True,
                  rebuilt_passivo: Optional[Decimal] = None) -> Tuple[bool, str]:
    """Tre condizioni, tutte necessarie (spec §3). Ritorna (accettato, motivo).

    `rebuilt_total` e' il totale LORDO della sezione ricostruita — per lo SP la somma
    dell'attivo netto PIU' la massa dei fondi nettati, perche' il totale stampato su
    questi file e' lordo (stessa aritmetica del cancello 1 di _hier_reconstruct).
    `rebuilt_passivo` e' l'omologo della colonna di DESTRA, sempre LORDO e sempre al
    netto del risultato d'esercizio (che il documento stampa come riga di pareggio,
    fuori dal totale di colonna). None = non misurabile, e allora il controllo si
    salta: un confronto sbagliato sarebbe peggio di un controllo assente.
    `before`/`after` sono i Quadratura del foglio prima e dopo il riscatto.

    `residual_measured` dice se il residuo di `after` e' una MISURA o un asserto: falso
    quando il documento non stampa alcun totale contro cui verificarlo.
    """
    # `section` e `sec.section` devono essere lo stesso: il corpo si dirama su
    # `sec.section` (vision_result, section_anchor), quindi un chiamante che passa
    # 'ce' con una VisionSection 'sp' applicherebbe in silenzio le formule dello SP.
    # ValueError e non assert: gli assert spariscono sotto -O, e il chiamante ha gia'
    # un try che degrada il riscatto a non-tentato.
    if section != sec.section:
        raise ValueError(f"sezione incoerente: richiesta '{section}', "
                         f"ricevuta '{sec.section}'")

    anchor = section_anchor(sec, declared)
    if anchor is None or anchor <= 0:
        return False, "nessuna ancora utilizzabile (ne' i totali vision ne' quelli di testo)"

    delta = abs(anchor - rebuilt_total)
    tol = reconcile_tolerance(anchor)
    if delta > tol:
        return False, (f"non riconcilia al totale stampato: ricostruito {rebuilt_total:,.2f} "
                       f"contro {anchor:,.2f} (scarto {delta:,.2f} > {tol:,.2f})")

    # Il gate 1 misurava la sola colonna di sinistra. Il passivo la vision lo ha
    # trascritto e la coerenza interna lo ha gia' attraversato: non usarlo lasciava
    # scoperto l'unico modo in cui questo riscatto puo' produrre un foglio SBAGLIATO
    # invece che incompleto. Una sovra-lettura del passivo non si vede nello sbilancio,
    # perche' net_contra_accounts la assorbe cancellando debiti fino alla massa dei
    # fondi: il foglio torna a quadrare e il debito risulta sottostimato, senza un
    # avviso. Qui il totale ricostruito del passivo si misura contro quello stampato,
    # con la stessa tolleranza.
    if rebuilt_passivo is not None:
        anchor_pas = sec.totals.get("right")
        if anchor_pas and anchor_pas > 0:
            delta_pas = abs(anchor_pas - rebuilt_passivo)
            tol_pas = reconcile_tolerance(anchor_pas)
            if delta_pas > tol_pas:
                return False, (f"il passivo ricostruito non riconcilia al totale stampato: "
                               f"{rebuilt_passivo:,.2f} contro {anchor_pas:,.2f} "
                               f"(scarto {delta_pas:,.2f} > {tol_pas:,.2f})")

    if after.is_empty:
        return False, "il riscatto produce un'estrazione vuota"

    # Un riscatto che spegne l'identita' CE/SP non e' mai un miglioramento, per quanto
    # migliori i totali: e' l'utile che smette di essere un solo numero.
    if before.utile_match and not after.utile_match:
        return False, "il riscatto rompe l'identita' utile CE = sp13"

    before_bad = _badness(before)
    # Il residuo del foglio riscattato e' una MISURA solo quando esisteva un'ancora
    # indipendente contro cui farla. Senza (layer di testo illeggibile: le ancore
    # dichiarate sono vuote e il reconcile ricade sugli stessi totali letti in vision),
    # build_sp_from_vision ha ASSERITO zero e nessuno lo ha verificato. Un controllo
    # che manca non e' un controllo superato: si porta avanti il residuo di prima,
    # cosi' il cancello non puo' incassare un miglioramento che nessuno ha misurato.
    # Stessa regola di importers/reliability.py — UNRELIABLE vuole una contraddizione,
    # un controllo assente da' "derived", mai un verdetto positivo.
    after_plug = after.plug_residual if residual_measured else before.plug_residual
    after_bad = abs(after.sbilancio) + abs(after_plug)
    fixed_identity = after.utile_match and not before.utile_match
    if after_bad >= before_bad and not fixed_identity:
        return False, (f"non migliora la quadratura: sbilancio {before.sbilancio:,.2f} -> "
                       f"{after.sbilancio:,.2f}, residuo {before.plug_residual:,.2f} -> "
                       f"{after_plug:,.2f}")

    # Riparare l'identita' CE/SP e' un miglioramento reale, ma non e' una licenza
    # illimitata: senza un tetto, un riscatto che sistema sp13 e insieme sbilancia il
    # foglio di mezzo milione passerebbe, perche' il gate 1 misura la sola colonna di
    # sinistra e non vede il passivo. Il tetto e' la stessa tolleranza di riconciliazione
    # del gate 1, non una nuova.
    if fixed_identity:
        slack = reconcile_tolerance(after.totale_attivo or before.totale_attivo)
        if after_bad > before_bad + slack:
            return False, (f"ripara l'identita' utile CE = sp13 ma sbilancia il foglio: "
                           f"scarto complessivo {before_bad:,.2f} -> {after_bad:,.2f} "
                           f"(oltre {slack:,.2f})")

    return True, (f"riconcilia a {anchor:,.2f} (scarto {delta:,.2f}); sbilancio "
                  f"{before.sbilancio:,.2f} -> {after.sbilancio:,.2f}")

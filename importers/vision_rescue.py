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


def mastro_level_rows(rows: Sequence[VisionRow]) -> Tuple[VisionRow, ...]:
    """Tiene solo le righe al livello MASTRO: quelle il cui codice ha il minor numero
    di cifre fra quelle lette.

    I dettagli (codice piu' lungo) la vision li sbaglia — sono le righe con gli importi
    corrotti nel testo sorgente — e non servono, perche' il mastro porta gia' l'intero
    importo della voce. Il filtro e' deterministico e non si fida della sola obbedienza
    del modello alla regola 2 del prompt. Le righe senza codice (totali intercettati per
    errore) sono scartate.
    """
    digits = {}
    for idx, row in enumerate(rows):
        only = re.sub(r"\D", "", row.code or "")
        if only:
            digits[idx] = len(only)
    if not digits:
        return ()
    level = min(digits.values())
    return tuple(r for idx, r in enumerate(rows) if digits.get(idx) == level)


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
    return VisionSection(
        section=section,
        rows=mastro_level_rows(rows),
        totals={
            "left": parse_amount(parsed.totale_sinistra),
            "right": parse_amount(parsed.totale_destra),
            "utile": parse_amount(parsed.utile),
            "perdita": parse_amount(parsed.perdita),
        },
    )

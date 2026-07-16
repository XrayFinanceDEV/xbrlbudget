"""
Motore unico di leveling + quadratura IV-CEE.

Stadio CONDIVISO a valle delle 4 macro-aree (A sintetico / B dettaglio /
C contrapposte / OTHER). Il router e gli estrattori restano separati: ognuno
estrae le voci a modo suo, poi le fa passare DA QUI per:

  1. risolvere ogni voce al suo nodo nella gerarchia di legge IV-CEE
     (art. 2424/2425), quindi al suo LIVELLO (1=lettere, 2=romani, 3=arabi,
     4=lettere minuscole);
  2. aggregare al LIVELLO DI LEGGE (il campo DB sp01-18 / ce01-20), preferendo
     il totale di voce dichiarato e sommando i figli solo quando il totale manca
     (mai entrambi → niente doppio conteggio);
  3. verificare la QUADRATURA (Attivo = Passivo, utile CE = sp13) e segnalare i
     residui invece di tamponarli in silenzio.

L'unica fonte di verita e `data/iv_cee_tree.json`. Questo modulo non conosce i
gestionali ne i layout: classifica per DESCRIZIONE contro l'albero, cosi la
quadratura dipende dalla gerarchia di legge e vale per ogni bilancio, non per i
casi singoli.
"""
import json
import logging
import os
import re
import unicodedata
from decimal import Decimal
from typing import Callable, Dict, List, NamedTuple, Optional, Tuple

from calculations.ce_result import calculate_ce_result

logger = logging.getLogger(__name__)

_TREE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "data", "iv_cee_tree.json")


# ---------------------------------------------------------------------------
# Normalizzazione descrizioni
# ---------------------------------------------------------------------------
def normalize(text: str) -> str:
    """lowercase, accenti rimossi, punteggiatura→spazio, spazi compattati."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", str(text))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower()
    t = re.sub(r"[^a-z0-9/]+", " ", t)   # tieni '/' (utile per v/clienti, c/c)
    t = re.sub(r"\s+", " ", t).strip()
    return t


class Node(NamedTuple):
    path: str
    level: int
    side: Optional[str]        # 'attivo'|'passivo' per SP, None per CE
    statement: str             # 'bs'|'ce'
    db_field: Optional[str]
    is_legal_leaf: bool
    is_total: bool
    is_result: bool
    netting: bool
    scadenza: Optional[str]
    label: str
    aliases: Tuple[str, ...]   # normalizzati


# ---------------------------------------------------------------------------
# Caricamento albero + indice alias
# ---------------------------------------------------------------------------
_TREE: Optional[Dict] = None
_ALIAS_INDEX: List[Tuple[str, Node]] = []   # (alias_normalizzato, nodo), ordinato per lunghezza desc


def _build_node(raw: dict, statement: str) -> Node:
    aliases = tuple(normalize(a) for a in raw.get("aliases", []))
    return Node(
        path=raw["path"], level=raw["level"], side=raw.get("side"),
        statement=statement, db_field=raw.get("db_field"),
        is_legal_leaf=bool(raw.get("is_legal_leaf")),
        is_total=bool(raw.get("is_total")),
        is_result=bool(raw.get("is_result")),
        netting=bool(raw.get("netting")),
        scadenza=raw.get("scadenza"),
        label=raw.get("label", raw["path"]),
        aliases=aliases,
    )


def load_tree() -> Dict:
    global _TREE, _ALIAS_INDEX
    if _TREE is not None:
        return _TREE
    with open(_TREE_PATH, encoding="utf-8") as f:
        data = json.load(f)
    nodes: List[Node] = []
    nodes += [_build_node(r, "bs") for r in data["balance_sheet"]]
    nodes += [_build_node(r, "ce") for r in data["income_statement"]]
    idx: List[Tuple[str, Node]] = []
    for n in nodes:
        for a in n.aliases:
            if a:
                idx.append((a, n))
    # alias piu lunghi prima: un match piu specifico vince su uno generico
    idx.sort(key=lambda x: len(x[0]), reverse=True)
    _TREE = {"nodes": nodes, "raw": data}
    _ALIAS_INDEX = idx
    return _TREE


# ---------------------------------------------------------------------------
# Risolutore: descrizione -> nodo di legge
# ---------------------------------------------------------------------------
def resolve(desc: str, side: Optional[str] = None,
            statement: Optional[str] = None) -> Optional[Node]:
    """Mappa una descrizione al nodo IV-CEE piu specifico.

    Strategia (dal segnale piu forte): alias esatto -> alias contenuto nella
    descrizione (il piu lungo vince) -> None. `side`/`statement`, se dati,
    restringono il match (l'attivo e il passivo condividono lettere A/B/C/D).
    """
    load_tree()
    nd = normalize(desc)
    if not nd:
        return None

    def ok(n: Node) -> bool:
        if statement and n.statement != statement:
            return False
        if side and n.side and n.side != side:
            return False
        return True

    # 1. match esatto
    for alias, node in _ALIAS_INDEX:
        if ok(node) and nd == alias:
            return node
    # 2. alias contenuto come parola/sequenza nella descrizione (piu lungo vince)
    for alias, node in _ALIAS_INDEX:
        if ok(node) and alias in nd:
            return node
    return None


# ---------------------------------------------------------------------------
# Adattatore per _be_reclassify (situazione_contabile_parser)
# ---------------------------------------------------------------------------
def classify_for_reclassify(desc: str, side: Optional[str] = None) -> Tuple[Optional[str], bool]:
    """Contratto richiesto da `_be_reclassify`: (db_field, specific).

    specific=True  -> ferma la discesa: la descrizione mappa a un campo DB foglia.
    specific=False -> nodo generico (Immobilizzazioni, Crediti, Debiti, PN, ...):
                      scendi nei figli per dettagliare.
    (None, False)  -> non classificabile a questo livello.
    """
    node = resolve(desc, side=side, statement="bs")
    if node is None:
        return None, False
    if node.netting:
        # i fondi vanno nettati dall'attivo: trattali come "specifici" col segno
        # gestito a monte dal chiamante (qui restituiamo il campo generico None).
        return None, True
    if node.db_field and node.is_legal_leaf and not node.is_total:
        return node.db_field, True
    # nodo-totale generico: lascia scendere
    return node.db_field, False


# ---------------------------------------------------------------------------
# Aggregazione "flat" (aree A/B/XBRL: voci gia al livello di legge)
# ---------------------------------------------------------------------------
class AggResult(NamedTuple):
    bs: Dict[str, Decimal]
    ce: Dict[str, Decimal]
    declared_totals: Dict[str, Decimal]   # totali di sezione dichiarati (per riconciliazione)
    unresolved: List[Tuple[str, Decimal]]  # voci non classificate (descr, importo)
    notes: List[str]


def _D(x) -> Decimal:
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


def aggregate_flat(items: List[dict]) -> AggResult:
    """Aggrega voci gia espresse al livello di legge (un importo per voce).

    Ogni item: {"desc": str, "amount": number, "side": 'attivo'|'passivo'|None,
                "scadenza": 'entro'|'oltre'|None}.
    Regola anti-doppio-conteggio: i nodi `is_total` (Immobilizzazioni, Attivo
    circolante, Crediti, Patrimonio netto, Debiti) NON entrano nella somma —
    sono registrati a parte per la riconciliazione; entrano solo le foglie legali.
    """
    load_tree()
    bs: Dict[str, Decimal] = {}
    ce: Dict[str, Decimal] = {}
    declared: Dict[str, Decimal] = {}
    unresolved: List[Tuple[str, Decimal]] = []
    notes: List[str] = []

    for it in items:
        desc = it.get("desc", "")
        amt = _D(it.get("amount", 0))
        side = it.get("side")
        scad = it.get("scadenza")
        node = resolve(desc, side=side)
        if node is None:
            if amt != 0:
                unresolved.append((desc, amt))
            continue
        if node.is_total and not node.is_legal_leaf:
            declared[node.path] = declared.get(node.path, Decimal(0)) + amt
            continue
        field = node.db_field
        if field is None:
            continue
        # scadenza esplicita ridirige crediti/debiti sul campo entro/oltre giusto
        if scad and node.statement == "bs":
            field = _apply_scadenza(field, scad)
        target = bs if node.statement == "bs" else ce
        target[field] = target.get(field, Decimal(0)) + amt

    return AggResult(bs=bs, ce=ce, declared_totals=declared,
                     unresolved=unresolved, notes=notes)


_ENTRO_OLTRE = {
    "sp06_crediti_breve": ("sp06_crediti_breve", "sp07_crediti_lungo"),
    "sp07_crediti_lungo": ("sp06_crediti_breve", "sp07_crediti_lungo"),
    "sp16_debiti_breve": ("sp16_debiti_breve", "sp17_debiti_lungo"),
    "sp17_debiti_lungo": ("sp16_debiti_breve", "sp17_debiti_lungo"),
}


def _apply_scadenza(field: str, scad: str) -> str:
    pair = _ENTRO_OLTRE.get(field)
    if not pair:
        return field
    return pair[0] if scad == "entro" else pair[1]


# ---------------------------------------------------------------------------
# Quadratura
# ---------------------------------------------------------------------------
_ATTIVO_FIELDS = ["sp01_crediti_soci", "sp02_immob_immateriali", "sp03_immob_materiali",
                  "sp04_immob_finanziarie", "sp05_rimanenze", "sp06_crediti_breve",
                  "sp07_crediti_lungo", "sp08_attivita_finanziarie", "sp09_disponibilita_liquide",
                  "sp10_ratei_risconti_attivi"]
_PASSIVO_FIELDS = ["sp11_capitale", "sp12_riserve", "sp13_utile_perdita", "sp14_fondi_rischi",
                   "sp15_tfr", "sp16_debiti_breve", "sp17_debiti_lungo", "sp18_ratei_risconti_passivi"]


class Quadratura(NamedTuple):
    totale_attivo: Decimal
    totale_passivo: Decimal
    sbilancio: Decimal          # attivo - passivo
    quadra: bool
    utile_ce: Optional[Decimal]
    sp13: Decimal
    utile_match: bool
    plug_residual: Decimal      # massa non classificata tamponata in sp09/sp16
    masked: bool                # quadra solo grazie al plug (composizione errata)
    is_empty: bool              # estrazione vuota/nulla (totale attivo ~ 0) → NON quadra
    hierarchy_consistent: bool  # aggregati e dettagli IV-CEE coincidono
    hierarchy_differences: Dict[str, Decimal]
    semantic_valid: bool        # tutti gli invarianti richiesti per uso downstream
    warnings: List[str]


# soglia oltre cui un plug rende la quadratura "mascherata" (composizione materialmente errata)
_MASK_PCT = Decimal("0.01")     # 1% del totale attivo


# Aggregate/detail relationships used by forecasts, cash flow and Rettifiche.  A
# positive aggregate with zero details is intentionally reported: it may be legal
# in an abbreviated source, but it is not safe to silently invent the breakdown
# required by downstream calculations.
_DETAIL_GROUPS: Dict[str, Tuple[str, ...]] = {
    "sp01_crediti_soci": ("sp01a_parte_richiamata", "sp01b_parte_da_richiamare"),
    "sp02_immob_immateriali": (
        "sp02a_costi_impianto", "sp02b_costi_sviluppo", "sp02c_brevetti",
        "sp02d_concessioni", "sp02e_avviamento", "sp02f_immob_in_corso",
        "sp02g_altre_immob_imm",
    ),
    "sp03_immob_materiali": (
        "sp03a_terreni_fabbricati", "sp03b_impianti_macchinari",
        "sp03c_attrezzature", "sp03d_altri_beni", "sp03e_immob_in_corso",
    ),
    "sp04_immob_finanziarie": (
        "sp04a_partecipazioni", "sp04b_crediti_immob_breve",
        "sp04c_crediti_immob_lungo", "sp04d_altri_titoli",
        "sp04e_strumenti_derivati_attivi",
    ),
    "sp05_rimanenze": (
        "sp05a_materie_prime", "sp05b_prodotti_in_corso",
        "sp05c_lavori_in_corso", "sp05d_prodotti_finiti", "sp05e_acconti",
    ),
    "sp06_crediti_breve": (
        "sp06a_crediti_clienti_breve", "sp06b_crediti_controllate_breve",
        "sp06c_crediti_collegate_breve", "sp06d_crediti_controllanti_breve",
        "sp06e_crediti_tributari_breve", "sp06f_imposte_anticipate_breve",
        "sp06g_crediti_altri_breve",
    ),
    "sp07_crediti_lungo": (
        "sp07a_crediti_clienti_lungo", "sp07b_crediti_controllate_lungo",
        "sp07c_crediti_collegate_lungo", "sp07d_crediti_controllanti_lungo",
        "sp07e_crediti_tributari_lungo", "sp07f_imposte_anticipate_lungo",
        "sp07g_crediti_altri_lungo",
    ),
    "sp12_riserve": (
        "sp12a_riserva_sovrapprezzo", "sp12b_riserve_rivalutazione",
        "sp12c_riserva_legale", "sp12d_riserve_statutarie",
        "sp12e_altre_riserve", "sp12f_riserva_copertura_flussi",
        "sp12g_utili_perdite_portati", "sp12h_riserva_neg_azioni_proprie",
    ),
    "sp14_fondi_rischi": (
        "sp14a_fondi_trattamento_quiescenza", "sp14b_fondi_imposte",
        "sp14c_strumenti_derivati_passivi", "sp14d_altri_fondi",
    ),
    "sp16_debiti_breve": (
        "sp16a_debiti_banche_breve", "sp16b_debiti_altri_finanz_breve",
        "sp16c_debiti_obbligazioni_breve", "sp16d_debiti_fornitori_breve",
        "sp16e_debiti_tributari_breve", "sp16f_debiti_previdenza_breve",
        "sp16g_altri_debiti_breve",
    ),
    "sp17_debiti_lungo": (
        "sp17a_debiti_banche_lungo", "sp17b_debiti_altri_finanz_lungo",
        "sp17c_debiti_obbligazioni_lungo", "sp17d_debiti_fornitori_lungo",
        "sp17e_debiti_tributari_lungo", "sp17f_debiti_previdenza_lungo",
        "sp17g_altri_debiti_lungo",
    ),
}

_CE_DETAIL_GROUPS: Dict[str, Tuple[str, ...]] = {
    "ce08_costi_personale": (
        "ce08a_tfr_accrual", "ce08b_salari_stipendi", "ce08c_oneri_sociali",
        "ce08d_altri_costi_personale",
    ),
    "ce09_ammortamenti": (
        "ce09a_ammort_immateriali", "ce09b_ammort_materiali",
        "ce09c_svalutazioni", "ce09d_svalutazione_crediti",
    ),
}


def _aggregate_detail_differences(
    bs: Dict[str, Decimal], ce: Optional[Dict[str, Decimal]], tol: Decimal
) -> Dict[str, Decimal]:
    """Return aggregate minus detail for every inconsistent IV-CEE family."""
    differences: Dict[str, Decimal] = {}
    for aggregate, details in _DETAIL_GROUPS.items():
        aggregate_value = _D(bs.get(aggregate, 0))
        detail_value = sum((_D(bs.get(k, 0)) for k in details), Decimal(0))
        diff = aggregate_value - detail_value
        if abs(diff) > tol:
            differences[aggregate] = diff

    if ce:
        for aggregate, details in _CE_DETAIL_GROUPS.items():
            aggregate_value = _D(ce.get(aggregate, 0))
            detail_value = sum((_D(ce.get(k, 0)) for k in details), Decimal(0))
            diff = aggregate_value - detail_value
            if abs(diff) > tol:
                differences[aggregate] = diff

        d_detail = _D(ce.get("ce17a_rivalutazioni", 0)) - _D(
            ce.get("ce17b_svalutazioni", 0)
        )
        d_aggregate = _D(ce.get("ce17_rettifiche_attivita_fin", 0))
        if (d_detail != 0 or d_aggregate != 0) and abs(d_aggregate - d_detail) > tol:
            differences["ce17_rettifiche_attivita_fin"] = d_aggregate - d_detail
    return differences


def check_quadratura(bs: Dict[str, Decimal], ce: Optional[Dict[str, Decimal]] = None,
                     tol: Decimal = Decimal("0.01")) -> Quadratura:
    att = sum((_D(bs.get(k, 0)) for k in _ATTIVO_FIELDS), Decimal(0))
    pas = sum((_D(bs.get(k, 0)) for k in _PASSIVO_FIELDS), Decimal(0))
    sbil = att - pas
    warnings: List[str] = []

    # Estrazione vuota/nulla: un bilancio reale non ha mai attivo == 0. Senza questo
    # controllo att==pas==0 darebbe sbilancio 0 → "quadra" (falso positivo che nasconde
    # le estrazioni vuote dei parser C — es. AITEC PROVVISORIO). Un vuoto NON quadra.
    is_empty = att <= tol and pas <= tol
    if is_empty:
        warnings.append(f"ESTRAZIONE VUOTA: attivo {att:,.2f} / passivo {pas:,.2f} ~ 0 "
                        f"— nessun dato estratto (NON quadra)")
    elif abs(sbil) > tol:
        warnings.append(f"BILANCIO NON QUADRATO: attivo {att:,.2f} != passivo {pas:,.2f} "
                        f"(sbilancio {sbil:,.2f})")

    # Anti-masking: _plug_residual (esposto dall'estrattore) misura la massa della fonte NON
    # classificata in alcuna voce IV-CEE. Nessun plug viene applicato — il bilancio resta come
    # estratto — ma un att==pas ottenuto con una quota rilevante di massa non spiegata e una
    # quadratura solo apparente: se il residuo supera l'1% del totale la composizione e
    # materialmente inaffidabile, quale che sia lo sbilancio.
    plug = abs(_D(bs.get("_plug_residual", 0)))
    masked = False
    if att > 0 and plug > max(tol, _MASK_PCT * att):
        masked = True
        warnings.append(f"QUADRATURA MASCHERATA: residuo {plug:,.2f} ({100 * plug / att:.1f}% "
                        f"del totale) non classificato — composizione non affidabile")

    utile_ce = None
    utile_match = True
    if ce:
        utile_ce = _net_profit_from_ce(ce)
        sp13 = _D(bs.get("sp13_utile_perdita", 0))
        # Tolleranza SEPARATA (e più larga) per l'utile: lo SP è ancorato dal pareggio,
        # mentre l'utile CE è RICOSTRUITO sommando ~25 voci estratte da un pass LLM
        # indipendente — uno scarto di pochi euro su un bilancio in euro interi è rumore,
        # non un errore di composizione. Scala con la dimensione del bilancio (0.1% del
        # totale attivo, minimo €2). NON tocca la tolleranza del pareggio Attivo==Passivo.
        utile_tol = max(Decimal("2"), att * Decimal("0.001"))
        if abs(utile_ce - sp13) > utile_tol:
            utile_match = False
            warnings.append(f"Utile CE {utile_ce:,.2f} != sp13 {sp13:,.2f} "
                            f"(diff {utile_ce - sp13:,.2f})")

    hierarchy_differences = _aggregate_detail_differences(bs, ce, tol)
    hierarchy_consistent = not hierarchy_differences
    for aggregate, diff in hierarchy_differences.items():
        warnings.append(
            f"GERARCHIA INCOERENTE: {aggregate} differisce dalla somma dettagli "
            f"di {diff:,.2f}"
        )

    # ``quadra`` retains its public name but is no longer allowed to hide a CE/SP
    # mismatch.  ``semantic_valid`` is the stronger downstream gate and also
    # requires the typed hierarchy used by forecasts and cash-flow calculations.
    quadra = abs(sbil) <= tol and utile_match and not masked and not is_empty
    semantic_valid = quadra and hierarchy_consistent and plug <= tol
    return Quadratura(totale_attivo=att, totale_passivo=pas, sbilancio=sbil,
                      quadra=quadra, utile_ce=utile_ce,
                      sp13=_D(bs.get("sp13_utile_perdita", 0)),
                      utile_match=utile_match, plug_residual=plug, masked=masked,
                      is_empty=is_empty, hierarchy_consistent=hierarchy_consistent,
                      hierarchy_differences=hierarchy_differences,
                      semantic_valid=semantic_valid, warnings=warnings)


def _net_profit_from_ce(ce: Dict[str, Decimal]) -> Decimal:
    """Compatibility wrapper around the single canonical CE formula."""
    return calculate_ce_result(ce).net_profit


# Derived aggregates whose value is, by definition, the sum of their legal
# sub-details. The IV-CEE schema (art. 2424) lists every debt sub-type under
# D) with an entro/oltre split but prints NO "totale debiti a breve/lungo"
# subtotal, so sp16/sp17 are always derived — never a source line. Only debiti
# are rolled up (as in the XBRL parser): for these the source always enumerates
# all sub-types, so the detail sum is authoritative. Crediti/riserve details can
# be partial, so their aggregates are left to the extractor.
_ROLLUP_AGGREGATES: Tuple[str, ...] = ("sp16_debiti_breve", "sp17_debiti_lungo")


def rollup_debiti_aggregates(bs: Dict[str, Decimal]) -> Dict[str, Decimal]:
    """Realign each debiti aggregate to its sub-detail sum, but only when doing so
    moves the balance sheet CLOSER to balancing.

    Returns a modified COPY. The aggregate (sp16/sp17) is a schema-derived total
    with no source line, so aligning it to its extracted parts introduces no
    invented amount. But the stochastic LLM can be wrong on EITHER side — a good
    aggregate with over-extracted details, or a good detail set with a drifted
    aggregate — so a blind rollup would unbalance a year that already tied
    (budget_585 current 2025: raw extraction balanced, a naive rollup broke it by
    ~127k). The self-validating guard keeps a change only if |attivo - passivo|
    does not grow: it fixes the drifted-aggregate case (585 prior 2024) without
    touching the drifted-detail case. Fires only when the details carry a
    non-zero sum (an aggregate with no details is a legal leaf, left untouched).
    """
    result = dict(bs)
    att = sum((_D(result.get(k, 0)) for k in _ATTIVO_FIELDS), Decimal(0))
    gap = att - sum((_D(result.get(k, 0)) for k in _PASSIVO_FIELDS), Decimal(0))
    for aggregate in _ROLLUP_AGGREGATES:
        details = _DETAIL_GROUPS.get(aggregate, ())
        detail_sum = sum((_D(result.get(k, 0)) for k in details), Decimal(0))
        current = _D(result.get(aggregate, 0))
        if detail_sum == 0 or abs(detail_sum - current) <= Decimal("0.01"):
            continue
        # Rolling up changes passivo by (detail_sum - current), so the signed gap
        # (attivo - passivo) shifts by (current - detail_sum). Keep it only if the
        # magnitude of the imbalance does not increase.
        new_gap = gap + (current - detail_sum)
        if abs(new_gap) <= abs(gap):
            result[aggregate] = detail_sum
            gap = new_gap
    return result


def reconcile_ivcee_balance(bs: Dict[str, Decimal],
                            declared: Optional[Dict[str, Optional[Decimal]]] = None,
                            label: str = "", cap_frac: Decimal = Decimal("0.05")
                            ) -> Dict[str, Decimal]:
    """Return an unchanged copy and report, but never plug, a balance difference.

    ``cap_frac`` is retained for API compatibility only.  Earlier versions inserted
    the short side in cash or short debt; that made a missing source row look like an
    accounting fact.  Candidate selection and validation may use the declared total,
    but reconciliation is now strictly diagnostic.
    """
    result = dict(bs)
    att = sum((_D(bs.get(k, 0)) for k in _ATTIVO_FIELDS), Decimal(0))
    pas = sum((_D(bs.get(k, 0)) for k in _PASSIVO_FIELDS), Decimal(0))
    gap = att - pas
    declared_attivo = (
        _D(declared.get("attivo")) if declared and declared.get("attivo") is not None else None
    )
    if abs(gap) > Decimal("0.01"):
        result["_unexplained_balance_difference"] = gap
        logger.warning(
            f"[{label}] IV-CEE non quadrato: attivo {att:,.2f}, passivo {pas:,.2f}, "
            f"differenza {gap:,.2f}; nessun valore contabile è stato modificato"
        )
    if declared_attivo is not None and abs(att - declared_attivo) > Decimal("0.01"):
        result["_declared_assets_difference"] = att - declared_attivo
    return result


def enforce_ce_sp_identity(bs: Dict[str, Decimal], ce: Optional[Dict[str, Decimal]],
                           label: str = "", tol: Optional[Decimal] = None,
                           prefer: str = "sp13",
                           declared: Optional[Dict[str, Optional[Decimal]]] = None
                           ) -> Dict[str, Decimal]:
    """Diagnose the CE/SP identity without altering either statement.

    ``prefer`` and ``declared`` remain accepted so existing callers do not break,
    but an arbiter may only select/reject a candidate.  It must never create a
    balancing amount in reserves, other income or other costs.
    """
    if not ce:
        return ce
    result = dict(ce)
    sp13 = _D(bs.get("sp13_utile_perdita", 0))
    ce_result = _net_profit_from_ce(ce)
    gap = ce_result - sp13
    if tol is None:
        tol = max(Decimal("2"), abs(sp13) * Decimal("0.001"))
    if abs(gap) > tol:
        result["_ce_sp_difference"] = gap
        logger.warning(
            f"[{label}] CE↔SP incoerente: utile CE {ce_result:,.2f}, sp13 {sp13:,.2f}, "
            f"differenza {gap:,.2f}; nessuna voce CE/SP è stata modificata"
        )

    if declared:
        declared_result = declared.get("utile")
        if declared_result is None and declared.get("perdita") is not None:
            declared_result = -_D(declared.get("perdita"))
        if declared_result is not None:
            result["_declared_result_difference_ce"] = ce_result - _D(declared_result)
            result["_declared_result_difference_sp"] = sp13 - _D(declared_result)
    return result


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    load_tree()
    samples = [
        ("Immobilizzazioni materiali", "attivo", "sp03_immob_materiali"),
        ("Totale immobilizzazioni", "attivo", None),            # totale -> generico
        ("Crediti verso clienti", "attivo", "sp06_crediti_breve"),
        ("Disponibilità liquide", "attivo", "sp09_disponibilita_liquide"),
        ("Capitale sociale", "passivo", "sp11_capitale"),
        ("Riserva legale", "passivo", "sp12_riserve"),
        ("Utile dell'esercizio", "passivo", "sp13_utile_perdita"),
        ("Debiti verso fornitori", "passivo", "sp16_debiti_breve"),
        ("T.F.R.", "passivo", "sp15_tfr"),
        ("Ricavi delle vendite e delle prestazioni", None, "ce01_ricavi_vendite"),
        ("Per servizi", None, "ce06_servizi"),
        ("Interessi e altri oneri finanziari", None, "ce15_oneri_finanziari"),
        ("Imposte sul reddito dell'esercizio", None, "ce20_imposte"),
        ("Fabbricati industriali", "attivo", None),             # sotto-conto: non classificato
    ]
    ok = 0
    for desc, side, expect in samples:
        n = resolve(desc, side=side)
        got = n.db_field if n else None
        flag = "OK " if got == expect else "XX "
        if got == expect:
            ok += 1
        print(f"{flag}{desc:48s} side={str(side):7s} -> {got}  (atteso {expect})")
    print(f"\n{ok}/{len(samples)} risolti correttamente")

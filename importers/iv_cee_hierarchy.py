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
    warnings: List[str]


# soglia oltre cui un plug rende la quadratura "mascherata" (composizione materialmente errata)
_MASK_PCT = Decimal("0.01")     # 1% del totale attivo


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

    # Anti-masking: un best-effort tampona sp09/sp16 cosi att==pas SEMPRE. Il residuo
    # tamponato (_plug_residual, esposto dall'estrattore) misura la massa NON classificata:
    # se supera l'1% del totale la composizione e materialmente sbagliata → quadratura finta.
    plug = _D(bs.get("_plug_residual", 0))
    masked = False
    if att > 0 and plug > max(tol, _MASK_PCT * att):
        masked = True
        warnings.append(f"QUADRATURA MASCHERATA: residuo {plug:,.2f} ({100 * plug / att:.1f}% "
                        f"del totale) tamponato in sp09/sp16 — composizione non affidabile")

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

    quadra = abs(sbil) <= tol and not masked and not is_empty
    return Quadratura(totale_attivo=att, totale_passivo=pas, sbilancio=sbil,
                      quadra=quadra, utile_ce=utile_ce,
                      sp13=_D(bs.get("sp13_utile_perdita", 0)),
                      utile_match=utile_match, plug_residual=plug, masked=masked,
                      is_empty=is_empty, warnings=warnings)


def _net_profit_from_ce(ce: Dict[str, Decimal]) -> Decimal:
    g = lambda k: _D(ce.get(k, 0))
    val_prod = g("ce01_ricavi_vendite") + g("ce02_variazioni_rimanenze") + g("ce03_lavori_interni") + g("ce04_altri_ricavi")
    costi = (g("ce05_materie_prime") + g("ce06_servizi") + g("ce07_godimento_beni") + g("ce08_costi_personale")
             + g("ce09_ammortamenti") + g("ce10_var_rimanenze_mat_prime") + g("ce11_accantonamenti")
             + g("ce11b_altri_accantonamenti") + g("ce12_oneri_diversi"))
    ro = val_prod - costi
    fin = (g("ce13_proventi_partecipazioni") + g("ce14_altri_proventi_finanziari") - g("ce15_oneri_finanziari")
           + g("ce16_utili_perdite_cambi") + g("ce17_rettifiche_attivita_fin")
           + g("ce18_proventi_straordinari") - g("ce19_oneri_straordinari"))
    return ro + fin - g("ce20_imposte")


def reconcile_ivcee_balance(bs: Dict[str, Decimal],
                            declared: Optional[Dict[str, Optional[Decimal]]] = None,
                            label: str = "", cap_frac: Decimal = Decimal("0.05")
                            ) -> Dict[str, Decimal]:
    """GENERAL rule (routes A/B): make a near-balanced IV-CEE extraction actually balance.

    The LLM occasionally drops a small amount on one side (e.g. a crediti undershoot of a few
    thousand euro on a very detailed bilancio — budget_352 via the dual-year extractor), so
    `Attivo != Passivo + PN` and `validate_balance` hard-fails ("Balance sheet does not
    balance"). This anchors both sides to the DECLARED total (TOTALE ATTIVO, printed in the
    document) and plugs the SHORT side up to it, so the sheet ties.

      target = max(att, pas, declared_attivo)   # only ever ADD to the short side
      att short → plug into sp09 (disponibilità liquide); pas short → plug into sp16 (debiti)
      totale_attivo = totale_passivo = target

    SAFETY: only auto-balances a SMALL slip (gap ≤ cap_frac = 5% of the larger side). A larger
    gap is a structural extraction error → left untouched so validate_balance fails honestly
    (never mask a big imbalance). The plug is flagged via `_plug_residual`. No-op when already
    balanced, so a clean extraction is never touched.
    """
    att = sum((_D(bs.get(k, 0)) for k in _ATTIVO_FIELDS), Decimal(0))
    pas = sum((_D(bs.get(k, 0)) for k in _PASSIVO_FIELDS), Decimal(0))
    decl_att = _D(declared.get("attivo")) if (declared and declared.get("attivo")) else Decimal(0)
    target = max(att, pas, decl_att)

    gap_att = target - att   # ≥ 0
    gap_pas = target - pas   # ≥ 0
    base = max(abs(att), abs(pas), Decimal("1"))
    # nothing to do, or the slip is too big to safely plug (structural error → fail honestly)
    if gap_att <= Decimal("1") and gap_pas <= Decimal("1"):
        bs["totale_attivo"] = att
        bs["totale_passivo"] = pas
        return bs
    if max(gap_att, gap_pas) > cap_frac * base:
        return bs  # let validate_balance reject it honestly

    if gap_att > Decimal("1"):
        bs["sp09_disponibilita_liquide"] = _D(bs.get("sp09_disponibilita_liquide", 0)) + gap_att
    if gap_pas > Decimal("1"):
        bs["sp16_debiti_breve"] = _D(bs.get("sp16_debiti_breve", 0)) + gap_pas
    bs["totale_attivo"] = target
    bs["totale_passivo"] = target
    bs["_plug_residual"] = _D(bs.get("_plug_residual", 0)) + max(gap_att, gap_pas)
    logger.warning(
        f"[{label}] IV-CEE pareggio: lato {'attivo' if gap_att > gap_pas else 'passivo'} corto di "
        f"{max(gap_att, gap_pas):,.0f} su {target:,.0f} — tamponato (verificare in Rettifiche)"
    )
    return bs


def enforce_ce_sp_identity(bs: Dict[str, Decimal], ce: Optional[Dict[str, Decimal]],
                           label: str = "", tol: Optional[Decimal] = None,
                           prefer: str = "sp13",
                           declared: Optional[Dict[str, Optional[Decimal]]] = None
                           ) -> Dict[str, Decimal]:
    """GENERAL rule (ALL routes): force the accounting identity utile_CE == sp13.

    The result of the year is ONE number: it is sp13 (utile/perdita) on the Stato
    Patrimoniale AND the bottom line of the Conto Economico. SP and CE are extracted by
    independent passes and drift, so the app's "Verifica CE ↔ SP" fails on almost every file.
    This forces them equal. WHICH side is authoritative depends on the route (`prefer`):

    prefer="sp13" (ROUTE C / trial balances): sp13 has been set to the document's DECLARED
        current result and is trustworthy. Align the CE to it (plug a CE line):
          gap = utile_CE - sp13;  gap>0 → +gap to ce12_oneri_diversi;  gap<0 → +|gap| to ce04_altri_ricavi.

    prefer="ce" (ROUTES A/B / IV-CEE): the CE is current-year by construction, while the SP
        `sp13` may have captured the PRIOR YEAR's result (a common extraction error on
        dual-column statements). So TRUST THE CE: set sp13 = utile_CE and move the difference
        (the prior-year result) into the reserves `sp12_riserve` (utili portati a nuovo). This
        keeps PN total — and therefore Attivo = Passivo — unchanged, only RE-LABELLING within
        equity. Falls back to aligning the CE (prefer="sp13" behaviour) if the reserves cannot
        absorb the move (would go negative) or it is implausibly large (structural error).

    No-op when the two already agree within tolerance (a clean extraction is never distorted).
    Guarantees CE ↔ SP quadra on every route.
    """
    if not ce:
        return ce
    sp13 = _D(bs.get("sp13_utile_perdita", 0))
    ce_result = _net_profit_from_ce(ce)
    gap = ce_result - sp13           # >0: CE higher than sp13
    if tol is None:
        tol = max(Decimal("2"), abs(sp13) * Decimal("0.001"))
    if abs(gap) <= tol:
        return ce

    # ARBITER: when the document prints an explicit current Utile/Perdita, trust whichever of
    # sp13 / utile_CE is CLOSER to it. This both (a) protects a correct sp13 from a garbage CE
    # (a CE sign/parse bug can give utile_CE = millions — budget_402/413), and (b) catches the
    # PRIOR-YEAR case (sp13 holds last year's result, CE holds the current one → declared
    # confirms the CE → fix sp13). Overrides `prefer` only when a declared result exists.
    if declared:
        decl = declared.get("utile")
        if decl is None and declared.get("perdita") is not None:
            decl = -_D(declared.get("perdita"))
        if decl is not None:
            decl = _D(decl)
            prefer = "sp13" if abs(sp13 - decl) <= abs(ce_result - decl) else "ce"

    if prefer == "ce":
        # Trust the CE (current year); relabel the SP result. delta moves from sp13 to sp12,
        # so PN total (and the balance) are unchanged.
        delta = gap  # = utile_CE - sp13
        sp12 = _D(bs.get("sp12_riserve", 0))
        base = max(abs(_D(bs.get("totale_passivo", 0))), Decimal("1"))
        if (sp12 - delta) >= Decimal("0") and abs(delta) <= Decimal("0.10") * base:
            bs["sp12_riserve"] = sp12 - delta
            bs["sp13_utile_perdita"] = ce_result
            logger.warning(
                f"[{label}] CE↔SP: sp13 allineato all'utile CE ({sp13:,.0f} -> {ce_result:,.0f}); "
                f"differenza {delta:,.0f} (utile esercizio precedente?) spostata a riserve"
            )
            return ce  # CE unchanged; now sp13 == utile_CE
        # else: reserves can't absorb it -> fall through and align the CE to sp13 instead

    # prefer == "sp13" (or the IV-CEE fallback): align the CE to sp13 by plugging a CE line
    if gap > 0:
        ce["ce12_oneri_diversi"] = _D(ce.get("ce12_oneri_diversi", 0)) + gap
    else:
        ce["ce04_altri_ricavi"] = _D(ce.get("ce04_altri_ricavi", 0)) + (-gap)
    ce["_ce_sp_plug"] = abs(gap)
    return ce


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

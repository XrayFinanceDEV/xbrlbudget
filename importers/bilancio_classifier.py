"""
Classificatore di tipologia bilancio (router per macro-area).

Dato un PDF (o il suo testo), individua la MACRO-AREA e quindi la ROTTA di
estrazione corretta, in modo che ogni file venga aperto con le regole giuste
e il pareggio Attivo = Passivo non salti.

Tre macro-aree (vedi Test/IMPORT-ROUTING-TAXONOMY.md):
  A — bilancio sintetico in IV CEE        → solo voci di legge, nessun conto CoGe
  B — dettagliato con macrovoci in IV CEE → scheletro IV CEE + sottoconti
  C — verifica a sezioni contrapposte      → conti CoGe Dare/Avere o Saldo, no schema di legge

Regole di rotta (il punto che protegge il pareggio):
  - C  → ROUTE_TRIAL: parser deterministico situazione_contabile (pareggio via
         "TOTALE A PAREGGIO" + riclassifica per descrizione, residuo plug+flag).
  - A/B → ROUTE_IVCEE: estrattore ancorato ai TOTALI DI VOCE IV CEE. Entrambe le
         aree hanno i totali di voce, quindi la stessa estrazione tiene il pareggio;
         in B i sottoconti di dettaglio vanno ignorati (si leggono i totali di voce).
  - XBRL nativo (.xbrl/.xml) → ROUTE_XBRL (parser XBRL, non il ramo PDF).
  - Non un bilancio completo (solo CE, nessun prospetto) → ROUTE_UNSUPPORTED:
         errore onesto, mai un plug silenzioso.

Il modulo è volutamente leggero (solo regex + i detector esistenti) così da poter
essere usato sia in import sia in test offline sui dump di testo.
"""

import os
import re
from typing import Optional, NamedTuple, Dict

# --- macro-aree ---
MACRO_A = "A"
MACRO_B = "B"
MACRO_C = "C"
MACRO_OTHER = "OTHER"

# --- rotte di estrazione ---
ROUTE_IVCEE = "IVCEE"            # A o B: estrattore IV CEE ancorato ai totali di voce
ROUTE_TRIAL = "TRIAL_BALANCE"    # C: parser deterministico situazione contabile
ROUTE_XBRL = "XBRL_NATIVE"       # file .xbrl/.xml: parser XBRL
ROUTE_UNSUPPORTED = "UNSUPPORTED"  # non importabile come bilancio completo


class Classification(NamedTuple):
    macro_area: str
    subcategory: str
    route: str
    gestionale: str
    confidence: str           # "high" | "med" | "low"
    signals: Dict[str, object]
    reason: str


# ---------------------------------------------------------------------------
# Segnali
# ---------------------------------------------------------------------------
def compute_signals(text: str, file_path: Optional[str] = None) -> Dict[str, object]:
    low = text.lower()
    # variante "senza spazi": rende i marker robusti alle intestazioni scritte
    # lettera-spaziata ("S T A T O  P A T R I M O N I A L E"), comuni in questi PDF.
    nos = re.sub(r"\s+", "", low)

    def has(marker_spaced: str) -> bool:
        """True se il marker compare nel testo normale o nella variante senza spazi."""
        return (marker_spaced in low) or (marker_spaced.replace(" ", "") in nos)

    s: Dict[str, object] = {}

    # marker forti
    s["itcc"] = ("itcc-ci-" in nos) or has("conforme alla tassonomia") or has("generato automaticamente")
    s["pareggio"] = has("totale a pareggio")
    s["verifica"] = has("bilancio di verifica")
    s["sit_contabile"] = has("situazione contabile")
    s["riclassificata"] = "riclassificat" in nos          # "riclassificata dettagliata" (B) / "riclassificato abbreviato"
    s["ago_xbrl"] = has("bilancio schema xbrl") or bool(re.search(r"\bago\s*-\s*\d", low))
    s["dettaglio"] = bool(re.search(r"dettaglio\s+(sottoconti|conti|voci)|con\s+dettaglio", low)) or \
        ("dettagliosottoconti" in nos) or ("dettaglioconti" in nos) or ("dettagliovoci" in nos)
    s["prospetto_economico"] = has("prospetto economico")

    # scheletro di legge IV CEE
    s["valore_produzione"] = has("valore della produzione")
    s["immobilizzazioni"] = "immobilizzazioni" in nos
    s["stato_patrimoniale"] = has("stato patrimoniale")
    s["conto_economico"] = has("conto economico")
    s["totale_attivo"] = bool(re.search(r"totale\s+attivo", low)) or ("totaleattivo" in nos)
    _voci = r"(immobilizzazioni|attivo|passivo|valoredellaproduzione|costidellaproduzione|crediti|debiti|rimanenze)"
    s["totale_voce"] = len(re.findall(r"totale" + _voci, nos))
    s["legal_skeleton"] = bool(s["valore_produzione"] and s["immobilizzazioni"])

    # presenza di una sezione PATRIMONIALE (per distinguere un documento SOLO economico).
    # Conservativo: basta UNO qualsiasi di questi marker patrimoniali per dire "ha lo SP".
    # NB: niente "rimanenze" qui — "variazione delle rimanenze" è una voce di CONTO
    # ECONOMICO, quindi non è un marker patrimoniale affidabile (regge 196/335 solo-CE).
    s["sp_present"] = bool(
        s["stato_patrimoniale"] or s["totale_attivo"] or s["immobilizzazioni"]
        or has("patrimonio netto") or has("attivo circolante") or has("passivita")
        or has("disponibilita liquide")
        or has("debiti verso") or has("crediti verso") or has("capitale sociale")
    )
    # contenuto ECONOMICO presente (CE)
    s["ce_present"] = bool(
        s["conto_economico"] or s["valore_produzione"] or s["prospetto_economico"]
        or has("costi della produzione") or has("totale costi") or has("totale ricavi")
    )

    # codici-PATH CEE (B): es. B.II.1.a) , C.II.5 bis , D.12.1.d
    s["cee_path"] = len(re.findall(r"\b[A-E]\.(?:[IVX]{1,4}|\d{1,2})(?:\s?(?:bis|ter|quater))?(?:[\.\s]\w{1,3})*\)", text))

    # codici conto di contabilità generale (B e C)
    s["depi"] = len(re.findall(r"\b\d{2}/\d{2}/\d{3}\b", text))            # XX/YY/ZZZ Sistemi/DEPI
    s["depi2"] = len(re.findall(r"\b\d{2}/\d{4}\b", text))                  # XX/YYYY
    s["teamsystem"] = len(re.findall(r"\b\d{2}/\d{4}/\d{4}\b", text))       # TeamSystem
    s["eight"] = len(re.findall(r"\b\d{8}\b", text))                        # 8-digit AGO/contrapposte
    s["dotted"] = len(re.findall(r"\b\d{2,3}\.\d{2,3}\.\d{2,3}", text))     # 10.05.001 dotted
    s["mastro_sub"] = len(re.findall(r"\b\d{3}\.\d{5}\b", text))            # NNN.NNNNN BILAGRA
    s["sixdigit_line"] = len(re.findall(r"(?m)^\s*\d{6}\b", text))          # single-column 6-digit
    s["dare_avere"] = ("saldo dare" in low) or ("dare" in low and "avere" in low)

    s["coge_codes"] = int(s["depi"]) + int(s["teamsystem"]) + int(s["eight"]) + \
        int(s["dotted"]) + int(s["mastro_sub"]) + int(s["sixdigit_line"])

    # layout a sezioni contrapposte (coordinate) — solo se ho il file
    s["contrapposte"] = False
    if file_path and os.path.exists(file_path):
        try:
            from importers.situazione_contabile_parser import is_contrapposte_file
            s["contrapposte"] = bool(is_contrapposte_file(file_path))
        except Exception:
            s["contrapposte"] = False

    # detector "situazione contabile" esistente (DEPI/TeamSystem/single-column/8-digit)
    s["is_sc"] = False
    try:
        from importers.situazione_contabile_parser import is_situazione_contabile
        s["is_sc"] = bool(is_situazione_contabile(text))
    except Exception:
        s["is_sc"] = False

    return s


def _gestionale(s: Dict[str, object], low: str) -> str:
    if s["ago_xbrl"]:
        return "AGO Infinity (Zucchetti)"
    if "teamsystem" in low or "powered by teamsystem" in low:
        return "TeamSystem"
    if "genya" in low:
        return "Genya"
    if "cerved" in low:
        return "Cerved"
    if s["itcc"]:
        return "itcc-ci-2018-11-04"
    if int(s["depi"]) >= 10 or int(s["depi2"]) >= 8:
        return "Sistemi/DEPI"
    if int(s["teamsystem"]) >= 5:
        return "TeamSystem"
    return "sconosciuto"


# ---------------------------------------------------------------------------
# Classificazione
# ---------------------------------------------------------------------------
def classify_bilancio(file_path: Optional[str] = None, text: Optional[str] = None) -> Classification:
    """Classifica un bilancio in macro-area + rotta di estrazione.

    Passare almeno uno tra `file_path` (PDF/XBRL) e `text` (testo gia' estratto).
    Se manca `text`, viene estratto dal PDF con PyMuPDF (prime pagine).
    """
    # 0) file XBRL nativo → parser XBRL, non il ramo PDF
    if file_path:
        ext = file_path.lower().rsplit(".", 1)[-1] if "." in file_path else ""
        if ext in ("xbrl", "xml"):
            return Classification(MACRO_OTHER, "XBRL nativo", ROUTE_XBRL, "XBRL",
                                  "high", {"ext": ext}, "estensione .xbrl/.xml")

    if text is None:
        if not file_path:
            raise ValueError("serve file_path o text")
        import fitz
        doc = fitz.open(file_path)
        text = "".join(p.get_text() for p in doc[:14])
        doc.close()

    low = text.lower()
    s = compute_signals(text, file_path)
    gest = _gestionale(s, low)

    def C_subcat() -> str:
        if int(s["teamsystem"]) >= 5:
            return "C/verifica TeamSystem"
        if int(s["eight"]) >= 5 and not s["depi"]:
            return "C/contrapposte 8-digit"
        if int(s["dotted"]) >= 10:
            return "C/contrapposte dotted"
        if int(s["mastro_sub"]) >= 5:
            return "C/verifica BILAGRA"
        if s["contrapposte"]:
            return "C1/sezioni contrapposte fisiche"
        if int(s["sixdigit_line"]) >= 10 or "saldo" in low:
            return "C2/colonna unica Saldo"
        return "C/verifica (generico)"

    # ----- Caso speciale: SOLO conto economico, nessuno stato patrimoniale -----
    # GENERALE: un documento con contenuto economico (conto economico / costi-ricavi /
    # valore della produzione) ma SENZA alcun marker patrimoniale non è un bilancio
    # completo → non si può ricostruire il pareggio. Vale anche quando il file stampa
    # un "TOTALE A PAREGGIO" che è in realtà il pareggio del SOLO conto economico
    # (= totale ricavi), un falso-amico che altrimenti lo manderebbe alla rotta C
    # (budget_376). Errore onesto, mai un plug silenzioso.
    if s["ce_present"] and not s["sp_present"]:
        return Classification(
            MACRO_C, "C4/solo conto economico (no SP)", ROUTE_UNSUPPORTED, gest,
            "high", s,
            "documento solo Conto Economico: manca lo Stato Patrimoniale, "
            "bilancio non ricostruibile")

    # ----- Facsimile XBRL itcc senza elenco conti → A1 -----
    # Vince su eventuali menzioni di "bilancio riclassificato" dentro la Nota
    # Integrativa: un facsimile di deposito non ha mai un elenco di conti CoGe.
    if s["itcc"] and int(s["coge_codes"]) < 5 and not s["pareggio"] and not s["verifica"]:
        return Classification(MACRO_A, "A1/facsimile deposito XBRL", ROUTE_IVCEE, gest,
                              "high", s, "tassonomia itcc / generato automaticamente, nessun elenco conti")

    # ----- B prima di C: se c'è lo scheletro di legge MA anche i conti, è B -----
    # (altrimenti i codici DEPI/8-digit dei file B verrebbero scambiati per C).
    if not s["pareggio"]:
        if s["ago_xbrl"] and s["legal_skeleton"]:
            return Classification(MACRO_B, "B3/XBRL esteso AGO", ROUTE_IVCEE, gest,
                                  "high", s, "header AGO 'BILANCIO SCHEMA XBRL' + scheletro IV CEE")
        if s["riclassificata"] and s["legal_skeleton"]:
            return Classification(MACRO_B, "B1/sit. riclassificata dettagliata", ROUTE_IVCEE, gest,
                                  "high", s, "'riclassificata' + scheletro IV CEE")
        if int(s["cee_path"]) >= 5 and s["legal_skeleton"]:
            return Classification(MACRO_B, "B1/codici-PATH CEE", ROUTE_IVCEE, gest,
                                  "high", s, f"{s['cee_path']} codici-PATH CEE + scheletro IV CEE")
        if s["dettaglio"] and s["legal_skeleton"] and int(s["coge_codes"]) >= 5:
            return Classification(MACRO_B, "B2/dettaglio sottoconti", ROUTE_IVCEE, gest,
                                  "high", s, "marker 'dettaglio' + conti CoGe + scheletro IV CEE")

    # ----- C: bilancio di verifica / situazione contabile -----
    if s["pareggio"] or s["verifica"] or s["is_sc"] or s["contrapposte"]:
        # IV CEE strutturato ma con codici conto di dettaglio (es. sottoconti DEPI
        # dentro lo schema di legge, budget_313/314): è B, NON una verifica. Vale
        # solo se NON ci sono i marker forti di verifica (pareggio/verifica/contrapposte).
        if (s["legal_skeleton"] and int(s["totale_voce"]) >= 2
                and not s["pareggio"] and not s["verifica"] and not s["contrapposte"]):
            return Classification(MACRO_B, "B/IV CEE con sottoconti", ROUTE_IVCEE, gest,
                                  "med", s, "scheletro IV CEE con totali di voce nonostante i codici conto")
        return Classification(MACRO_C, C_subcat(), ROUTE_TRIAL, gest,
                              "high" if (s["pareggio"] or s["verifica"]) else "med", s,
                              "marker verifica/situazione contabile o layout contrapposte")

    # ----- A: scheletro di legge senza conti CoGe -----
    if s["legal_skeleton"] or s["itcc"] or (s["stato_patrimoniale"] and s["totale_attivo"]):
        if s["itcc"]:
            sub = "A1/facsimile deposito XBRL"
            conf = "high"
        elif "abbreviat" in low or "2435-bis" in low:
            sub = "A2/abbreviato"
            conf = "high"
        elif "micro" in low or "2435-ter" in low:
            sub = "A2/micro"
            conf = "high"
        elif s["riclassificata"]:
            sub = "A3/riclassificato con scostamenti"
            conf = "high"
        else:
            sub = "A/sintetico IV CEE"
            conf = "med" if s["legal_skeleton"] else "low"
        return Classification(MACRO_A, sub, ROUTE_IVCEE, gest, conf, s,
                              "scheletro IV CEE / tassonomia, nessun elenco conti")

    # ----- fallback: non riconosciuto come bilancio completo -----
    return Classification(MACRO_OTHER, "non riconosciuto", ROUTE_UNSUPPORTED, gest,
                          "low", s, "nessuno scheletro di legge né elenco conti riconoscibile")
